import os

bind = os.environ.get("HTTP_BIND", "0.0.0.0:8081")
workers = 1
worker_class = "gthread"
threads = 8
# FIFO deadlines are enforced by the application, including stalled I/O.
timeout = 0
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
