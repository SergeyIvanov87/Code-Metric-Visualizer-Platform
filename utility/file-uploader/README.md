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

The Compose deployment mounts the same tmpfs-backed volume at
`/dev/shm/file-uploader` in producers and the service. Deployments using a
separate producer container must mount `file-uploader-staging` there at that
same absolute path so the handshake's directory symlink resolves identically.

Paths matching `file_regex` are recreated beneath
`destination/preferred_directory`; other regular files are counted as skipped.
Only `conflict_policy=fail` is supported. Symlinks, hard links, special files,
path traversal, and overwriting existing destinations are rejected.
