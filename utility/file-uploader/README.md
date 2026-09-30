# Streaming uploads

The file-uploader service exposes three deferred pseudo-filesystem queries:

* `streaming_file_upload` accepts one byte stream through a FIFO. Its optional
  `expected_bytes` argument prevents a short or interrupted stream from being
  installed.
* `streaming_directory_upload` accepts a tree through a request-scoped staging
  directory and transfers each closed, stable file through the existing
  `streaming_file_upload` API.
* `streaming_directory_events` observes files copied into shared staging and
  returns batches of per-file readiness events without copying them to
  `/uploads`.

## Shared-staging directory events

`streaming_directory_events` is intended for containers that mount the same
staging volume at `/staging`. Its handshake returns an `input` directory on
the familiar deferred API path, the canonical `staging` directory, a live
`events` FIFO, and the ordinary final `result` FIFO. `input` is a symbolic link
to `staging`; all participating containers must therefore mount `/staging` at
the same absolute path.
Producers should copy beneath an excluded
temporary directory (for example `.incoming`, which the default directory
filter excludes) and atomically rename completed files to their final paths.

Every open-and-drain of `events` returns one JSON document containing all
events accumulated since the previous successfully delivered batch:

```json
{"first_sequence":1,"last_sequence":40,"events":[...40 events...]}
```

Read until EOF; a FIFO is a byte stream, so a single `read(2)` is not guaranteed
to contain the complete JSON document. Events are sequence numbered and also
contain the relative path, byte count, modification time, device, and inode.
The files remain in shared staging after the API request expires. This endpoint
reports readiness only: it does not copy to `/uploads`, guarantee persistent
storage, or report that a consumer has processed a file. After the event
session idle timeout, `result` returns a final summary and the common deferred
executor cleans up the request-local FIFOs and journal.
Cleanup unlinks the request-local `input` link but does not traverse it or
remove the files in `staging`. Consumers that need files after request cleanup
must retain the canonical `staging` path from the handshake.

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
is deliberately non-blocking: an absent or slow reader never stalls ingestion.
Each worker retains an ordered backlog of events that could not yet be written;
when a reader reconnects, it receives the complete backlog rather than only the
latest event. The reader must drain the FIFO, and the history exists only for the
lifetime of the directory-upload processor. The final result remains
authoritative. Copy files into `input`, preferably by renaming completed files
into place. The request completes after the configured update quiet period once
the staging tree and worker queue are empty.

`input` is a real directory inside the deferred request directory, not a
container-only symbolic link. Consequently, a host that mounts the API tree can
use ordinary filesystem tools directly, for example:

```sh
cp -r /path/to/project "$(jq -r .input < handshake.json)/"
```

Each successfully transferred staging file is deleted immediately after the
nested upload confirms its exact byte count. Failed staging files remain until
request cleanup so their paths can be reported. The input tree is request-scoped
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
before reporting success. `need_flush=false` is intended only for a coordinator
that provides its own safe durability barrier.
