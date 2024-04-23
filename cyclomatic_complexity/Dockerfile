# syntax=docker/dockerfile:1

FROM alpine:latest as build
WORKDIR package
# install app dependencies
RUN apk add --no-cache git gcc musl-dev make

# Seems doesn't work RUN curl https://aur.archlinux.org/cgit/aur.git/snapshot/pmccabe.tar.gz --output pmccabe.tar.gz && mkdir pmccabe && tar xzvf pmccabe.tar.gz && makepkg -sf --noconfirm
RUN git clone https://gitlab.com/pmccabe/pmccabe.git && cd pmccabe && make -e DESTDIR=/ install
RUN git clone https://github.com/SergeyIvanov87/pmccabe_visualizer.git && git clone https://github.com/brendangregg/FlameGraph.git


FROM alpine:latest
WORKDIR package
ARG SCRIPT_GEN_LOC=services

# install app dependencies
RUN apk add --no-cache python3 dos2unix
RUN apk add --no-cache inotify-tools bash
RUN apk add --no-cache perl

COPY --from=build /usr/bin/pmccabe /usr/bin/pmccabe
RUN mkdir pmccabe_visualizer && mkdir FlameGraph
# For some reasons you need specify `/package` path from `build` otherwise WORKDIR failed to resolve it
COPY --from=build /package/FlameGraph/flamegraph.pl FlameGraph/flamegraph.pl
COPY --from=build /package/pmccabe_visualizer/*.py pmccabe_visualizer/


COPY cyclomatic_complexity/*.sh /package/
COPY cyclomatic_complexity/*.py /package/
COPY cyclomatic_complexity/API /package/API

COPY cyclomatic_complexity/$SCRIPT_GEN_LOC/*.sh /package/

RUN mkdir -p /opt
COPY common/modules /opt/modules
COPY common/build_api_executors.py /opt/
COPY common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py /opt/
COPY common/make_api_readme.py /opt/
RUN dos2unix /opt/*
RUN dos2unix /opt/modules*

RUN dos2unix /package/*

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/package/init.sh", "/package", "/mnt", "/opt", "/api"]
