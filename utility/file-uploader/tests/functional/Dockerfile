FROM streaming_file_uploader

RUN apk add --no-cache py3-pytest
COPY utility/file-uploader/tests/functional/test_*.py /tests/

ENTRYPOINT ["pytest", "-v", "/tests"]
