#! /usr/bin/env python

import argparse
import os
import pyinotify
import re
import sys
import time

from collections import defaultdict

parser = argparse.ArgumentParser(
    prog="Aggregates test-containers logger output regarding pass rate"
)

log_formats = ("raw", "pcap")

parser.add_argument("log_directory", help="Log directory with files to observe")
parser.add_argument("name_regex", help="Regex to match a container name considered as a test-container")
parser.add_argument("-f", "--format", help="Expected file formatting: \"raw\",\"pcap\". Default: \"raw\"", type=str, default=log_formats[0])
parser.add_argument("-t", "--timeout", help="Timeout [milliseconds]. Wait for activity on logger files and exit if no event happened", type=int, default=60000)
args = parser.parse_args()



wm = pyinotify.WatchManager()
mask = pyinotify.IN_DELETE | pyinotify.IN_CREATE | pyinotify.IN_MODIFY

class TestRecord:
    def __init__(self, timestamp, data, status = 0):
        self.timestamp = timestamp
        self.data = data
        self.status = status

    @staticmethod
    def __parse_timeprefix__(string, fmt):
        try:
            t = time.strptime(string, fmt)
            remainder = ""
        except ValueError as v:
            error_str = "unconverted data remains: "
            if len(v.args) > 0 and v.args[0].startswith(error_str):
                time_prefix = string[:-(len(v.args[0]) - len(error_str))]
                t = time.strptime(time_prefix, fmt)
                remainder = string[len(time_prefix):]
            else:
                raise
        return t, remainder


    @staticmethod
    def create_from_string(string, time_fmt = "%b %d %H:%M:%S"):
        time, remainder = TestRecord.__parse_timeprefix__(string, time_fmt)
        message_parts = [ l.strip() for l in remainder.split(":")]
        message_parts.pop(0) # remove container name, we already got it
        logger_message = ":".join(message_parts)
        return TestRecord(time, logger_message)

class TestStatistic:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.error_log = ""

    def print(self):
        print(f"total/passed/skipped/failed: {self.total}/{self.passed}/{self.skipped}/{self.failed}")
        if self.failed != 0:
            print(self.error_log)
        if self.failed == 0 and self.skipped != 0:
            print(self.warn_log)

class LogParser:
    def __init__(self):
        self.records = []

    def consume(self, raw_record):
        if raw_record.isspace():
            return
        try:
            record = TestRecord.create_from_string(raw_record)
            self.records.append(record)
        except Exception as e:
            print(f"not a valid logger record: {raw_record}\nError {e}\n")

    def collect_statistic(self):
        test_amount_regex = re.compile(r"^collected (\d+) item[s]?$")
        test_failed_regex = re.compile(r"^=+\s+(\d+)\s+failed\s+in\s+.*=+$")
        test_passed_regex = re.compile(r"^=+\s+(\d+)\s+passed\s+in\s+.*=+$")
        test_skipped_regex = re.compile(r"^=+\s+(\d+)\s+skipped\s+in\s+.*=+$")
        stat = TestStatistic()
        if len(self.records) == 0:
            return stat
        for r in self.records:
            amount_found = test_amount_regex.match(r.data)
            if amount_found:
                stat.total += int(amount_found.group(1))
                continue

            failed_found = test_failed_regex.match(r.data)
            if failed_found:
                stat.failed += int(failed_found.group(1))
                continue

            passed_found = test_passed_regex.match(r.data)
            if passed_found:
                stat.passed += int(passed_found.group(1))
                continue

            skipped_found = test_skipped_regex.match(r.data)
            if skipped_found:
                stat.skipped += int(skipped_found.group(1))
                continue

        if stat.failed != 0:
            stat.error_log = "\n".join([f.data for f in self.records])
        if stat.skipped != 0:
            stat.warn_log = "\n".join([f.data for f in self.records])

        return stat

class PcapLogParser(LogParser):
    def __init__(self):
        LogParser.__init__(self)

    @staticmethod
    def  canonize_pcap_record(record):
        if record[0] != '<':
            raise RuntimeError(f"PCAP record prefix must start with '<', got:\n {record}")
        close_index = record.find('>', 0 )
        if close_index == -1:
            raise RuntimeError(f"PCAP record prefix must be closed by '>', got:\n {record}")
        return record[close_index + 1:]

    def consume(self, raw_record):
        if raw_record.isspace():
            return
        try:
            raw_record = PcapLogParser.canonize_pcap_record(raw_record)
            LogParser.consume(self,raw_record)
        except Exception as e:
            print(f"not a valid PCAP logger record: {raw_record}\nError {e}\n")

class LogDispatcher:
    def __init__(self, regex, ParserType = LogParser):
        self.files_offset_bytes = {}
        self.container_log_parser = {}
        self.container_name_regex = re.compile(regex)
        self.ParserType = ParserType

    def dispatch(self, file_name):
        if file_name not in self.files_offset_bytes.keys():
            self.files_offset_bytes[file_name] = 0

        with open(file_name, "r") as file:
            file.seek(0, 2)
            size = file.tell()
            if size < self.files_offset_bytes[file_name]:
                # truncated
                self.files_offset_bytes[file_name] = 0
            # set a position where a last attempt stopped
            file.seek(self.files_offset_bytes[file_name])

            # consume file data
            # since unbuffered input, which even might be represented by 1 symbol, is expected
            # application MUST not process input non-terminated by '\n'.
            # Once a line terminated bye EOL, it indicates a complete syslog-ng packet here
            for line in file:
                if line[-1] != '\n':
                    print (f"Skip: not enough data yet, file offset: {self.files_offset_bytes[file_name]}")
                    raise BufferError()

                self.files_offset_bytes[file_name] += len(line)
                container_name_match = self.container_name_regex.match(line)
                if not container_name_match or len(container_name_match.groups()) < 1:
                    continue
                container_name = container_name_match.group(1)
                if container_name not in self.container_log_parser.keys():
                    self.container_log_parser[container_name] = self.ParserType()

                self.container_log_parser[container_name].consume(line)

    def gather_statistics(self):
        stat = defaultdict(TestStatistic)
        for k,v in self.container_log_parser.items():
            stat[k] = v.collect_statistic()
        return stat

class EventHandler(pyinotify.ProcessEvent):

    def __init__(self, log_dispatcher):
        self.log_dispatcher = log_dispatcher
        self.file_processed_event_count = 0

    def process_IN_CREATE(self, event):
        print(f"File: {event.pathname} - has been created")
        try:
            self.log_dispatcher.dispatch(event.pathname)
        except BufferError:
            return

        self.file_processed_event_count += 1

    def process_IN_DELETE(self, event):
        print(f"File: {event.pathname} - has been removed")

    def process_IN_MODIFY(self, event):
        print(f"File: {event.pathname} - has been modified")
        try:
            self.log_dispatcher.dispatch(event.pathname)
        except BufferError:
            return
        self.file_processed_event_count += 1

format_parsers = (LogParser, PcapLogParser)
assert len(log_formats) == len(format_parsers)
format_index = log_formats.index(args.format)
files_dispatcher = LogDispatcher(args.name_regex, format_parsers[format_index]) #typically must be: r"^.*\s.*\s(.*tester.*)\[\d+\]:.*$")
handler = EventHandler(files_dispatcher)
notifier = pyinotify.Notifier(wm, handler, timeout=args.timeout)
wdd = wm.add_watch(args.log_directory, mask, rec=True)

# notifier.loop()
notifier.process_events()
while notifier.check_events():
    notifier.read_events()
    notifier.process_events()

# If no event happened, it might indicate that aggregator established watch points after file I/O had happened
# Let's analyze all files in monitoring directories, if no events were detected
if handler.file_processed_event_count == 0:
    print(f"No activities on directory: {args.log_directory} were detected. Analyze files forcibly...")

    files = [os.path.join(args.log_directory,f) for f in os.listdir(args.log_directory)]
    for f in files:
        if os.path.isfile(f):
            print(f"process file: {f}")
            handler.log_dispatcher.dispatch(f)
else:
    print(f"No more activities in logger during {args.timeout}milliseconds. Start analysis of collected logs...")

stat = handler.log_dispatcher.gather_statistics()

ret=0
passed_count=0
total_count=0
for k,v in stat.items():
    print(f"Statistic of \"{k}\" - total: {v.total}, failed: {v.failed}, passed: {v.passed}, skipped: {v.skipped}", file=sys.stdout, flush=True)

    total_count += v.total
    passed_count += v.passed
    if v.skipped != 0:
        print(f"SKIPPED tests in {k}: {v.skipped}",file=sys.stderr)

    if v.failed != 0:
        print(f"FAILED tests in {k}: {v.failed}/{v.total}",file=sys.stderr)
        ret = -1

    if v.total != v.failed + v.passed + v.skipped:
        print(f"Statistic of \"{k}\" is inconsistent! Total: {v.total}, failed: {v.failed}, passed: {v.passed}, skipped: {v.skipped}", file=sys.stderr)
        ret = -1

if ret == 0:
    if passed_count == 0 or total_count == 0:
        print("No any tests were executed which is interpreted as FAILED result. Please check your setup configuration", file=sys.stderr)
        exit(-1)
    print(f"All tests PASSED: ({passed_count}/{total_count})")

exit(ret)
