FROM test_pseudo_fs:latest

RUN apk add --no-cache inotify-tools py3-requests curl

RUN mkdir /package
COPY common/shell_utils /package/shell_utils

COPY fs_api_proxy/http_proxy//tests/functional/mock_upstream_service/data/API /package/API
COPY fs_api_proxy/http_proxy//tests/functional/mock_upstream_service/*.py /tests/
COPY fs_api_proxy/http_proxy//tests/functional/mock_upstream_service/*.sh /tests/

RUN dos2unix /tests/*

ARG UPSTREAM_SERVICE=mock_upstream_service
ENV UPSTREAM_SERVICE=$UPSTREAM_SERVICE

ARG DOWNSTREAM_SERVICE=service_a
ENV DOWNSTREAM_SERVICE=$DOWNSTREAM_SERVICE

ARG DOWNSTREAM_SERVICE_NETWORK_ADDR=stub_downstream_service_network_addr
ENV DOWNSTREAM_SERVICE_NETWORK_ADDR=$DOWNSTREAM_SERVICE_NETWORK_ADDR

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
