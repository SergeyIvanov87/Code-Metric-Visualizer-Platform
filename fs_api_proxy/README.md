# Description

Collection of filesystem API proxies, which designated to decouple microservices on an infrastructure level

#P.S.
to use debugger and be able to attach to process

`apk add gdb python3-dbg --no-cache`

in docker compose add

```
    cap_add:
      - SYS_PTRACE
```

## List of supported API proxies:

- [HTTP Proxy](http_proxy/README.md)
