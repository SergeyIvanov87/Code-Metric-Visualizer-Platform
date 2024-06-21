#!/bin/bash

echo $HOSTNAME

# Fix BUG with service command execution: add missed pipe link
#ln -s /config/syslog-ng.ctl /run/syslog-ng.ctl

# launch sshd server to listen incoming connections
# TODO no security at all, use open password in this PoC
echo "PermitRootLogin yes" >> /etc/ssh/sshd_config
ssh-keygen -A
echo "root:syslog-ng" | chpasswd
/usr/sbin/sshd

# docker inspect results used here [ENTRYPOINT + CMD]
exec /init
