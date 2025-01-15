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


is_service_unrechable_a_available = False

@app.route('/',methods=['HEAD'])
def portal():
    global is_service_unrechable_a_available

    host_addr_info = socket.gethostbyaddr(request.remote_addr)
    if host_addr_info[0].find("service_unreachable_a") != -1:
        if not is_service_unrechable_a_available:
            return "Page not found", 404
    return "Available", 200


@app.route("/set_service_availability", methods=["GET", "HEAD"])
def set_service_availability():
    global is_service_unrechable_a_available

    service_name=None
    available=None
    for k,v in request.args.items():
        if k == "service_name":
            service_name = v
            continue
        if k == "available":
            available = v
            continue

    if (service_name == "service_unreachable_a") and (available is not None):
        is_service_unrechable_a_available = (available.lower() in ['true', '1'])

    return f"service_name: {service_name}, available: {available}, {is_service_unrechable_a_available}"

@app.route("/api/api.pmccabe_collector.restapi.org/service_unreachable_a/service_unreachable_a_req_2_not_available", methods=["GET", "HEAD"])
def service_unreachable_a_req_2_not_available():
    return "Page not found", 404

#@app.route("/", methods=methods, defaults={"path": ""})
@app.route("/<path:path>", methods=methods)
def hello_world(path):
    print(f"*** Received data at: {path}")
    file_echo_request_path = '/' + path + "_DATA"

    if request.method != "HEAD":
        with open (file_echo_request_path, "w") as file:
            for param,value in request.args.items():
                file.write(f"{param}={value}")
    return f"{file_echo_request_path}"

if __name__ == "__main__":
    app.run()
