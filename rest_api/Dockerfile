# syntax=docker/dockerfile:1.3-labs

FROM alpine:latest
WORKDIR package

ARG FLASK_APP=rest_api_server FLASK_RUN_HOST=0.0.0.0 FLASK_RUN_PORT=5000
ENV FLASK_APP=$FLASK_APP FLASK_RUN_HOST=$FLASK_RUN_HOST FLASK_RUN_PORT=$FLASK_RUN_PORT

ARG WAIT_FOR_API_SERVICE_PROVIDER_INITIALIZED_ATTEMPTS=4 WAIT_FOR_API_SERVICE_PROVIDER_STARTED_ATTEMPTS=5 WAIT_FOR_SERVER_STARTING_LIMIT_SEC=5 MY_FLASK_INSTANCE_PIDFILE=/package/rest_api_server_pid
ENV WAIT_FOR_API_SERVICE_PROVIDER_INITIALIZED_ATTEMPTS=$WAIT_FOR_API_SERVICE_PROVIDER_INITIALIZED_ATTEMPTS WAIT_FOR_API_SERVICE_PROVIDER_STARTED_ATTEMPTS=$WAIT_FOR_API_SERVICE_PROVIDER_STARTED_ATTEMPTS WAIT_FOR_SERVER_STARTING_LIMIT_SEC=$WAIT_FOR_SERVER_STARTING_LIMIT_SEC MY_FLASK_INSTANCE_PIDFILE=$MY_FLASK_INSTANCE_PIDFILE

# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache busybox-openrc alpine-conf doas
RUN apk add --no-cache py3-flask py3-markdown pipx curl

COPY rest_api/rest_api_server /package/rest_api_server
COPY rest_api/*.sh /package/
COPY rest_api/*.py /package/
COPY rest_api/API /package/API

RUN mkdir -p /opt
COPY common/modules /opt/modules
COPY common/shell_utils /opt/shell_utils
COPY common/build_api_executors.py /opt/
COPY common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py /opt/
COPY common/make_api_readme.py /opt/
COPY common/restore_api_from_pseudo_fs.py /opt/

RUN <<EOF
dos2unix /package/*
dos2unix /opt/*
dos2unix /opt/modules*
rc-update add syslog boot
EOF

ENV DOCKER_SYSLOG_NG_DRIVER_FILE_HANDLER=/var/log/docker_syslog-ng_driver.log
ARG DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL=DEBUG
ENV DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL=$DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL
RUN ln -sf /proc/1/fd/1 ${DOCKER_SYSLOG_NG_DRIVER_FILE_HANDLER}

VOLUME /api

# user creation
ARG UID=1201 GID=23456 USER=rest_api
ENV UID=$UID GID=$GID USER=$USER GROUPNAME=pmccabe

RUN addgroup \
    --gid "$GID" \
    "$GROUPNAME" \
&&  adduser \
    --disabled-password \
    --gecos "" \
    --home "$(pwd)" \
    -u $UID \
    --ingroup "$GROUPNAME" \
    --no-create-home \
    $USER \
&& adduser ${USER} wheel

# allow group wheel to become root
RUN  <<EOF
mkdir -p /etc/doas.d && chmod -R o+rwx /etc/doas.d && echo "permit nopass :${GROUPNAME}" >> /etc/doas.d/doas.conf
mkdir -p -m 777 /api
chown -R ${USER}:${GROUPNAME} /api
chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /opt && chown -R ${USER}:${GROUPNAME} /var/log
EOF

USER ${USER}
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api"]
