---
name: container-test-diagnostics
description: Use when choosing or running repository tests, debugging Compose build contexts or service readiness, collecting test diagnostics, or investigating legacy and streaming test aggregators.
---

# Run and diagnose container tests

Run commands from the repository root unless a source explicitly states otherwise. Read [the test matrix](../../../HowTo/Agent-Repository-Map.md#test-matrix) and the matching `.github/workflows` job before launching a suite.

1. Choose the smallest scope that exercises the changed behavior: pure Python checks, common API lifecycle suite, owning-service functional tests, then cross-service integration when needed.
2. Inspect the selected Compose file and included/extended files. Resolve build contexts relative to their defining Compose file and inspect Dockerfile `COPY` sources; many images require the repository root. Use `docker compose -f <selected-file> config --quiet` before a build. This validates configuration, not behavior.
3. Inspect external volume/network prerequisites and required environment variables. Analysis needs `PROJECT_PATH`; Analytic needs `PROJECT_URL` and `PROJECT_BRANCH`. Do not blindly reproduce CI-wide image/container pruning or remove unrelated resources on a shared machine.
4. For finite service functional tests, propagate the tester's status using `--abort-on-container-exit --exit-code-from <tester-service>`. The tester name is specific to the Compose model; see the matrix.
5. For streaming capture, read [its lifecycle documentation](../../../common/images/streaming_test_aggregator/README.md) and `.github/workflows/streaming-test-aggregator.yml`. This is detached orchestration: collect the aggregator status first, and run/collect final validation only after success. `docker wait` prints the container status; its own successful invocation does not mean that status was zero.
6. Keep one `TEST_EXECUTION_ID` throughout an on-demand streaming run, result collection, and cleanup. Use a unique ID for repeated runs. The permanent Envoy supports one active tap subscriber, so unique IDs alone do not make overlapping captures safe.
7. Distinguish process startup from readiness: broker topic/metadata readiness, Envoy `/ready`, tap attachment, and terminal capture events are separate stages. For admin streaming tap, preserve `JSON_BODY_AS_BYTES`; binary length-delimited format is invalid for that sink.
8. Collect `ps --all`, logs, tester/aggregator exit codes, and relevant capture artifacts before teardown. Consult `.github/actions/upload-test-aggregator-artifacts/action.yml` for legacy capture exports. Keep diagnostics out of committed source and avoid exposing interpolated secrets in Compose configuration output.
9. Tear down only the test project you created. Use `down --volumes` only for disposable test state, never persistent analytic databases or a permanent logger project. Preserve diagnostics before removing test volumes.

## Architecture references

For streaming capture lifecycle or replacing the legacy aggregator, read:

- [Accepted one-shot event-pipeline ADR](../../../common/images/streaming_test_aggregator/EVENT_PIPELINE_ARCHITECTURE_DECISION_RECORD_v1_0.md): permanent Envoy versus execution-scoped capture components, controller ownership, terminal events, authoritative results, and failure semantics. Keep its hardening plan separate from already implemented behavior.
- [Legacy substitution assessment](../../../common/images/streaming_test_aggregator/LEGACY_SUBSTITUTION_ASSESSMENT.md): why replacement requires orchestration/configuration changes rather than an image rename, plus traffic isolation, outage/restart limits, and promotion conditions. Check current CI and component code before treating those conditions as satisfied or outstanding.

For upload-specific failure scenarios, follow the records in [streaming ingestion](../streaming-ingestion/SKILL.md#architecture-references). Use the current workflow and Compose models for executable commands; an architectural lifecycle diagram is not a complete launch recipe.

## Completion

Report exact commands and statuses, the earliest failed readiness/data stage, and what remains untested. A green test-runner container is insufficient if the authoritative aggregator failed.
