# syntax=docker/dockerfile:1

FROM alpine:latest
WORKDIR package
ARG SCRIPT_GEN_LOC=services

# install app dependencies
RUN apk add --no-cache python3 dos2unix
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache rrdtool librsvg potrace imagemagick ghostscript-fonts terminus-font

COPY *.sh /package/
COPY *.py /package/
COPY API /package/API

COPY $SCRIPT_GEN_LOC/*.sh /package/
RUN dos2unix /package/*

RUN mkdir /main_image_env
ENV MAIN_IMAGE_ENV_SHARED_LOCATION_ENV="/main_image_env"
VOLUME /api
VOLUME /rrd_data
ENTRYPOINT ["/package/init.sh", "/package", "/main_image_env", "/api", "/rrd_data"]
