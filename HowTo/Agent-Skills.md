# Agent skills: use and authoring

A skill is a reusable procedure an AI agent can load for a particular kind of task. It combines instructions with optional reference material, scripts, or examples. It teaches the agent how to work in this repository without rediscovering the same conventions every time. It does not train the model or give it extra permissions.

Each skill here lives in `.agents/skills/<name>/SKILL.md`. The YAML frontmatter supplies a name and a description that tells an agent when to use it. The Markdown body supplies the procedure and checks. Large background material belongs in linked references so agents load it only when needed.

## Available repository skills

| Skill | Use it for |
| --- | --- |
| [repository-navigation](../.agents/skills/repository-navigation/SKILL.md) | Finding the owner and tracing dependencies across platform stacks |
| [interservice-dependencies](../.agents/skills/interservice-dependencies/SKILL.md) | Declaring consumed APIs, dependency command endpoints, and service/test readiness gates |
| [filesystem-api-development](../.agents/skills/filesystem-api-development/SKILL.md) | Schema/generator changes, FIFO sessions, deferred lifecycle and REST exposure |
| [http-api-customization](../.agents/skills/http-api-customization/SKILL.md) | HTTP route discovery, gateway precedence and ambassador development |
| [streaming-ingestion](../.agents/skills/streaming-ingestion/SKILL.md) | File/directory transfers, shared-staging events, sealing, backpressure and cleanup |
| [agentic-rag-development](../.agents/skills/agentic-rag-development/SKILL.md) | Dispatcher backends, chunk/vector consistency, retrieval and inference configuration |
| [container-test-diagnostics](../.agents/skills/container-test-diagnostics/SKILL.md) | Choosing tests, Compose builds, readiness, aggregation and diagnostics |

The [repository map](Agent-Repository-Map.md) provides shared architecture knowledge and source references. These skills were authored against `origin/main` at `2569e2c`; verify current code when behavior changes.

## Using a skill

In agents that support repository skills under `.agents/skills`, open this checkout and invoke a skill by its name, for example:

> Use $filesystem-api-development to add a new endpoint. Use $container-test-diagnostics to choose and run its checks.

The root [AGENTS.md](../AGENTS.md) lists task-to-skill mappings so agents can find these procedures even without automatic skill discovery. Each skill links relevant architecture records with guidance on when to read them and how to distinguish implemented behavior from proposals or historical findings.

Automatic selection depends on the agent and its skill-discovery support. For agents that do not discover this directory, explicitly ask them to read the relevant `SKILL.md` and follow its linked references. Keep each skill beside this checkout because its relative links point into repository source. These files are repository skills, not an installation into this chat's hosted skill catalog.

## Creating a useful skill

1. **Pick one recurring task.** “Modify deferred upload cleanup” is actionable; “be a good developer” is too broad. Split unrelated workflows.
2. **Inspect real evidence.** Read implementation, schemas, tests, and CI. Record where facts came from. Distinguish current code from proposed architecture.
3. **Write the trigger first.** Describe tasks and symptoms that should select the skill. Avoid descriptions such as “helpful repo information.”
4. **Write a short decision-making procedure.** Explain where to start, which contract to preserve, when to choose another path, and how to finish. Use exact paths and commands verified in the repo.
5. **Include hard-won details.** Here, that means newline-framed FIFO requests, separate handshake/final results, shared-staging ownership, and delayed stale-vector deletion. General programming advice adds little value.
6. **Define observable success.** Name the tester, expected behavior and failure evidence. State prerequisites and distinguish isolated checks from live service verification.
7. **Try representative tasks.** Ask an agent to use the skill for a normal case, a failure case and a related task where the skill should not activate. Inspect its choices and resulting diff. Fix missing steps or ambiguous triggers.
8. **Maintain it with the code.** Update a skill when commands, paths, protocols or prerequisites change. Prefer links to authoritative references over copying large sections into every skill.

### Minimal template

```markdown
---
name: focused-task-name
description: Use when changing [specific subsystem] or diagnosing [specific symptom].
---

# Perform the task

Read [the relevant contract](relative/path/to/source) first.

1. Locate the owner and closest working example.
2. Make the change while preserving [specific invariant].
3. Handle [known failure mode].
4. Run [verified focused command], then the relevant integration scope.

## Completion

Report behavior changed, checks and results, and remaining limitations.
```

Optional `references/` material can hold long specifications. Add scripts only when a repeatable operation benefits from deterministic execution; describe their inputs, outputs, dependencies, and side effects. Do not embed credentials, add unrequested approval steps, or promise checks that were never run.

## Skill quality checks

- Would the description select this skill for a realistic request?
- Can an agent find every referenced path and run commands from the stated directory?
- Does the procedure explain decisions and failure handling rather than only listing files?
- Is success independently observable?
- Does the skill contain repository-specific knowledge that saves real investigation?
- Can a maintainer update it without keeping several copies of the same facts in sync?

Metadata and link validation establish structure. They do not prove that an agent will perform a real task correctly; that requires trial tasks and the relevant service checks.
