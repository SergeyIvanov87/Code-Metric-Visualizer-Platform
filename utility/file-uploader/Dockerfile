FROM alpine:3.20.6
WORKDIR /package

RUN apk add --no-cache bash coreutils inotify-tools python3
RUN mkdir -p /opt /uploads

COPY common/modules /opt/modules
COPY common/shell_utils /opt/shell_utils
COPY common/api_management.py common/build_api_executors.py common/build_api_services.py /opt/
COPY common/build_api_pseudo_fs.py common/make_api_readme.py common/renew_pseudo_fs_pipes.py /opt/
COPY common/canonize_internal_api.py /opt/
COPY common/deferred_query_launcher.py common/deferred_query_executor.py /opt/
COPY utility/file-uploader/API /package/API
COPY utility/file-uploader/*.py utility/file-uploader/*.sh /package/
RUN chmod +x /opt/*.py /package/*.py /package/*.sh

VOLUME ["/api", "/uploads"]
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api"]
