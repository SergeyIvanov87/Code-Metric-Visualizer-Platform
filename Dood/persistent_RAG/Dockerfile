FROM docker:28.4.0-cli
WORKDIR /opt/persistent-rag
COPY images.tar /opt/persistent-rag/images.tar
COPY stack.yaml entrypoint.sh ./
ENTRYPOINT ["/bin/sh", "/opt/persistent-rag/entrypoint.sh"]
