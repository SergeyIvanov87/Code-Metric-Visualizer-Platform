FROM test_pseudo_fs:latest

ARG UID=9201
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=rest_api_functional_api_initializer
ENV USER=$USER
ENV GROUPNAME=pmccabe

COPY rest_api/API /API
COPY rest_api/tests/functional/api_initializer/*.sh /tests/
COPY rest_api/tests/functional/api_initializer/*.py /tests/
COPY rest_api/tests/functional/data /tests/data

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*

VOLUME ["/api"]

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

RUN mkdir -p -m 777 /api && chown -R ${USER}:${GROUPNAME} /api
RUN chown -R ${USER}:${GROUPNAME} /API && chown -R ${USER}:${GROUPNAME} /tests

USER ${USER}
ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
