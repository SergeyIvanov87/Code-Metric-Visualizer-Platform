# AI chat agent

Chat inference sources and CPU, NVIDIA, and Intel Vulkan configuration profiles
live in this service. `AI_AGENT_INFERENCE_CONFIG` selects an inference JSON
profile. GPU profiles require a matching llama.cpp build and reject unavailable
hardware rather than falling back to CPU.

`API/deps/rag-subsystem` mirrors all six business schemas from `../ai_agent/API`,
including the separate URI (`rag_add`) and inline-data (`rag_add_data`) APIs.
Refresh these copies whenever the provider contracts change.

`API/deps/docs-dispatcher/read_id.json` mirrors the dispatcher API consumed by
chat retrieval when Chroma returns document IDs; refresh it with the provider
schema whenever that contract changes.

Inference configuration tests use mocked hardware probes and do not validate
live model inference or GPU availability. Run from the repository root:

```sh
docker compose -f ai_agents_framework/ai_chat_agent/compose-unit.test.yaml up --build --abort-on-container-exit --exit-code-from ai-chat-agent-unit-tester
```

The public chat functional suite runs the real CPU inference agent with
session-aware Chroma and dispatcher test doubles:

```sh
docker compose -f ai_agents_framework/ai_chat_agent/compose-functional.test.yaml config --quiet
docker compose -f ai_agents_framework/ai_chat_agent/compose-functional.test.yaml up --build --abort-on-container-exit --exit-code-from ai-chat-agent-functional-tester
```

Production hardware Compose profiles are not yet implemented in this service.
