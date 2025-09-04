# syntax=docker/dockerfile:1

FROM test_pseudo_fs

RUN apk add --no-cache inotify-tools alpine-conf doas py3-requests curl

RUN mkdir /package
COPY common/shell_utils /package/shell_utils

COPY fs_api_proxy/http_proxy//tests/functional/mock_upstream_service/data/API /package/API
COPY fs_api_proxy/http_proxy//tests/functional/mock_upstream_service/*.py /tests/
COPY fs_api_proxy/http_proxy//tests/functional/mock_upstream_service/*.sh /tests/

RUN dos2unix /tests/*

ARG UPSTREAM_SERVICE=mock-upstream-service
ENV UPSTREAM_SERVICE=$UPSTREAM_SERVICE

ARG DOWNSTREAM_SERVICE=service_a
ENV DOWNSTREAM_SERVICE=$DOWNSTREAM_SERVICE

ARG DOWNSTREAM_SERVICE_NETWORK_ADDR=stub-downstream-service-network-addr
ENV DOWNSTREAM_SERVICE_NETWORK_ADDR=$DOWNSTREAM_SERVICE_NETWORK_ADDR

VOLUME ["/api", "/mnt"]

ARG UID=10001 GID=23456 USER=mock_upstream_service
ENV UID=$UID GID=$GID USER=$USER GROUPNAME=pmccabe

# create user
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
    $USER \
&& adduser ${USER} wheel

# allow group wheel to become root
RUN mkdir -p /etc/doas.d && chmod -R o+rwx /etc/doas.d && echo "permit nopass :${GROUPNAME}" >> /etc/doas.d/doas.conf   && \
    mkdir -p -m 777 /api && chown -R ${USER}:${GROUPNAME} /api  && \
    mkdir -p -m 777 /mnt && chown -R ${USER}:${GROUPNAME} /mnt  && \
    chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /tests

USER ${USER}
ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
