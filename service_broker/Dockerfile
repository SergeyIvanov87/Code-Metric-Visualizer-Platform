FROM alpine:latest
WORKDIR package

ENV CRON_REPO_UPDATE_SCHEDULE="0 0 * * *"

# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix bash
RUN apk add --no-cache apk-cron

COPY service_broker/*.sh /package/
COPY service_broker/*.py /package/
COPY service_broker/API /package/API

RUN dos2unix /package/*

RUN mkdir -p /opt
COPY common/modules /opt/modules
COPY common/build_api_executors.py /opt/
COPY common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py /opt/
COPY common/make_api_readme.py /opt/
RUN dos2unix /opt/*
RUN dos2unix /opt/modules*

VOLUME ["/api"]
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api"]
