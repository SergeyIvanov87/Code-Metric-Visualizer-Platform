# Streaming integration capture recreation RCA

## Incident

[Run 40247424605, job 121331848481](https://github.com/SergeyIvanov87/Code-Metric-Visualizer-Platform/actions/runs/40247424605/job/121331848481?pr=146)
failed on 2026-10-26 with exit code 255 and
`capture completed without any connection logs`. This is an integration
orchestration failure independent of PR #146's CUDA/Vulkan image changes.

## Evidence and cause

The workflow starts the capture-only Compose model, then builds and starts the
functional-test model. The latter includes all capture services in the same
project. Thus the second build exports the running capture images again and
the second `up` reconciles the active one-shot services.

The job log records both capture images built twice, followed by:

- 00:03:33–00:03:44 UTC: `log_event_aggregator` recreated.
- 00:03:44–00:03:45 UTC: `tap_subscriber` recreated.
- 00:03:51 UTC: the three testers started.
- 00:04:27 UTC: aggregator exit 255 reported.

Recreation stops the original subscriber. Its SIGTERM handler deliberately
finalizes capture and publishes `capture_complete`, even when no tester has
started. The replacement consumer uses the same capture ID, group and Kafka
topic, with `auto.offset.reset=earliest` and no automatic commits. It therefore
can consume the original subscriber's empty terminal event. It correctly rejects
a capture containing zero connection logs.

The uploaded diagnostic artifact (12619395971) confirms the distinction:
subscriber decoded and per-producer files contain all three testers' pytest
summaries, but the consumer output has no connection logs and only its readiness
marker. The replacement subscriber captured the later traffic; that does not
invalidate the earlier terminal event consumed by the aggregator.

The exact Compose reconciliation reason is not logged. Local resolved service
configuration hashes match between both models; unchanged YAML alone does not
guarantee container preservation after rebuilding image references. The observed
recreation and the subscriber shutdown path establish the lifecycle failure.

## Correction

Build the logger and complete included test model before starting capture.
Remove the redundant capture-only build. Add `--no-recreate` when introducing
testers so the subscriber and consumer retain their process lifetime, even if
Compose would otherwise reconcile an image reference. Update the documented
staged launch to use the same ordering and preservation flag.

Preserve the aggregator's empty-capture failure and subscriber's graceful
shutdown semantics; suppressing either would hide an orchestration defect.

## Validation

- Aggregator unit suite: 17 passed.
- Subscriber unit suite: 22 passed (separate process because the aggregator
  suite installs a module-level Kafka stub).
- All three workflow Compose models: `config --quiet` passed.
- Workflow YAML parsing and all inline shell blocks: passed `bash -n`.
- `git diff --check`: passed.
- Full Docker integration and the repaired GitHub Actions run remain unverified.
  CI should confirm successful authoritative aggregation and final validation
  (`All tests PASSED: (5/6)`), with no capture-service recreation when testers start.
