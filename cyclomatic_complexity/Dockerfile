# syntax=docker/dockerfile:1

FROM alpine:latest as build
WORKDIR package
# install app dependencies
RUN apk add --no-cache git gcc musl-dev make

# Seems doesn't work RUN curl https://aur.archlinux.org/cgit/aur.git/snapshot/pmccabe.tar.gz --output pmccabe.tar.gz && mkdir pmccabe && tar xzvf pmccabe.tar.gz && makepkg -sf --noconfirm
RUN git clone https://gitlab.com/pmccabe/pmccabe.git && cd pmccabe && make -e DESTDIR=/ install
RUN git clone https://github.com/SergeyIvanov87/pmccabe_visualizer.git && git clone https://github.com/brendangregg/FlameGraph.git


FROM alpine:latest

ARG UID=1001
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=cc
ENV USER=$USER
ENV GROUPNAME=pmccabe

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
    $USER

WORKDIR package
ARG SCRIPT_GEN_LOC=services

# install app dependencies
RUN apk add --no-cache coreutils python3 dos2unix
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache perl

COPY --from=build /usr/bin/pmccabe /usr/bin/pmccabe
RUN mkdir pmccabe_visualizer && mkdir FlameGraph
# For some reasons you need specify `/package` path from `build` otherwise WORKDIR failed to resolve it
COPY --from=build /package/FlameGraph/flamegraph.pl FlameGraph/flamegraph.pl
COPY --from=build /package/pmccabe_visualizer/*.py pmccabe_visualizer/


RUN mkdir -p /opt
COPY common/modules /opt/modules
COPY common/shell_utils /opt/shell_utils
COPY [common/api_management.py,
      common/build_api_executors.py,
      common/build_api_services.py,
      common/build_api_pseudo_fs.py,
      common/build_common_api_services.py,
      common/make_api_readme.py,
      common/renew_pseudo_fs_pipes.py
      /opt/]

RUN <<EOF
dos2unix /opt/*
dos2unix /opt/modules*
EOF

COPY [cyclomatic_complexity/*.sh,
      cyclomatic_complexity/*.py,
      cyclomatic_complexity/$SCRIPT_GEN_LOC/*.sh,
      /package/]
COPY cyclomatic_complexity/API /package/API

RUN dos2unix /package/*

VOLUME ["/api", "/mnt"]

RUN  <<EOF
mkdir -p -m 777 /mnt && mkdir -p -m 777 /api
chown -R ${USER}:${GROUPNAME} /mnt && chown -R ${USER}:${GROUPNAME} /api
chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /opt
EOF

USER ${USER}
ENTRYPOINT ["/package/init.sh", "/package", "/mnt", "/opt", "/api"]
