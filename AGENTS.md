# Repository instructions for AI agents

## Find the relevant skill

Task-specific procedures are in `.agents/skills/*/SKILL.md`. Before working on a
matching task, read the relevant skill below. If the agent application does not
automatically discover repository skills, open the linked file directly.
Load only the skills and references needed for the task.

| Task | Skill |
| --- | --- |
| Locate an owner, trace dependencies, or choose a platform stack | [repository-navigation](.agents/skills/repository-navigation/SKILL.md) |
| Change schemas, generated executors, FIFO sessions, deferred requests, or REST exposure | [filesystem-api-development](.agents/skills/filesystem-api-development/SKILL.md) |
| Change streaming uploads, shared staging, directory events, sealing, or cleanup | [streaming-ingestion](.agents/skills/streaming-ingestion/SKILL.md) |
| Change document storage, chunk/vector consistency, retrieval, or inference configuration | [agentic-rag-development](.agents/skills/agentic-rag-development/SKILL.md) |
| Change dispatcher backend compositions, access/store schemas, or storage entries | [docs-dispatcher](.agents/skills/docs-dispatcher/SKILL.md) |
| Select tests or diagnose Compose, readiness, capture, or test aggregation | [container-test-diagnostics](.agents/skills/container-test-diagnostics/SKILL.md) |

For cross-cutting work, combine the owning subsystem skill with the test skill.
Use [the repository map](HowTo/Agent-Repository-Map.md) for architecture and source
locations and [the skills guide](HowTo/Agent-Skills.md) for usage and maintenance.

## Use architecture records as context

Relevant skills link directly to implementation recaps, design reviews, and ADRs
under `Architecture_Design_Decisions/` and the streaming test subsystem. Read the
linked record when changing the decision or boundary it explains; do not load
all records for every task.

Distinguish an original proposal, an implementation recap, a review finding, and
a future recommendation. Check current code, schemas, and tests before treating
any recorded behavior or limitation as current. Preserve the design rationale
when fixing a bug; explain an intentional architectural change when necessary.

## Working conventions

- Run repository commands from the checkout root unless the selected workflow
  specifies another directory. Inspect Compose build contexts and overlays.
- Change source schemas and generators for generated filesystem APIs.
- Use the smallest relevant checks, and report what ran and what remains unverified.
- Update affected skills and references when their paths, commands, or contracts change.
