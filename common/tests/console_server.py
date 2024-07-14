import os
import signal
import subprocess


def launch_detached(server_script_path, server_env, args):
    server=subprocess.Popen(server_script_path, env=server_env)
    return server

def kill_detached(server_subprocess):
    try:
        os.killpg(os.getpgid(server_subprocess.pid), signal.SIGKILL)
    except Exception:
        pass
