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
COPY common/shell_utils /opt/shell_utils
COPY common/api_management.py /opt/
COPY common/renew_pseudo_fs_pipes.py /opt/
COPY common/build_api_executors.py /opt/
COPY common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py /opt/
COPY common/build_common_api_services.py /opt/
COPY common/canonize_internal_api.py /opt/
COPY common/check_missing_pseudo_fs_from_schema.py /opt/
COPY common/make_api_readme.py /opt/

RUN dos2unix /opt/*
RUN dos2unix /opt/modules*

ARG SKIP_API_DEPS_CHECK=false
ENV SKIP_API_DEPS_CHECK=$SKIP_API_DEPS_CHECK

VOLUME ["/api"]
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api"]
