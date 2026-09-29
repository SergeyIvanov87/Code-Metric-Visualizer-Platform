# Streaming uploads

The file-uploader service exposes two deferred pseudo-filesystem queries:

* `streaming_file_upload` accepts one byte stream through a FIFO. Its optional
  `expected_bytes` argument prevents a short or interrupted stream from being
  installed.
* `streaming_directory_upload` accepts a tree through a request-scoped staging
  directory and transfers each closed, stable file through the existing
  `streaming_file_upload` API.

## Directory upload

Write the query arguments, including a unique `SESSION_ID`, to
`streaming_directory_upload/POST/exec`, then read
`result.json_<SESSION_ID>`. The handshake reports an `input` directory, one
`status-<id>` FIFO per worker, and the final `result` FIFO:

```json
{
  "input": "/api/.../deferred-.../input",
  "input_type": "DIRECTORY",
  "status": ["/api/.../deferred-.../status-1"],
  "status_type": "FIFO[]",
  "protocol": "cmvp.directory-upload.v1",
  "result": "/api/.../deferred-.../async_result",
  "result_type": "FIFO"
}
```

Open status FIFOs before copying when every progress event is important. Status
is deliberately non-blocking: an absent or slow reader never stalls ingestion,
and the final result is authoritative. Copy files into `input`, preferably by
renaming completed files into place. The request completes after the configured
update quiet period once the staging tree and worker queue are empty.

`input` is a real directory inside the deferred request directory, not a
container-only symbolic link. Consequently, a host that mounts the API tree can
use ordinary filesystem tools directly, for example:

```sh
cp -r /path/to/project "$(jq -r .input < handshake.json)/"
```

Directory uploads disable the nested uploader's per-file `fsync` and use a
coordinated durability barrier after either `flush_file_threshold` files
(default 256) or `flush_byte_threshold` bytes (default 64 MiB), whichever comes
first. A final barrier always runs before the aggregate result is returned.
Successfully transferred staging files are deleted only after their batch is
durable. Failed staging files remain until request cleanup so their paths can be
reported. The input tree is request-scoped
and is deleted together with the deferred request after completion, timeout,
or shutdown. Deployments that require tmpfs staging can mount the shared API
volume itself on tmpfs; the directory must
remain visible at the path published in the handshake to every producer.

`file_allow_regex` is an allow-list for regular files and defaults to `.*`;
`file_skip_regex` is a deny-list and defaults to matching nothing. The directory
equivalents are `dir_allow_regex` and `dir_skip_regex`. All four expressions use
a full match against the POSIX relative path, and a skip match takes precedence
over an allow match. Rejecting a directory rejects its complete subtree. By
default, `dir_skip_regex` excludes hidden directories at every level, as well
as `__pycache__`, `__pypackages__`, and `node_modules`. Zero-byte files are
also filtered. All filtered regular files are counted in `files_skipped`.

Only `conflict_policy=fail` is supported. Symlinks, hard links, special files,
and other unsupported nodes are removed from staging without being followed or
uploaded; the final `items_skipped` and `items_skipped_path` fields report them.
Path traversal and overwriting existing destinations remain request errors.
By default a file-transfer error stops discovery of new work after already
queued and active work reaches a safe boundary. Set `tolerate_errors=true` to
continue discovering and copying subsequent files; the final result remains an
error and lists every failed relative path.

The processor applies admission limits of 1,024 bytes and 64 components per
relative path, 10,000 files, 10,000 directories, and 100 GiB of staged regular
file data. File, directory, and byte admission counts are evaluated after the
size and regex filters, so excluded paths do not consume those limits. These
bounds keep reconciliation metadata and the final bounded FIFO result finite
and protect a long-lived service from an unbounded staging tree.

`streaming_file_upload` accepts `need_flush=true|false` and defaults to `true`.
With the default, it preserves the existing behavior of synchronizing file data
before reporting success. `need_flush=false` is intended only for bulk
coordinators that provide their own durability barrier; it is not a promise that
data has reached stable storage when the individual file result is returned.

On Linux, reconciliation uses filesystem events to wake scans promptly and backs
them with periodic full scans. Unsupported or exhausted watchers fall back to
the original polling behavior without changing filtering or admission semantics.
