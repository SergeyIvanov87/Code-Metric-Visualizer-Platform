FROM alpine:latest
WORKDIR package

ENV PROJECT_URL="this must be a project URL"
ENV PROJECT_BRANCH="this must be a project branch"

# install app dependencies
RUN apk add --no-cache python3 dos2unix
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache git apk-cron

COPY observable_project_version_control/*.sh /package/
COPY observable_project_version_control/*.py /package/
COPY observable_project_version_control/API /package/API

RUN mkdir -p /opt
COPY common/modules /opt/modules
COPY common/build_api_executors.py /opt/
COPY common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py /opt/
COPY common/make_api_readme.py /opt/

RUN dos2unix /opt/*
RUN dos2unix /opt/modules*
RUN dos2unix /package/*

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/package/init.sh", "/package", "/mnt", "/opt", "/api"]
