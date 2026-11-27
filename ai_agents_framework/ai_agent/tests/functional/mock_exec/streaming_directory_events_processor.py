#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from mock_utils.mock_case import run

parser=argparse.ArgumentParser()
parser.add_argument('--request-directory',required=True,type=Path)
mode=parser.add_mutually_exclusive_group()
mode.add_argument('--check-arguments',action='store_true')
mode.add_argument('--prepare-api-channel',action='store_true')
parser.add_argument('--initial-timeout')
parser.add_argument('--update-timeout')
parser.add_argument('arguments',nargs=argparse.REMAINDER)
args=parser.parse_args()
values=args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
if args.check_arguments:
    raise SystemExit(run('streaming_directory_events.json', values))
request=args.request_directory
stage=request/'staging'
events=request/'events'
if args.prepare_api_channel:
    stage.mkdir()
    os.mkfifo(events,0o644)
    print(json.dumps({'input':str(stage),'input_type':'DIRECTORY','staging':str(stage),'events':str(events),'events_type':'FIFO'}))
else:
    with events.open('w'):
        pass
    print('{}')
