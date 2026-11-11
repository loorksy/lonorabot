# Gap 1: the live voice-call path

Repository /home/user/lonorabot at HEAD 9f5b1da. Scope: `packages/voice/src/lonora_voice/` (realtime.py, handoff.py, context.py, sessions.py), the tests under `tests/voice/` and `tests/check_voice_*.py`. All paths are relative to the repo root.

## 0. Summary

1. A live call does not have its own brain. The Live speech model only talks; every piece of work is delegated to the same text runtime in the same thread (`packages/voice/src/lonora_voice/sessions.py:159` `"delegation": {"type": "client"}`; the gateway turns each delegation into an ordinary chat message and run, `packages/voice/src/lonora_voice/realtime.py:291-296`). So every text-chat failure of the production conversation (symbol_not_found, broker_account_not_found, "if you want, I can search") also happens inside a call, and the call adds its own ways to fail.
2. The gateway hands the outcome of the run to the Live model as text, with no cleaning. A completed run's reply goes through unchanged (`realtime.py:439-443`), Markdown markers, backticks and internal codes included (journey V1). A failed, cancelled or taken-over run is reduced to the literal string `"Backend status: " + run.status + ". " + run.error_code` (`realtime.py:461-464`), for example `Backend status: failed. model_not_configured` (V2). The apps never show that: they map the failure to a family and show owner-language text (`apps/web/src/conversation/Cards.tsx:25-38`, `apps/mobile/lib/i18n.ts:616`).
3. The backend run does not know its answer will be heard. The 31-line "Voice behavior" policy block (`packages/agent-runtime/resources/system/lonora.md:177-207`, markers included) is attached to the tools `owner_notify`, `owner_attention_list`, `owner_call_request` (`packages/agent-runtime/resources/system/manifest.json:132-134`), not to voice-origin runs. A voice-origin run only gets a 5-sentence `<voice_observation>` block about provisional transcripts (`packages/agent-runtime/src/lonora_agent/context/builder.py:137-144`). Reproduced in V1: the run's system prompt has `<voice_observation>` and does not contain "Voice behavior".
4. Every fixed sentence the gateway itself produces is English: the handoff failure (`realtime.py:41-44`), "The agent is paused or unavailable. No work was started." (`:424`), "The backend finished; no additional result was returned." (`:442`), "Ask the user for the information the backend still needs." (`:459`), "The full backend result is available in the chat transcript." (`:52`). Whether the Live model translates them for an Arabic speaker is not observable here (the Live provider is not run): UNSURE. The setup instruction asks it to "Reply in the user's language" (`sessions.py:24-25`).
5. Two outcomes here exist FOR the money-safety rules and are labelled "needed for safety": `APPROVAL_CARD` (`realtime.py:34-39`) and the refusal to start work from an incomplete transcript (ADR 0001 line 19). Everything else in the voice outcome table (section 3) is not a safety rule.
6. No production call is in evidence. The production conversation has two voice NOTES (seq 45 and 47, `production-trace.md` Part 3) and no live call. All journeys below are reproductions of the code path, not observations of production.

## 1. What is scripted and what is real

REAL in every journey: the API app, PostgreSQL (database `audit_j7_test`), message admission (`send_message`, called by the voice code), the context builder, the executor and tool loop, the tool registry, the fake-SDK MetaApiBroker from `j1_lib.py` (V1 only), and the repository's own `RealtimeVoiceSession.update`, `.delegate`, `.tick` (`realtime.py:78`, `:182`, `:362`).

SCRIPTED (labelled in the driver and below): the Live provider's transcript and delegation events (the "speech"), the model turns of the backend run, the websocket (a recorder that stores every command the gateway would send to the Live provider), and the provider failure in V2.

NOT RUN: the Live provider itself. What it finally says aloud after receiving the gateway's text is not known. The evidence in each journey is the literal `session.commentary.append` command the real `tick()` sent.

Each journey uses a uniquely named non-personal agent and its own thread (`fresh_harness` in the driver), because database 7 is shared and the Personal Agent's single thread holds another agent's history. The driver reuses the owner already on the database (`ln_owners`), else creates `gap1-voice@example.com`.

Driver: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/gap1_voice.py`. Rerun any journey (V1 to V8):

```
cd /home/user/lonorabot && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 7 && .venv/bin/python /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/gap1_voice.py V1
```

Raw outputs: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/GAP1-V1.txt` ... `GAP1-V8.txt`, `GAP1-V7b-text-chunks.txt`, `GAP1-existing-checks.txt`.

## 2. How a call works (code reading, each step confirmed by a journey)

- Call setup sends the Live provider one configuration: `{"model", "instructions", "delegation": {"type": "client"}, "input": seed, "store": False}` (`sessions.py:155-163`). There is no language or transcription-language field in it.
- The call's instructions are `VOICE_INSTRUCTIONS` (`sessions.py:23-35`) plus the voice_surface policy, binding context, the agent/owner context JSON and a closing authority line (`packages/voice/src/lonora_voice/context.py:196-201`). `VOICE_INSTRUCTIONS` says "Delegate all trading operations, portfolio and market lookups ... to the existing backend agent" and "Speak verified backend results".
- The Live provider emits transcript deltas and a "delegation" event. The gateway collects the words of that window (`realtime.py:85-125`, `:126-152`), waits 1.2 seconds of stability (`handoff.py:14`, `realtime.py:239`), and submits the text as an owner chat message with `send_message` (`realtime.py:291-296`). The run is a normal run on the normal agent and thread.
- Every 0.35 s (`realtime.py:530`) `tick()` looks at the delegation's runs (`realtime.py:386-388`). When all runs are in a final state (`:429-434`) it builds a string per run (`:435-464`), cuts it into chunks under 480 bytes (`:47-60`) and sends each as `session.commentary.append` (`:472-494`).

## 3. Outcome table: every owner-facing failure string made by the voice gateway

Classes: RECOVERABLE-NOT-LED (the agent could continue and does not), OWNER-NEEDED (a real owner decision/action), DEAD-END, BUG, LEAK (internal code or markup reaches the owner). "Needed for safety" marks rules that must stay.

| # | Where | Text the gateway sends | Class | Journey |
|---|---|---|---|---|
| F1 | `realtime.py:41-44`, used `:245` | "I couldn't pass that voice turn to Lonora, so I haven't started new work. You can continue in this call or send a message in the chat; any ongoing work is preserved." | Not starting work: needed for safety (ADR 0001:19; asserted by `tests/voice/test_live.py:426-427`). Wording and no retry: RECOVERABLE-NOT-LED (the gateway drops this window for good, `realtime.py:247`, and the owner must say it again). English only. | V4 |
| F2 | `realtime.py:419-428` | "The agent is paused or unavailable. No work was started." | OWNER-NEEDED (the owner paused the agent; `messages.py:514-515` skips paused agents). The message is already in the chat, with no run. | V5 |
| F3 | `realtime.py:461-464` | `"Backend status: " + run.status + ". " + (run.error_code or "")` | LEAK and DEAD-END for `failed` (code spoken, no retry, no next step). For `cancelled`: only the wording is poor (English status word, empty tail); the owner pressed stop, so it is not a dead end. For `waiting_takeover`: OWNER-NEEDED but not explained. | V2, V7 |
| F4 | `realtime.py:444-460` | the question text of the latest assistant message; if none, "Ask the user for the information the backend still needs." | Question: OWNER-NEEDED, but the choices of the card are not read out (V3). Fallback: BUG (an instruction to the speech model is used as the content; not reached by a natural path I could find, see V7). | V3, V7 |
| F5 | `realtime.py:439-443` | `run.result`, else "The backend finished; no additional result was returned." | Verbatim result: carries every text-path failure and all markup (LEAK, V1). Empty result: DEAD-END. | V1, V7 |
| F6 | `realtime.py:51-52` | result cut at 2400 characters, then "\nThe full backend result is available in the chat transcript." | BUG (cut in the middle of a sentence, English tail, no summary). | V7 |
| F7 | `realtime.py:34-39`, used `:270` and `:415` | the approval-card instruction | Needed for safety (money moves only through the approval card; speech is not approval). | V6 |
| F8 | `realtime.py:285-290` | "Updated voice transcript for the preceding request (supersedes that observation):\n" + text, stored as the OWNER's chat message | LEAK of an English technical frame into the owner's own bubble. Needed for safety to keep a revision explicit (`realtime.py:283-284`); the English wording is not. | V8 |
| F9 | `realtime.py:166-175`, `sessions.py:151,201-203,212` | call-level codes `voice_connection_failed`, `voice_call_already_active`, `voice_backend_unavailable` | Not spoken by the gateway. Translation is uneven: web translates `voice_backend_unavailable` and `voice_connection_failed` (`apps/web/src/lib/user_error.ts:136-140`) but has no case for `voice_call_already_active`, which falls to the generic default `The request could not be completed. Try again.` (`user_error.ts:227-228`); mobile translates only `voice_connection_failed` (`apps/mobile/lib/i18n.ts:396-399`) and a search of `apps` and `packages` finds no mobile entry for the other two. Small defect: a second call attempt gets a generic message with no reason (UNSURE whether mobile has another generic fallback; not read). | none |

Per-family count of failure outcomes the voice gateway produces itself (F1 to F8): RECOVERABLE-NOT-LED 1 (F1 wording/retry), OWNER-NEEDED 3 (F2, F4 question, F4 takeover half of F3), DEAD-END 2 (F3 failed, F5 empty; the F5 empty case was only forced, see V7), BUG 2 (F4 fallback, F6), LEAK 3 (F3 code, F5 markup, F8 frame), needed for safety 3 (F1 non-start, F7, F8 explicitness). Several rows have two classes, so the counts add up to more than 8.

## 4. Journeys

### V1. «شو وضع الذهب» in a call on the XAUUSDm account

Owner request (spoken): «شو وضع الذهب». Class: LEAK + the existing text-path failures (recoverable-not-led, technical-question). Command: see section 1, `V1`. Raw: `runs/GAP1-V1.txt`.

SCRIPTED turns:
1. Provider events: transcript «شو وضع الذهب» at 0-900 ms, delegation at offset 1500.
2. Backend model turn 1: `list_accounts`. Turn 2: `market_snapshot {account_id, symbol: "XAUUSD"}`. Turn 3: `market_instrument` same arguments. Turn 4: the owner's verbatim example reply (his text from the task; it is scripted, not evidence of what a real model writes).

REAL runtime output (verbatim, trimmed):
- Delegation after the real `delegate()`: `"status": "running"`, one run id (the call became a chat run).
- `market_snapshot` result: `{"ok": false, "code": "symbol_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}`
- `market_instrument` result: `{"ok": false, "code": "broker_account_not_found", "recovery": {"category": "not_found", ...}}` (same block as in the production trace, point 3 of `TIMELINE_CORRECTION.md`; no candidate symbols).
- Run system prompt check: `contains <voice_observation>: true`; `contains the 'Voice behavior' chapter (lonora.md:177): false`; `contains 'Keep ordinary spoken responses': false`.
- Run row: `status: completed`, `result` equals the scripted reply.
- Command the real `tick()` sent to the Live provider (`session.commentary.append`), verbatim:
  `ما قدرت أقرأ الذهب على هذا الحساب لأن الرمز/الارتباط الحالي غير مطابق في البيانات المتاحة.` / `- محاولة الذهب على `XAUUSD` رجعت **symbol_not_found**` / `- ومحاولة تفاصيل العقد رجعت **broker_account_not_found** على نفس الربط` / `الخطوة التالية المفيدة: أبحث لك عن اسم الذهب الصحيح على هذا الحساب إذا أردت.`

What the owner hears: unknown (the Live model is not run). What the gateway hands it: the run's text byte for byte, with `symbol_not_found` and `broker_account_not_found`, backticks and `**`. Nothing in the voice path removes or rewrites them.

Root cause:
- The result is passed through unchanged: `realtime.py:439-441` (`result.append(run.result ...)`), chunked at `:465-471`, sent at `:487-494`.
- The backend run is not told its answer is spoken: voice-origin runs get only `<voice_observation>` (`builder.py:137-144`); the "Voice behavior" chapter is attached to the tools `owner_notify`/`owner_attention_list`/`owner_call_request` (`manifest.json:132-134`) and enters a run only after one of those tools is called (`packages/agent-runtime/src/lonora_agent/skills/system_policy.py:134-142`, chapters chosen from tool calls). The Live model's own instruction says "Speak verified backend results" (`sessions.py:27`), which asks it to repeat the result rather than rephrase it. Whether it rephrases anyway is UNSURE.
- The failure itself (no symbol discovery on `symbol_not_found`, the offer "if you want") is the text-runtime behaviour documented in the J1 journeys; in a call it is worse because the owner cannot see the card, only hear it, and "ضع حرف m" has to be spoken (see V8).
- Production fit: not observed in a call. It is the same run content as production message [10].

### V2. The backend run fails during a call: "Backend status: failed. model_not_configured"

Owner request: «شو وضع الذهب». Class: LEAK + DEAD-END. Command: `V2`. Raw: `runs/GAP1-V2.txt`.

SCRIPTED: the provider failure. The model call is replaced by one that raises `LonoraError("model_not_configured", 409)`, the exact error of `packages/providers/src/lonora_providers/router.py:211`, which production produced five times (point 8 of `TIMELINE_CORRECTION.md`).

REAL output:
- Run row: `{"status": "failed", "error_code": "model_not_configured", "result": null}`.
- Gateway command sent: `Backend status: failed. model_not_configured`.
- Second delegation, run cancelled (owner pressed stop): run row `{"status": "cancelled", "error_code": null}`; gateway command: `Backend status: cancelled. ` (nothing after the full stop).

What the owner hears: unknown; what the gateway supplies is the status word and the code, in English, with no next step and no retry. Root cause: `realtime.py:461-464`. The text path has the opposite design: it keeps the run failure as a family and each client renders Arabic text and a retry button (`packages/db/src/lonora_db/runs.py:40-47`, `apps/web/src/conversation/Cards.tsx:25-38`, `apps/mobile/lib/i18n.ts:616`). The voice branch never calls `failure_data`. Had the owner called on the fresh install of production (no model routing until 2026-11-11 09:37 UTC) the gateway would have supplied exactly this string; no call is in the evidence, so that is inference.

### V3. A question card during a call: only the question is spoken

Owner request: «اشتري ذهب». Class: OWNER-NEEDED with an incomplete hand-off. Command: `V3`. Raw: `runs/GAP1-V3.txt`.

SCRIPTED: backend turn 1 calls `wait_for_input` with `question="كم تريد حجم الصفقة؟"` and `choices` `0.01` and `0.02`.

REAL output: run row `waiting_input`; thread messages: user «اشتري ذهب», assistant «كم تريد حجم الصفقة؟»; gateway command: `كم تريد حجم الصفقة؟`.

The two choices exist only on the card (`input_request.choices`, `packages/db/src/lonora_db/runs.py:62`; exposed at `:73-75`). `tick()` reads only `message.content` of the latest assistant message (`realtime.py:445-458`). So the spoken side hears a question with no options and no suggested number. This is the question shape the owner objected to ([24] in the chat, asking the size although the task said to choose its own lot size). Whether the call screen shows the card is UNSURE (client code not read for this gap).

### V4. The handoff fails: the owner hears an English apology and nothing runs

Owner request: «شو وضع الذهب» (never reaches the backend). Class: needed for safety (non-start) + RECOVERABLE-NOT-LED (no retry, English). Command: `V4`. Raw: `runs/GAP1-V4.txt`.

SCRIPTED: a delegation event arrives with no transcript fragment (provider lag), then the clock is moved 31 s past the 30 s limit (`realtime.py:40`).

REAL output: log `voice_handoff_failed ... code=transcript_missing`; task `status: result`, `handoff_error: transcript_missing`, `failed_fingerprint` set; gateway command: `I couldn't pass that voice turn to Lonora, so I haven't started new work. You can continue in this call or send a message in the chat; any ongoing work is preserved.`; runs created for the thread: `0`.

Root cause: `realtime.py:239-256`. The reasons that trigger it include transient ones (`transcript_settling`, `transcript_missing`) and hard ones (`transcript_event_conflict`, `transcript_overlap`, `handoff.py:60-81`, `realtime.py:98-100`). The code treats them alike after 30 s. The owner is led to nothing: the window is fenced by `failed_fingerprint` (`realtime.py:215-220`, `:247`) and only new speech starts new work. Needed for safety: ADR 0001 line 19, "it must never create financial work from an incomplete utterance or tell the owner to repeat a request solely because the handoff is late". The safe part is not creating work; the English wording and the lack of an automatic retry of a read-only request such as «شو وضع الذهب» are not part of that rule. Note the sentence does not tell the owner to repeat, which matches the ADR, but also does not tell him what happened.

### V5. The agent is paused during the call: silence in the chat, an English sentence on the call

Owner request: «شو وضع الذهب». Class: OWNER-NEEDED. Command: `V5`. Raw: `runs/GAP1-V5.txt`.

SCRIPTED: the agent row is paused after the call began (the call setup itself refuses a paused agent, `sessions.py:100-101`), then speech and a delegation arrive.

REAL output: the task becomes `running` with `"run_ids": []` and a stored `message_id` (the owner's message is in the chat); gateway command: `The agent is paused or unavailable. No work was started.`

Root cause: `send_message` skips paused agents with `if agent.paused: continue` (`packages/db/src/lonora_db/messages.py:514-515`), returning no runs; `tick()` maps "no runs" to the English sentence (`realtime.py:419-428`). The owner paused it: a real owner decision, the refusal is by design. The sentence says "paused or unavailable", a guess between two states, and gives no way to resume.

### V6. Pending approval card: later speech is blocked (needed for safety)

Owner request: «نعم وافق» (a spoken yes while a card is open). Class: needed for safety. Command: `V6`. Raw: `runs/GAP1-V6.txt`.

SCRIPTED: a pending `TradeApprovalRow` is put in the thread; the owner's words arrive as a delegation.

REAL output: task `status: result`, `suppressed_fingerprint` set; gateway command is `APPROVAL_CARD` verbatim: `The approval card is inside this call and has Approve and Reject buttons. Tell the owner only to press one button. Do not ask them to say or type yes, and do not ask which pair or to repeat the symbol. Speech and chat text are not approval. Do not start another order.`; chat messages created from the spoken yes: `0`.

Root cause and label: `realtime.py:258-275` and `:34-39`. Needed for safety: money moves only through an approval card at the single executor; a spoken yes must not approve. The code comment says why (`realtime.py:265-266`: "Another spoken fragment must not become a user message: that steering cancels the approval before the owner can press the button."). This rule is not a failure to fix. One side effect to note for whoever works on voice language: the text is written as an instruction to the Live model, in English; if the model reads it out the owner hears it in English (UNSURE).

### V7. Forced run states: the literal fallback strings and the 2400-character cut

Class: BUG / DEAD-END (F4 fallback, F5 empty, F6). Command: `V7`; text chunker: the raw file `runs/GAP1-V7b-text-chunks.txt` (a direct call of the real `text_chunks`). Raw: `runs/GAP1-V7.txt`.

Honest limit: in this journey the run row is edited directly (state forced), because I found no natural path that produces these states. They are shown only to print the literal strings `tick()` sends. The assistant messages of the thread were deleted for the `waiting_input` case so that the fallback branch is reached.

REAL output of `tick()` for each forced state:
- `waiting_input`, no assistant message newer than the run: `Ask the user for the information the backend still needs.`
- `completed`, `result` empty: `The backend finished; no additional result was returned.`
- `waiting_takeover`: `Backend status: waiting_takeover. `
- `completed`, 3000-character Arabic result: 10 chunks, the last is `'. \nThe full backend result is available in the chat transcript.'` (2461 characters total).

Root cause: `realtime.py:442`, `:456-460`, `:461-464`, `:51-52`. The fallback at `:459` is an instruction aimed at the Live model placed where an answer belongs. In the natural case (V3) the message exists, so the fallback is reached only when the question message is missing or older than the run (`realtime.py:445-455`); UNSURE if a real run can do that.

### V8. «ضع حرف m» spoken late: an English frame appears in the owner's own chat bubble

Owner request (spoken): «شو وضع الذهب» then, in the same window, «ضع حرف m يعني XAUUSDM». Class: LEAK (English technical frame in an owner message); the explicit revision is needed for safety. Command: `V8`. Raw: `runs/GAP1-V8.txt`.

SCRIPTED: two transcript fragments in one window, settled twice.

REAL output, thread messages (role, content):
- user: `شو وضع الذهب`
- user: `Updated voice transcript for the preceding request (supersedes that observation):` newline `شو وضع الذهب ضع حرف m يعني XAUUSDM`
- task `revision: 2`, same run id (the correction steers the existing run).

Root cause: `realtime.py:285-290` writes the English frame into the message content that `send_message` stores (`:291-296`), so it appears in the owner's thread and in the model's history, and the Arabic is mixed with English. `tests/check_voice_handoff_recovery.py` asserts the frame text endswith the new words (it encodes the behaviour). Needed for safety: corrections stay explicit and withdraw the old unexecuted proposal (`realtime.py:297-317`); only the English wording is incidental.

## 5. Findings about the context the call gives the speech model

- The Live model's context is capped at 7500 bytes (`context.py:17`), with the owner profile at 500 (`context.py:165`), the memory view at 600 (`:181`), scratchpad notes at 600 (`:72`), live state at 900 (`:194`) and agent instructions at 1000 (`:160`). The backend run is far richer. It is the backend run that answers, so this cap matters only for what the speech model says on its own.
- No language is configured for live transcription: `sessions.py:155-163` has no such field; the owner's `reply_language` is passed only as text inside the context JSON (`context.py:171`). In production the value is empty (point 9 of `TIMELINE_CORRECTION.md`). Whether the Live provider guesses the language is UNSURE; for voice notes it demonstrably did (Turkish gibberish, seq 45 and 47).
- `VOICE_INSTRUCTIONS` forbids asking which pair "if this agent has a bound account and symbol" (`sessions.py:29-30`), which is a good rule but only applies to a bound agent. The production agent has `trading_symbol` null (`TIMELINE_CORRECTION.md` point 1), so the rule would not apply to it. This is stated from the instruction text; I did not test it.

- Added by checker: after a question is spoken (`waiting_input`), the delegation goes to `delivered` (`realtime.py:429-434`, `:475-476`) and only tasks with status `running` are watched for run results (`realtime.py:387`). So if the owner answers by pressing a choice on the card and the same run then resumes and finishes, no code path in `tick()` reads the final result to the call. UNSURE: not reproduced; a spoken answer starts a new delegation (`realtime.py:291-296`) and would be covered.
- Added by checker: F2's "or unavailable" is broader than the code. `send_message` returns no run for an agent only when `agent.paused` (`packages/db/src/lonora_db/messages.py:514-515`); no other "unavailable" branch exists in that loop (`:512-515`). The sentence guesses between two states where there is one.

## 6. Existing checks that were run

- `tests/check_voice_handoff_recovery.py`: `Voice handoff recovery: 6 PostgreSQL acceptance scenarios passed`.
- Search over `tests`, `packages`, `apps` for the strings of F2-F4 (`Backend status`, `paused or unavailable`, `information the backend still needs`, `no additional result`): the only hits are the source lines in `realtime.py:424`, `:442`, `:459`, `:463`. No test asserts them. F1 is asserted (`tests/voice/test_live.py:426-427`) but only that it does not say "repeat". The F6 tail is asserted only as a substring (`tests/voice/test_live.py:616`, `"full backend result" in chunks[-1]`), so the cut and its English tail are encoded behaviour, not an accident.
- Doc versus code: `docs/architecture/decisions/0001-agent-first-evolution.md:19` states a handoff failure must be "distinct from unintelligible speech"; the code honours it (V4 sentence does not say repeat). Nothing in the docs mentions the F3 string or the absence of failure families on the voice branch; the code wins.

## 7. What I could not confirm

- What the Live model says aloud after receiving `session.commentary.append`; the provider is paid and was not run. All "what the owner hears" statements stop at "what the gateway supplies".
- Whether the call screen shows question cards and their choices (V3).
- Whether a real run can end `waiting_input` with no newer assistant message, or `completed` with no result (V7 uses forced states).
- Whether production had the Live (OpenAI) voice provider configured at all; no call appears in the trace.

## 8. Citation check (author's list; see the verification log below)

Every `path:line` above was re-opened with `grep -n`, `sed -n` or the Read tool while writing: realtime.py lines 34-44, 47-60, 85-125, 166-175, 182-360 (239-256, 258-275, 285-296, 297-317), 362-494 (386-388, 390-418, 419-428, 429-434, 439-443, 444-460, 461-464, 465-471, 472-494); sessions.py 23-35, 100-101, 119-121, 151, 155-163, 201-203, 212; context.py 17, 165-201; builder.py 137-144; lonora.md 167-175 and 177-207; manifest.json 132-134; packages/agent-runtime/src/lonora_agent/skills/system_policy.py 109-110 and 134-142; messages.py 514-515; runs.py 40-47 and 74-75; Cards.tsx 25-38; user_error.ts 136-140; i18n.ts 396-399 and 616; ADR 0001 line 19; test_live.py 426-427. The repository status was clean (`git status --short` empty) after all runs.

## Verification log

- Citations opened: 118 distinct `path:line` / range citations (every one in sections 0 to 8, re-read in the source with `cat -n`), plus 5 raw-run files and `production-trace.md:140`, `TIMELINE_CORRECTION.md` points 1, 3, 8, 9.
- Journeys rerun: V1 to V8 were executed again with the driver command of section 1 (database 7). All eight reproduced the quoted outputs: V1 tool codes and the `<voice_observation>`/"Voice behavior" checks, V2 `Backend status: failed. model_not_configured` and `Backend status: cancelled. `, V3 question-only command, V4 handoff sentence with 0 runs, V5 paused sentence, V6 `APPROVAL_CARD` with 0 chat messages, V7 four literal strings (3000 chars gave 10 chunks, 2461 characters spoken), V8 English frame in the owner's message with `revision: 2`. Repository status stayed clean.
- Citations corrected: 6 (system_policy.py path was missing its directory, twice; context caps `165-195` split into five exact lines; `runs.py:74-75` to `:62`; the F9 translation claim; the `realtime.py:265-266` quote now verbatim; the `0.35` tick interval now cited at `realtime.py:530`).
- Claims refuted or downgraded:
  1. "36-line Voice behavior chapter": the block `lonora.md:177-207` is 31 lines. Fixed.
  2. F9 "the apps translate" all three call-level codes: false for `voice_call_already_active` (no entry in web or mobile) and for `voice_backend_unavailable` on mobile. Rewritten; no longer "not a defect".
  3. F3 `cancelled` as DEAD-END: downgraded to a wording problem (the owner pressed stop). DEAD-END count 3 to 2.
  4. V3: the choices citation `runs.py:74-75` did not show choices; they are built at `runs.py:62`.
  5. Section 5 byte caps were cited to a range that excluded two of them (instructions at `context.py:160`, scratchpad at `:72`). Fixed.
  6. Section 6 said no test touches the F2-F4 strings; true, but the F6 tail is asserted at `tests/voice/test_live.py:616`. Added.
  7. V6 comment quote was a paraphrase in the middle; now verbatim.
- Claims checked and kept: the F1 to F8 line numbers and quotes, the `APPROVAL_CARD` and handoff-failure texts, the 2400 cut and 480-byte chunking, `sessions.py:159`, ADR 0001 line 19 quote, `messages.py:514-515`, `builder.py:137-144` (5 sentences), `manifest.json:132-134`, per-family counts other than DEAD-END (RECOVERABLE-NOT-LED 1, OWNER-NEEDED 3, BUG 2, LEAK 3, needed for safety 3).
- Absence claims re-searched with two greps each: no test asserts the F2-F4 strings (`grep -rn` over tests, packages, apps for the four strings; only the source lines hit); no translation of `voice_call_already_active` (`grep -rn already_active apps packages`).
- Added findings (2): the `delivered` task is never re-watched after a card answer resumes the run (UNSURE, code reading only); F2 "or unavailable" is imprecise. Both in section 5.
- Not changed: classification of F1 as needed for safety plus RECOVERABLE-NOT-LED wording; no hint found that a recovery tool exists in the voice gateway itself.
