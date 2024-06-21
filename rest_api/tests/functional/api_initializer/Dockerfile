FROM test_pseudo_fs:latest

COPY rest_api/API /API
COPY rest_api/tests/functional/api_initializer/*.sh /tests/
COPY rest_api/tests/functional/api_initializer/*.py /tests/
COPY rest_api/tests/functional/data /tests/data

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*

VOLUME ["/api"]

ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
