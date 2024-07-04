import requests
import time
import sys

def ping_service(service, port):
    url = f"http://{service}:{port}"
    headers = {'Accept-Charset': 'UTF-8'}
    try:
        resp = requests.head(url, headers=headers)
        resp.raise_for_status()  # Raises a HTTPError if the status is 4xx, 5xxx
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return False
    except requests.exceptions.HTTPError:
        return True

    return resp.ok


def if_service_ceased_until(service, port, max_iteration_limit, iteration_timeout_sec = 1):
    iteration_number = 0
    while ping_service(service, port) and iteration_number <= max_iteration_limit:
        print(f"Waiting for service \"{service}:{port}\" termination, iteration: {iteration_number}/{max_iteration_limit}", file=sys.stdout, flush=True)
        time.sleep(iteration_timeout_sec)
        iteration_number+=1

    return iteration_number < max_iteration_limit

def if_service_started_up_until(service, port, max_iteration_limit, iteration_timeout_sec = 1):
    iteration_number = 0
    while not ping_service(service, port) and iteration_number <= max_iteration_limit:
        print(f"Waiting for service \"{service}:{port}\" starting up, iteration: {iteration_number}/{max_iteration_limit}", file=sys.stdout, flush=True)
        time.sleep(iteration_timeout_sec)
        iteration_number+=1

    return iteration_number < max_iteration_limit

def if_service_reconfigured(service, port, max_stop_waiting_iteration_limit, max_start_waiting_iteration_limit, iteration_timeout_sec = 1):
    stopped = False
    started = False;
    if if_service_ceased_until(service, port, max_stop_waiting_iteration_limit, iteration_timeout_sec):
        stopped = True

    if if_service_started_up_until(service, port, max_start_waiting_iteration_limit, iteration_timeout_sec):
        started = True
    return (stopped, started)
