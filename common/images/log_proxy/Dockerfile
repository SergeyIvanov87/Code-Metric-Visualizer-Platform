FROM envoyproxy/envoy:dev-5451efd9b8f8a444431197050e45ba974ed4e9d8
RUN apt-get update && apt-get install -y openssh-client sshpass curl dos2unix

COPY common/images/log_proxy/envoy.yaml /etc/envoy/envoy.yaml
RUN chmod go+r /etc/envoy/envoy.yaml

ADD common/images/log_proxy/bootstrap.sh /etc/bootstrap.sh
RUN dos2unix /etc/bootstrap.sh

COPY common/shell_utils/ssh.sh /package/ssh.sh

RUN dos2unix /package/* && chmod +x /package/*.sh

ARG ENVOY_ADMIN_PORT=9901
ENV ENVOY_ADMIN_PORT=${ENVOY_ADMIN_PORT}

ARG MAX_BUFFERED_RX_BYTES=4294967295
ENV MAX_BUFFERED_RX_BYTES=${MAX_BUFFERED_RX_BYTES}

ARG UPSTREAM_SYSLOG_TCP_PORT=13601
ENV UPSTREAM_SYSLOG_TCP_PORT=${UPSTREAM_SYSLOG_TCP_PORT}

ARG DOWNSTREAM_SYSLOG_TCP_PORT=6601
ENV DOWNSTREAM_SYSLOG_TCP_PORT=${DOWNSTREAM_SYSLOG_TCP_PORT}

ARG DOWNSTREAM_SYSLOG_HOSTNAME=api.pmccabe_collector.syslog-ng
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
