FROM ubuntu@sha256:c4a8d5503dfb2a3eb8ab5f807da5bc69a85730fb49b5cfca2330194ebcc41c7b

SHELL ["/bin/bash", "-c"]

RUN <<EOF
    apt-get update
    apt-get install -y --no-install-recommends coreutils python3 python3-pip python3-pytest python-is-python3 dos2unix inotify-tools bash
EOF

#RUN pipx install --include-deps --global -v chromadb-client
RUN python -m pip install --break-system-packages -U chromadb-client sentence_transformers


ARG UID=1599
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=rag_functional_tester
ENV USER=$USER
ENV GROUPNAME=pmccabe
ARG EXIT_ONCE_DONE=true
ENV EXIT_ONCE_DONE=$EXIT_ONCE_DONE

VOLUME ["/api", "/mnt"]

RUN <<EOF
    apt-get install adduser
    groupadd --gid "$GID" "$GROUPNAME"
    adduser --disabled-password --gecos "" --home "$(pwd)" -u $UID --ingroup "$GROUPNAME" --no-create-home $USER
    adduser ${USER} sudo
EOF


COPY common/tests/*.py /tests/

# TODO temporary source of utils
RUN mkdir -p /tests/utils
COPY common/*.py /tests/utils/
COPY common/modules /tests/utils/modules
COPY common/shell_utils /tests/utils/shell_utils

COPY ai_agents_framework/RAG/tests/functional/*.py /tests/
COPY ai_agents_framework/RAG/tests/functional/*.sh /tests/

# TODO think about sending those via ssh
RUN mkdir /package
COPY ai_agents_framework/RAG/tests/functional/data /package/test_data

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*
RUN dos2unix /tests/utils/shell_utils/*



RUN mkdir -p -m 777 /mnt && chown -R ${USER}:${GROUPNAME} /mnt
RUN chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /tests

#USER ${USER}
ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api"]
