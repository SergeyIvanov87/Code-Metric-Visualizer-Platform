# syntax=docker/dockerfile:1

FROM alpine:latest
WORKDIR package

ARG FLASK_APP=rest_api_server
ENV FLASK_APP=$FLASK_APP

ARG FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_HOST=$FLASK_RUN_HOST

ARG FLASK_RUN_PORT=5000
ENV FLASK_RUN_PORT=$FLASK_RUN_PORT

ARG WAIT_FOR_SERVER_STARTING_LIMIT_SEC=5
ENV WAIT_FOR_SERVER_STARTING_LIMIT_SEC=$WAIT_FOR_SERVER_STARTING_LIMIT_SEC

ARG MY_FLASK_INSTANCE_PIDFILE=/package/rest_api_server_pid
ENV MY_FLASK_INSTANCE_PIDFILE=$MY_FLASK_INSTANCE_PIDFILE

# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix busybox-openrc
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache py3-flask py3-markdown pipx curl

COPY rest_api/rest_api_server /package/rest_api_server
COPY rest_api/*.sh /package/
COPY rest_api/*.py /package/
COPY rest_api/API /package/API
RUN dos2unix /package/*

RUN mkdir -p /opt
COPY common/modules /opt/modules
COPY common/shell_utils /opt/shell_utils
COPY common/build_api_executors.py /opt/
COPY common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py /opt/
COPY common/make_api_readme.py /opt/
COPY common/restore_api_from_pseudo_fs.py /opt/

RUN <<EOF
dos2unix /opt/*
dos2unix /opt/modules*
rc-update add syslog boot
EOF

ENV DOCKER_SYSLOG_NG_DRIVER_FILE_HANDLER=/var/log/docker_syslog-ng_driver.log
ARG DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL=DEBUG
ENV DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL=$DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL
RUN ln -sf /proc/1/fd/1 ${DOCKER_SYSLOG_NG_DRIVER_FILE_HANDLER}

VOLUME /api
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api"]
