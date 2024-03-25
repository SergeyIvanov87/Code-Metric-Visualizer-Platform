FROM alpine:latest
WORKDIR package

ENV CRON_REPO_UPDATE_SCHEDULE="0 0 * * *"

# install app dependencies
RUN apk add --no-cache python3 dos2unix bash
RUN apk add --no-cache apk-cron

COPY service_broker/*.sh /package/
COPY service_broker/*.py /package/
COPY service_broker/API /package/API

RUN mkdir /main_image_env

COPY cyclomatic_complexity/*.py /main_image_env/

RUN dos2unix /package/*
RUN dos2unix /main_image_env/*

VOLUME ["/api"]
ENV MAIN_IMAGE_ENV_SHARED_LOCATION_ENV="/main_image_env"
ENTRYPOINT ["/package/init.sh", "/package", "/main_image_env", "/api"]
