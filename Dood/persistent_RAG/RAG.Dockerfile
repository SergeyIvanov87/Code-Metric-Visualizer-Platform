FROM persistent-rag/rag-base:local
COPY chroma.yaml /etc/persistent-rag/chroma.yaml
ENTRYPOINT ["dumb-init", "--", "chroma", "run", "/etc/persistent-rag/chroma.yaml"]
