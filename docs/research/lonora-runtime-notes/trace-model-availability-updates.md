# Model not configured, retries, and server updates

Scope: thread 3c25305d, messages [1] to [4] of the owner's export, the five failed runs, the retry
chain, the three server updates of 2026-11-11, and the `/super-bot` 404s. Repository at main
`9f5b1da`, read-only. All times UTC. `path:line` is relative to the repository root.

Reproduction script: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/model_not_configured_retry.py`
Raw output: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/model_not_configured_retry.out`

## Summary

1. The five failed runs failed because the installation had no model selected at all. The server
   recorded the correct code (`model_not_configured`). The web error card then replaced it with a
   generic "provider could not be reached" text, because the card picks its text from one of five
   "families" and almost every code that starts with `model_` lands in the family `model` (the
   exceptions are the quota, rate-limit and timeout failures; see (a)).
2. A truthful sentence for this exact code already exists in the web catalog
   («اربط مزودًا واختر نموذجًا عالميًا في الإعدادات.»). The web client of the build that served on
   2026-11-10 rendered it for a failed reply (by its code; what the owner had on screen that
   evening is UNSURE, see (a)). The error card introduced in the build that went live at 08:41:30 on 2026-11-11 stopped
   using it for model failures. This is a regression in the client text, not a server fault.
3. Every retry in the chain was a press of «إعادة المحاولة» in the web client. Nothing in the
   server retries a failed conversational run, and nothing re-drives failed runs when a model
   becomes configured.
4. The first greeting's card was never pressed again after its one retry failed. The card was
   still on screen and still worked (it is message [2] of the export). In the reproduction the
   reply that finally comes is written with both greetings in the model's input; for the
   production run d5b850bc this is TRACE BODIES MUST CONFIRM (its model input is not in the trace).
5. An update stops both processes for the better part of a minute (the trace gives three windows
   of 43 seconds; UNSURE whether each window starts at the stop or only after the backup, see (c)).
   Runs, question cards, watches, timers,
   steering and the reply preview are all stored in the database and survive. Run 57dcaeb0 was not
   interrupted: it was accepted by the new API and waited 8 seconds for the new Gateway to start.
6. `GET /api/agents/<id>/super-bot` does not exist on main and no client on main calls it. An
   older client build did.

---

## (a) `model_not_configured` shown as «تعذّر الوصول إلى مزوّد النموذج»

### Where the code is raised

| Site | Condition |
|---|---|
| `packages/core/src/lonora_core/model_routing.py:23-24` | `select_model`: the routing policy has no model for the capability. The router catches this one and continues with `primary = None` (`packages/providers/src/lonora_providers/router.py:163-168`). |
| `packages/providers/src/lonora_providers/router.py:210-211` | `route()`: after joining the run's model, the agent's own choice, the global route, the agent's fallbacks, the global backups and the owner's allowed additions (`router.py:177-184`), the candidate list is empty. |
| `packages/providers/src/lonora_providers/credentials.py:23` | A candidate exists but its provider has no stored key and no `LONORA_<PROVIDER>_API_KEY` in the environment (`credentials.py:14-22`). The environment lookup also reads a `.env` file in the working directory (`credentials.py:20`). The router turns it into `FailureReason.NOT_CONFIGURED` (`router.py:276-280`) and, if no candidate answers, raises the exhausted error at `router.py:344`; `_exhausted` picks `NOT_CONFIGURED` only when every candidate failed for that reason (`router.py:364-367`). Code mapping: `packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:97`. |

On a new database the settings rows `model_routing`, `model_backups` and `model_allowed` do not
exist. `SettingsRepository.get` returns `{}` for a missing row
(`packages/db/src/lonora_db/transactions.py:231-239`) and `RoutingPolicy` defaults to
`unified: None` (`packages/contracts/src/lonora_contracts/model_routing.py:28-30`). So the
candidate list is empty and `router.py:211` fires. (One more way to an empty list, not relevant
here because no agent or run model was chosen: a candidate that the agent or the run chose is
skipped when `agent_route_applies` is false for the capability, `router.py:203-206`.) The
production trace agrees: `model_allowed`
was first written at 09:37:16 and `model_routing` at 09:37:25 on 2026-11-11 (trace Part 1, Q7).
The reproduction produces the same code with no routing row (step 1 of the output). The output
does not print which of the three sites raised; that it is `router.py:211` follows from reading the
code (an empty candidate list raises before any key is looked up), not from the output.

TRACE BODIES MUST CONFIRM: whether a provider key was already stored before 09:37 (the trace has
the settings rows, not the secrets table). It does not change the cause: with no routing,
`router.py:211` fires before any key is looked up.

### How the run fails

- The model turn is called at `packages/agent-runtime/src/lonora_agent/tool_loop.py:505-516`.
  The error is passed to `plan_failure` (`tool_loop.py:517-523`).
- `plan_failure` returns `raise` for anything that is not transient
  (`packages/agent-runtime/src/lonora_agent/model_recovery.py:174-175`). "Not configured" is not
  transient: `packages/providers/src/lonora_providers/resilience.py:96` (`Recovery(0, 0, True, False)`,
  the fourth field is `transient`, `resilience.py:67-68`), and the plain code is not in
  `TRANSIENT_CODES` (`resilience.py:119`, `130-134`). So there is no backoff and no automatic retry.
- The error reaches `execute_run` (`packages/agent-runtime/src/lonora_agent/executor.py:310-312`),
  which calls `record_failure` (`executor.py:76-93`) and then `fail_run`
  (`packages/db/src/lonora_db/runs.py:452-487`). `fail_run` sets `status = "failed"`,
  `error_code = "model_not_configured"`, stores `model_metadata.failure` and emits `run.failed`
  with `{"code": ..., "failure": ...}` (`runs.py:464-487`).
- No assistant message is written. The only thing the owner can see is the client's rendering of
  the failed run.

This matches the trace: each failed run lasted one to two seconds (trace, run lifecycle).

### How the code becomes the owner's notice

`packages/agent-runtime/src/lonora_agent/runtime_notices.py` is not involved. That module holds
notices addressed to the model and the Task attention texts (`runtime_notices.py:1-9`,
`142-169`); its only model-related entry is `model_unavailable` for Tasks held after repeated
provider outages (`runtime_notices.py:163-168`). The owner notice for a failed conversational run
is built entirely in the web client from the run row.

The mapping, step by step:

1. Server, family: `failure_family` returns `"model"` for a code that starts with `model_`
   (`packages/core/src/lonora_core/runtime_failure.py:39-52`, the deciding line is `50-51`),
   unless an earlier branch catches it: a provider reason of billing, rate limit or timeout
   (`runtime_failure.py:31-35`, `41-42`), the code `model_billing_exhausted` (quota, `27`, `44-45`)
   or `model_rate_limited` (rate, `28`, `46-47`). `model_not_configured` raised at `router.py:211`
   is a plain error with no provider reason (`executor.py:83`), so it goes to line `50-51`.
   `fail_run` stores it (`packages/db/src/lonora_db/runs.py:467-470`). The run API returns it as
   `failure` (`runs.py:40-47`). The contract allows only five families: quota, rate, timeout,
   model, other (`packages/contracts/src/lonora_contracts/runs.py:23-31`).
2. Client, family: `failureOf` takes `run.failure.family`; without it, it falls back to a regular
   expression where any code containing `model` or `provider` is the family `model`
   (`apps/web/src/conversation/Cards.tsx:27-39`, line `37`).
3. Client, text: for the family `model` the card uses one fixed title and one fixed text
   (`apps/web/src/conversation/Cards.tsx:69-83`):
   - title, `Cards.tsx:73`: `The model is not available right now` →
     `apps/web/src/i18n/locales/ar/messages.po:7331-7332`: «النموذج غير متاح حاليًا»
   - text, `Cards.tsx:81`: `The model provider could not be reached. Try another model or retry shortly.` →
     `messages.po:7335-7336`: «تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.»
   - buttons, `Cards.tsx:84` and `Cards.tsx:116`: «تغيير النموذج» and «إعادة المحاولة».
4. `run.error_code` is used for the text only in the family `other` (`Cards.tsx:82`). For a
   `model_*` code the card never looks at the code again.

So the card says "the provider could not be reached" for an unreachable provider, a rejected key,
a missing model endpoint, a blocked answer and a missing configuration alike (the codes are listed
at `packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:90-98`). For
`model_not_configured` it is untrue: no provider was contacted.

The reproduction prints the stored payload and the card texts read from the catalog file
(output, step 1):

```
run after execution: {"status": "failed", "error_code": "model_not_configured", "failure": {"family": "model", "retry_after_seconds": null}}
run.failed event payload: {"code": "model_not_configured", "failure": {"family": "model", "retry_after_seconds": null}}
what the web card renders for this run: {"family": "model", "title": "النموذج غير متاح حاليًا", "text": "تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.", "buttons": ["تغيير النموذج", "إعادة المحاولة"]}
```

(The "card renders" line is computed by a transcription of `Cards.tsx:27-39` and `69-84` in the
script, with the strings read from `messages.po`. The card was not rendered in a browser.)

### Does a distinct, truthful notice exist?

Yes, in the web catalog, but the error card does not use it.

- `apps/web/src/lib/user_error.ts:88-89`: `model_not_configured` →
  `Connect a provider and choose a global model in Settings.` →
  `apps/web/src/i18n/locales/ar/messages.po:1994-1995`: «اربط مزودًا واختر نموذجًا عالميًا في الإعدادات.»
- The card's «تغيير النموذج» button does lead to the right place:
  `apps/web/src/conversation/Conversation.tsx:610-613` opens `/app/settings?tab=models`.

It was shown before. In build `efb4911` (serving on 2026-11-10) a failed reply was rendered by
`FailedReplyNotice`, which printed `userError({ code: run.error_code })`
(`git show efb4911:apps/web/src/pages/shell/message-cards.tsx`, lines 21-49, the text at line 44),
and `user_error.ts` already had the same sentence
(`git show efb4911:apps/web/src/lib/user_error.ts`, lines 82-83). `efb4911` and `aa50e8e` have no
`AgentErrorCard` and no retry route (`git grep "could not be reached\|run-retry" efb4911` and
`aa50e8e`: no match). Both first appear in `2477c22`
(`git grep` at `2477c22`: `apps/web/src/conversation/Cards.tsx:81`,
`packages/db/src/lonora_db/run_retry.py:87`), which went live at 08:41:30 on 2026-11-11.

One other place on main still prints the truthful sentence for a failed run:
`apps/web/src/pages/ActivityList.tsx:236` (`userError({ code: run.error_code })`). UNSURE whether
that component is reachable: `grep -rn "ActivityList" apps/web/src` finds no importer outside its
own file.

Consequence for message [2] of the export: the export was taken on 2026-11-11 with the current
client, so it shows the card's text. UNSURE: what the owner actually saw on 2026-11-10 at 16:44;
from the code of `efb4911` the web client would have shown «اربط مزودًا واختر نموذجًا عالميًا في
الإعدادات.» with no button, but which client and which cached build he used that evening is not in
the trace.

Mobile: the catalog has no entry for `model_not_configured`
(`grep -c model_not_configured apps/mobile/lib/i18n.ts` → 0). The thread screen shows a failed
run's code through `errorText` (`apps/mobile/app/thread.tsx:821-849`), which falls back to
`request_failed` for an unknown code (`apps/mobile/lib/session.tsx:174-176`):
«تعذر تنفيذ الطلب. حاول مرة أخرى.» (`apps/mobile/lib/i18n.ts:574`). The mobile catalog does hold
«اضبط توجيه النماذج من الإعدادات العامة في الويب.» under the keys `route_unconfigured` and
`model_route_missing` (`apps/mobile/lib/i18n.ts:587-594`), but no server code emits either key
(`grep -rn "model_route_missing\|route_unconfigured" --include=*.py apps packages` → no match).
`packages/chat-ui` has no error catalog (its sources are markdown, tables and icons only).

### What a fresh install does about model routing

- Nothing is seeded. The only writer of `model_routing` is `save_policy`
  (`packages/providers/src/lonora_providers/routing_policy.py:13-15`), reached only from
  `PUT /api/settings/models` (`apps/api/src/lonora_api/routes/model_router.py:20-25`), which the
  Settings page calls (`apps/web/src/lib/model_routing.ts:13`).
- First-run setup creates the owner and the personal agent, nothing else
  (`apps/api/src/lonora_api/routes/onboarding.py:17-23`,
  `packages/auth/src/lonora_auth/owner_policy.py:13-26`).
- Saving a provider key stores the key only; it does not choose a model
  (`apps/api/src/lonora_api/routes/providers.py:27-35`).
- The installer writes empty optional provider keys into `.env`
  (`infra/compose/install.sh:203-205`). With `--env-from` it may copy the old provider keys and
  the encryption key (`infra/compose/install.sh:29-35`), but it creates a new database, so the
  old settings rows (routing, allowed models) and the encrypted keys stored in the old database
  do not come along (`docs/operations.md:24`).
- Message admission does not check for a model. `POST /threads/{id}/messages` creates a run
  whenever the agent has no active run in the thread (`apps/api/src/lonora_api/routes/messages.py:92-101`,
  `packages/db/src/lonora_db/messages.py:516-524`, `576-593`); with an active run the message is
  attached to that run instead (`messages.py:570-574`).
- `/ready` checks the database and the Gateway heartbeat (`apps/api/src/lonora_api/health.py:22-25`);
  it does not look at model settings.
- Documentation: `README.md:31` says to open the system settings, add provider keys, discover the
  catalog and choose the global routing. The post-install steps in `docs/operations.md:124-129`
  list the backup key, the owner account and host hardening; they do not mention a model.

So a new installation accepts conversation before any model exists, and the first message fails.

---

## (b) The retry chain

### Who created each retry

`retry_run` (`packages/db/src/lonora_db/run_retry.py:79-148`) has one caller: the route
`POST /api/runs/{run_id}/retry` (`apps/api/src/lonora_api/routes/runs.py:63-77`;
`grep -rn "retry_run\b" --include=*.py apps packages` shows only the route and the definition).
The route has one caller in the clients: the error card's button
(`apps/web/src/conversation/Conversation.tsx:602-609`, wired to the card at
`Conversation.tsx:1001`). The mobile app has no call to it
(`grep -rn "/retry" apps/mobile --include=*.ts --include=*.tsx` → no match; its `onRetry` at
`apps/mobile/app/thread.tsx:1031` resends an unsent message, a different thing).

The retry run's id is derived from the failed run's id
(`run_retry.py:87`: `stable_id(row.id, "run-retry")`, a version-5 UUID,
`packages/session/src/lonora_session/idempotency.py:7-8`). In the trace the two original runs
have version-4 ids (`b1cea9d1-4805-4148-…`, `603d1bb0-45b6-45bb-…`) and the four retries have
version-5 ids (`e2bc2eae-9986-5ebf-…`, `cf008869-1911-5dad-…`, `7b86f6fb-8ab4-5745-…`,
`d5b850bc-9200-5540-…`), each with `retry_of` set as `run_retry.py:132` writes it. So all four
were created by this route, which means by a press of «إعادة المحاولة» in the web client (or a
direct call to the same route by the signed-in owner; the trace cannot tell these apart).
None was automatic.

Checked by computation (added by the checker): `uuid5(NAMESPACE_URL, "<failed run id>:run-retry")`
gives exactly the four retry ids of the trace: b1cea9d1-… → `e2bc2eae-9986-5ebf-8997-041aeef63429`,
603d1bb0-… → `cf008869-1911-5dad-ac4a-64300ddc5280`, cf008869-… → `7b86f6fb-8ab4-5745-9a53-da1fc332967d`,
7b86f6fb-… → `d5b850bc-9200-5540-bbbb-87e64e5df348`. No other code derives an id with the nonce
`run-retry` (`grep -rn "run-retry" --include=*.py apps packages` → `run_retry.py:87` only).

| Run | Time (2026-11-11) | Retry of | Message | Result |
|---|---|---|---|---|
| e2bc2eae | 08:55:57 | b1cea9d1 | seq 1 | failed, `model_not_configured` |
| cf008869 | 08:56:00 | 603d1bb0 | seq 2 | failed, `model_not_configured` |
| 7b86f6fb | 09:05:37 | cf008869 | seq 2 | failed, `model_not_configured` |
| d5b850bc | 09:37:44 | 7b86f6fb | seq 2 | completed, «مرحباً. كيف أساعدك؟» |

The first two presses came 14 minutes after build `2477c22` (the first build with the card and the
retry route) went live at 08:41:30. The last came 19 seconds after `model_routing` was saved at
09:37:25.

### How the card and the retry behave (code)

- A new message while the previous run is `failed` starts a new run: only
  `queued`, `leased`, `running` and `waiting_input` runs count as active
  (`packages/db/src/lonora_db/messages.py:521`), otherwise a new run is created
  (`messages.py:576-584`). That is why the second «مرحبا» has its own run (603d1bb0).
- The client shows one card per failed run under the owner message it answered
  (`apps/web/src/lib/failed-replies.ts:4-20`), except runs that another run names as `retry_of`
  (`packages/core/src/run-state.ts:23-32`, `apps/web/src/conversation/Conversation.tsx:596-601`,
  `991-993`).
- One failed run has at most one retry. A second request for the same run returns the existing
  retry run and creates nothing (`run_retry.py:87-90`). After a failed retry the original's card
  is gone and a new card stands for the retry run, under the same message.
- A retry carries the same `input_seq` (`run_retry.py:125-133`), and claiming keeps it
  (`packages/db/src/lonora_db/runs.py:270-277`).

### Why seq 1's chain stopped after one failure

Nothing in the code stopped it. After e2bc2eae failed at 08:55:59, its card stayed under message
[1] with a working retry button. The owner pressed the card under message [3] at 09:05:37 and at
09:37:44, and did not press the one under [1] again. That card is message [2] of the export: it is
placed between [1] and [3], which is where `Conversation.tsx:991-1004` draws the card of an
unretried failed run for seq 1 (e2bc2eae). After 09:37:44 seq 2 had no unretried failed run, so
its card was gone and only the first greeting's card remained.

UNSURE: why the owner did not press it again. The trace records runs, not intentions. Two things
in the code make it likely to be overlooked: the card under an older message scrolls away as the
conversation grows, and both cards carried the same text, which did not say that a setting was
missing.

In effect the greeting was answered once. The reproduction shows that the run that answers seq 2
receives both greetings as conversation input (output, step 6):

```
SCRIPTED model input for that retry (roles and text, system prompt omitted): [{"role": "user", "content": "<lonora_context_data>…"}, {"role": "user", "content": "مرحبا"}, {"role": "user", "content": "مرحبا"}]
```

### Does anything re-drive failed runs once a model is configured?

No.

- A worker claims only `queued` runs, or `leased`/`running` runs whose lease expired
  (`packages/db/src/lonora_db/runs.py:194-202`). `failed` is never eligible.
- Saving the routing writes one settings row and does nothing else
  (`apps/api/src/lonora_api/routes/model_router.py:20-25`,
  `packages/providers/src/lonora_providers/routing_policy.py:13-15`).
- The Gateway's steps are listed at `packages/gateway/src/lonora_gateway/service.py:40-65` and
  `260-285`. The only one that retries failed work is `task_retries`, and it selects Tasks whose
  failure is marked `automatic` (`packages/db/src/lonora_db/task_recovery.py:334-351`). For Tasks,
  `model_not_configured` is in the list that waits for the owner instead
  (`task_recovery.py:34-49`). The conversation runs here are not Task runs.
- The run-level model backoff (`model_recovery.py:155-200`) applies to transient failures only;
  see (a).

### Reproduction (database 8, shared; own agent `audit8 model-not-configured f0b79baf`)

What is real: the API application, the message route, the retry route, the settings route, the
real model router, `execute_run`, the real tool registry. What is SCRIPTED: the model adapter that
answers after routing exists (three fixed replies, each prefixed `SCRIPTED`), and a placeholder
provider key in the process environment. Runs were leased by id instead of by a Gateway worker,
because the database is shared. The `model_routing` row was removed again at the end.

| Step | Action | Result |
|---|---|---|
| 0 | check settings | no `model_routing`, `model_backups`, `model_allowed` rows |
| 1 | send «مرحبا» (seq 1) | run 48aaf443 failed, `model_not_configured`, family `model`; card text as quoted in (a) |
| 2 | send «مرحبا» (seq 2) | run 15661e2c failed the same way; two cards on screen |
| 3 | `POST /runs/48aaf443/retry`, `POST /runs/15661e2c/retry` | HTTP 202 each; new runs c3f10465 (`retry_of` 48aaf443) and 79562c3a (`retry_of` 15661e2c); both fail the same way. A second `POST /runs/48aaf443/retry` returns c3f10465 again, already `failed` |
| 4 | `POST /runs/79562c3a/retry` | run aaf7694d fails the same way |
| 5 | `PUT /settings/models` (unified, openai / gpt-5.4-mini) | all five runs stay `failed`; nothing is queued; both cards unchanged |
| 6 | `POST /runs/aaf7694d/retry` | run d6622ee6 completes; reply stored as seq 3; seq 2's card is gone, seq 1's card remains |
| 7 | send «مين انت» (seq 4) | answered (seq 5); the model input contains both greetings and the first reply |
| 8 | `POST /runs/c3f10465/retry` (the first greeting's card) | run c7b8a9f4 completes; its reply is stored at the end of the thread (seq 6), not next to message 1 |

Steps 1 to 6 reproduce the production chain exactly: two failed originals, one retry each, a
second and third retry for seq 2 only, an answer for seq 2 only, and one card left under the first
greeting. Step 8 shows that the remaining card would have produced an answer at any time after
09:37:25, placed at the bottom of the conversation.

---

## (c) What a server update does

### The sequence

`lonora update` (`infra/compose/lonora:703-818`):

1. `compose stop gateway api`, confirm both are down, then turn the maintenance flag on
   (`infra/compose/lonora:146-155`, called at `773`). While the flag exists the proxy answers every
   request that is not GET, HEAD or OPTIONS with 503 and
   `{"error":"maintenance","message":"يجري التحديث، حاول بعد دقائق. An update is in progress; try again in a few minutes."}`
   (`infra/compose/Caddyfile.prod:15-28`).
2. Backup, install the new deployment files, pin the image, run migrations as their own step
   (`infra/compose/lonora:779-798`; the API container does not migrate on start in production,
   `infra/compose/docker-compose.prod.yml:41`, `entrypoint.sh:7-8`).
3. Start the database, API and proxy and wait for `/health`; the Gateway stays stopped
   (`infra/compose/lonora:803-807`).
4. Turn maintenance off, then start the Gateway and wait for `/ready`
   (`infra/compose/lonora:808-814`). The Gateway container starts only after the API is healthy
   (`docker-compose.prod.yml:76-77`).

Between steps 4's two halves the API accepts messages while no worker exists yet. Both services
are separate processes from one image (`entrypoint.sh:4-10`; `pyproject.toml:17-18`). Runs are
executed only by the Gateway (`packages/gateway/src/lonora_gateway/service.py:108-142`,
`packages/gateway/src/lonora_gateway/run_dispatch.py:31-93`); the API only writes rows.

In the trace each of the three windows lasted 43 seconds (09:54:14 to 09:54:57, 10:23:03 to
10:23:46, 10:37:29 to 10:38:12; trace Part 1, "Builds over these runs").

UNSURE (added by the checker): what the two ends of a window are. The trace does not say where the
times come from. The update script writes exactly two time-stamped lines per update to
`history.log`: one after the services are stopped and the backup is finished
(`infra/compose/lonora:791`, after `773` and `781`) and one after `/ready` passed (`lonora:816`).
If the windows were read from that file, each one starts after the stop and the backup, and the
real time without a Gateway is longer than 43 seconds by the duration of the stop and the backup.
What the trace does bound for the first update: a run completed on the old Gateway at 09:53:39 and
the new Gateway leased a run at 09:54:56, so the Gateway was away for at most 77 seconds. The end
of the window agrees with the script: the lease at 09:54:56 comes one second before 09:54:57,
which fits "`/ready` passed" (`lonora:814-816`).

### A run in flight

Gateway shutdown (`packages/gateway/src/lonora_gateway/service.py:311-325`):

- SIGTERM sets the stop flag (`apps/worker/src/lonora_worker/signals.py:6-9`,
  `service.py:327-328`). Workers stop claiming new runs (`service.py:111`), but a run already
  executing continues.
- `drain` waits up to 25 seconds for the worker tasks, then cancels them
  (`packages/gateway/src/lonora_gateway/shutdown.py:8-14`). The container is given 40 seconds
  before it is killed (`docker-compose.prod.yml:78`).
- A cancelled run is not failed: the cancellation is re-raised unless the lease was lost
  (`packages/agent-runtime/src/lonora_agent/executor.py:307-309`), so the row stays `running`.
- `release_leases` then puts every run this process still holds back to `queued`, keeps the fence
  and emits `run.queued` with `reason_code: "gateway_drained"`
  (`packages/db/src/lonora_db/runs.py:490-526`, called at `service.py:320`).
- If the process is killed before that, the lease simply expires (default 120 seconds,
  `apps/api/src/lonora_api/env.py:96`) and the next worker claims the run as a recovery
  (`runs.py:196-201`, `266-269`, event `run.recovered` at `runs.py:287`). After five consecutive
  recoveries the run is failed with `run_recovery_limit` (`runs.py:21`, `547-558`).

The new Gateway resumes from the run's stored checkpoint, not from the beginning:
`restore_checkpoint` rebuilds the transcript and the pending tool calls from `execution_state`
(`packages/agent-runtime/src/lonora_agent/loop_restore.py:31-65`,
`packages/agent-runtime/src/lonora_agent/recovery.py:7-13`). A tool call that had started but has
no stored result is not blindly repeated: a stored result is reused
(`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:42-54`); a call that is neither
read-only nor safe to replay returns `tool_execution_uncertain` to the model
(`tool_dispatch.py:82-95`); a financial call re-inspects the same recorded operation instead of
sending a new one (`tool_dispatch.py:43-52`, `55-69`). What is lost is the model turn that was in
progress (its text is produced again) and its reply preview, which belongs to the old lease
(`packages/db/src/lonora_db/streaming.py:41-53`).

Run 57dcaeb0 in the trace: it did not span the old Gateway. The owner's message was accepted at
09:54:48, which is inside the update window, so the new API was already up and maintenance was
already off (step 4). The run was `queued` until the new Gateway claimed it at 09:54:56 and
finished at 09:54:59 (trace, run lifecycle). The 8 seconds are the Gateway's start-up; the run
itself took 3 seconds. This reading does not depend on what the start of the window means: a POST
is refused while the maintenance flag exists (`Caddyfile.prod:17-28`), and the old API cannot have
taken it, because the stop, backup, migration and both starts would then have to fit into the 8
seconds before the lease. UNSURE: whether 09:54:48 was the owner's first attempt to send «طيب»;
an earlier attempt refused with 503 leaves no row in the database. No other run was open during any of the three windows (trace run list:
the run before the first window ended at 09:53:39, and there is none between 10:00:21 and 10:53:35).
The trace already supports a single claim: Part 2 lists one `queued` and one `leased` for this run
("leased only at 09:54:56") and states that the thread has no `recovered` event at all.
TRACE BODIES MUST CONFIRM only the stored numbers (`lease_fence` 1, `recovery_count` 0); the
digest does not print them.

A message sent during steps 1 to 3 is refused with the 503 above. The web client treats a 503
without a Lonora code as "API unavailable" (`apps/web/src/lib/api.ts:92-97`) and counts it as an
answer from the server, not as "never arrived" (`apps/web/src/lib/outgoing-messages.ts:9-20`).
The send path then marks the message `failed` in the outbox and does not resend it by itself; only
a message that got no answer from the API (no network, or a bare 502/504 from the proxy while the
API container is down and the flag is not set) is kept as `queued` and flushed later
(`apps/web/src/hooks/useThreads.ts:224-229`). Three such unnamed 503s within 30 seconds switch the
whole shell to its maintenance overlay (`apps/web/src/shell/Shell.tsx:512-518`, `934`).
UNSURE: the exact look of a `failed` outgoing message and of the overlay; neither was rendered in a
browser here.

### A pending `wait_for_input` card

It is database state. When a run asks a question, the question is stored in the run's
`execution_state.input_requests`, the run becomes `waiting_input` and its lease is cleared
(`packages/agent-runtime/src/lonora_agent/executor.py:192-212`, `245-246`). A waiting run holds
no worker and is not eligible for claiming (`packages/db/src/lonora_db/runs.py:194-202`), so a
restart does not touch it. The owner's answer is an ordinary message that puts the run back to
`queued` (`packages/db/src/lonora_db/messages.py:571-573`). An answer sent while maintenance is on
gets the 503. In this conversation both cards were asked and answered between updates
(09:56:33 to 09:56:46 and 09:59:28 to 09:59:45), so no card was pending during an update.

### Watches and timers

All are rows evaluated by Gateway steps on an interval (`service.py:40-65`): watches every 2
seconds by `check_watches` (`service.py:222-223`,
`packages/gateway/src/lonora_gateway/wake_dispatch.py:6-7`), routines, Task waits and Task retries
likewise. A watch's schedule and last observed value live in its row
(`packages/market/src/lonora_market/watchers.py:389`, `577-589`). During the 43 seconds nothing is
evaluated; afterwards the new Gateway picks up whatever is due (`watchers.py:407-412`). The trace
shows watches 1 to 3 still being checked at 12:29, after all three updates (trace Part 1, Q4).
UNSURE: whether a price that crossed a level and came back entirely inside a window is noticed; I
did not read the crossing logic.

### State held only in memory (lost on every update)

| State | Where | Effect of losing it |
|---|---|---|
| Per-owner service objects in the Gateway and in the API | `packages/gateway/src/lonora_gateway/service.py:101`, `apps/api/src/lonora_api/runtime.py:14` | rebuilt on first use (`service.py:144-157`, `runtime.py:20-41`) |
| Broker connections | `packages/adapters/src/lonora_adapters/brokers/base.py:23` | reconnected on first use; the first broker call after an update is slower |
| Live quote and candle stream tasks, their versions and last-event times | `packages/market/src/lonora_market/runtime.py:51-56` | restarted by the `market` step (`service.py:205-206`) |
| Market data cache | `packages/market/src/lonora_market/cache.py:9` | first reads go to the broker |
| Model provider health: which models or keys are temporarily benched, learned output caps | `packages/providers/src/lonora_providers/resilience.py:162-166`, `packages/providers/src/lonora_providers/router.py:139` | a benched model is tried again at once |
| Reply-preview chunks not yet written | `packages/agent-runtime/src/lonora_agent/stream_publication.py:13-21` | part of a preview in progress; the stored preview is in the run row (`packages/db/src/lonora_db/streaming.py:12-21`) |
| The transcript of the round in progress since the last checkpoint | local variables of the loop; checkpoint at `packages/db/src/lonora_db/runs.py:330-333` | that model turn is repeated (see "A run in flight") |
| Voice session tasks | `packages/gateway/src/lonora_gateway/service.py:97` | a live voice call ends (`service.py:321`) |
| Step liveness records and watchdog episodes | `packages/gateway/src/lonora_gateway/liveness.py:73`, `packages/gateway/src/lonora_gateway/watchdog.py:80` | rebuilt; diagnostic only |
| Sign-in rate-limit counters | `apps/api/src/lonora_api/middleware/rate_limit.py:29` | reset |
| Gateway process identity (lease owner name) | `packages/gateway/src/lonora_gateway/process_identity.py:5-6` | new identity; old leases are released or expire |
| Cached policy texts and token encodings | `packages/agent-runtime/src/lonora_agent/skills/system_policy.py:36`, `apps/worker/src/lonora_worker/main.py:17-20` | reloaded at start |
| Container logs | (container is recreated) | lost, as the timeline note records |

Not in memory, so not lost: runs and their checkpoints, question cards, the owner's mid-run
messages ("steering": rows consumed at `packages/agent-runtime/src/lonora_agent/steering.py:20-51`),
the reply preview, events, watches, Tasks, routines, sessions and settings. I found no
per-thread state held in memory: nothing in the runtime, Gateway or API keeps a dictionary keyed
by thread (search for instance and module level containers across `packages/*/src` and
`apps/*/src`; the hits are the ones in the table).

### Client connections

- The web client holds one event stream (`apps/web/src/lib/events.ts:41-44`). When the API stops,
  the stream errors and the client reconnects with a growing delay of 0.5 to 10 seconds
  (`events.ts:47-54`, `83`), sending the last event number it saw (`events.ts:42`).
- Events are rows read from the database (`packages/bus/src/lonora_bus/durable_events.py:10-27`,
  `apps/api/src/lonora_api/routes/events.py:47-59`), and the server resumes from the client's
  cursor or `Last-Event-ID` (`events.py:34-44`, `101-111`). Events written while the client was
  disconnected are delivered after reconnection; none are lost.
- The stream is a GET, so the proxy does not block it during maintenance
  (`Caddyfile.prod:22`, `29-34`); it fails only while the API container itself is down.
- The page shell is served with `Cache-Control: no-store` (`apps/api/src/lonora_api/app.py:163-168`),
  so a reload after an update loads the new client. A tab that stays open keeps running the old
  client code until it is reloaded. The shell does tell the owner: it compares the served build id
  (`GET /api/version`, `apps/api/src/lonora_api/routes/version.py:16-30`) with its own on the event
  stream's ready frame and shows «يتوفر إصدار جديد» (`apps/web/src/i18n/locales/ar/messages.po:294-295`)
  with an Update button that reloads
  (`apps/web/src/shell/UpdateBar.tsx:7-29`, `43`; mounted at `apps/web/src/shell/Shell.tsx:932`).
  The owner can dismiss it and keep the old client.

Net effect on this conversation, consistent with the lead's point 11: one message waited 8
seconds for the new Gateway. Nothing else in the trace is attributable to the updates.

---

## (d) The nine `GET /api/agents/<id>/super-bot` 404s (10:50 to 10:53)

- The API on main has no such route. The routers under `/agents` are in
  `apps/api/src/lonora_api/routes/agents.py:24`, `agent_delivery.py:11`, `agent_models.py:27`,
  `agent_permissions.py:10`, `agent_state.py:8`, `knowledge.py:16`, `performance.py:11`; none
  defines `super-bot` (`grep -rn "super-bot" apps` → no match). An unknown path under `/api/`
  is answered with `endpoint_not_found`, 404 (`apps/api/src/lonora_api/app.py:153-156`).
- No client on main calls it: `grep -rn "super-bot\|super_bot\|superBot" apps packages/chat-ui packages/core`
  finds only two attention labels (`apps/web/src/components/ai/AttentionInbox.tsx:28-29`,
  `apps/mobile/components/attention-inbox.tsx:32-33`), no request.
- The route and its callers existed in an older build. At commit `876c96d` (2026-10-29):
  server `apps/api/src/lonora_api/routes/device_authority.py:133`
  (`@router.get("/agents/{agent_id}/super-bot")`); mobile
  `apps/mobile/components/super-bot-cards.tsx:42`; web
  `apps/web/src/components/trading/SuperBotCards.tsx:23` and `43`
  (all read with `git grep … 876c96d`). They are gone in `efb4911` and in main. The table was
  retired by migration `packages/db/migrations/versions/0040_retire_super_bot_requests.py`.
- So the caller was a client older than the server: most plausibly an installed mobile app or a
  browser tab still running an old bundle. UNSURE which; the request log has no client version in
  the lines quoted. The repository's history here is shallow, so I could not name the commit that
  removed the route.
- The 404s are harmless to the server. They fall in the same minutes as the Task being cancelled
  at 10:51:04 (trace Part 3 closing note: 404s from 10:50:56 to 10:53:20).
  UNSURE: that the two are connected, and that an older client did the cancelling; the trace only
  says the cancellation is "not in this thread (probably from the UI)". Consistent with an old
  client, but not proof: the site was switched from an older installation to this one at
  2026-11-10 16:05 (timeline note), so clients installed or opened before that date were built for
  a different server version.

---

## Open points

- TRACE BODIES MUST CONFIRM: whether a provider key existed before 09:37 on 2026-11-11.
- TRACE BODIES MUST CONFIRM: the stored `lease_fence` and `recovery_count` of run 57dcaeb0 (the
  events in trace Part 2 already show a single lease and no recovery).
- TRACE BODIES MUST CONFIRM: that the model input of production run d5b850bc held both greetings.
- UNSURE: what the start of each 43-second window marks (the stop, or the end of the backup).
- UNSURE: what the owner saw on screen on 2026-11-10 (client build in use that evening).
- UNSURE: why the first greeting's card was not pressed again.
- UNSURE: the on-screen look of a message refused with 503 during maintenance (the code marks it
  failed and does not resend it).
- UNSURE: watch crossings that begin and end inside an update window.
- Not examined: Task run 779e4761 (another thread), which was waiting on a watch across the
  updates; the trace has no lifecycle for it.

---

## Verification log

Independent check of this file against the repository at `9f5b1da` (read-only; `git status --short`
empty before and after) and against `production-trace.md`. The file as it stood before the check is
kept at `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/trace-model-availability-updates.before-check.md`.

### Citations opened

- Every `path:line` in sections (a) to (d) was opened at main, about 190 line references in roughly 80 distinct
  files, plus the old revisions `efb4911`, `aa50e8e`, `2477c22` and `876c96d` with `git show` and
  `git grep`. All point at the code they are said to point at, except the corrections below.
- Verbatim strings confirmed in their files: the card title and text, both button labels
  (`messages.po:1480-1481`, `5932-5933`, `7330-7336`), the truthful sentence (`messages.po:1994-1995`,
  and `1689-1690` at `efb4911`), the mobile strings (`apps/mobile/lib/i18n.ts:574`, `587-594`), the
  maintenance body (`infra/compose/Caddyfile.prod:27`).
- Reproduction rerun on database 8: `scripts/model_not_configured_retry.py` →
  `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/model_not_configured_retry.check.out`
  (stderr empty, exit 0). Identical to the stored output once the random run, agent and thread ids
  are masked. The table of steps 0 to 8 matches the output line by line.
- Absence claims rechecked with a second, different search each: no other caller of `retry_run`
  (whole tree, tests included); no other client call to `/retry` (web, mobile, shared packages);
  no `model_not_configured` text in any TypeScript file except `apps/web/src/lib/user_error.ts:88`;
  no writer of the `model_routing` row except `routing_policy.py:15` (searched `SettingsRepository().put`,
  migrations, `infra`, `scripts`); no `super-bot` request in any client on main; no code path that
  moves a `failed` conversational run back to `queued` (all nine assignments of `"queued"` to a run
  were read: they start from `waiting_input`, a leased run, or a Task).
- Trace consistency: run ids, times, `retry_of` links, the 14-minute and 19-second gaps, the three
  43-second windows, the two question-card intervals and the watch timestamps all agree with
  `production-trace.md` Parts 1 to 3.

### Corrected

1. Summary 1 and (a) step 1 said every `model_*` code falls in the family `model` and called the
   choice "four-way". There are five families, and `model_billing_exhausted`, `model_rate_limited`
   and any failure whose provider reason is billing, rate limit or timeout are sent elsewhere
   first (`packages/core/src/lonora_core/runtime_failure.py:27-35`, `41-49`). The conclusion for
   `model_not_configured` is unchanged.
2. "raises it at `router.py:364-367`": those lines choose the error; the raise is at
   `router.py:344`. Added that the key lookup also reads `.env` (`credentials.py:20`).
3. "`/ready` checks the Gateway heartbeat only": it checks the database too (`health.py:22-25`).
4. "`POST …/messages` always creates a run": only when the agent has no active run in the thread
   (`packages/db/src/lonora_db/messages.py:516-524`, `570-574`).

### Downgraded

1. "An update stops both processes for about 43 seconds" → UNSURE. The trace does not define the
   ends of its windows, and the script's own log lines (`infra/compose/lonora:791`, `816`) would
   give a window that starts after the stop and the backup. Bound from the trace: at most 77
   seconds without a Gateway in the first update.
2. "The build that served on 2026-11-10 showed it" (summary 2) → hedged to "its web client code
   renders it"; the body already marked the owner's actual screen as UNSURE.
3. "The reply that finally came was written with both greetings in the model's context" (summary 4)
   → shown by the reproduction only; marked TRACE BODIES MUST CONFIRM for production run d5b850bc.
4. "which suggests the owner had a second, older client open at that moment" in (d) → UNSURE; the
   trace gives a coincidence in time and nothing else.
5. "The reproduction hits the same site" → the output shows the code, not the raise site; the site
   follows from reading the router.

### Upgraded or resolved

1. Run 57dcaeb0, single claim: trace Part 2 already shows one lease and no `recovered` event; only
   the stored counters remain for the bodies.
2. Client behaviour on the maintenance 503: resolved from code (message marked failed, not resent;
   overlay after three 503s in 30 seconds); only the on-screen look stays UNSURE.

### Added

1. The four retry ids of the trace recomputed from the failed runs' ids with the route's own
   formula; all four match. This proves the retry route created them.
2. A second way to an empty candidate list in the router (`router.py:203-206`).
3. `apps/web/src/pages/ActivityList.tsx:236` still prints the truthful sentence, with no importer
   found.
4. The web shell's "new version" bar after an update (`UpdateBar.tsx`, `routes/version.py`).
5. Why the reading of run 57dcaeb0 holds whichever way the window is defined, and the open question
   of an earlier refused send.

### Refuted

None of the six summary findings was refuted. No guard-pass claim appears in this file (the reply
guards are covered in `trace-guards.md`).
