## Conversation dissection, groups D, E, F and G

Code at `9f5b1da`; times UTC (export is UTC+1). [4]-[55] ran on `2477c22`, [56]-[71] on `cd2cc91`, [72]-[81] on `9f5b1da`; all contain PR #42. Policy, `trade.py` and voice code are unchanged since `2477c22`. SCRIPTED = driver-written model turns, real runtime; driver files are under `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts`. `lonora.md` = `packages/agent-runtime/resources/system/lonora.md`; other bare file names follow a full path given earlier in the section.

| Message | Run | What the agent did | Code terms | On main | Evidence |
|---|---|---|---|---|---|
| D [24] «ما أقدر أنفّذ صفقة شراء بدون **حجم الصفقة**» | 00f7b6bc | Read balance, quote, instrument; asked for a size | No default size; `volume` mandatory (`packages/contracts/src/lonora_contracts/trading.py:77-81`); deciding line in an unloaded chapter (`lonora.md:337`) | FAILS | Part 4 #27-#29; `conv_d_delegation.py` 1a |
| D [31] «لا أستطيع فتح 10 صفقات…» | cc8399d7 | No tool call | No limit on trade count (`packages/trading/src/lonora_trading/account_authority.py:262-263`, `:282-286`); model's own refusal | FAILS | Parts 1-2; `conv_d_ten_debug.py`: 9 of 10 buys executed |
| D [33] numbers asked in prose | 1755d8d8 | No tool call; dropped "ten trades" | Card exists (`packages/tools/src/lonora_tools/runtime_control.py:22-32`); use is advice only (`lonora.md:131`) | FAILS | Parts 1-2; `conv_d_delegation.py` 3a, 3b |
| D [35] plan on current position, ends in offer | 94d50998 | Three reads: «الخطة جاهزة على **المركز الحالي فقط**», «إذا تريد، أضع لك **أمر إغلاق مشروط**…»; set nothing | `modify_position` native and granted (`packages/contracts/src/lonora_contracts/trading.py:18-38`); SL, TP null (Part 4 #37) | FAILS | `conv_d_delegation.py` 4a, 4b |
| E [49] «لم أفهم… اكتبها بالعربية» | 26cb3997 | Asked owner to write it | Turkish transcript «ımuz lazım birasta»; STT got no language (`packages/voice/src/lonora_voice/voice_notes.py:55-58`, `:72`; `packages/adapters/src/lonora_adapters/voice/stt.py:26`) | FAILS | Part 3 seq 45; `conv_efg.py` E |
| E [51] Turkish reply | 11f8603e | Replied in Turkish | `latest_owner_message` (`packages/agent-runtime/src/lonora_agent/context/memory.py:131`), `lonora.md:58` | FAILS | Part 3 seq 47, Q6; `conv_efg.py` E |
| F `symbol_not_found`, `broker_account_not_found` [10] | 1ae9a14c | Quoted codes and broker details | Tool-result `code` plus `recovery` (`packages/agent-runtime/src/lonora_agent/environment.py:204-210`); broker details instructed (`packages/tools/src/lonora_tools/account.py:63-64`) | FAILS | Part 4 #15, #17 |
| F `waiting`, `owner_attention`, `routines`, `goals` [59] [65] | f51d1db6, 049af207 | Raw fields | `packages/tools/src/lonora_tools/supervision.py:149-158`, `:220-255`; no filter | FAILS | `conv_efg.py` F |
| F `watch_cancel` [75] [77] | 3fa683e6, e79b4bf2 | Named the tool | In system text (`packages/agent-runtime/resources/constitution/trading-policy.md:7`); filter ignores tool names (`packages/core/src/lonora_core/public_reply.py:42`) | FAILS (observed) | `conv_efg.py` F |
| F raw `**` in [22] ([20]) | 9d557f9e, e7ca6fb6 | Image attachments | Caption drawn with `agent={false}` (`apps/web/src/conversation/Message.tsx:402-409`; `apps/web/src/conversation/Markdown.tsx:277-281`) | FAILS on web | Owner screenshot |
| F `** text**` in [16] [18] [24] [26] [35] [41] [59] [65] | various | Inner-space markers | No server normalisation; bubbles bold them (`apps/web/src/conversation/Markdown.tsx:68`; `apps/mobile/components/markdown.tsx:22`) | PARTLY | `conv_efg_markdown.mjs` |
| F «أغهِقه» [41] | run ~09:51 | Garbled word | Model output; no word check | FAILS | Part 3 seq 38 |
| F option icons [61] [67] | ddae66ad, e343c96a | `wait_for_input` cards | Web: no CSS for `.opt-row` (`apps/web/src/conversation/Cards.tsx:150-171`; `packages/ui-web/src/icons/icon.tsx:5-19`); Expo: `size={18}` (`apps/mobile/components/conversation-question.tsx:88-90`) | FAILS web; UNSURE Expo | Not rendered |
| G [2] «النموذج غير متاح حاليًا» | b1cea9d1, 603d1bb0 | Error card, no reply | `model_not_configured`, family `model` (`packages/core/src/lonora_core/runtime_failure.py:50-51`; `apps/web/src/conversation/Cards.tsx:69-83`) | FAILS | Part 1; `model_not_configured_retry.py` step 1 |
| G [1] / [3] | b1cea9d1 (seq 1), 603d1bb0 (seq 2) | [1] never answered; [3] answered by a retry | A retry answers one message (`packages/db/src/lonora_db/run_retry.py:79-148`) | FAILS | Part 1 run list |

## D. What the full delegation grants and why the agent still asked

**Envelope.** `AccountAuthorityEnvelope` (`packages/contracts/src/lonora_contracts/account_authority.py:107-119`); full delegation is recognised from terms (`:37-49`): mode full, scope account, all ten actions (`:12-26`), no expiry, six caps unset (`:27-34`). It has no size, lot, risk or stop field (SCRIPTED, `conv_d_delegation.py`). Signing also creates the Task «إدارة حساب التداول», told to "choose your own justified direction, lot size, stops, targets and management plan… Do not ask for each order" (`packages/auth/src/lonora_auth/account_authority.py:148-150`); that is the Task's own Run prompt; chat runs never see it (`packages/tools/src/lonora_tools/supervision.py:219-227`).

**No default volume exists; three documents say none is chosen for the owner.** "No hardcoded lot or loss amount is chosen for the owner." (`docs/account-authority.md:127`); "There is no default instrument, currency, volume or stop." (`docs/broker-position-sizing.md:6-7`); "Never default authority, size limits or autonomy." (`packages/agent-runtime/resources/system/lonora.md:23`, always loaded). The only server numbers near a size are the broker `volume_min`/`volume_step` (`packages/contracts/src/lonora_contracts/market.py:15-17`) and `max_trade_risk` (`packages/contracts/src/lonora_contracts/risk_limits.py:25-26`; not set). Brief principle 6 has nothing to read: an owner decision is needed.

**Policy lines.** Chapters load from tool calls already made in the run (`packages/agent-runtime/src/lonora_agent/skills/system_policy.py:134-143`); replayed history carries none, so `trading` is absent until `trade_execute` runs in that run.

- Every run, toward choosing: "Explicit full management lets you choose size, stops and targets without per-order approval or default volume/activity quotas" (`lonora.md:106`). Toward asking: "Ask only for genuinely missing user intent, financial limits or business parameters" (`packages/agent-runtime/resources/constitution/tool-policy.md:3`).
- Unloaded `trading` chapter: "Under active signed full management, choose size, stops and targets from current analysis within broker constraints; do not ask the owner to choose routine trading parameters." (`lonora.md:337`; also in skill `trade-management`, read only via `skill_view`). The `market` chapter adds "Missing economics is unavailable, never a guessed lot size or guaranteed loss ceiling." (`lonora.md:230`).

SCRIPTED: after the three production reads the `trading` line was absent; it appeared only after `trade_execute` (`conv_d_delegation.py` 1a, 1b). No guard touches these replies: stop gates act on Task runs only (`packages/agent-runtime/src/lonora_agent/stop_gates.py:178-181`).

**Volume validator.** `trade_execute buy` without `volume` returns `tool_arguments_invalid` / `volume_required`: nothing sent, no card, no pointer to a size source (`packages/contracts/src/lonora_contracts/trading.py:77-81`; SCRIPTED, 1a).

**Trap: identical trade calls in one run, and a false notice.** Operation id = `stable_id(run_id, "trade:" + request_hash(args))` (`packages/tools/src/lonora_tools/trade.py:635`); an existing id returns the stored receipt without sending (`packages/trading/src/lonora_trading/execution.py:162-168`). SCRIPTED (`conv_d_delegation.py` 2b, 2c): eight identical 0.01 buys gave five `confirmed` results, one `operation_id`, one new position; call 6 `guardrail_blocked` (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:69`); call 7 halted the run, owner text «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.» From the second identical call a notice says "Each call is a separate effect, not a retry" (`tool_guardrails.py:117-121`, `:370-373`), false for `trade_execute` in one run, where it is a replay. `TradeRequest` has no count field. Idempotency is a money-safety rule. It did not cause [31].

**`modify_position` works.** It needs `position_id` and one absolute `stop_loss`/`take_profit` (`trading.py:54-76`, `:92`); the grant covers it (`packages/trading/src/lonora_trading/account_authority.py:314-327` restricts `bounded` mode only). With contract size 100 the plan is TP 4052.819, SL 4049.819 for the 4050.819 entry; SCRIPTED 4b confirmed it, zero cards.

No money-safety rule requires any of the four D replies: "Never silently increase lot size, remove a stop, or change account to make a trade pass." (`lonora.md:338`) stands.

## E. Voice and reply language

**Owner root cause 9: CONFIRMED.** The hint is `OwnerProfileRow.reply_language`, "without one the provider detects it" (`packages/voice/src/lonora_voice/voice_notes.py:55-58`); the adapter omits `language` when empty (`packages/adapters/src/lonora_adapters/voice/stt.py:26`); the voice contract has no language field (`packages/contracts/src/lonora_contracts/domain.py:96-99`); the model is not told it is a transcript (`packages/core/src/lonora_core/message_preview.py:37-48`). `reply_language` is empty in production. SCRIPTED (`conv_efg.py` E): `"language": null`.

**Regression.** `ce92a10` (11-10 07:04 UTC) replaced the constant `LANGUAGE = "ar"` with the profile lookup; it is an ancestor of `2477c22`.

**Turkish reply.** With an empty profile the context says `latest_owner_message` (`packages/agent-runtime/src/lonora_agent/context/memory.py:131`) and the policy says to reply in `reply_language`, else the latest message's language (`lonora.md:58`). The latest message was the Turkish transcript «Bu korkuluklar nasıl hakkında»; no guard checks language.

Dead code: `packages/voice/src/lonora_voice/transcription.py:8-11` passes no language and nothing imports it.

## F. Leaks and display

**The only server reply filter** is `redact_private_reply`: credentials, private paths, UUIDs; "Presentation is owned by the model's instructions, not a keyword veto on replies." (`packages/core/src/lonora_core/public_reply.py:1-5`, `:37-51`, applied at `packages/agent-runtime/src/lonora_agent/model_runtime.py:239-248`). It deliberately ignores codes, tool names and internal states; nothing else on the reply path reads wording. SCRIPTED: a reply with every leaked term kept them all; only a UUID changed.

**Owner root cause 10: PARTLY.** No server normalisation (confirmed). Web bubbles use `mdInline` (`apps/web/src/conversation/Markdown.tsx:68`) and mobile a regex (`apps/mobile/components/markdown.tsx:22`); both bold `** 0.24**` with a misplaced space. The CommonMark renderer (`packages/chat-ui/src/markdown.web.tsx:20-21`) is reached only by generated-UI replies (`apps/web/src/components/visual/RichResponse.tsx:103`); no production reply had `rich_content`. The raw `**` in [22] is the image-caption path (`apps/web/src/conversation/Message.tsx:402-409`): well-formed bold shows raw there too. UNSURE: whether the inner spaces are the model's text or an export artefact.

**Owner root cause 11: web only.** `Icon` is an `<svg viewBox="0 0 24 24">` with no size, "sized by CSS" (`packages/ui-web/src/icons/icon.tsx:5-19`); no stylesheet has `.opt-list` or `.opt-row`; the reference has them (`docs/ui-reference/Lonora-Desktop-37.html:2224-2228`). Expo draws no chevron (`apps/mobile/components/conversation-question.tsx:75-90`).

**Diacritics.** When a redaction fires the whole reply passes `normalized_text`, which drops every `Mn` character (`public_reply.py:29-34`, `:63`); SCRIPTED: «أغهِقه» became «أغهقه».

## G. «النموذج غير متاح»: the real cause and the retry chain

**`model_not_configured`.** No routing existed until 2026-11-11 09:37:25 UTC (Q7). A new database has no `model_routing` row (`packages/db/src/lonora_db/transactions.py:231-239`), so the candidate list is empty and `packages/providers/src/lonora_providers/router.py:210-211` raises. It is not transient (`packages/agent-runtime/src/lonora_agent/model_recovery.py:174-175`): the run fails at once with no assistant message (`packages/db/src/lonora_db/runs.py:452-487`). All five failed runs are this code. The only writer is `PUT /api/settings/models` (`packages/providers/src/lonora_providers/routing_policy.py:13-15`); admission does not check for a model (`packages/db/src/lonora_db/messages.py:516-524`).

**Family mapping and fixed card text.** Every `model_*` code except billing, rate and timeout maps to family `model` (`packages/core/src/lonora_core/runtime_failure.py:39-52`): one title and text per family (`apps/web/src/conversation/Cards.tsx:69-83`): «النموذج غير متاح حاليًا», «تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.» (`apps/web/src/i18n/locales/ar/messages.po:7332`, `:7336`). The code is read only for family `other` (`Cards.tsx:82`). Ten codes share it (`packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:80-99`); here it is untrue.

**The truthful string exists but is unused.** `apps/web/src/lib/user_error.ts:88-89` maps `model_not_configured` to «اربط مزودًا واختر نموذجًا عالميًا في الإعدادات.» (`messages.po:1994-1995`). Code at `efb4911` printed it for failed replies (`apps/web/src/pages/shell/message-cards.tsx` at `efb4911`, lines 21-49); `AgentErrorCard` and `run_retry.py` first appear in `2477c22` (live 11-11 08:41).

**Who created each retry.** Only the card button calls `POST /api/runs/{id}/retry` (`apps/api/src/lonora_api/routes/runs.py:63-77`), the sole caller of `retry_run` (ids recompute from `packages/db/src/lonora_db/run_retry.py:87`). Retries on 11-11: e2bc2eae 08:55 (of b1cea9d1, seq 1) failed; cf008869 08:56 (of 603d1bb0, seq 2) failed; 7b86f6fb 09:05 (of cf008869, seq 2) failed; d5b850bc 09:37:44 (of 7b86f6fb, seq 2) answered «مرحباً. كيف أساعدك؟», 19 s after routing was saved.

**Why [1] never got an answer.** A retry answers one message and keeps its `input_seq` (`run_retry.py:87-90`, `:125-133`). The card of e2bc2eae stayed under seq 1: it is [2] (`Conversation.tsx:991-1004`). Saving routing re-runs nothing: only `queued` runs and expired leases are claimed (`packages/db/src/lonora_db/runs.py:194-202`). SCRIPTED (`model_not_configured_retry.py` steps 5-8): a late press answers at the thread end. UNSURE why the owner did not press it.

**Automatic retry exists only for transient provider failures.** The router walks a candidate chain inside one request; when it is exhausted, transient reasons re-queue the run (`model_recovery.py:59`) and after 3 consecutive failures it fails with the provider's code (`model_recovery.py:187-194`). Everything else, `model_not_configured` included, fails on the first attempt.

## What a server update does

`lonora update` stops gateway and API, sets a maintenance flag (503 for non-GET), backs up, migrates, restarts both (`infra/compose/lonora:703-818`). Trace windows: 43 s each (09:54:14, 10:23:03, 10:37:29 UTC); outage length UNSURE (a window may start after the stop and backup, `infra/compose/lonora:791`, `:816`).

**Survives:** runs and checkpoints (resumed from `execution_state`, `packages/agent-runtime/src/lonora_agent/loop_restore.py:31-65`), question cards (a `waiting_input` run holds no worker, `packages/db/src/lonora_db/runs.py:194-202`), watches, Tasks, settings. **Lost:** the in-progress model turn (repeated), preview chunks, broker connections, container logs. A message sent during the stop gets 503, marked `failed`.

**Run 57dcaeb0:** accepted 09:54:48, leased 09:54:56 by the new Gateway, completed 09:54:59: an 8 s wait (Part 2).

## /super-bot 404s

Nine `GET /api/agents/<id>/super-bot` 404s, 10:50-10:53: no route and no caller on main (`apps/api/src/lonora_api/app.py:153-156`); both existed at `876c96d` (`apps/api/src/lonora_api/routes/device_authority.py:133`). Probably an old cached client (UNSURE).

## Causes the owner did not list (from these notes)

1. The `trading` line that settles [24]/[35] and the Task's lot-size text never reach a chat run (`lonora.md:337`).
2. Identical trade calls replay one operation under a notice calling them separate effects (`tool_guardrails.py:117-121`); nothing holds an open request such as [30].
3. `ce92a10` removed the fixed Arabic STT hint; a redaction strips all Arabic diacritics; image captions render no Markdown.
4. One error sentence for ten codes; a retry answers one message; saving routing re-drives nothing; admission ignores a missing model.

## Open items

- TRACE MUST CONFIRM: `ln_account_authorities.envelope`; run 65e8b682's `trade_execute` result body and journal row; whether Task run 779e4761 sized a trade; which STT model made the transcripts (logs gone); `agent_inspect` arguments in f51d1db6, 049af207; raw `content` of [16], [18], [22], [35], [65]; whether provider keys existed at 16:44 UTC on 11-10; `lease_fence`/`recovery_count` of 57dcaeb0; that d5b850bc's input held both greetings.
- UNSURE: Expo option icons and retry; what the owner saw on 11-10; why the first card was not pressed; watch crossings inside an update window; origin of the 404s; answer-then-trade after a card.
