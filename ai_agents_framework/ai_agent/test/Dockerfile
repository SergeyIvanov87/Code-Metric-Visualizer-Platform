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

RUN apk add --no-cache doas \
 && dos2unix /tests/init.sh /tests/*.py \
 && chmod +x /tests/init.sh \
 && addgroup --gid "$GID" "$GROUPNAME" \
 && adduser --disabled-password --gecos "" --home /tests --uid "$UID" \
      --ingroup "$GROUPNAME" --no-create-home "$USER" \
 && chown -R "$USER:$GROUPNAME" /tests /API

# The shared outage test masks FIFOs owned by real provider users. Restrict
# privilege elevation to that existing test file; all other tests stay non-root.
RUN mkdir -p /etc/doas.d \
 && echo "permit nopass setenv { PYTHONPATH SHARED_API_DIR MAIN_SERVICE_NAME MODULES OPT_DIR WORK_DIR } ${USER} as root cmd /usr/bin/pytest args -s /tests/test_1_inner_api_functionality.py" > /etc/doas.d/doas.conf \
 && chmod 0600 /etc/doas.d/doas.conf

USER $USER
ENTRYPOINT ["/tests/init.sh"]
