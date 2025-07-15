FROM test_pseudo_fs:latest

ARG UID=10001
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=mock_upstream_service
ENV USER=$USER
ENV GROUPNAME=pmccabe

RUN addgroup \
    --gid "$GID" \
    "$GROUPNAME" \
&&  adduser \
    --disabled-password \
    --gecos "" \
    --home "$(pwd)" \
    -u $UID \
    --ingroup "$GROUPNAME" \
    --no-create-home \
    $USER

RUN apk add --no-cache py3-flask py3-markdown pipx curl

RUN mkdir -m 777 /package

COPY fs_api_proxy/http_proxy//tests/functional/stub_downstream_service_network_addr/*.py /tests/
COPY fs_api_proxy/http_proxy//tests/functional/stub_downstream_service_network_addr/*.sh /tests/

RUN dos2unix /tests/*

ARG DOWNSTREAM_SERVICE_NETWORK_ADDR=stub_downstream_service_network_addr
ENV DOWNSTREAM_SERVICE_NETWORK_ADDR=$DOWNSTREAM_SERVICE_NETWORK_ADDR

VOLUME ["/api", "/mnt"]

# allow group wheel to become root
RUN mkdir -p -m 777 /api
RUN mkdir -p -m 777 /mnt
RUN chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /tests

USER ${USER}
ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
