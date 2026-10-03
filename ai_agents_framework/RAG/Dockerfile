FROM chromadb/chroma:1.5.9.dev10-amd64

ADD ai_agents_framework/RAG/bootstrap.sh /etc/bootstrap.sh
RUN apt-get update && apt-get install -y openssh-server

ENTRYPOINT ["/bin/bash","-c"]
CMD ["/etc/bootstrap.sh"]
