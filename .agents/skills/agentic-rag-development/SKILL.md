---
name: agentic-rag-development
description: Use when changing document dispatcher backends, chunk storage, document add/delete, Chroma reconciliation, retrieval, filesystem API wrappers, or agent inference configuration.
---

# Develop the agentic RAG pipeline

Use the [RAG source map](../../../HowTo/Agent-Repository-Map.md#agentic-rag) to locate the stage that owns the bug.

1. Trace document operations through `ai_agents_framework/ai_agent/sources/fs_api_wrappers.py`, dispatcher entrypoints in `ai_agents_framework/docs_dispatcher/sources`, backend modules, and the vector store. Preserve document IDs versus chunk IDs and their metadata relationships.
2. For backend changes, read `dispatcher_backend_config.py` and [backend configuration](../../../ai_agents_framework/docs_dispatcher/sources/backend/dispatcher/README.md). The dispatcher routes to same-named command modules using the configured backend name. The package named `mysql_persistent` defaults to a SQLite URI: verify configuration rather than inferring the engine from the directory name. Refer to secret paths without printing their contents. For backend selection and filesystem ownership, follow [dispatcher maintenance](../docs-dispatcher/SKILL.md): shared directory and metadata operations belong to `StorageRecordEntryInterface`, while payload operations belong to `PersistentStorageRecordEntry`.
3. For reconciliation, read `rag_sync.py` and `tests/test_rag_sync.py`. Validate source pages and duplicate chunk IDs, preserve stable chunk metadata, and delay deletion of stale Chroma IDs until source enumeration succeeds. A failed or incomplete page must not be interpreted as an empty authoritative source. Preserve partial-progress error reporting.
4. For add/delete behavior, trace `rag_add.py`, `rag_delete.py`, and dispatcher storage operations. Preserve wrapper distinctions between inline textual document data and URI input. Verify both document storage and embeddings; deleting one does not prove deletion of the other.
5. For inference changes, read `inference_config.py`, configuration tests, and [agent runtime guidance](../../../ai_agents_framework/ai_agent/README.md). CPU, NVIDIA, and Intel Vulkan use different build/runtime requirements. GPU profiles must validate device/backend availability; do not silently fall back to CPU. Each replica loads its own model and cache.
6. Run focused tests, then the relevant dispatcher, RAG store, or full agent functional scope from [test diagnostics](../container-test-diagnostics/SKILL.md). Mocked reconciliation tests do not establish live database, model, or GPU readiness.

## Focused checks

```sh
python -m pytest -q ai_agents_framework/ai_agent/tests/test_fs_api_wrappers.py ai_agents_framework/ai_agent/tests/test_rag_sync.py ai_agents_framework/ai_agent/tests/test_rag_delete.py ai_agents_framework/ai_agent/tests/test_inference_config.py
```

## Architecture references

For storage ownership, ingestion, retrieval, or recovery changes, read:

- [Agentic RAG implementation v1](../../../Architecture_Design_Decisions/Agentic-RAG/implementation_v1.md): filesystem content authority, SQL metadata/ID allocation, Chroma as a derived index, chunk byte ranges, ingestion rollback, and filesystem-to-SQL-to-Chroma recovery ordering. It includes diagrams and an implementation map.
- [Architecture review](../../../Architecture_Design_Decisions/Agentic-RAG/Review_v1.md): qualifications to that model, including cross-store transaction gaps, existing-record metadata synchronization, repeated-text chunk offsets, and full-sync embedding costs. Use its findings as investigation leads and failure-test scenarios, not proof that every issue is still present.

Verify the described behavior against current backend configuration, storage code, and tests. In particular, do not infer database engine or transactional guarantees from the implementation document's use of “MySQL.” Encryption and other future recommendations are not implemented guarantees. These records do not specify GPU configuration; use the runtime guidance above for inference-only changes.

## Completion

State which storage stages changed, how consistency is retained on failure, and which checks used mocks versus running services. Report hardware-dependent checks as unverified if hardware is unavailable.
