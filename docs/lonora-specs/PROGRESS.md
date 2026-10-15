# Progress

## Current wave

Wave 1: shared foundations and safe vertical integration. Branch `feat/coherent-agent-foundations`, audited base `895eaa8`. All 18 supplied originals copied byte-for-byte, including 03 activation extension; root read every source before foundation design. Specs are capability requirements, not a numeric task queue.

## Active workstreams

- Root: explicit Personal scope, idempotent bootstrap, schema, timeline anchor/inbox contract, cross-workstream registration and docs.
- Skills: validated selective runtime, immutable policy split, provenance diagnostics and legacy compatibility.
- Chat: shared chronological timeline, mobile scroll/loading/preview and guarded voice initialization.
- Market: canonical health assessment, stale-input watch suspension and recovery.
- Tasks: extend tickets/runs, separate same-agent work and conversation lanes, safe control/status/checkpoints.
- Execution: immediate pre-submit revalidation, account serialization, typed quality/exposure.

## Completed foundations

- Existing primitives audited: Agent bindings, leased Runs/checkpoints/steering, ticket work threads, peer/outcome receipts, Gateway, market snapshots/wake receipts, goals/decisions, approvals and journal.
- All 18 specifications preserved and indexed. No source document discarded or summarized away.

## Blockers

- No specification files missing.
- Physical Android voice crash reproduction/logcat and OS authentication need an available Android runtime. Do not certify from TypeScript/browser checks.
- Official speech/order-flow/depth sources must report unavailable where actual feed lacks them; no fabricated evidence.
- Production deployment is outside this branch-only implementation task.

## Resolved dependencies

One HealthSnapshot; explicit Agent role (no wildcard); ticket-based task identity; one approval sequence-anchor contract; one shared chronological TS projector. ToolLoop integration has sequenced ownership. Root alone changes schema/migrations.

## Remaining dependencies

Task/health/identity foundations → collaboration/mention identity, evidence/thesis, manual broker diffs, attention, Super Bot authorization, shadow/performance, replay and UI live projection. None marked complete merely because a related primitive exists.

## Checks

No new-code checks completed yet. Existing baseline source was pulled from main; prior test results are not counted as current verification. No live-money or production mutation tests.

## Next integration point

Integrate wave-1 scoped commits; migrate disposable PostgreSQL; test scope/approval sequencing/task concurrency/watch health/pre-submit gating; run Ruff/Pyright/client checks, update requirement-level statuses with actual test evidence before wave 2.
