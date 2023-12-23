# syntax=docker/dockerfile:1

FROM archlinux:base-devel
WORKDIR package

# install app dependencies
RUN pacman -Sy --noconfirm python python-pip inotify-tools rrdtool librsvg potrace imagemagick

COPY *.sh /package/
COPY *.py /package/
COPY API.fs /package/API.replicated.fs

COPY services/*.sh /package/

RUN ["python", "../../../local/build_local_api.py", "build", "API.replicated.fs", "/mnt"]

ENTRYPOINT ["/package/init.sh", "/package", "/mnt"]
