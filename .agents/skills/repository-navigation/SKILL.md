---
name: repository-navigation
description: Use when locating code, tracing service dependencies, or choosing the Analysis, Analytic, HTTP proxy, or agentic RAG stack in Code Metric Visualizer Platform.
---

# Navigate the platform

1. Read the [repository map](../../../HowTo/Agent-Repository-Map.md). Identify the owning service before editing shared code.
2. Trace the behavior from its `API/*.json` schema to `api_generator.py` or processor, then `init.sh`, Dockerfile, and service Compose entry point. Generated runtime scripts are outputs; change their generator.
3. For cross-service calls, inspect the consumer's `API/deps` directory and the shared volume/network wiring in the chosen root Compose file. The REST server exposes filesystem APIs; an HTTP symptom may originate in the FIFO provider.
4. Select the stack deliberately: `compose-analysis.yaml` analyzes a local `PROJECT_PATH`; `compose-analytic.yaml` uses `PROJECT_URL`, `PROJECT_BRANCH`, VCS updates, and broker scheduling. The `*-http-api*` variants add another transport boundary. Agentic RAG is under `ai_agents_framework`.
5. Read applicable design decisions as context, then verify behavior in current code and tests. A proposal is not proof that a feature is implemented.
6. Use [container-test-diagnostics](../container-test-diagnostics/SKILL.md) to select checks for the owning component and its consumers.

## Architecture references

When a task needs the reasoning behind a feature, use the focused record lists in:

- [Filesystem API development](../filesystem-api-development/SKILL.md#architecture-references) for deferred lifecycle and ownership.
- [Streaming ingestion](../streaming-ingestion/SKILL.md#architecture-references) for bulk upload versus shared-staging notifications and performance tradeoffs.
- [Agentic RAG development](../agentic-rag-development/SKILL.md#architecture-references) for content authority, derived indexes, and recovery.
- [Container test diagnostics](../container-test-diagnostics/SKILL.md#architecture-references) for one-shot capture and legacy substitution.

Start with the record for the affected boundary. Read implementation recaps alongside original reviews when they disagree, and confirm the current behavior in code and tests.

## Completion

Report the owner, request/data path, affected consumers, chosen test scope, and any unverified assumptions. For a metric change, distinguish CC generation from RRD persistence and graph rendering.

## Example

“Flamegraph returns empty output”: begin at `cyclomatic_complexity/API/flamegraph.json` and `cyclomatic_complexity/api_generator.py`, inspect watch-list/statistic inputs, then trace the REST adapter only if filesystem output is correct.
