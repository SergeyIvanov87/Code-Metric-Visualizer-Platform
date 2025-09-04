FROM test_pseudo_fs

ARG UID=9001
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=cc_functional_tester
ENV USER=$USER
ENV GROUPNAME=pmccabe

COPY cyclomatic_complexity/API /API

COPY cyclomatic_complexity/tests/functional/*.py /tests/
COPY cyclomatic_complexity/tests/functional/*.sh /tests/

# TODO think about sending those via ssh
RUN mkdir /package
COPY cyclomatic_complexity/tests/functional/data /package/test_data

RUN dos2unix /tests/*

VOLUME ["/api", "/mnt"]
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

RUN mkdir -p -m 777 /mnt && chown -R ${USER}:${GROUPNAME} /mnt
#RUN mkdir -p -m 777 /api && chown -R ${USER}:${GROUPNAME} /api
RUN chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /tests

USER ${USER}
ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api"]
