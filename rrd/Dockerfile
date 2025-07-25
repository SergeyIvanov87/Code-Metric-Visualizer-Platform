# syntax=docker/dockerfile:1

FROM alpine:latest
WORKDIR package
ARG SCRIPT_GEN_LOC=services

ARG UID=1101
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=rrd
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
    $USER


# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix
RUN apk add --no-cache inotify-tools bash
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


COPY rrd/*.sh /package/
COPY rrd/*.py /package/
COPY rrd/API /package/API

COPY rrd/$SCRIPT_GEN_LOC/*.sh /package/

RUN dos2unix /package/*
RUN dos2unix /opt/*
RUN dos2unix /opt/modules*

ARG SKIP_API_DEPS_CHECK=false
ENV SKIP_API_DEPS_CHECK=$SKIP_API_DEPS_CHECK

ARG TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC=30
ENV TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC=$TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC

VOLUME ["/api", "/rrd_data"]

ARG MICROSERVICE_NAME=rrd
ENV MICROSERVICE_NAME=$MICROSERVICE_NAME

RUN mkdir -p -m 777 /api && mkdir -p -m 777 /rrd_data
RUN chown -R ${USER}:${GROUPNAME} /api && chown -R ${USER}:${GROUPNAME} /rrd_data
RUN chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /opt
USER ${USER}
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api", "/rrd_data"]
