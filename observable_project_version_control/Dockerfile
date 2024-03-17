FROM alpine:latest
WORKDIR package

ENV PROJECT_URL="this must be a project URL"
ENV PROJECT_BRANCH="this must be a project branch"
ENV CRON_REPO_UPDATE_SCHEDULE="0 0 * * *"

# install app dependencies
RUN apk add --no-cache python3 dos2unix
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache git apk-cron

COPY observable_project_version_control/*.sh /package/
COPY observable_project_version_control/*.py /package/
COPY observable_project_version_control/API /package/API

RUN mkdir /main_image_env

COPY cyclomatic_complexity/*.py /main_image_env/

RUN dos2unix /package/*
RUN dos2unix /main_image_env/*

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/package/init.sh", "/package", "/mnt", "/main_image_env", "/api"]
