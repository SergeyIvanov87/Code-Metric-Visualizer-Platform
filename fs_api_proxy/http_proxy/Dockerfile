# syntax=docker/dockerfile:1.3-labs

FROM alpine:latest
WORKDIR package

# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache busybox-openrc alpine-conf doas
RUN apk add --no-cache curl

RUN mkdir -p /opt
COPY common/modules /opt/modules
COPY common/shell_utils /opt/shell_utils
COPY common/api_management.py /opt/
COPY common/build_api_executors.py /opt/
COPY common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py /opt/
COPY common/make_api_readme.py /opt/
COPY common/restore_api_from_pseudo_fs.py /opt/
COPY common/renew_pseudo_fs_pipes.py /opt/

COPY fs_api_proxy/http_proxy/*.sh /package/
COPY fs_api_proxy/http_proxy/*.py /package/


RUN dos2unix /opt/* && \
    dos2unix /opt/modules* && \
    dos2unix /package/* && \
    rc-update add syslog boot

ARG UPSTREAM_SERVICE=
ENV UPSTREAM_SERVICE=$UPSTREAM_SERVICE

# as a service directory name in the project directory
# as a service directory name in an upstream 'API/deps' directory
ARG DOWNSTREAM_SERVICE=
ENV DOWNSTREAM_SERVICE=$DOWNSTREAM_SERVICE

ARG DOWNSTREAM_SERVICE_NETWORK_ADDR=
ENV DOWNSTREAM_SERVICE_NETWORK_ADDR=$DOWNSTREAM_SERVICE_NETWORK_ADDR

ARG DOWNSTREAM_SERVICE_CONNECT_ATTEMPT=
ENV DOWNSTREAM_SERVICE_CONNECT_ATTEMPT=$DOWNSTREAM_SERVICE_CONNECT_ATTEMPT

ENV DOCKER_SYSLOG_NG_DRIVER_FILE_HANDLER=/var/log/docker_syslog-ng_driver.log
ARG DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL=DEBUG
ENV DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL=$DOCKER_SYSLOG_NG_DRIVER_LOG_LEVEL
RUN ln -sf /proc/1/fd/1 ${DOCKER_SYSLOG_NG_DRIVER_FILE_HANDLER}

VOLUME /api

ARG UID=2001 GID=23456 USER=http_proxy
ENV UID=$UID GID=$GID USER=$USER GROUPNAME=pmccabe

# user creation
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

# allow group GROUPNAME to become root
RUN mkdir -p /etc/doas.d && chmod -R o+rwx /etc/doas.d && echo "permit nopass :${GROUPNAME}" >> /etc/doas.d/doas.conf && \
    mkdir -p -m 777 /api && chown -R ${USER}:${GROUPNAME} /api && \
    chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /opt && chown -R ${USER}:${GROUPNAME} /var/log

USER ${USER}
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api"]
