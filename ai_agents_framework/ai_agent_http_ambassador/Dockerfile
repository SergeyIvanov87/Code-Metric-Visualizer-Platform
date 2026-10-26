# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
COPY ai_agents_framework/ai_agent_http_ambassador/requirements.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt
COPY ai_agents_framework/ai_agent/API/chat.json ai_agents_framework/ai_agent/API/rag_add.json /app/API/
COPY common/modules/api_fs_query.py /app/
COPY ai_agents_framework/ai_agent_http_ambassador /app/
RUN groupadd -g 23456 pmccabe && useradd -u 2002 -g pmccabe --no-create-home ambassador \
    && chmod -R a+rX /app
USER ambassador
ARG MAIN_MENU_PATH=/api.pmccabe_collector.restapi.org
ENV MAIN_MENU_PATH=${MAIN_MENU_PATH} PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8081
CMD ["gunicorn", "--config", "gunicorn.conf.py", "server:create_app()"]
