FROM test_pseudo_fs

ARG UID=1531
ARG GID=23456
ARG USER=ai_agent_rag_functional_tester
ENV UID=$UID GID=$GID USER=$USER GROUPNAME=pmccabe

# The tester deliberately receives only the public API descriptions and test
# fixtures. No private implementation file is part of this image.
COPY ai_agents_framework/ai_agent/API /API
COPY ai_agents_framework/ai_agent/test/*.py /tests/
COPY ai_agents_framework/ai_agent/test/init.sh /tests/init.sh
COPY ai_agents_framework/ai_agent/test/data /tests/data

RUN dos2unix /tests/init.sh /tests/*.py \
 && addgroup --gid "$GID" "$GROUPNAME" \
 && adduser --disabled-password --gecos "" --home /tests --uid "$UID" \
      --ingroup "$GROUPNAME" --no-create-home "$USER" \
 && chown -R "$USER:$GROUPNAME" /tests /API

USER $USER
ENTRYPOINT ["/tests/init.sh"]
