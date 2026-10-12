FROM alpine:3.20.6
WORKDIR /package
ENV STAGING_ROOT=/api/.staging

RUN apk add --no-cache bash coreutils inotify-tools python3 doas
RUN mkdir -p /opt /uploads

COPY --from=common modules /opt/modules
COPY --from=common shell_utils /opt/shell_utils
COPY --from=common api_management.py build_api_executors.py build_api_services.py /opt/
COPY --from=common build_api_pseudo_fs.py make_api_readme.py renew_pseudo_fs_pipes.py /opt/
COPY --from=common canonize_internal_api.py /opt/
COPY --from=common deferred_query_launcher.py deferred_query_executor.py /opt/
COPY API /package/API
COPY *.py *.sh /package/
RUN chmod +x /opt/*.py /package/*.py /package/*.sh

VOLUME ["/api", "/uploads"]

# user creation
ARG UID=2001 GID=23456 USER=utility
ENV UID=$UID GID=$GID USER=$USER GROUPNAME=pmccabe

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
    $USER \
&& adduser ${USER} wheel


RUN <<EOF
mkdir -p /etc/doas.d && chmod -R o+rwx /etc/doas.d && echo "permit nopass :${GROUPNAME}" >> /etc/doas.d/doas.conf
mkdir -p -m 777 /mnt && mkdir -p -m 777 /api
chown -R ${USER}:${GROUPNAME} /mnt && chown -R ${USER}:${GROUPNAME} /api
chown -R ${USER}:${GROUPNAME} /package && chown -R ${USER}:${GROUPNAME} /opt && chown -R ${USER}:${GROUPNAME} /var/log
EOF

USER ${USER}
ENTRYPOINT ["/package/init.sh", "/package", "/opt", "/api"]
