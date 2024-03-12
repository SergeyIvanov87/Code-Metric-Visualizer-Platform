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


COPY *.sh /package/
COPY API /package/API

COPY $SCRIPT_GEN_LOC/*.sh /package/

RUN mkdir /main_image_env
VOLUME /main_image_env
COPY *.py /main_image_env/

RUN dos2unix /package/*
RUN dos2unix /main_image_env/*

ENTRYPOINT ["/package/init.sh", "/package", "/mnt", "/main_image_env"]
