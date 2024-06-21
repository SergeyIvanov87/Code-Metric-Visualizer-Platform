FROM linuxserver/syslog-ng:4.5.0

RUN apk add openssh patch
COPY common/images/syslog-ng_image/config/syslog-ng.conf /config/syslog-ng.conf
COPY common/images/syslog-ng_image/config/volatile.conf /config/volatile.conf
VOLUME ["/var/log/"]

ADD common/images/syslog-ng_image/bootstrap.sh /etc/bootstrap.sh
ENTRYPOINT ["/bin/sh","-c"]
CMD ["/etc/bootstrap.sh"]
