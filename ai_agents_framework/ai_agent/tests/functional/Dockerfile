FROM test_pseudo_fs

COPY ai_agents_framework/ai_agent/API /tests/API
COPY ai_agents_framework/ai_agent/tests/functional/*.py /tests/
COPY ai_agents_framework/ai_agent/tests/functional/*.sh /tests/
COPY ai_agents_framework/ai_agent/tests/functional/mock_exec /tests/mock_exec
COPY ai_agents_framework/ai_agent/tests/functional/mock_utils /tests/mock_utils
COPY ai_agents_framework/ai_agent/tests/functional/api_test_cases /tests/api_test_cases
COPY ai_agents_framework/ai_agent/tests/functional/data /tests/rag_data

RUN <<EOF
dos2unix /tests/*
dos2unix /tests/mock_exec/*
dos2unix /tests/mock_utils/*
chmod +x /tests/*
chmod +x /tests/mock_exec/*
chmod +x /tests/mock_utils/*
EOF

ARG UID=9401
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=ai-agent-functional-tester
ENV USER=$USER
ENV GROUPNAME=pmccabe

ENV TEST_RAG_DB_HOST=test-rag-db-host
ENV TEST_RAG_DB_PORT=9000

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
RUN <<EOF
mkdir -p -m 777 /api
chown -R ${USER}:${GROUPNAME} /api
chown -R ${USER}:${GROUPNAME} /tests/rag_data
mkdir -p -m 777 /API
chown -R ${USER}:${GROUPNAME} /tests && chown -R ${USER}:${GROUPNAME} /API && chown -R ${USER}:${GROUPNAME} /API

touch /tests/env.sh
chown ${USER}:${GROUPNAME} /tests/env.sh
EOF

USER ${USER}
ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
