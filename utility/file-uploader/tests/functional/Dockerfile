FROM file_uploader

RUN apk add --no-cache py3-pytest
COPY utility/file-uploader/tests/functional/test_file_upload.py /tests/

ENTRYPOINT ["pytest", "-v", "/tests/test_file_upload.py"]
