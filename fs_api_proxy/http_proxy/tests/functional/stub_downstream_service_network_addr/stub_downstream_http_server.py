#!/usr/bin/python

from markupsafe import escape
from subprocess import Popen, PIPE, STDOUT

import io
import json
import os
import socket
import stat
import subprocess

from flask import Flask
from flask import jsonify
from flask import redirect
from flask import request
from flask import send_file
from flask import render_template

from pprint import pprint
from textwrap import wrap

from time import sleep

from api_fs_query import APIQuery

app = Flask(__name__)

methods = ["GET", "POST", "PATCH", "DELETE"]


@app.route("/", methods=methods, defaults={"path": ""})
@app.route("/<path:path>", methods=methods)
def hello_world(path):
    print(f"*** Received data at: {path}")
    file_echo_request_path = '/' + path + "_DATA"
    with open (file_echo_request_path, "w") as file:
        for param,value in request.args.items():
            file.write(f"{param}={value}")
    return f"{file_echo_request_path}"



if __name__ == "__main__":
    app.run()
