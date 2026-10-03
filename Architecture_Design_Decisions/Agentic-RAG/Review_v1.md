# Agentic RAG implementation, version 1: architecture review

## Review scope

This review evaluates the architecture described in
[`implementation_v1.md`](implementation_v1.md) against the implementation in
`ai_agents_framework/ai_agent` and `ai_agents_framework/docs_dispatcher`. It
assesses the design as it exists; it is not a replacement architecture.

## Executive assessment

The architecture has a sound conceptual foundation, but the current
implementation is not yet production-ready for sensitive or large document
collections.

The strongest decisions are:

- separating authoritative document content from the vector index;
- resolving search results by stable chunk ID instead of copying text into
  Chroma;
- treating the SQL metadata store and Chroma as rebuildable indexes;
- reconciling derived stores from the filesystem; and
- delaying stale-vector deletion until a complete source scan succeeds.

The principal risks are:

1. filesystem metadata is declared authoritative, but synchronization does not
   update metadata for existing SQL records;
2. the active checked-in backend configuration uses SQLite rather than a
   separate MySQL service;
3. ingestion is not atomic across SQL and filesystem storage;
4. the SQL database must be available to allocate an ID before ingestion can
   write the authoritative filesystem record;
5. a full Chroma sync recomputes and upserts every embedding;
6. repeated chunk text can be assigned the wrong byte offset; and
7. storage access controls and encryption are not ready for sensitive data.

| Area | Assessment |
| --- | --- |
| Separation of responsibilities | Good |
| Source-of-truth model | Good intention, incomplete enforcement |
| Recovery model | Good foundation |
| Transactional consistency | Weak |
| Scalability | Adequate for version 1, weak for large corpora |
| Retrieval design | Reasonable baseline |
| Security | Not production-ready |
| Documentation accuracy | Mostly accurate, with important qualifications |

## Strengths

### Content is separated from vector search

The filesystem owns document bytes, SQL indexes IDs and metadata, and Chroma
supports semantic search. Ingestion sends Chroma chunk IDs, embeddings, and
routing metadata, but no chunk text. Retrieval asks Chroma for IDs and
distances, then obtains accepted chunks through `docs_dispatcher`.

This separation provides useful properties:

- Chroma can be rebuilt without restoring a second copy of document content;
- a vector database compromise does not directly expose the stored plaintext;
- storage and search can have independent backup and scaling policies; and
- retrieval authorization can eventually be centralized in the dispatcher.

Chroma does not literally store only embeddings: it also stores record IDs and
minimal routing metadata. The implementation document describes that nuance
correctly.

Relevant implementation:

- `ai_agents_framework/ai_agent/sources/rag_add.py`
- `ai_agents_framework/ai_agent/sources/rag_sync.py`
- `ai_agents_framework/ai_agent/sources/rag_answer_question.py`
- `ai_agents_framework/ai_agent/sources/docs_retriever.py`

### The dispatcher is an appropriate storage boundary

`docs_dispatcher` prevents the RAG agent from depending directly on filesystem
layout or SQL credentials. It is a suitable boundary for future backend
selection, validation, authorization, auditing, and encryption. Encryption
should remain behind this boundary so callers do not need to distinguish an
encrypted backend from a plaintext backend.

### Derived indexes are rebuildable

The recovery direction is correct:

1. scan the filesystem and reconcile SQL records;
2. enumerate the reconciled document and chunk hierarchy;
3. read chunk content through the dispatcher;
4. recompute and upsert vectors; and
5. remove vectors that are absent from a successfully completed source scan.

`rag_sync.py` accumulates source chunk IDs over all result pages. It deletes
stale Chroma IDs only during finalization. If a chunk read or embedding fails,
the scan does not reach finalization, so unvisited records are not incorrectly
treated as stale. This is a strong safety property.

### Stable IDs support reconstruction

Document and chunk IDs are reflected in filesystem directory names. When SQL
is missing a filesystem record, synchronization recreates the SQL row with the
existing ID. This preserves parent-child relationships and Chroma identities
without renumbering restored content.

### Chunk ranges reduce storage amplification

Chunks are represented by a parent document ID and a byte range. Reading a
chunk loads the parent document and returns that range. Overlapping chunk text
therefore does not need to be persisted separately in the filesystem, SQL, and
Chroma.

### Deletion ordering follows the source-of-truth model

The delete operation discovers the affected Chroma IDs, deletes the dispatcher
records, and then deletes the vectors. If authoritative deletion fails, the
vectors remain. If vector deletion fails afterward, synchronization can remove
the stale vectors later. That ordering is preferable to deleting from Chroma
first.

## High-priority findings

### 1. Metadata authority is not fully enforced

The architecture says that filesystem content, hierarchy, and metadata are
authoritative. The synchronization implementation updates an existing SQL row
when its URI, offset, size, parent ID, or document type differs. It does not
compare or update `metadata_json`.

Filesystem metadata is copied into SQL when a missing row is created, but a
metadata difference on an existing row survives synchronization. Therefore,
the documented invariant that SQL metadata matches filesystem sidecars is not
currently guaranteed.

Relevant implementation:

- `ai_agents_framework/docs_dispatcher/sources/backend/mysql/sync.py`
- `ai_agents_framework/docs_dispatcher/sources/backend/mysql/doc_storage/models.py`

**Impact:** metadata search can return stale values even after a successful
sync, and the effective metadata authority becomes ambiguous.

**Recommended direction:** either reconcile every mirrored metadata field from
the filesystem or explicitly designate SQL as authoritative for searchable
metadata. The former is consistent with the documented design.

### 2. The active backend is SQLite, not an independent MySQL service

Both the active dispatcher backend configuration and `backends/mysql.yaml`
currently use:

```text
sqlite:////mnt/file_storage/rag_docs_database.db
```

The backend code can construct a real `mysql+pymysql` connection, but the
checked-in active configuration stores SQLite in the same mounted hierarchy as
the documents.

Relevant configuration and implementation:

- `ai_agents_framework/docs_dispatcher/sources/backend/dispatcher/current`
- `ai_agents_framework/docs_dispatcher/sources/backend/dispatcher/backends/mysql.yaml`
- `ai_agents_framework/docs_dispatcher/sources/backend/mysql/app/database.py`

**Impact:** the configured SQL index and document storage do not have
independent failure domains, and the MySQL-centered operational description can
mislead deployers.

**Recommended direction:** distinguish the logical SQL metadata role, the
SQLite development profile, and the MySQL production profile. If MySQL is a
production requirement, provide a production composition that actually uses
it.

### 3. Full-document ingestion is not atomic

The dispatcher commits the initial SQL record before it creates the filesystem
directory and writes the document and sidecars. It subsequently updates the SQL
parent relationship. Failures can therefore leave:

- a SQL row without a filesystem record;
- an incomplete filesystem directory;
- filesystem content without the final SQL fields; or
- an error response before the RAG agent receives an ID it can roll back.

The agent's rollback protects failures that happen after `put_doc` returns, but
it cannot delete an allocation whose `put_doc` operation failed without
returning its ID. Synchronization eventually repairs some partial states, but
that is recovery rather than atomicity.

Relevant implementation:

- `ai_agents_framework/docs_dispatcher/sources/backend/mysql/put_doc.py`
- `ai_agents_framework/docs_dispatcher/sources/backend/mysql/app/crud.py`
- `ai_agents_framework/ai_agent/sources/rag_add.py`

**Recommended direction:** use explicit ingestion states, idempotent steps, and
a transaction or operation ID. A temporary filesystem directory followed by an
atomic rename can also reduce visible partial state. The dispatcher should
clean up SQL and filesystem artifacts when its own insertion fails.

### 4. A database outage prevents new ingestion

Filesystem-to-SQL synchronization can reconstruct records that were already
committed to storage. It does not make ingestion available while SQL is down,
because SQL allocates the ID before a filesystem directory can be created.

This is a valid consistency-over-availability decision, but the recovery claim
must be interpreted precisely:

- rebuilding missing or stale SQL metadata from committed filesystem records
  is supported;
- accepting new documents while the SQL ID allocator is unavailable is not.

If offline ingestion becomes a requirement, IDs should be generated without a
live central database, for example with a collision-resistant identifier.

### 5. Repeated text can produce incorrect chunk offsets

Chunk attachment locates content with `parent_data.find(chunk_data)`, which
returns the first matching byte sequence. Identical text that appears more than
once can therefore produce several chunk records pointing at the same first
occurrence.

Relevant implementation:

- `ai_agents_framework/docs_dispatcher/sources/backend/mysql/attach_doc_chunk.py`

The retrieved text may still look correct because the repeated passages are
identical, but provenance, ordering, citations, and surrounding-context
expansion can be wrong.

**Recommended direction:** make the splitter produce explicit start and end
offsets, pass those offsets to the dispatcher, and validate that the referenced
bytes match the supplied chunk.

## Consistency and integrity findings

### Parent documents must be immutable

Chunk IDs refer to byte ranges in their parent. If a parent file is modified in
place, offsets can select unrelated content even when the file retains the same
size. The current SQL reconciliation compares structural fields rather than
document bytes.

Committed parent documents should be immutable. An update should create a new
document version and regenerate all chunks, or it should atomically replace the
document, chunk records, and vector generation.

### Content and configuration fingerprints are missing

Useful reconstruction metadata would include:

- a document content hash;
- a chunk content hash;
- a splitter configuration and version;
- an embedding model and revision;
- an embedding normalization configuration;
- a metadata revision; and
- a filesystem record schema version.

These fingerprints would allow synchronization to distinguish unchanged
records from content or model changes.

### Synchronization is eventually consistent, not atomic

Chroma records are upserted while pages are processed. A failure halfway leaves
some new vectors and some old vectors, although stale deletion is safely
deferred. A later sync converges the collection.

This behavior is acceptable for version 1, but operations and monitoring should
report partial completion. A future implementation could use a generation ID,
a shadow collection followed by promotion, or query filtering by the active
embedding generation.

### Synchronization lacks a stable source snapshot

The reviewed code does not visibly prevent two sync jobs from overlapping or
ingestion and deletion from changing the hierarchy during offset-based
pagination. A global sync lease, immutable source generation, database snapshot,
or stable-ID cursor would make reconciliation deterministic under concurrency.

## Scalability findings

### Every sync recomputes every embedding

The Chroma reconciliation reads, embeds, and upserts each current chunk. It
classifies existing IDs as updated and always reports an empty `not_changed`
list. The cost therefore grows with the complete corpus rather than the number
of changes.

This is simple and reliable for a small corpus, but expensive at scale. Content
and embedding-configuration fingerprints would allow unchanged vectors to be
skipped.

### Chunk and embedding tokenizers are not aligned

The splitter measures 220-token chunks with `cl100k_base`, while the embedding
model is `sentence-transformers/all-MiniLM-L6-v2`, whose code comments note a
256-word-piece limit. A chunk within the first limit is not necessarily within
the second because the tokenizers differ.

Some vectors may represent a truncated prefix while retrieval returns the
complete stored chunk. Chunk sizing should use the embedding model's tokenizer
with a safety margin.

## Retrieval-quality findings

### The relevance threshold requires calibration

Retrieval uses a global maximum distance of `1.0`, explicitly marked as an
initial value. A threshold depends on the embedding model, normalization,
distance function, corpus, and recall requirements. It should be configurable
per collection and calibrated using retrieval evaluation data.

### Search does not yet exploit the metadata index

Vector search currently uses a query embedding and result count without
metadata, tenant, source, or authorization filters. The architecture should
eventually define whether metadata search is performed before vector lookup,
through Chroma filters, after vector lookup, or as a hybrid lexical and vector
query.

### Overlapping results can dominate context

Adjacent chunks overlap by design, but retrieval has no visible diversity or
deduplication stage. Several nearly identical chunks can consume model context.
Maximal marginal relevance, adjacency merging, or reranking would improve
context efficiency.

## Security findings

Keeping future encryption behind `docs_dispatcher` is the correct abstraction,
but encryption is only one part of the security model. A functional composition
initializes document storage with mode `0777`, which is unsuitable as a model
for sensitive production data.

Before production use, the deployment should provide:

- a dedicated non-root dispatcher identity;
- least-privilege filesystem permissions;
- a volume mounted only by services that require it;
- authenticated and authorized dispatcher operations;
- private database networking and transport protection;
- tenant isolation and authorization-aware retrieval;
- audit logs for ingestion, reads, deletion, and synchronization;
- encrypted backups; and
- documented key rotation and recovery procedures.

Volume encryption would protect offline media, but it would not prevent a
compromised container with the volume mounted from reading or poisoning data.

## Recommended priorities

### Priority 0: correctness

1. Reconcile filesystem metadata into existing SQL rows.
2. Clean up partial SQL and filesystem state during insertion failures.
3. Replace first-match chunk discovery with explicit offsets.
4. Enforce document immutability or versioned updates.

### Priority 1: operational reliability

1. Separate SQLite development and MySQL production profiles.
2. Add synchronization locking or generation-based snapshots.
3. Store content hashes and embedding-configuration versions.
4. Expose partial synchronization state and operational metrics.

### Priority 2: security

1. Replace permissive storage permissions with least privilege.
2. Add dispatcher authentication, authorization, and auditing.
3. Define encrypted storage, backup, and key-management procedures.
4. Define tenant isolation before enabling metadata filtering.

### Priority 3: scale and retrieval quality

1. Re-embed only new or changed chunks.
2. Chunk with the embedding model's tokenizer.
3. Calibrate collection-specific distance thresholds.
4. Add metadata filters, overlap deduplication, and reranking.
5. Consider generation-based Chroma index promotion.

## Final verdict

The architecture's core direction is appropriate:

> authoritative content store → rebuildable metadata index → rebuildable vector
> index → ID-based content retrieval

The conceptual decomposition should be retained. The main issue is that several
documented guarantees are stronger than the current implementation:

- existing SQL metadata is not fully reconstructed from filesystem metadata;
- the active configuration does not match the MySQL-centered deployment model;
- ingestion has non-atomic failure windows;
- repeated text makes chunk provenance ambiguous; and
- security and incremental indexing require further work.

The architecture is suitable as a version 1 direction, but the implementation
should not yet be considered production-ready for sensitive or large-scale
document collections.
