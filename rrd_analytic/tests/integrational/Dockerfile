# supplementary image for build prerequisites only
FROM alpine:latest as build
WORKDIR package
# install app dependencies
RUN apk add --no-cache git gcc musl-dev make

# Seems doesn't work RUN curl https://aur.archlinux.org/cgit/aur.git/snapshot/pmccabe.tar.gz --output pmccabe.tar.gz && mkdir pmccabe && tar xzvf pmccabe.tar.gz && makepkg -sf --noconfirm
RUN git clone https://gitlab.com/pmccabe/pmccabe.git && cd pmccabe && make -e DESTDIR=/ install
RUN git clone https://github.com/SergeyIvanov87/pmccabe_visualizer.git


# main image logic
FROM test_pseudo_fs
WORKDIR package

COPY --from=build /usr/bin/pmccabe /usr/bin/pmccabe
RUN mkdir -p /package/pmccabe_visualizer
COPY --from=build /package/pmccabe_visualizer/*.py /package/pmccabe_visualizer/

COPY rrd_analytic/API /API
COPY common/API /API/deps
COPY cyclomatic_complexity/API /API/deps/cyclomatic_complexity
COPY rrd_analytic/API /API/deps/rrd_analytic

COPY rrd_analytic/tests/integrational/*.py /tests/
COPY rrd_analytic/tests/integrational/*.sh /tests/

COPY rrd_analytic/*.py /tests/

RUN dos2unix /tests/*
RUN dos2unix /tests/*
VOLUME ["/api", "/mnt", "/rrd_data"]

ARG MICROSERVICE_NAME=rrd-integrational-tester
ENV MICROSERVICE_NAME=$MICROSERVICE_NAME
ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api", "/rrd_data"]
