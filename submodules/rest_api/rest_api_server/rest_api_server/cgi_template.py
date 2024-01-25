#!/usr/bin/python

from markupsafe import escape
from subprocess import Popen, PIPE, STDOUT
import subprocess

from rest_api_server import app
'''
@app.route("/cc",  methods=['GET'])
def watch_list():
    f = open("/mnt/api.pmccabe_collector.restapi.org/cc/GET/exec", "w")
    p = Popen(['echo','0'], stdout=f, stderr=STDOUT)

    pout = subprocess.run(['cat', '/mnt/api.pmccabe_collector.restapi.org/cc/GET/result.txt'], stdout=PIPE, stderr=STDOUT,universal_newlines=True)
    print(pout.stdout)

    return f"<p>{pout.stdout.split()}</p>"


@app.route('/cc/statistic/view/flamegraph')
def flamegraph():
    f = open("/mnt/api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph/GET/exec", "w")
    p = Popen(['echo','0'], stdout=f, stderr=STDOUT)
    pout = subprocess.run(['cat', '/mnt/api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph/GET/result.svg'], stdout=PIPE, stderr=STDOUT,universal_newlines=True)
    return f"<p>{pout.stdout}</p>"


@app.route('/cc/statistic/view',  methods=['GET'])
def view():
    f = open("/mnt/api.pmccabe_collector.restapi.org/cc/statistic/view/GET/exec", "w")
    p = Popen(['echo','0'], stdout=f, stderr=STDOUT)
    pout = subprocess.run(['cat', '/mnt/api.pmccabe_collector.restapi.org/cc/statistic/view/GET/result.collapsed'], stdout=PIPE, stderr=STDOUT,universal_newlines=True)
    return f"<p>{pout.stdout}</p>"


@app.route('/cc/statistic',  methods=['GET'])
def statistic():
    f = open("/mnt/api.pmccabe_collector.restapi.org/cc/statistic/GET/exec", "w")
    p = Popen(['echo','0'], stdout=f, stderr=STDOUT)
    pout = subprocess.run(['cat', '/mnt/api.pmccabe_collector.restapi.org/cc/statistic/GET/result.xml'], stdout=PIPE, stderr=STDOUT,universal_newlines=True)
    return f"<p>{pout.stdout}</p>"
'''
