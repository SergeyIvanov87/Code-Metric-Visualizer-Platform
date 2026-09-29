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

The input tree is request-scoped and is deleted together with the deferred
request after completion, timeout, or shutdown. Deployments that require tmpfs
staging can mount the shared API volume itself on tmpfs; the directory must
remain visible at the path published in the handshake to every producer.

Paths matching `file_regex` are recreated beneath
`destination/preferred_directory`; other regular files are counted as skipped.
Only `conflict_policy=fail` is supported. Symlinks, hard links, special files,
and other unsupported nodes are removed from staging without being followed or
uploaded; the final `items_skipped` and `items_skipped_path` fields report them.
Path traversal and overwriting existing destinations remain request errors.

The processor applies admission limits of 1,024 bytes and 64 components per
relative path, 10,000 files, 10,000 directories, and 100 GiB of staged regular
file data. These bounds keep reconciliation metadata and the final atomic FIFO
result finite and protect a long-lived service from an unbounded staging tree.
