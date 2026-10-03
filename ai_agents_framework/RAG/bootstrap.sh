#!/bin/bash

echo $HOSTNAME

# launch sshd server to listen incoming connections
# TODO no security at all, use open password in this PoC
echo "PermitRootLogin yes" >> /etc/ssh/sshd_config
ssh-keygen -A
echo "root:RAG" | chpasswd

service ssh start

# docker inspect results used here [ENTRYPOINT + CMD]
exec dumb-init -- chroma run /config.yaml
