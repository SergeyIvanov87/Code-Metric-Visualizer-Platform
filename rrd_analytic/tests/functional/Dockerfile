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

ARG UID=9101
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=rrd_functional_tester
ENV USER=$USER
ENV GROUPNAME=pmccabe

COPY --from=build /usr/bin/pmccabe /usr/bin/pmccabe
RUN mkdir -p /package/pmccabe_visualizer
COPY --from=build /package/pmccabe_visualizer/*.py /package/pmccabe_visualizer/

COPY rrd_analytic/tests/functional/data /package/test_data

COPY rrd_analytic/API /API
COPY rrd_analytic/*.py /tests/

COPY rrd_analytic/tests/functional/*.sh /tests/
COPY rrd_analytic/tests/functional/*.py /tests/

RUN dos2unix /tests/*
VOLUME ["/api", "/mnt", "/rrd_data"]

ENV RRD_TESTABLE_CONTAINER_HOSTNAME=""

ARG EXIT_ONCE_DONE=true
ENV EXIT_ONCE_DONE=$EXIT_ONCE_DONE

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

RUN mkdir -p -m 777 /api && chown -R ${USER}:${GROUPNAME} /api
RUN mkdir -p -m 777 /mnt && chown -R ${USER}:${GROUPNAME} /mnt
RUN mkdir -p -m 777 /rrd_data && chown -R ${USER}:${GROUPNAME} /rrd_data
RUN chown -R ${USER}:${GROUPNAME} /API && chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /tests

USER ${USER}

ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api", "/rrd_data"]
