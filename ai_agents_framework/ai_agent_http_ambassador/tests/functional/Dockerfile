FROM python:3.12-alpine
WORKDIR /tests
COPY ai_agents_framework/ai_agent_http_ambassador/tests/functional/test_http.py /tests/
COPY ai_agents_framework/ai_agent_http_ambassador/tests/functional/init.sh /tests/
RUN adduser -D -u 1536 tester && chmod -R a+rX /tests
USER tester
ENTRYPOINT ["/bin/sh", "/tests/init.sh"]
