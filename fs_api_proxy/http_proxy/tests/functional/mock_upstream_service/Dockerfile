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
    $USER \
&& adduser ${USER} wheel


RUN apk add --no-cache inotify-tools alpine-conf doas py3-requests curl

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

# allow group wheel to become root
RUN mkdir -p /etc/doas.d && chmod -R o+rwx /etc/doas.d && echo "permit nopass :wheel" >> /etc/doas.d/doas.conf
RUN mkdir -p -m 777 /api && chown -R ${USER}:${GROUPNAME} /api
RUN mkdir -p -m 777 /mnt && chown -R ${USER}:${GROUPNAME} /mnt
RUN chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /tests

USER ${USER}
ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
