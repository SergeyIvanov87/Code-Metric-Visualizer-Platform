# syntax=docker/dockerfile:1

FROM archlinux:base-devel
WORKDIR package

# install app dependencies
RUN pacman -Sy --noconfirm python python-pip git inotify-tools
# Seems doesn't work RUN curl https://aur.archlinux.org/cgit/aur.git/snapshot/pmccabe.tar.gz --output pmccabe.tar.gz && mkdir pmccabe && tar xzvf pmccabe.tar.gz && makepkg -sf --noconfirm
RUN git clone https://gitlab.com/pmccabe/pmccabe.git && cd pmccabe && make -e DESTDIR=/ install
RUN git clone https://github.com/SergeyIvanov87/pmccabe_visualizer.git
RUN git clone https://github.com/brendangregg/FlameGraph.git

COPY *.sh /package/

ENTRYPOINT ["/package/init.sh", "/package", "/mnt"]

