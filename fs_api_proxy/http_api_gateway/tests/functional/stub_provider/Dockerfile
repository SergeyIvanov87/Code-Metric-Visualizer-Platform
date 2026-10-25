FROM python:3.12-alpine
WORKDIR /app
COPY fs_api_proxy/http_api_gateway/tests/functional/stub_provider/server.py /app/server.py
USER nobody
EXPOSE 8080
ENTRYPOINT ["python", "/app/server.py"]
