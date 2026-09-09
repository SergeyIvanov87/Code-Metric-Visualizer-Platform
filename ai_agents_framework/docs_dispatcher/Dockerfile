FROM alpine:3.20.6

WORKDIR /package
ARG SCRIPT_GEN_LOC=services

# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache busybox-openrc alpine-conf doas
RUN apk add --no-cache perl py3-sqlalchemy

#SHELL ["/bin/bash", "-c"]


RUN <<EOF
    mkdir /opt
    mkdir /package
    mkdir -p /etc/dispatcher
EOF

COPY common/modules /opt/modules
COPY common/shell_utils /opt/shell_utils
COPY ["common/api_management.py", "common/build_api_executors.py", "common/build_api_services.py", "common/build_api_pseudo_fs.py", "common/build_common_api_services.py", "common/make_api_readme.py", "common/renew_pseudo_fs_pipes.py", "/opt/"]

RUN <<EOF
    dos2unix /opt/* && \
    dos2unix /opt/modules*
EOF

COPY ai_agents_framework/docs_dispatcher/API /API
COPY ai_agents_framework/docs_dispatcher/sources /package
COPY ai_agents_framework/docs_dispatcher/sources/backend/dispatcher /etc/dispatcher

# user creation
ARG UID=1511 GID=23456 USER=rag_docs_dispatcher
ENV UID=$UID GID=$GID USER=$USER GROUPNAME=pmccabe

RUN addgroup \
    --gid "$GID" \
    "$GROUPNAME" \
&&  adduser \
    --disabled-password \
    --gecos "" \
    --home "$(pwd)" \
    -u $UID \
    --ingroup "$GROUPNAME" \
    --no-create-home \
    $USER \
&& adduser ${USER} wheel


RUN <<EOF
    mkdir -p /etc/doas.d && chmod -R o+rwx /etc/doas.d && echo "permit nopass :${GROUPNAME}" >> /etc/doas.d/doas.conf
    mkdir -p -m 777 /etc/dispatcher
    chown -R ${USER}:${GROUPNAME} /etc/dispatcher
    mkdir -p -m 777 /api
    chown -R ${USER}:${GROUPNAME} /mnt
    chown -R ${USER}:${GROUPNAME} /api
    chown -R ${USER}:${GROUPNAME} /package
    chown -R ${USER}:${GROUPNAME} /opt
    chown -R ${USER}:${GROUPNAME} /var/log
    chown -R ${USER}:${GROUPNAME} /API
EOF

VOLUME ["/api", "/etc/dispatcher"]

USER ${USER}
ENTRYPOINT ["/package/init.sh", "/package", "/etc/dispatcher", "/opt", "/api"]
