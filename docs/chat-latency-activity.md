# Chat admission, context latency and actual activity

## Production findings

The October 27 follow-up investigated the owner's slow Send and first-reply
screenshots against the actual deployed runtime, including existing long
conversations. The previous isolated fresh-conversation acceptance did not
exercise every production history/provenance path.

| Observation | Measured result |
| --- | --- |
| Slow context's memory provenance stage | 12,693.36 ms |
| Another context's memory provenance stage | 8,271.90 ms |
| Synchronous pre-reply history summary | 7,805.83 ms |
| Existing user-run queue delay in the recent sample | approximately 22–179 ms |
| Provider first text in those recent turns | approximately 1.4–2.6 s |
| Public authenticated duplicate-nonce ACK from the VPS | 22.77–77.09 ms |

The ACK probe reused an existing committed message/receipt, temporarily issued
and removed an authenticated session, and verified no additional Run. It measures
the public server path from the VPS, not the owner's cellular connection or a
fresh live trading request.

The provenance query filtered Agent, event kind and memory version, but omitted
the leading owner equality required by `ln_events_owner_agent_kind_cursor`.
Production `EXPLAIN (ANALYZE, BUFFERS)` observed a parallel sequential scan taking
**6,097.846 ms**. Adding canonical Agent ownership selected that existing index
and took **0.361 ms** on the same ledger. The query now derives ownership from
`ln_agents`; legacy unknown provenance remains unknown. No migration, event
deletion, new index or provenance cache is required.

## Runtime changes

- Foreground execution starts context/model work without awaiting an archive
  model. A separate supervised Gateway history loop examines a bounded projection
  of completed conversational Runs and processes up to five distinct threads per
  tick. Summary work never occupies a conversation worker or keeps Writing active.
- Summaries begin proactively at 80 unsummarized messages, retain the existing
  recent-history budget, and only archive through the completed turn's frozen
  input. Original messages are retained. The existing summary-cursor comparison
  prevents overlapping work from overwriting a newer summary; no database lock
  spans a model request. Failed/cancelled/live Runs cannot enter settled maintenance.
- A bounded read gate admits at most three concurrent client API reads. Send,
  cancellation and other mutations bypass it, as do the independent SSE/WebSocket
  connections. Queued reads remain cancellable and session-fenced. This reserves
  browser HTTP/1 connection capacity without cancelling a financial operation,
  introducing an automatic retry, or treating a local enqueue as server acceptance.
- Web mutations additionally request high browser fetch priority. Real network
  and model latency still vary; no constant first-token time is promised.
- Activity is a small projection recorded in the existing leased progress
  transaction. There is no extra status HTTP request, model generation, timer
  sequence or commit. Reload/reconnection can restore the last observed phase
  without replaying the entire tool/token history.
- Web header and transcript avatars use the same actual event projection. Search,
  reading, analysis, execution, learning and writing follow the work performed;
  reading trade history is not classified as executing an order. Terminal states
  retain precedence over active-tool observations.
- A provider attempt starts one reply generation instead of an extra preliminary
  generation followed immediately by another. Fallback remains fenced, and legacy
  adapters without attempt callbacks initialize their stream on first publication.
  The existing bounded publisher still keeps provider reads independent of storage.
- Cold-release acceptance exposed another avoidable cost: skill scope checks were
  serializing the entire native schema catalog merely to read permitted names.
  Those checks now read current registry membership directly, retaining the same
  read-only exclusions and fresh revocation checks. Hash-verified offline encoders
  are initialized before Gateway readiness rather than during the first message.

## Verification

- `bash scripts/build.sh`: required formatting, lint, Pyright, generated-resource
  checks, TypeScript checks and all seven builds pass.
- Full Python suite: **1,347 passed**, using disposable migrated PostgreSQL.
- `tests/check_chat_latency.py`: actual provenance reads, durable activity, a
  committed reply and a subsequent Send while the archive model is deliberately
  blocked; later owner input is excluded from that earlier summary.
- `tests/check_memory_provenance.py`: owner/Agent/legacy authorship remains exact.
  Its scripted fixture now selects its actual tool result rather than assuming
  the final model-context message is a tool result; visual guidance can follow it.
- `tests/check_streaming.py`: all 19 durable-stream/peer integration checks pass.
- All **150** client unit checks pass. They cover bounded read capacity, queued cancellation, session fences,
  immediate Web/native Send despite saturated reads, restored activity and stale
  event rejection. Browser checks cover pending/accepted handoff, retries, drafts,
  SSE recovery, RTL/theme variants and real header activity while Run GETs fail.
  Seventeen browser scenarios passed in the combined run; the added header
  scenario passed separately after its fixture received a real owner-message
  anchor (the original Run-only fixture had no transcript input to attach to).

The restored cloud instance initially needed its existing PostgreSQL container
started and upstream hash-verified tokenizer caches restored. An interrupted
browser launch left an owned test server on port 8830; that exact process was
stopped before retrying. Loopback test traffic uses `NO_PROXY` for localhost.
These setup corrections do not change application authentication, TLS trust,
source assertions, production data or broker authority.

Raw diagnostic outputs remain ignored under `.runtime/chat-latency-*` and
`.runtime/chat-query-plan-comparison.log`; no credentials or conversation text
are committed here. Production deployment reuses the existing signed Android
runtime/certificate and immutable API/Gateway release path, without backups.
