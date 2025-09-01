# syntax=docker/dockerfile:1.3-labs

FROM alpine:latest
WORKDIR package

ENV CRON_REPO_UPDATE_SCHEDULE="0 0 * * *"

# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix
RUN apk add --no-cache busybox-openrc alpine-conf doas
RUN apk add --no-cache apk-cron bash

COPY service_broker/*.sh /package/
COPY service_broker/*.py /package/
COPY service_broker/API /package/API

RUN dos2unix /package/*

RUN mkdir -p /opt
COPY common/modules /opt/modules
COPY common/shell_utils /opt/shell_utils
COPY common/api_management.py /opt/
COPY common/renew_pseudo_fs_pipes.py /opt/
COPY common/build_api_executors.py /opt/
COPY common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py /opt/
COPY common/build_common_api_services.py /opt/
COPY common/canonize_internal_api.py /opt/
COPY common/check_missing_pseudo_fs_from_schema.py /opt/
COPY common/get_service_api_deps.py /opt/
COPY common/make_api_readme.py /opt/

RUN <<EOF
dos2unix /opt/*
dos2unix /opt/modules*
rc-update add syslog boot
EOF

ENV DOCKER_SYSLOG_NG_DRIVER_FILE_HANDLER=/var/log/docker_syslog-ng_driver.log
ARG DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL=DEBUG
ENV DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL=$DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL
RUN ln -sf /proc/1/fd/1 ${DOCKER_SYSLOG_NG_DRIVER_FILE_HANDLER}

ARG SKIP_API_DEPS_CHECK=false
ENV SKIP_API_DEPS_CHECK=$SKIP_API_DEPS_CHECK

ARG TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC=30
ENV TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC=$TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC

ARG MICROSERVICE_NAME=service-broker
ENV MICROSERVICE_NAME=$MICROSERVICE_NAME

VOLUME ["/api"]

ARG UID=1301 GID=23456 USER=service_broker
ENV UID=$UID GID=$GID USER=$USER GROUPNAME=pmccabe

# create user
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


# allow group to become root
RUN  <<EOF
mkdir -p /etc/doas.d && chmod -R o+rwx /etc/doas.d && echo "permit nopass :${GROUPNAME}" >> /etc/doas.d/doas.conf
mkdir -p -m 777 /api
chown -R ${USER}:${GROUPNAME} /api
chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /opt && chown -R ${USER}:${GROUPNAME} /var/log
EOF

USER ${USER}
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api"]
