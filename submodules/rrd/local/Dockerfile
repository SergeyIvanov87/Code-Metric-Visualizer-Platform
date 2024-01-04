# syntax=docker/dockerfile:1

FROM archlinux:base-devel
WORKDIR package

# install app dependencies
RUN pacman -Sy --noconfirm python python-pip inotify-tools rrdtool librsvg potrace imagemagick

COPY *.sh /package/
COPY *.py /package/
COPY API.fs /package/API.replicated.fs

COPY services/*.sh /package/

RUN mkdir /main_image_env
ENV MAIN_IMAGE_ENV_SHARED_LOCATION_ENV="/main_image_env"
ENTRYPOINT ["/package/init.sh", "/package", "/mnt", "/main_image_env"]
