import sys
import threading
import time

heartbeat_sending = False
def aggregator_heartbeat(test_name):
    global heartbeat_sending
    while heartbeat_sending:
        time.sleep(1)
        print(f"Test '{test_name}' is in progress...", file=sys.stdout, flush=True)

class Heartbeat:
    def __init__(self):
        self.is_hearbeat_goes_off = False
        self.async_executor = None

    def __execute__(self, message_to_send, polling_second_count = 1):
        interval_count=1
        while self.is_hearbeat_goes_off:
            time.sleep(int(polling_second_count))
            print(f"{message_to_send}[{interval_count}]", file=sys.stdout, flush=True)
            interval_count += 1
        print(f"Heartbeat has stopped sending: {message_to_send}")

    def run(self, message_to_send, polling_second_count = 1):
        self.is_hearbeat_goes_off = True
        self.async_executor = threading.Thread(target=self.__execute__, args=[message_to_send, polling_second_count])
        self.async_executor.start()

    def stop(self):
        self.is_hearbeat_goes_off = False
        self.async_executor.join()
        print("heartbeat thread has stopped")
