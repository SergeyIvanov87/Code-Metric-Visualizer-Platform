#!/usr/bin/python

from markupsafe import escape
from subprocess import Popen, PIPE, STDOUT

import io
import json
import markdown
import os
import socket
import stat
import subprocess

from flask import request
from flask import send_file
from flask import render_template

from rest_api_server import app
from time import sleep

from api_fs_query import APIQuery

@app.route('/restart')
def restart():
    os._exit(0)
