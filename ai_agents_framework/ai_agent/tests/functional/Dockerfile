FROM test_pseudo_fs

COPY ai_agents_framework/ai_agent/API API
COPY ai_agents_framework/ai_agent/tests/functional/*.py /tests/
COPY ai_agents_framework/ai_agent/tests/functional/*.sh /tests/
COPY ai_agents_framework/ai_agent/tests/functional/mock_exec /tests/mock_exec

RUN <<EOF
dos2unix /tests/*
dos2unix /tests/mock_exec/*
chmod +x /tests/*
chmod +x /tests/mock_exec/*
EOF

ARG UID=9401
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=ai-agent-functional-tester
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
