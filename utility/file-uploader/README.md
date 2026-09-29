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

`input` is a symbolic link to a request-scoped directory in a shared tmpfs
staging root. The default root is `/dev/shm/file-uploader`. Compose bind-mounts
that exact absolute host path at the exact same container path, which is
required so that the published link resolves in both mount namespaces.

On a native Linux host, prepare the root before starting Compose:

```sh
export FILE_UPLOADER_STAGING_ROOT=/dev/shm/file-uploader
mkdir -p "$FILE_UPLOADER_STAGING_ROOT"
chmod 2770 "$FILE_UPLOADER_STAGING_ROOT"
docker compose -f utility/file-uploader/compose.yaml up
```

`FILE_UPLOADER_STAGING_ROOT` may be changed, but it must be an absolute,
tmpfs-backed host path and must retain the same value inside the service and
every producer container. The supplied Compose files apply that mapping to the
service and functional-test producer.

The host can then use ordinary filesystem tools through the API symlink:

```sh
cp -r /path/to/project "$(jq -r .input < handshake.json)/"
```

The real staging tree is deleted together with the deferred request after
completion, timeout, or shutdown. Docker Desktop users must choose a path that
is shared by the Docker VM and the host; the `/dev/shm` default is intended for
native Linux deployments.

Paths matching `file_regex` are recreated beneath
`destination/preferred_directory`; other regular files are counted as skipped.
Only `conflict_policy=fail` is supported. Symlinks, hard links, special files,
path traversal, and overwriting existing destinations are rejected.
