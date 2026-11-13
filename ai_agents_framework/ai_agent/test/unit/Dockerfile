FROM python:3.12-slim

COPY --chmod=0755 common/proxy_setup_image_helpers/with-proxy-ca.sh /usr/local/bin/with-proxy-ca.sh
WORKDIR /tests
COPY common/modules /opt/modules
COPY ai_agents_framework/ai_agent/sources /package
COPY ai_agents_framework/ai_agent/test/unit/cases /tests/cases
COPY ai_agents_framework/ai_agent/test/unit/init.sh /tests/init.sh
ENV PYTHONPATH=/package:/opt/modules
ENTRYPOINT ["/bin/bash", "/tests/init.sh", "/tests", "/package"]

RUN --mount=type=secret,id=proxy_ca,mode=0444 \
    /usr/local/bin/with-proxy-ca.sh python -m pip install --no-cache-dir pytest chromadb setuptools
