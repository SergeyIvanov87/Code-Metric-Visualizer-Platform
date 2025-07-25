FROM test_pseudo_fs:latest

COPY service_broker/API API
COPY service_broker/tests/functional/*.py /tests/
COPY service_broker/tests/functional/*.sh /tests/
COPY service_broker/*.py /tests/

RUN dos2unix /tests/*

ARG UID=9301
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=service_broker_functional_tester
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

VOLUME ["/api"]
RUN mkdir -p -m 777 /api
RUN chown -R ${USER}:${GROUPNAME} /api
RUN mkdir -p -m 777 /API
RUN chown -R ${USER}:${GROUPNAME} /tests && chown -R ${USER}:${GROUPNAME} API && chown -R ${USER}:${GROUPNAME} /API
USER ${USER}
ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
