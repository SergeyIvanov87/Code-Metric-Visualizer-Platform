# syntax=docker/dockerfile:1.3-labs

FROM alpine:latest
WORKDIR package
ARG SCRIPT_GEN_LOC=services

# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache busybox-openrc alpine-conf doas
RUN apk add --no-cache rrdtool librsvg potrace imagemagick ghostscript-fonts terminus-font

RUN mkdir -p /opt
COPY common/modules /opt/modules
COPY common/shell_utils /opt/shell_utils
COPY common/api_management.py /opt/
COPY common/build_api_executors.py /opt/
COPY common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py /opt/
COPY common/build_common_api_services.py /opt/
COPY common/canonize_internal_api.py /opt/
COPY common/check_missing_pseudo_fs_from_schema.py /opt/
COPY common/get_service_api_deps.py /opt/
COPY common/make_api_readme.py /opt/
COPY common/renew_pseudo_fs_pipes.py /opt/


COPY rrd_analytic/*.sh /package/
COPY rrd_analytic/*.py /package/
COPY rrd_analytic/API /package/API

COPY rrd_analytic/$SCRIPT_GEN_LOC/*.sh /package/

RUN dos2unix /package/* && \
    dos2unix /opt/* && \
    dos2unix /opt/modules*

ARG SKIP_API_DEPS_CHECK=false TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC=30 MICROSERVICE_NAME=rrd_analytic
ENV SKIP_API_DEPS_CHECK=$SKIP_API_DEPS_CHECK TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC=$TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC MICROSERVICE_NAME=$MICROSERVICE_NAME

VOLUME ["/api", "/rrd_data"]

ARG UID=1101 GID=23456 USER=rrd_analytic
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


RUN mkdir -p /etc/doas.d && chmod -R o+rwx /etc/doas.d && echo "permit nopass :${GROUPNAME}" >> /etc/doas.d/doas.conf   && \
    mkdir -p -m 777 /api && mkdir -p -m 777 /rrd_data   && \
    chown -R ${USER}:${GROUPNAME} /api && chown -R ${USER}:${GROUPNAME} /rrd_data   && \
    chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /opt

USER ${USER}
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api", "/rrd_data"]
