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
COPY *.py /package/
COPY API.fs /package/API.replicated.fs

COPY services/*.sh /package/

RUN ["python", "./build_api_services.py", "API.replicated.fs"]

RUN mkdir /main_image_env
VOLUME /main_image_env
COPY *.py /main_image_env/

ENTRYPOINT ["/package/init.sh", "/package", "/mnt", "/main_image_env"]
