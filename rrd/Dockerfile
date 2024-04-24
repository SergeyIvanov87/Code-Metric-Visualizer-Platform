# syntax=docker/dockerfile:1

FROM alpine:latest
WORKDIR package
ARG SCRIPT_GEN_LOC=services

# install app dependencies
RUN apk add --no-cache python3 dos2unix
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache rrdtool librsvg potrace imagemagick ghostscript-fonts terminus-font

COPY rrd/*.sh /package/
COPY rrd/*.py /package/
COPY rrd/API /package/API

COPY rrd/$SCRIPT_GEN_LOC/*.sh /package/
RUN dos2unix /package/*

RUN mkdir -p /opt
COPY common/modules /opt/modules
COPY common/build_api_executors.py /opt/
COPY common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py /opt/
COPY common/make_api_readme.py /opt/
RUN dos2unix /opt/*
RUN dos2unix /opt/modules*

VOLUME /api
VOLUME /rrd_data
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api", "/rrd_data"]
