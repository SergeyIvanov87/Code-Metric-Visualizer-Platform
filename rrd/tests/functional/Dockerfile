# supplementary image for build prerequisites only
FROM alpine:latest as build
WORKDIR package
# install app dependencies
RUN apk add --no-cache git gcc musl-dev make

# Seems doesn't work RUN curl https://aur.archlinux.org/cgit/aur.git/snapshot/pmccabe.tar.gz --output pmccabe.tar.gz && mkdir pmccabe && tar xzvf pmccabe.tar.gz && makepkg -sf --noconfirm
RUN git clone https://gitlab.com/pmccabe/pmccabe.git && cd pmccabe && make -e DESTDIR=/ install
RUN git clone https://github.com/SergeyIvanov87/pmccabe_visualizer.git


# main image logic
FROM test_pseudo_fs:latest
WORKDIR package

COPY --from=build /usr/bin/pmccabe /usr/bin/pmccabe
RUN mkdir -p /package/pmccabe_visualizer
COPY --from=build /package/pmccabe_visualizer/*.py /package/pmccabe_visualizer/

COPY cyclomatic_complexity/API/statistic.json /cc_API/
# TODO think about sending those via ssh
COPY rrd/tests/functional/data /package/test_data

COPY rrd/API /API
COPY rrd/*.py /tests/

COPY rrd/tests/functional/*.sh /tests/
COPY rrd/tests/functional/*.py /tests/

RUN dos2unix /tests/*
VOLUME ["/api", "/mnt", "/rrd_data"]

ENV RRD_TESTABLE_CONTAINER_HOSTNAME=""
ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api", "/rrd_data"]
