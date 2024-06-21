FROM test_pseudo_fs:latest

COPY cyclomatic_complexity/API /API

COPY cyclomatic_complexity/tests/functional/*.py /tests/
COPY cyclomatic_complexity/tests/functional/*.sh /tests/

# TODO think about sending those via ssh
RUN mkdir /package
COPY cyclomatic_complexity/tests/functional/data /package/test_data

RUN dos2unix /tests/*

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api"]
