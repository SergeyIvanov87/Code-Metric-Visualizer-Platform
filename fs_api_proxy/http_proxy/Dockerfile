# syntax=docker/dockerfile:1

FROM alpine:latest
WORKDIR package

ARG UID=2001
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=http_proxy
ENV USER=$USER
ENV GROUPNAME=pmccabe

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


# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix busybox-openrc alpine-conf doas
RUN apk add --no-cache inotify-tools bash
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


RUN <<EOF
dos2unix /opt/*
dos2unix /opt/modules*
dos2unix /package/*
rc-update add syslog boot
EOF

ARG UPSTREAM_SERVICE=
ENV UPSTREAM_SERVICE=$UPSTREAM_SERVICE

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

# allow group wheel to become root
RUN mkdir -p /etc/doas.d && chmod -R o+rwx /etc/doas.d && echo "permit nopass :wheel" >> /etc/doas.d/doas.conf
RUN mkdir -p -m 777 /api && chown -R ${USER}:${GROUPNAME} /api
RUN chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /opt && chown -R ${USER}:${GROUPNAME} /var/log

USER ${USER}
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api"]
