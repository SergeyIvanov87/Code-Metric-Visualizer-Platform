# Optional proxy trust

This directory owns the shared Compose resource, empty-file default, and
`with-proxy-ca.sh` command wrapper. Set `PROXY_CA_FILE` to an absolute path to a
readable public PEM CA file or bundle. An unset/empty variable selects
`empty-proxy-ca.pem`; missing or empty additional CA files leave command trust
settings unchanged. Never supply private keys.

Compose entrypoints that consume the secret must import
`compose-proxy-trust.yaml`, directly or through an existing `include` chain.
Services explicitly opt in with `build.secrets: [proxy_ca]` and, when needed,
`secrets: [proxy_ca]` for runtime. `extends` imports service settings but not
top-level resources. For `-f` overlays, paths to the included file resolve from
the first Compose file. The empty-file fallback resolves within this directory.

Copy the helper into a base image once, then wrap network-dependent commands:

```dockerfile
COPY --chmod=0755 common/proxy_setup_image_helpers/with-proxy-ca.sh /usr/local/bin/with-proxy-ca.sh
RUN --mount=type=secret,id=proxy_ca,mode=0444 \
    /usr/local/bin/with-proxy-ca.sh apk add --no-cache python3 curl
```

Derived images inherit the helper but must still mount the secret for each
network-dependent RUN. The isolated REST image copies the same helper from its
existing `common` named build context. Services that genuinely require outbound TLS at runtime can prefix their
ENTRYPOINT with `/usr/local/bin/with-proxy-ca.sh`. REST installs dependencies
during the build and therefore does not use this runtime option.

The helper is compatible with Bash and `/bin/sh`, so it can bootstrap Alpine
before Bash is installed. It combines the system bundle with a nonempty extra
CA, configures Python/Requests/pip/curl trust for the command, preserves its
stdin and exit status, forwards INT/TERM, and removes the temporary bundle when
the command exits. `PROXY_CA_PATH` overrides the in-container extra CA path;
`SYSTEM_CA_FILE` overrides the system bundle path. TLS verification stays on.
No additional CA is installed permanently or stored in exported image layers.
Changing a BuildKit secret does not invalidate cached layers: use `--no-cache`
when rechecking downloads with changed trust. Proxy addresses remain configured
through Docker's standard proxy settings.
