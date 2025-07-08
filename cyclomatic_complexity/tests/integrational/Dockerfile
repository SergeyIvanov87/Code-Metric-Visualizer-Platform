FROM test_pseudo_fs:latest

COPY cyclomatic_complexity/API /API
COPY common/API /API/deps
COPY cyclomatic_complexity/API /API/deps/cyclomatic_complexity

COPY common/shell_utils /tests/utils/shell_utils

COPY cyclomatic_complexity/tests/integrational/*.py /tests/
COPY cyclomatic_complexity/tests/integrational/*.sh /tests/

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/shell_utils/*

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api"]
