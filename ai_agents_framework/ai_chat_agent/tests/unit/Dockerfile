FROM python:3.12-slim
COPY --chmod=0755 common/proxy_setup_image_helpers/with-proxy-ca.sh /usr/local/bin/with-proxy-ca.sh
WORKDIR /tests
COPY common/modules /opt/modules
COPY common/tests/heartbeat.py /opt/modules
COPY common/tests/utils.py /opt/modules
COPY ai_agents_framework/ai_chat_agent/sources /package
COPY ai_agents_framework/ai_chat_agent/config /config
COPY ai_agents_framework/ai_chat_agent/tests/unit/cases /tests/cases
COPY ai_agents_framework/ai_chat_agent/tests/unit/init.sh /tests/init.sh
ENV AI_CHAT_TEST_CONFIG_ROOT=/config
RUN --mount=type=secret,id=proxy_ca,mode=0444 /usr/local/bin/with-proxy-ca.sh python -m pip install --no-cache-dir pytest
ENV PYTHONPATH=/package:/opt/modules
ENTRYPOINT ["/bin/bash", "/tests/init.sh", "/tests", "/package"]
