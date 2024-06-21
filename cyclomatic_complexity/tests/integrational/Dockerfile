FROM test_pseudo_fs:latest

COPY cyclomatic_complexity/API /API

COPY cyclomatic_complexity/tests/integrational/*.py /tests/
COPY cyclomatic_complexity/tests/integrational/*.sh /tests/

RUN dos2unix /tests/*

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api"]
