FROM test_pseudo_fs

ARG UID=9202
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=rest-api-functional-service-tester
ENV USER=$USER
ENV GROUPNAME=pmccabe

# install app dependencies
RUN apk add --no-cache py3-requests py3-flask py3-markdown curl

COPY rest_api/API /API

COPY rest_api/tests/*.py /tests/
COPY rest_api/tests/functional/service_tester/*.py /tests/
COPY rest_api/tests/functional/service_tester/*.sh /tests/
COPY rest_api/tests/functional/data /tests/data
COPY rest_api/rest_api_server/rest_api_server/templates /tests/templates

# TODO temporary source of utils
COPY rest_api/*.py /tests/

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
