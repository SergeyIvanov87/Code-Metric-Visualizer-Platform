# supplementary image for build prerequisites only
FROM alpine:latest as build
WORKDIR package
# install app dependencies
RUN apk add --no-cache git gcc musl-dev make

# Seems doesn't work RUN curl https://aur.archlinux.org/cgit/aur.git/snapshot/pmccabe.tar.gz --output pmccabe.tar.gz && mkdir pmccabe && tar xzvf pmccabe.tar.gz && makepkg -sf --noconfirm
RUN git clone https://gitlab.com/pmccabe/pmccabe.git && cd pmccabe && make -e DESTDIR=/ install
RUN git clone https://github.com/SergeyIvanov87/pmccabe_visualizer.git


# main image logic
FROM alpine:latest

WORKDIR tests

# install app dependencies
RUN apk add --no-cache python3 pytest dos2unix bash

COPY --from=build /usr/bin/pmccabe /usr/bin/pmccabe
RUN mkdir -p /package/pmccabe_visualizer
COPY --from=build /package/pmccabe_visualizer/*.py /package/pmccabe_visualizer/


COPY rrd/API /API
COPY cyclomatic_complexity/API/statistic.json /cc_API/

COPY common/tests/*.py /tests/
COPY rrd/tests/e2e/*.py /tests/
COPY rrd/tests/e2e/*.sh /tests/

# TODO think about sending those via ssh
COPY rrd/tests/e2e/data /mnt/

# TODO temporary source of utils
RUN mkdir -p /tests/utils
COPY rrd/*.py /tests/

RUN dos2unix /tests/*

COPY common/*.py /tests/utils/
COPY common/modules /tests/utils/modules

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*

RUN dos2unix /tests/*
VOLUME ["/api", "/mnt", "/rrd_data"]

ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api", "/rrd_data"]
