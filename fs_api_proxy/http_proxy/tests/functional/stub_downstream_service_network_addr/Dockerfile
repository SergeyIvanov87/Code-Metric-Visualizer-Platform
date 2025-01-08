FROM test_pseudo_fs:latest
RUN apk add --no-cache py3-flask py3-markdown pipx curl

RUN mkdir /package

COPY fs_api_proxy/http_proxy//tests/functional/stub_downstream_service_network_addr/*.py /tests/
COPY fs_api_proxy/http_proxy//tests/functional/stub_downstream_service_network_addr/*.sh /tests/

RUN dos2unix /tests/*

ARG DOWNSTREAM_SERVICE_NETWORK_ADDR=stub_downstream_service_network_addr
ENV DOWNSTREAM_SERVICE_NETWORK_ADDR=$DOWNSTREAM_SERVICE_NETWORK_ADDR

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
