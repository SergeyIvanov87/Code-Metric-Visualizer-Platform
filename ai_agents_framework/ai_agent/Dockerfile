ARG BASE_IMAGE=ubuntu@sha256:c4a8d5503dfb2a3eb8ab5f807da5bc69a85730fb49b5cfca2330194ebcc41c7b
FROM ${BASE_IMAGE}

SHELL ["/bin/bash", "-c"]

COPY --chmod=0755 common/proxy_setup_image_helpers/with-proxy-ca.sh /usr/local/bin/with-proxy-ca.sh

RUN --mount=type=secret,id=proxy_ca,mode=0444 <<EOF
    set -e
    /usr/local/bin/with-proxy-ca.sh apt-get update
    /usr/local/bin/with-proxy-ca.sh apt-get install -y --no-install-recommends coreutils python3 python3-pip python-is-python3 dos2unix inotify-tools bash libgomp1
EOF

WORKDIR /package

# /package is also the runtime user's home and is replaced by a source-code
# volume. Do not let stale packages under /package/.local shadow the coherent
# dependency set installed into /usr/local below.
ENV PYTHONNOUSERSITE=1

RUN --mount=type=secret,id=proxy_ca,mode=0444 <<EOF
    set -e
    /usr/local/bin/with-proxy-ca.sh pip install --break-system-packages chromadb langchain-chroma langchain-huggingface langchain-text-splitters tiktoken sentence-transformers
EOF

RUN <<EOF
    mkdir -p /opt /package
    mkdir -p /assets/rag
EOF

COPY common/modules /opt/modules
COPY common/shell_utils /opt/shell_utils
COPY ["common/api_management.py", "common/build_api_executors.py", "common/build_api_services.py", "common/build_api_pseudo_fs.py", "common/build_common_api_services.py", "common/canonize_internal_api.py", "common/check_missing_pseudo_fs_from_schema.py", "common/get_service_api_deps.py", "common/make_api_readme.py", "common/renew_pseudo_fs_pipes.py", "common/deferred_query_launcher.py", "common/deferred_query_executor.py", "/opt/"]

RUN <<EOF
    dos2unix /opt/* && \
    dos2unix /opt/modules*
EOF

ENV MAX_WORKERS=32

ARG SKIP_API_DEPS_CHECK=false
ENV SKIP_API_DEPS_CHECK=$SKIP_API_DEPS_CHECK
ARG TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC=30
ENV TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC=$TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC
COPY ai_agents_framework/ai_agent/API /API
COPY ai_agents_framework/ai_agent/sources /package
RUN dos2unix /package/*

VOLUME ["/api", "/mnt", "/assets/rag"]

# user creation
ARG UID=1501 GID=23456 USER=ai_agent
ENV UID=$UID GID=$GID USER=$USER GROUPNAME=pmccabe


RUN <<EOF
    /usr/local/bin/with-proxy-ca.sh apt-get install adduser
    groupadd --gid "$GID" "$GROUPNAME"
    adduser --disabled-password --gecos "" --home "$(pwd)" -u $UID --ingroup "$GROUPNAME" --no-create-home $USER
EOF


RUN --mount=type=secret,id=proxy_ca,mode=0444 <<EOF
mkdir -p -m 777 /mnt && mkdir -p -m 777 /api
chown -R ${USER}:${GROUPNAME} /mnt && chown -R ${USER}:${GROUPNAME} /api && chown -R ${USER}:${GROUPNAME} /assets && chown -R ${USER}:${GROUPNAME} /api
chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /opt && chown -R ${USER}:${GROUPNAME} /var/log
chown -R ${USER}:${GROUPNAME} /API
EOF



USER ${USER}
ENTRYPOINT ["/package/init.sh", "/package", "/mnt", "/opt", "/api"]
