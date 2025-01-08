# syntax=docker/dockerfile:1

FROM alpine:latest
WORKDIR package


# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix
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

RUN dos2unix /opt/*
RUN dos2unix /opt/modules*

COPY fs_api_proxy/http_proxy/*.sh /package/
COPY fs_api_proxy/http_proxy/*.py /package/

RUN dos2unix /package/*

ARG UPSTREAM_SERVICE=
ENV UPSTREAM_SERVICE=$UPSTREAM_SERVICE

ARG DOWNSTREAM_SERVICE=
ENV DOWNSTREAM_SERVICE=$DOWNSTREAM_SERVICE

ARG DOWNSTREAM_SERVICE_NETWORK_ADDR=
ENV DOWNSTREAM_SERVICE_NETWORK_ADDR=$DOWNSTREAM_SERVICE_NETWORK_ADDR

VOLUME /api
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api"]
