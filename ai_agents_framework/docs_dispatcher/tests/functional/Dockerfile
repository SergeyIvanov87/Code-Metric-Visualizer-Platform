FROM test_pseudo_fs

ARG UID=1529
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=docs_dispatcher_functional_tester
ENV USER=$USER
ENV GROUPNAME=pmccabe

COPY ai_agents_framework/docs_dispatcher/API /API

COPY ai_agents_framework/docs_dispatcher/tests/functional/*.py /tests/
COPY ai_agents_framework/docs_dispatcher/tests/functional/*.sh /tests/

# TODO think about sending those via ssh
RUN mkdir /package
COPY ai_agents_framework/docs_dispatcher/tests/functional/data /package/test_data

RUN dos2unix /tests/*

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

RUN <<EOF
mkdir -p -m 777 /mnt
chown -R ${USER}:${GROUPNAME} /mnt
mkdir -p -m 777 /api
chown -R ${USER}:${GROUPNAME} /api
RUN chown -R ${USER}:${GROUPNAME} /package
chown -R ${USER}:${GROUPNAME} /tests
EOF
VOLUME ["/api", "/mnt"]

USER ${USER}
ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api"]
