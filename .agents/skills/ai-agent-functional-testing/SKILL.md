---
name: ai-agent-functional-testing
description: Use when adding or changing ai_agent public filesystem API functional cases, dependency mocks, case JSON contracts, or positive-flow pipeline coverage.
---

# Test the AI agent through its functional API

Treat `ai_agents_framework/ai_agent/tests/functional` as the authoritative test boundary for public `ai_agent` use cases. The test runs the real agent and Chroma while replacing unavailable downstream services with filesystem-API-compatible mocks. Integration tests may extend this boundary by replacing mocks with real services.

## Trace the complete query path

1. Start at the public schema under `ai_agent/API` and its processor under `ai_agent/sources`.
2. Follow calls through `sources/fs_api_wrappers.py` to schemas under `ai_agent/API/deps`.
3. Inspect `tests/functional/api_generator.py` to confirm how generated dependency executors pass arguments, stdin, and deferred-query state to `mock_exec`.
4. Keep the public test, dependency mocks, and JSON cases aligned with those contracts.

## Define public cases

Store each public case in `tests/functional/api_test_cases/<api>.json`. Use one top-level property whose name is the exact outer `SESSION_ID`:

```json
{
  "human_readable_SESSION_ID_value_describing_a_test_case": {
    "query": {"parameter": "value"},
    "answer": {"error_code": 0}
  }
}
```

The test executor reads that first property, serializes `query` into the API argument format, creates `APIQueryInterruptible` with the value of `SESSION_ID` equal to "human_readable_SESSION_ID_value_describing_a_test_case", calls the API, waits for completion, and compares the decoded result with `answer`. Validate a deferred API completed result, not merely its initial handshake.
Then it proceeds to the next `SESSION_ID` in the JSON

Use deterministic mounted fixtures and deterministic expected values. Normalize only genuinely runtime-generated fields when an API contract necessarily includes them.

## Define dependency mock cases

Give every called dependency its own `<api>.json`. Reuse the outer case identity: processors generate inner session IDs whose prefix is the outer session. Each candidate response contains:

```json
{
  "human_readable_SESSION_ID_value_describing_a_test_case": [
    {
      "query_sent": {"parameter": "expected value"},
      "query_received": {"parameter": "expected value"},
      "answer": {"dependency": "response"}
    }
  ]
}
```

The mock must recover the invoking session, select the matching top-level case, parse every argument or stdin payload, match the complete query against `query_received`, and return only the corresponding `answer`. It must fail clearly and log the exchange when no entry matches. The field `query_sent` repeats the parameters of the initial `query` using which the mock was invoked, it is used for diagnostic purposes.

Use a list when the same dependency is called repeatedly, such as one chunk attachment per document chunk. Preserve call-specific IDs and metadata. For positive-flow branching, provide only calls that should occur; for example, a successful `put_doc` permits subsequent `attach_doc_chunk` calls.

## Limitations

Do not create any testing scripts in the manner of unit-testing. All new tests must be added as test cases and public cases, so that each `<api>.json` will be growing.

## Implement and verify

Keep helpers minimal and shared only where they make the case contract clearer. The functional container generates executors, services, and pseudo-filesystem nodes from dependency manifests during `init.sh`; do not bypass that path by directly invoking a mock or processor.

Follow [container test diagnostics](../container-test-diagnostics/SKILL.md). Executable verification belongs to the container entrypoint; never run pytest or standalone test scripts directly. Use:

```sh
docker compose -f ai_agents_framework/ai_agent/compose-functional.test.yaml config --quiet
docker compose -f ai_agents_framework/ai_agent/compose-functional.test.yaml up --build --abort-on-container-exit --exit-code-from ai-agent-functional-tester
```

Report which public APIs and dependency calls were covered, which services were real or mocked, and anything that could not be verified.
