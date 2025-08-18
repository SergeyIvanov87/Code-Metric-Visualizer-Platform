FROM test_pseudo_fs

# install app dependencies
RUN apk add --no-cache py3-requests curl

COPY rest_api/API /API

COPY rest_api/*.py /tests/
COPY rest_api/tests/*.py /tests/
COPY rest_api/tests/integrational/*.sh /tests/
COPY rest_api/tests/integrational/*.py /tests/

# copy API schemas
COPY cyclomatic_complexity/API/*.json /tests/collected_API/
COPY rrd/API/*.json /tests/collected_API/

RUN dos2unix /tests/*

VOLUME ["/api"]

ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
