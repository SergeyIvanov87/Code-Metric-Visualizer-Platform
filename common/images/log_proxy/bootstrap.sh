#!/bin/bash

source /package/ssh.sh

echo "${HOSTNAME}"

echo "Remove all SSH stored keys to prevent 'man-in-the-middle' complaint, as host identities may change in our virtual network"
rm -f /root/.ssh/known_hosts

echo "Wait until syslog-ng SSH server started"
wait_for_ssh "root" "${DOWNSTREAM_SYSLOG_HOSTNAME}" "${DOWNSTREAM_SSH_SECRET}"
execute_ssh_cmd "root" "${DOWNSTREAM_SYSLOG_HOSTNAME}" "${DOWNSTREAM_SSH_SECRET}" "while syslog-ng-ctl healthcheck -c /config/syslog-ng.ctl && [[ \$? != 0 ]]; do echo \"waiting for syslog-ng running...\" && sleep 1; done"

# Bootstrap the port/address placeholders before starting Envoy.
sed -i "s/ENVOY_ADMIN_PORT/${ENVOY_ADMIN_PORT}/" /etc/envoy/envoy.yaml
sed -i "s/MAX_BUFFERED_RX_BYTES/${MAX_BUFFERED_RX_BYTES}/" /etc/envoy/envoy.yaml
sed -i "s/UPSTREAM_AGGREGATOR_TCP_PORT/${UPSTREAM_AGGREGATOR_TCP_PORT}/" /etc/envoy/envoy.yaml
sed -i "s/DOWNSTREAM_SYSLOG_TCP_PORT/${DOWNSTREAM_SYSLOG_TCP_PORT}/" /etc/envoy/envoy.yaml
sed -i "s/DOWNSTREAM_SYSLOG_HOSTNAME/${DOWNSTREAM_SYSLOG_HOSTNAME}/" /etc/envoy/envoy.yaml


/docker-entrypoint.sh envoy -c /etc/envoy/envoy.yaml
