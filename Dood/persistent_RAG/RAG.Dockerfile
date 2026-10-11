FROM persistent-rag/rag-base:local
# Chroma's Rust image has no Python interpreter; install the HTTP probe tool.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*
COPY chroma.yaml /etc/persistent-rag/chroma.yaml
ENTRYPOINT ["dumb-init", "--", "chroma", "run", "/etc/persistent-rag/chroma.yaml"]
