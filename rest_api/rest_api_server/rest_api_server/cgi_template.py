#!/usr/bin/python

from markupsafe import escape
from subprocess import Popen, PIPE, STDOUT

import io
import json
import logger
import markdown
import os
import signal
import socket
import stat
import subprocess
import syslog
import time

from flask import redirect
from flask import request
from flask import send_file
from flask import render_template

from rest_api_server import app
from time import sleep

from api_fs_query import APIQuery
from api_fs_query import APIQueryInterruptible

docker_logger = logger.Logger()

original_sigint_processor = None
queries_in_progress = 0

def process_signal(sig, frame):
    global original_sigint_processor
    global queries_in_progress

    docker_logger.info(f'Signal catched: {sig}, {signal.SIGINT}queries_in_progress: {queries_in_progress}')
    if queries_in_progress == 0:
        if sig == 2:
            docker_logger.info(f"original_sigint_processor:{original_sigint_processor}")
            if callable(original_sigint_processor):
                original_sigint_processor(sig, frame)
            else:
                docker_logger.info("ssssssssssssssssssssss")
                #original_sigint_processor(sig, frame)
                signal.signal(sig, original_sigint_processor)
                os.kill(os.getpid(), signal.SIGTERM)
    else:
        docker_logger.info(f'Signal: {sig} IGNORED as interrupions are disabled')


original_sigint_processor = signal.signal(signal.SIGINT, process_signal)
#signal.signal(signal.SIGTERM, process_signal)

@app.route('/restart')
def restart():
    os._exit(0)
