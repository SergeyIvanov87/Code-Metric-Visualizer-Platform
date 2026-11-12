FROM alpine:3.20.6
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    apk add --no-cache bash python3 py3-pytest py3-setuptools
WORKDIR /repo
COPY common/modules /repo/common/modules
COPY ai_agents_framework/ai_agent/sources /repo/ai_agents_framework/ai_agent/sources
COPY ai_agents_framework/ai_agent/API /repo/ai_agents_framework/ai_agent/API
COPY utility/file-uploader/streaming_directory_events_processor.py /repo/utility/file-uploader/
COPY utility/file-uploader/API/streaming_directory_events.json /repo/utility/file-uploader/API/
COPY ai_agents_framework/ai_agent/tests /repo/ai_agents_framework/ai_agent/tests
COPY ai_agents_framework/ai_agent/test/unit /tests
ENV PYTHONPATH=/repo/common/modules:/repo/ai_agents_framework/ai_agent/sources
ENTRYPOINT ["/bin/sh", "/tests/init.sh"]
