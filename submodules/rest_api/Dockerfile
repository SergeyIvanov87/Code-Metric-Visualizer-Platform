# syntax=docker/dockerfile:1

FROM alpine:latest
WORKDIR package
#ARG SCRIPT_GEN_LOC=rest_api_server

# install app dependencies
RUN apk add --no-cache python3 dos2unix
RUN apk add --no-cache py3-flask py3-markdown pipx

COPY *.sh /package/
COPY *.py /package/
COPY API /package/API
COPY $SCRIPT_GEN_LOC /package/

RUN mkdir /main_image_env
ENV MAIN_IMAGE_ENV_SHARED_LOCATION_ENV="/main_image_env"
ENTRYPOINT ["/package/init.sh", "/package", "/mnt", "/main_image_env"]
