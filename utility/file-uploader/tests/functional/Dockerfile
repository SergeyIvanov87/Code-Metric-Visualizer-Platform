FROM streaming_file_uploader

# Install test dependencies as root rather than the inherited service user.
USER root
RUN apk add --no-cache py3-pytest
COPY utility/file-uploader/tests/functional/test_*.py /tests/
RUN chown -R "${USER}:${GROUPNAME}" /tests

# Prepare the fixture volume for the unchanged non-root uploader service.
ENTRYPOINT ["bash", "-ec", "chown \"${USER}:${GROUPNAME}\" /uploads; exec su -s /bin/sh -c 'exec pytest -v /tests' \"${USER}\""]
