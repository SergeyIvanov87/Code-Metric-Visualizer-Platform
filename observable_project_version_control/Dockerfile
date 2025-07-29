FROM alpine:latest
WORKDIR package

ARG EXIT_ON_INIT_FAIL=true
ENV PROJECT_URL="this must be a project URL" PROJECT_BRANCH="this must be a project branch" EXIT_ON_INIT_FAIL=${EXIT_ON_INIT_FAIL}

# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache git apk-cron

RUN mkdir -p /opt
COPY common/modules /opt/modules
COPY common/shell_utils /opt/shell_utils
COPY common/api_management.py /opt/
COPY common/build_api_executors.py /opt/
COPY common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py /opt/
COPY common/make_api_readme.py /opt/
COPY common/renew_pseudo_fs_pipes.py /opt/

COPY observable_project_version_control/API /package/API
COPY observable_project_version_control/*.py /package/
COPY observable_project_version_control/*.sh /package/

RUN dos2unix /opt/*
RUN dos2unix /opt/modules*
RUN dos2unix /package/*

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/package/init.sh", "/package", "/mnt", "/opt", "/api"]
