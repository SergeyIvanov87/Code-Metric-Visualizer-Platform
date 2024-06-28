#!/usr/bin/python

import os
from flask import Flask

# Unfortunately the code belowe doesn't work
# put it as an example of overriding startupt routine...
def on_startup():
    print("PidTraceableServer is starting")
    pid_file_path = os.getenv('MY_FLASK_INSTANCE_PIDFILE', '/packages/rest_api_server_pid')
    with open (pid_file_path, "w") as pid_file:
        pid_file.write(os.getpid())


class PidTraceableServer(Flask):
    def run(self, host=None, port=None, debug=None, load_dotenv=True, **options):
        print("customizations")
        with self.app_context():
            on_startup()
        super(PidTraceableServer, self).run(host=host, port=port, debug=debug, load_dotenv=load_dotenv, **options)

app = PidTraceableServer(__name__)

import rest_api_server.cgi
