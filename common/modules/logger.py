#!/usr/bin/env python

import logging
import os

import logging.handlers
import socket

class Logger(logging.Logger):
    log_level = {"DEBUG" : logging.DEBUG, "ERROR" : logging.ERROR, "WARNING": logging.WARNING, "CRITICAL" : logging.CRITICAL, "FATAL" : logging.FATAL}

    def __init__(self):
        if "DOCKER_SYSLOG_NG_DRIVER_FILE_HANDLER" not in os.environ.keys():
            raise RuntimeError("Cannot create Logger as the environment variable 'DOCKER_SYSLOG_NG_DRIVER_FILE_HANDLER' is not specified")
        logging.Logger.__init__(self, "syslog-ng docker handler")

        log_level_str = os.environ.get("DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL")
        if log_level_str not in Logger.log_level.keys():
            raise RuntimeError(f"Cannot create Logger as the environment variable 'DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL' has the unexpected value: {log_level_str}. Please choose from: {Logger.log_level.keys()}")
        self.setLevel(logging.DEBUG)

        handler = logging.FileHandler(os.environ.get("DOCKER_SYSLOG_NG_DRIVER_FILE_HANDLER"))
        self.addHandler(handler)
