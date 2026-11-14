FROM alpine:3.20.6
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    apk add --no-cache bash python3 py3-pytest py3-sqlalchemy py3-pymysql
WORKDIR /tests
COPY common/modules /opt/modules
COPY ai_agents_framework/docs_dispatcher/sources /package
COPY ai_agents_framework/docs_dispatcher/tests/unit/cases /tests/cases
COPY ai_agents_framework/docs_dispatcher/tests/unit/init.sh /tests/init.sh
ENV PYTHONPATH=/package:/package/backend:/opt/modules
ENTRYPOINT ["/bin/bash", "/tests/init.sh", "/tests", "/package"]
