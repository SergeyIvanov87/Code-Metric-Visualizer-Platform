FROM python:3.12-alpine
WORKDIR /tests
COPY fs_api_proxy/http_api_gateway/tests/functional/tester/test_gateway.py /tests/test_gateway.py
ENTRYPOINT ["python", "/tests/test_gateway.py"]
