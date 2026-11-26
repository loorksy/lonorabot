# Gap analysis: the agent loop and harness

Lonora (`/home/user/wt-agent/fxmain`, main at `d8193b98`) compared with OpenMausBot and Rakazo, using `reports/openmausbot-loop.md` and `reports/rakazo-loop.md`. Scope: one turn end to end, retries, recovery, compaction, subagents and the run lifecycle.

Method: I started from Lonora's floorplan (`floorplan/architecture.json`, the `backend-libs.agent.runtime`, `worker`, `backend-libs.integrations.bus` and `backend-libs.models.providers` node lists), then read the code. Every gap below is backed by a `file:line` quote from Lonora. Nothing was executed and nothing was edited. Reference-project claims come from the two reports, not from running their code.

Effort scale: **S** ≤ 1 day, **M** 2–4 days, **L** 1–2 weeks, **XL** > 2 weeks.

## Ranked recommendations

| # | Recommendation | Verdict | Learned from | Main Lonora files | VISION / DECISIONS | Effort |
|---|---|---|---|---|---|---|
| 1 | Make every tool-call id non-empty and unique within a Run before anything executes | **Adopt** | Rakazo (unique ids per run), OpenMausBot (duplicate id is a protocol error) | `agent-runtime/.../model_runtime.py` or `tool_loop.py`, `adapters/.../openai_compatible.py` | 6.2, 6.3, 5.3.3, 12.1, 17 (strengthens them; no conflict) | S |
| 2 | Cooperative drain: on SIGTERM, hand each running Run back at its next safe boundary; cancel only as a backstop | **Adopt** | Rakazo (`drainRuns`, `yielded` handback between steps) | `gateway/service.py`, `agent-runtime/.../tool_loop.py`, `executor.py` | 6.3, 6.8, 6.9, 17; Amendment 3 items 6 and 9; D11 | S |
| 3 | Anthropic prompt caching for the in-Run transcript (a rolling breakpoint, with volatile runtime blocks kept after it) | **Adapt** | OpenMausBot (stable/volatile prompt split), Rakazo (cache-stable prefix, per-turn data last) | `adapters/.../anthropic.py`, `agent-runtime/.../model_runtime.py` | 12, D6/D41 (the customer pays with their own key), 6.10 (labels kept), P1 (no limit added) | M |
| 4 | Routine overlap: skip or coalesce a due tick while an earlier Run of the same routine is unfinished | **Adopt** | Rakazo (`findPendingRoutineTick`, skip if previous tick active), OpenMausBot (overlap policy, `missed` rows) | `db/.../routines.py` | 11.5, 11.6, 17; P1 not affected | S |
| 5 | Notice a cancelled Run within ~2 s, not at the next lease renewal (≤ 40 s) | **Adapt** | Rakazo (1 s watchdog), OpenMausBot (immediate interrupt) | `agent-runtime/.../executor.py`, `db/.../runs.py` | 4.6, 4.7, 7.1.5, D6/D41 | S |
| 6 | Prune transient stream events (`run.delta`, `run.rich_partial`) of settled Runs; widen the 25 ms coalescing window | **Adopt** | Rakazo (deletes transient events at finalize), OpenMausBot (progress frames are live-only) | `db/.../events.py`, `gateway/service.py`, `agent-runtime/.../stream_publication.py` | Amendment 3 item 4 (disk is a plan resource), D10, D13, 17 | S |
| 7 | Show an inline provider retry on the status line before the router sleeps | **Adapt** | OpenMausBot (`turn.retrying` chip) | `providers/.../router.py`, `agent-runtime/.../model_runtime.py`, web/mobile labels | 17 (status line built from what is really happening) | S |
| 8 | Stamp the prompt/manifest version on each Run | **Adopt** | Rakazo (`promptVersion()` on the run row) | `db/.../runs.py` or `executor.py`, `agent-runtime/.../skills/system_policy.py` | 5.8.6; phase 5 (prompt rewrite) | S |
| 9 | Should a conversation's helper Run open a new listed conversation? | **Owner decision** | Rakazo (helper shown as a card in the parent thread) | `agent-runtime/.../collaboration/subagents.py`, `db/.../threads.py` | P5 (the conversation list); 11.6 covers routines only | M if changed |

Where Lonora is already ahead, the reference ideas are listed under "Already better" below and are not repeated as work.

---

## 1. What Lonora does today: one turn end to end

Paths are relative to `/home/user/wt-agent/fxmain`.

1. **Entry.** `send_message` (`packages/db/src/lonora_db/messages.py:332`) checks `client_nonce` idempotency (`:338`), then `admit_agent` (`:708`) runs. A paused agent keeps the message for resume (`:721-725`). An active Run receives a `SteeringRow` (`:824`, `:829`); a queued continuation drops its retry deadline (`:825-827`); otherwise a new `RunRow` is queued (`:833-845`).
2. **Claim.** The gateway runs `maximum_subagents + 1` shared worker loops plus one `conversation`-lane loop (`packages/gateway/src/lonora_gateway/service.py:482-497`). Each polls every 0.5 s through `dispatch_one` (`run_dispatch.py:31-91`) into `claim_next` (`packages/db/src/lonora_db/runs.py:239-355`). That function gives one active Run per thread, `skip_locked`, a retry `not_before` read from the checkpoint (`:258-259`), expired-lease recovery with `recovery_count` (`:247-255`, `:327-330`) and `lease_fence += 1`.
3. **Execute.** `AgentRuntime.execute` (`packages/agent-runtime/src/lonora_agent/runtime.py`) calls `execute_run` (`executor.py:100-356`). A heartbeat renews the lease every `lease_seconds / 3` (`executor.py:45-74`), the status becomes `running`, and the loop result is routed to an external wait, `waiting_input`, or `complete_run`. `ToolRetryScheduled` requeues the Run with a deadline (`:298-341`). A stale lease is discarded silently. Anything else goes to `fail_run`.
4. **Loop.** `execute_tool_loop` (`tool_loop.py:349-676`) does the following in order:
   - restores the checkpoint (`loop_restore.py`);
   - routes a pending question, an external wait or a new wake;
   - at every round, calls `cancellation_checkpoint` and `task_checkpoint` (`:435-436`);
   - at a limit or halt, makes the checkpointed final tool-less report (`finish_turn`, `:231-346`);
   - runs the pending tool block segment by segment, and owner steering supersedes the calls that have not started (`:482-486`);
   - merges steering, adds a budget warning, compacts (`compact_for_turn`, `:137-179`), makes the model turn (`model_turn`, `model_runtime.py:32-299`), appends the reply and checkpoints it;
   - returns the final answer through the structural conversation gate (`conversation_gate.py`).
5. **Tools.** `dispatch_call` (`tool_dispatch.py:23-153`) handles one call:
   - a stored receipt is replayed;
   - an ambiguous financial route is reconciled on the same operation;
   - an interrupted call that is not read-only or replay-safe gets `tool_execution_uncertain` (`:83-96`);
   - intent is persisted immediately before an effect (`before_effect`, `:97-99`).

   Guardrails are persisted in the checkpoint (`tool_guardrails.py:53-73`). Parallel segments come from `tool_batch.py`.
6. **Model resilience.** The router (`packages/providers/src/lonora_providers/router.py:284-540`) works through an ordered candidate chain, with bounded retries per reason, an output boost or correction, and a bench on failure (`resilience.py:73-96`, `:174-209`). After the whole chain fails, `plan_failure` (`model_recovery.py:155-202`) decides what happens: compact and retry on overflow, a jittered backoff whose profile depends on who waits (`:58-63`), or escalation.
7. **Context and compaction.** `build_context` (`context/builder.py:60-`) builds the context. In-Run compaction is a persisted view over the canonical messages, with a deterministic fallback; operational state is re-read from the database, never trusted to a summary (`context_engine.py:10-19`, `compacted_view` `:394`, `deterministic_summary` `:585`). Cross-Run history summaries come from `context/compaction.py`, driven by `gateway/history_maintenance.py`.
8. **Subagents and peers.** A helper Run is created with depth < 2 and at most `maximum_subagents` concurrent (`collaboration/subagents.py:23-42`). Peer delegation refuses cycles (`peer_messages.py:28-41`), and both are idempotent by call id. Outcomes return through `outcome_return.py`. Cancelling a Run cancels its children (`db/cancellation.py:56-70`).
9. **Streaming and the UI.** Every progress write is fenced (`progress.py:16`, `require_lease(..., lock=True)`), coalesced by `stream_publication.py`, and stored in the durable `ln_events` table (`db/schema.py:445-470`). Clients resume from a database cursor (`apps/api/src/lonora_api/websocket/events.py:77-91`).
10. **End and shutdown.**
    - `complete_run` (`db/runs.py:421-510`) refuses to complete while steering is outstanding (`:425-431`), so the same Run answers it.
    - A Run that keeps crashing is quarantined, or held while a financial operation is unresolved (`runs.py:590-638`).
    - On SIGTERM the gateway waits 25 s, cancels, then releases leases with the fence kept (`service.py:505-519`, `shutdown.py:8-14`, `runs.py:551-587`).

The rest of this document compares that path with the two references.

---

## 2. Recommendations in detail

### R1. Unique, non-empty tool-call ids per Run (Adopt, S)

**What the references do.**
- Rakazo makes tool call ids unique per run (`uniqueToolCallIdStream`, `runs/turn/tool-call-ids.ts`; Rakazo report §2.D.17 and .20).
- OpenMausBot treats a duplicate `call.id` within a turn as a protocol error, "refusing to repeat an operation" (OpenMausBot report §5.3).

**Lonora today.** Provider ids are taken verbatim, and nothing checks that they are non-empty or unique:
- the streamed OpenAI-compatible path starts each id empty and only concatenates fragments, so a provider that omits ids yields `""`. It does this at `packages/adapters/src/lonora_adapters/models/openai_compatible.py:210-213`:
  ```python
  call = calls.setdefault(int(fragment["index"]), {"id": "", "name": "", "arguments": ""})
  call["id"] += fragment.get("id", "")
  ```
  and the id goes into the `ToolCall` unchanged at `:232-234`;
- the same happens on the non-streamed path (`:108-109`) and in Anthropic (`anthropic.py:140`, `:242-243`);
- `ToolCall.id: str` has no constraint (`packages/adapter-kit/src/lonora_adapter_kit/types.py:8-11`).

Every per-call identity in the harness is derived from that id:
- receipts: `result_identity` = `stable_id(run_id, "tool-result:" + call.id)` (`packages/tools/src/lonora_tools/tool_results.py:24-25`);
- `effect_key` / `resource_id` (`packages/tools/src/lonora_tools/context.py:56-61`);
- the Trade Approval id (`packages/tools/src/lonora_tools/trade.py:408`: `stable_id(context.lease.run_id, "approval:" + context.call_id)`);
- the helper and peer Run ids (`subagents.py:27-29`, `peer_messages.py:19-27`).

**What goes wrong.** Say a compatible endpoint returns `call_0` in round 3 and again in round 9.
- **Same name and arguments.** `dispatch_call` returns the round-3 receipt instead of executing (`tool_dispatch.py:43-55`). A quote read in round 9 shows round-3 prices as current.
- **Different arguments.** The call fails with `tool_result_identity_conflict` (`tool_results.py:88-91`). The model sees a failure it cannot explain.

Two calls in one reply that both have id `""` collide the same way.

The safety core holds either way. The execution door's own operation id and fingerprint stop a double send (6.2, 6.3), and freshness is re-checked at send (6.5). But the agent reasons on stale or false results, which goes against 5.3.3 in spirit, and a second intended order fails with a conflict.

**Recommendation.** After `model_turn` returns, and before the assistant message is appended and checkpointed (`tool_loop.py:631-640`; also the ignored calls in `finish_turn`, `:293-296`), rewrite the id of any call that is empty, repeated in the reply, or already present in the Run's transcript. The new id is server-derived and deterministic, for example `stable_id(run_id, f"call:{round}:{index}")`.
- The rewritten id is what Lonora stores and sends back to the provider, because Lonora resends its own transcript.
- Leave ids from Anthropic (`toolu_…`) and OpenAI untouched when they are already unique, so existing checkpoints and receipts keep matching.
- Record the original id in `provider_metadata` for diagnosis.

**Tests.**
- A fake adapter that emits `""` and repeated ids across rounds: no receipt collision, the second call executes, and the transcript stays valid.
- The core regression tests in 14.1.2 still pass.

### R2. Cooperative drain at a safe boundary (Adopt, S)

**What the references do.** Rakazo drains for up to 5 min. It keeps renewing leases, and each run hands itself back between steps through `finishTurn` → `{type:"yielded", checkpoint}` → `requeueInterruptedRun`, so the next worker continues with the next model call (Rakazo report §6, "Graceful drain").

**Lonora today.** Stop is checked only before a claim, at `packages/gateway/src/lonora_gateway/service.py:156`:
```python
while not self.stop.is_set():
```
A Run already executing keeps starting model rounds and tools. The loop's boundaries (`tool_loop.py:435-436`, `:483`) check the lease and Task controls, never the drain. `serve()` then calls `await drain(loops)` (`service.py:511`), which waits `grace_seconds: float = 25` (`shutdown.py:8`) and cancels whatever is still running (`shutdown.py:11-14`). After that, `release_leases` (`service.py:515`) requeues the Runs.

A worker cancelled in the middle of a non-replay-safe tool leaves an in-flight marker. On the next claim that marker becomes `tool_execution_uncertain` (`tool_block.py:51-96`); a financial operation goes to reconciliation and possibly to the owner's settle card (6.8). So the restart itself manufactures uncertainty. Every `lonora` update, rollback and restore runs `quiesce`, which is `compose stop gateway api` (`infra/compose/lonora:254-260`). In Lonora Cloud that is the weekly update window (D11) and every suspension (Amendment 3 item 9).

**Recommendation.**
- Add a draining flag that the gateway sets before `drain(loops)` and the runtime can read.
- At the existing boundaries, check the flag: the top of the round loop (`tool_loop.py:435`), before each tool segment (`:483`), and before a model turn. When it is set, persist `environment.retry = {"not_before": now, "reason_code": "gateway_drained"}` and raise `ToolRetryScheduled`. This is exactly how a Task continuation releases its worker today (`continuation.py:86-90`), and the executor already turns it into `queued` (`executor.py:298-341`). The lease fence and the checkpoint are kept.
- Keep the 25 s cancel as the backstop for a call that does not end.
- Never interrupt a tool already past `before_effect`: let it finish within its own deadline.

**VISION.** Nothing in section 6 changes: the door, the journal and the fence are untouched. The change only reduces how often 6.3 and 6.8 are needed. It fits Amendment 3 item 6 ("MUST NOT change section 6 or any agent behaviour").

**Tests.** Start a Run with a slow read tool, signal stop, and assert:
- the Run is requeued at the boundary with no uncertain marker;
- the next claim continues from the same checkpoint;
- `tests/check_execution_recovery.py` still passes.

### R3. Anthropic caching of the in-Run transcript (Adapt, M)

**What the references do.**
- OpenMausBot keeps the stable half of the system prompt byte-identical and sends volatile context inside the newest user message, under "replaces any earlier copy" (`server/drivers/prompt-split.ts`; OpenMausBot report §3.1).
- Rakazo keeps the sent prefix stable and places per-turn data such as `<current_time>` and recall after it (Rakazo report §2.C.13 and D.19).

**Lonora today.**
- Every `role="system"` message, wherever it sits, is hoisted into the single Anthropic `system` string (`packages/adapters/src/lonora_adapters/models/anthropic.py:20-25`).
- Exactly one cache breakpoint is set, on the first-party policy prefix (`anthropic.py:66-87`, `:84`):
  ```python
  {"type": "text", "text": system[:split], "cache_control": {"type": "ephemeral"}}
  ```
- No breakpoint is placed on the conversation, so a 24-round tool loop (`maximum_tool_rounds` default 24, `apps/api/src/lonora_api/env.py:91`) re-sends its growing transcript uncached on every round.
- `model_turn` inserts runtime-context system blocks per request: the capability inventory at index 1, and the observation catalog and the per-request visual capabilities block at the end (`model_runtime.py:70-93`). For OpenAI-style wires these stay at the end, "after the cached prefix" as the comment intends. For Anthropic they are hoisted into the system string, ahead of every message. The observation catalog is derived from `messages` (`model_runtime.py:80-84`), so it can change between rounds. That would invalidate any message-level cache even if a breakpoint were added.

Usage already records `cached_tokens` (`packages/db/src/lonora_db/usage.py:30`), so the effect is measurable.

**Recommendation.**
1. In the Anthropic adapter, add a second `cache_control` on the last content block of the final message. Anthropic allows a few breakpoints, and the policy one stays.
2. Send the trailing runtime blocks as a labelled user-role context block after that breakpoint, instead of as system text. `ModelMessage.context_origin="runtime_context"` already defines "labelled context data or a runtime marker in the user role" (`adapter-kit/.../types.py:16-19`), so the provenance rule 6.10 is kept.
3. Leave the per-wake system head as it is. Within one Run it is stable; across wakes 5.4 requires a fresh picture anyway.
4. Measure `cached_tokens / input_tokens` per Run before and after, on a recorded 10-round tool loop.

**VISION.** This lowers the cost of the customer's own key (D6, D41) without limiting model use (P1, 12). The trailing block keeps its runtime label (6.10). There is no conflict.

**Risks.** The moved blocks change wording position. Re-run `scripts/agent_eval` to catch behaviour drift.

### R4. Routine overlap (Adopt, S)

**What the references do.**
- Rakazo's `wakeRoutine` advances `nextRunAt` and creates the run in one transaction, coalesces onto a pending tick, skips when the previous tick is still active, and dedupes by `routine:<id>:<scheduled_for>` (Rakazo report §6).
- OpenMausBot has an overlap policy (queue vs skip) and records `missed` rows (OpenMausBot report §9.3).

**Lonora today.**
- `due_query` filters only on enabled, due, agent not paused and one-shot state (`packages/db/src/lonora_db/routines.py:83-94`).
- `enqueue_routine` creates a Run unconditionally (`:141-155`) and then advances `next_run_at`, collapsing missed schedules (`:168-171`).
- Nothing checks for an unfinished Run of the same `routine_id`: a grep for `routine_id` under `lonora_db` finds only `routines.py`.
- The interval can be as short as 60 s (`packages/contracts/src/lonora_contracts/routines.py:11`).
- During a model outage a routine Run backs off for up to 900 s (`WORK` profile, `model_recovery.py:61`). While it is in backoff it is not eligible (`runs.py:258-259`) and does not make its thread "active" (`:287-293`), so the next tick's newer Run is claimed ahead of it (`:316-321`).

The result is a pile of queued routine Runs, all retrying. When the provider recovers they run back to back on the customer's key and each may report the same thing, which goes against 11.5 ("nothing new posts nothing") and 11.6.

**Recommendation.** In `enqueue_routine`, when a Run with `model_metadata.routine_id == row.id` is still unfinished (`queued`, `leased`, `running` or `waiting_input`), do the following:
- advance `next_run_at` without creating a Run;
- record the coalesced tick, for example a counter in the routine's state, so the next Run's wake context can say "N ticks were skipped while the previous run was still working".

This matches the existing "collapse missed schedules" rule (`routines.py:170`). It is not an activity limit (P1): the routine still fires on its schedule once the earlier tick ends.

**Tests.**
- A 60 s routine whose first Run is stuck in backoff: after five minutes exactly one Run exists, with a coalesced count.
- A one-shot routine is unaffected.

### R5. Faster cancel detection (Adapt, S)

**What the references do.**
- Rakazo re-checks the fence and status at most once a second, and a 1 s watchdog timer catches quiet model calls (Rakazo report §2.E.25 and §4).
- OpenMausBot interrupts the engine and revokes the per-turn capabilities at once (OpenMausBot report §10).

**Lonora today.** `cancel_locked` only bumps the fence and settles the stream (`packages/db/src/lonora_db/cancellation.py:36-41`). Nothing signals the worker, which finds out in one of three ways:
- at the next fenced write, such as a streamed delta (`progress.py:16`) or a checkpoint;
- at the next round's `cancellation_checkpoint` (`tool_loop.py:435`);
- at the next lease renewal, `await asyncio.sleep(lease_seconds / 3)` (`executor.py:55`), with `run_lease_seconds` defaulting to 120 (`env.py:90`).

While a reasoning model is thinking before its first token, during a long tool, or during a router backoff sleep (`router.py:515`), there are no fenced writes. The cancelled Run keeps working, and keeps spending the owner's key, for up to 40 s. Run cancel is a live path: it serves the owner's route (`apps/api/src/lonora_api/routes/cancellation.py:16-21`, used by `apps/web/src/hooks/useThreads.ts`), Lonora's `cancel_run` action (`packages/tools/src/lonora_tools/supervision.py:537`) and the morning brief (`trading/morning_brief.py:791`).

**Recommendation.** Next to `keep_lease`, add a watcher that reads `status, lease_fence` of the Run every ~2 s and calls the same `lose()` (`executor.py:107-110`) when the fence moved. With at most `maximum_subagents + 2` concurrent Runs per installation, the load is negligible.

Optional refinement: while a non-read-only call is past `before_effect`, defer `lose()` until that call returns, so a cancel never lands inside an effect. Today the renewal path can already land there; the journal and reconciliation cover it (6.2, 6.3).

**VISION.** This is the owner's cancel of a reply or of work (4.6, 4.7, 7.1.5), not the trading Stop that Amendment 1 removed. There is no conflict.

### R6. Retention and coalescing of transient stream events (Adopt, S)

**What the references do.**
- Rakazo's `finalizeRun` deletes transient events (`thread.progress`, thinking meta) of the run and batches text at 250 ms (Rakazo report §2.F.29 and §8.5).
- OpenMausBot coalesces deltas at 50 ms and keeps progress frames live-only, never logged (OpenMausBot report §12.1).

**Lonora today.**
- Stream text is coalesced for only 25 ms (`agent-runtime/.../stream_publication.py:46`, `await asyncio.sleep(0.025)`).
- Each publication is a transaction that locks the Run row, rewrites `model_metadata` with the cumulative stream and inserts one `ln_events` row per ≤ 1024-character chunk (`progress.py:14-16`, `:62-85`).
- `ln_events` (`db/schema.py:445-470`) is never pruned: no code outside migrations deletes from it (grep over `packages/db/src/lonora_db` and `packages/gateway`).

Every reply therefore leaves hundreds of delta rows forever. These rows go into the database backup (D10), and disk is a hosting plan resource (Amendment 3 item 4, D13).

**Recommendation.**
1. Add a gateway step that deletes `run.delta` and `run.rich_partial` events of Runs in a terminal state, older than about 24 h. Keep `tool.*`, `message.created`, `run.reply_committed` and every non-stream kind. This is safe for clients because:
   - reconnection projects the latest activity from the Run row (`progress.py:28-30`);
   - the final text arrives in `message.created`;
   - deleting rows below the public cursor does not disturb `publish_committed` (`events.py:28-58`).

   Check the web and mobile reducers for any dependence on historical deltas before enabling it.
2. Raise the coalescing window to 50–100 ms. This is a UX trade-off: test first-text latency with the existing `stream_timings`.

### R7. Show inline provider retries (Adapt, S)

**What the reference does.** Each OpenMausBot driver retry emits `turn.retrying {attempt, delayMs, reason}`, which the UI shows as a chip (OpenMausBot report §7.1).

**Lonora today.** The router sleeps between same-candidate retries with no event (`router.py:509-516`, `await self.sleep(wait)`). The next `on_attempt` progress event fires only after the sleep (`:467-468`). Waits honour `Retry-After` up to 20 s (`resilience.py:101`), plus a 1–8 s backoff. For that time the status line shows stale activity. Run-level backoffs are already visible (`executor.py:329-341`, `run.retry_scheduled`).

**Recommendation.** Give the router an optional `on_retry(reason, delay)` callback. `model_turn` turns it into a fenced `run.retrying` progress event, which also feeds the `activity` projection (`progress.py:18-39`). Web and mobile show one plain line in the owner's language, such as "the model provider is busy, retrying", with no codes (17).

### R8. Prompt version on each Run (Adopt, S)

**What the reference does.** Rakazo stamps `promptVersion()` on every run row for release comparison (Rakazo report §2.C.15).

**Lonora today.** The operating manual is verified against `manifest["manual_sha256"]` at load (`agent-runtime/.../skills/system_policy.py:57`). A grep for `manual_sha256`, `prompt_version` and `policy_version` across `packages` finds only that check, so no Run records which manual or bootstrap produced it.

**Recommendation.** When a Run becomes `running` (`executor.py:114-128`), write `model_metadata.prompt_version = {manual_sha256, bootstrap_sha256}`. `scripts/agent_eval` can then compare behaviour across the phase-5 prompt rewrite (5.8.1, 5.8.6).

### O1. Helper Runs as listed conversations (owner decision)

**Lonora today.** A helper of a foreground Run opens a new `purpose="conversation"` thread titled with the task (`collaboration/subagents.py:48-53`). `list_threads` returns every conversation-purpose thread (`db/threads.py:147-152`), so each helper appears in the owner's conversation list. Helpers of background work use hidden work threads (`docs/proactivity.md:116-118`).

**What the reference does.** Rakazo inserts the helper as a separate run, shown as a `subagent` card message inside the parent chat (Rakazo report §5).

**Question for the owner.** P5 limits the outside-conversation surface to "the agent and conversation list". 11.6 forbids "a new chat per routine" but says nothing about helpers. Should helper work appear as a card in the parent conversation, or keep its own listed chat? If it changes, the work is M: a hidden work thread with a card in the parent, on web and mobile.

---

## 3. Already better: where Lonora is ahead

| Area | Lonora (evidence) | OpenMausBot | Rakazo |
|---|---|---|---|
| The loop is Lonora's own | `tool_loop.py:349-676`; P4 honoured | The loop belongs to third-party CLIs; behaviour differs per engine (report §14.2) | The core loop is the third-party Pi library; ~1400 lines compensate for it (report §10) |
| Fenced, durable Runs | `claim_next` with fence++ (`runs.py:239-355`); every progress write fenced (`progress.py:16`) | Turn state in module-level maps in a 15k-line file (report §14.1) | Equal (lease + fence) |
| Checkpoint before effect, honest replay | `before_effect` (`tool_dispatch.py:97-99`); interrupted → `tool_execution_uncertain` (`:83-96`); `close_pending` (`tool_block.py:51-96`); financial reconcile on the same operation (`tool_dispatch.py:56-70`) | Restart policy keyed on outward actions | "A turn cut mid-step repeats its model call and tool call" (report §10) |
| Restart quarantine | `quarantine_run` holds, never fails, a Run with an unresolved financial operation (`runs.py:590-638`); `MAX_RUN_RECOVERIES = 5` (`:29`) | Fails reruns after outward actions | Setup-failure streak only |
| Loop guard | Persisted in the checkpoint; exact-failure, no-progress, identical-call, cycle and identical-effect streaks (`tool_guardrails.py:53-73`) | Repeat detector, interactive notice only | Similar fingerprints (`tool-loop.ts`), no effect streak |
| Limit exit | Checkpointed tool-less final report (`tool_loop.py:231-346`); Task slices (`continuation.py:20-93`) | Cap handoff file + continuation | Tool-call fuse, stop message |
| Model recovery | Typed taxonomy at the adapter boundary; per-reason recovery table (`resilience.py:73-96`); bench by credential/model; learned output cap (`router.py:456-459`, `resilience.py:221-225`); run-level profile by who waits (`model_recovery.py:58-63`) | Regex on error text, four overlapping layers (report §14.3–4) | Comparable; run-level retry weaker (report §10) |
| Compaction | Persisted view, canonical messages never rewritten, deterministic fallback, operational state re-read from the database (`context_engine.py:10-19`) | Side-model summary; no guard on tool-state facts (report §14.7) | Summary path dormant; "retrieval" default (report §10) |
| Steering | Same Run continues; unstarted calls superseded; blocks never split (`tool_loop.py:482-486`); `complete_run` refuses with steering outstanding (`runs.py:425-431`) | Steer or queue; `indeterminate` can lose a message (report §14.8) | Equal; a late message spawns a new run |
| Event log | Durable `ln_events` with a cursor; one `run_id` index (`schema.py:458`); resume from the database (`websocket/events.py:77-91`) | In-memory replay buffer; four ids per run (report §14.5–6) | Equal |
| Subagents | Runs with depth < 2, cap 4, read-only helper scope, idempotent by call id, peer cycle refusal (`subagents.py:23-42`, `peer_messages.py:28-41`); cancel cascades (`db/cancellation.py:56-70`) | Full bots with threads (report §14.9) | Equal |
| End-of-turn check | Structural only, never reads prose (`conversation_gate.py:1-24`) | Text heuristics (`nudgeAnnouncedAction`) | Silent-final nudge |
| Stall bounds | Model read timeout 90 s (`adapters/models/base.py:74`); per-tool dispatch deadline (`tool_dispatch.py:100-101`); watchdog + quarantine (`gateway/watchdog.py`) | 20 min turn stall watchdog | 120 s / 180 s stream timeouts |
| Missed schedules | Collapsed into one wake (`routines.py:170-171`) | Catch-up window, `missed` rows | Stale-wake guard |
| Model-free waiting | Watches evaluated by the gateway without a model (`gateway/service.py:301-304`) | `wait_until` probes | Watch tick |

---

## 4. Considered and skipped

| Idea | Source | Why skipped |
|---|---|---|
| Route short messages to a cheaper "quick model" | OpenMausBot `quick-model-fallback.ts` | **Conflicts with VISION 12.3** (the owner assigns the model). Needs the owner. |
| Per-tree execution, wake and request budgets (`totalExecutions` 300, wake budget 48) | OpenMausBot runtime windows | **Conflicts with P1** (no activity budgets). Lonora's bounds are per-Run technical limits. |
| Third-party loop (Pi), CLI engines, MCP-served harness tools | Both | **Conflicts with P4**. |
| Limit failover between subscription sign-ins | OpenMausBot `limit-failover.ts` | **Conflicts with P8 and 12.2** (API keys only). Lonora's bench + chain covers key-level failover. |
| A pure `admit()` table | OpenMausBot `admission.ts` | Behaviour already covered (`messages.py:708-845`). A refactor only for testability fails CLAUDE.md "Simplicity First". |
| Per-turn capability bearer for out-of-process tools | OpenMausBot | Lonora tools run in-process under the lease. The workspace CLI's callback is a separate topic (7.3). |
| Postgres NOTIFY instead of 0.5 s claim polling | Rakazo | One installation per owner (Amendment 3 item 1). Polling cost is small. Revisit only if VM CPU is measured as a problem. |
| Learn the context window from the overflow error text | Rakazo | Lonora shrinks admission per Run on a provider-proven overflow (`model_recovery.py:166-173`), and unknown models use the policy maximum (`model_windows.py:1-12`). Low value. |
| Drop thinking blocks on a signature mismatch | Rakazo | Lonora sends no thinking or reasoning parameters today (grep of the adapters). Belongs to the models topic. |
| Leader-elected reconciler | Rakazo | One gateway per installation. |
| Model-free precheck before a routine run | Rakazo `tickRoutineWatch` | Condition-based work already uses model-free watches; a routine is a scheduled judgment by design (5.2, 11.5). |

---

## 5. Owner questions

1. **O1**: should helper Runs appear in the conversation list, or as a card in the parent conversation?
2. Optional, only if the owner wants it: a cheap-model route for trivial replies. It would need an explicit change to 12.3. Not recommended.

## 6. Limits of this analysis

- **Not read in full:** `context/compaction.py` (cross-Run), `loop_restore.py`, `tool_batch.py`, `outcome_return.py`, `genui_compile.py`, the client reducers (relevant to R6), and `ExecutionService` (only its contract from VISION 6 was relied on).
- **R1:** the failure is shown by reading the code paths. I did not reproduce it against a live endpoint. Which providers emit empty or repeated ids is not verified here.
- **R3:** the saving is an expectation. Measure it with `cached_tokens` before committing.
