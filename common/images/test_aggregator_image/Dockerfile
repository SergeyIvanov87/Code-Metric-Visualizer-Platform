FROM envoyproxy/envoy:dev-5451efd9b8f8a444431197050e45ba974ed4e9d8
RUN apt-get update && apt-get install -y openssh-client sshpass python3 python3-pip python3-pyinotify curl inotify-tools dos2unix
RUN python3 -m pip install --no-cache-dir --target=/opt/test-aggregator-python xds-protos==1.83.1
ENV PYTHONPATH=/opt/test-aggregator-python

COPY common/images/test_aggregator_image/envoy.yaml /etc/envoy/envoy.yaml
RUN chmod go+r /etc/envoy/envoy.yaml

# Aggregator is supposed to gather and to analyze *test* logs from clear environment
# Thus it's about to remove ALL logs from our syslog SHARED VOLUME directory
# This aggregator opts in traffic monitoring on syslog-ng port and capture
# only tester-containers information

RUN mkdir -p /logs && mkdir -p /package
VOLUME ["/logs"]
RUN rm -rf /logs/*
RUN chmod -R 777 /logs

ADD common/images/test_aggregator_image/bootstrap.sh /etc/bootstrap.sh
RUN dos2unix /etc/bootstrap.sh

COPY common/images/test_aggregator_image/log_aggregator.py /package/log_aggregator.py
COPY common/images/test_aggregator_image/log_watcher_service.sh /package/log_watcher_service.sh
COPY common/images/test_aggregator_image/tap_watcher_service.sh /package/tap_watcher_service.sh
COPY common/images/test_aggregator_image/decode_envoy_tap.py /package/decode_envoy_tap.py
COPY common/shell_utils/ssh.sh /package/ssh.sh

RUN dos2unix /package/* && chmod +x /package/*.sh


ARG WAIT_MSEC_UNTIL_FINISH=15000
ENV WAIT_MSEC_UNTIL_FINISH=$WAIT_MSEC_UNTIL_FINISH

ARG ENVOY_ADMIN_PORT=9901
ENV ENVOY_ADMIN_PORT=${ENVOY_ADMIN_PORT}

ARG MAX_BUFFERED_RX_BYTES=16777216
ENV MAX_BUFFERED_RX_BYTES=${MAX_BUFFERED_RX_BYTES}

ARG UPSTREAM_SYSLOG_TCP_PORT=13601
ENV UPSTREAM_SYSLOG_TCP_PORT=${UPSTREAM_SYSLOG_TCP_PORT}

ARG DOWNSTREAM_SYSLOG_TCP_PORT=6601
ENV DOWNSTREAM_SYSLOG_TCP_PORT=${DOWNSTREAM_SYSLOG_TCP_PORT}

ARG DOWNSTREAM_SYSLOG_HOSTNAME=syslog-ng
ENV DOWNSTREAM_SYSLOG_HOSTNAME=${DOWNSTREAM_SYSLOG_HOSTNAME}

ARG DOWNSTREAM_SSH_SECRET=syslog-ng
ENV DOWNSTREAM_SSH_SECRET=${DOWNSTREAM_SSH_SECRET}

# For some reasons HEALCHECK won't begin until initial `interval` is elapsed, then the first check will be executed
# The main script aggregator has waiting timeout and once it reached then finalization procedure commenced
# If healthcheck interval is lesser than aggregator waiting timeout then finalization won't start.
# As docker documentation says, there are anothe options for healthcheck: --start-period & --start-interval.
# The last one allows to configure probes frequency during former one, thus using `--start-interval` we can send probes
# more often during --start-period and reach out container healthy-state
# Finally: --interval must be large enough (?infinity?); --start-interval must be lesser than aggregator waiting timeout & --start-period should be reasonable
# The following configuration is OK for most cases
HEALTHCHECK --interval=60m --start-interval=5s --start-period=15s --timeout=3s  CMD logger -n 127.0.0.1 -P ${UPSTREAM_SYSLOG_TCP_PORT} -T --octet-count "Hello" || exit 1

ENTRYPOINT ["/bin/sh","-c"]
CMD ["/etc/bootstrap.sh"]
