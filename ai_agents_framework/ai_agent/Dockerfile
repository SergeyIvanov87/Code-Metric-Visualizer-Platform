FROM ubuntu@sha256:c4a8d5503dfb2a3eb8ab5f807da5bc69a85730fb49b5cfca2330194ebcc41c7b

SHELL ["/bin/bash", "-c"]

RUN <<EOF
    apt-get update
    apt-get install -y --no-install-recommends coreutils python3 python3-pip python-is-python3 dos2unix inotify-tools bash doas git cmake clang libgomp1 gcc g++
EOF

# gcc g++ are both required for installion of llama-cpp-python

WORKDIR /package

# /package is also the runtime user's home and is replaced by a source-code
# volume. Do not let stale packages under /package/.local shadow the coherent
# dependency set installed into /usr/local below.
ENV PYTHONNOUSERSITE=1

RUN <<EOF
    pip install --break-system-packages langchain langchain-chroma langchain-community langchain-huggingface langchain_openai langchain-text-splitters tiktoken sentence-transformers
    pip install --break-system-packages llama-cpp-python
    pip install --break-system-packages chromadb chromadb-client sentence_transformers pypdf requests pydantic tqdm
EOF

RUN <<EOF
    mkdir /opt
    mkdir /package
    mkdir -p /assets/rag
    mkdir -p /assets/models
EOF

COPY common/modules /opt/modules
COPY common/shell_utils /opt/shell_utils
COPY ["common/api_management.py", "common/build_api_executors.py", "common/build_api_services.py", "common/build_api_pseudo_fs.py", "common/build_common_api_services.py", "common/make_api_readme.py", "common/renew_pseudo_fs_pipes.py", "/opt/"]

RUN <<EOF
    dos2unix /opt/* && \
    dos2unix /opt/modules*
EOF

#TODO COPY ["ai_agent/*.sh", "ai_agent/*.py", "/package/"]
COPY ai_agents_framework/ai_agent/API /API

VOLUME ["/api", "/mnt", "/assets/rag", "/assets/models", "/package"]

# user creation
ARG UID=1501 GID=23456 USER=ai_agent
ENV UID=$UID GID=$GID USER=$USER GROUPNAME=pmccabe


RUN <<EOF
    apt-get install adduser
    groupadd --gid "$GID" "$GROUPNAME"
    adduser --disabled-password --gecos "" --home "$(pwd)" -u $UID --ingroup "$GROUPNAME" --no-create-home $USER
    adduser ${USER} sudo
EOF


RUN <<EOF
echo "permit nopass :${GROUPNAME}" >> /etc/doas.conf
mkdir -p -m 777 /mnt && mkdir -p -m 777 /api
chown -R ${USER}:${GROUPNAME} /mnt && chown -R ${USER}:${GROUPNAME} /api && chown -R ${USER}:${GROUPNAME} /assets && chown -R ${USER}:${GROUPNAME} /api
chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /opt && chown -R ${USER}:${GROUPNAME} /var/log
chown -R ${USER}:${GROUPNAME} /API
EOF



USER ${USER}
ENTRYPOINT ["/package/init.sh", "/package", "/mnt", "/opt", "/api", "/assets/models"]
