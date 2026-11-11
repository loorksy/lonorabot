# Conversation groups E, F, G and root causes 9, 10, 11 on main (9f5b1da)

Scope: voice and language ([48]-[51]), leaked terms and display ([10], [16]-[65], [41], [61], [67], [75], [77]), availability ([2], [3]).
Method: code reading at 9f5b1da with `path:line`, plus two scripted reproductions on database `audit_j13_test`.

- Reproduction note (checker): the driver is not idempotent. It leaves `reply_language = "ar"` in the database after section E, so a second run on the same database shows `"language": "ar"` in the first E block. Truncate every application table of database 13 first (as `scripts/reset_db9.sh` does for database 9); after that the output matches `conv-EFG.out` line for line apart from run ids and timestamps. The "F run metadata flags" block prints nulls because it reads `RunRow.model_metadata`, while those flags are written to the reply's `provider_metadata` (`packages/agent-runtime/src/lonora_agent/model_runtime.py:261-268`); the nulls are not evidence either way.
- Driver: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/conv_efg.py`, raw output `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/conv-EFG.out` (stderr in `conv-EFG.err`).
- Bold patterns: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/conv_efg_markdown.mjs`, output `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/conv-EFG-markdown.out`.
- SCRIPTED in the driver: the speech-to-text provider, every model reply, and the provider outage in G2. Everything else is the real runtime (API app, admission, executor, tool loop, real router in G1, retry endpoint, voice settlement, context builder, reply protection).
- Times: I use the lead's corrected timeline (`TIMELINE_CORRECTION.md`): export times are UTC+1. [1]-[3] are 2026-11-10 16:44-16:48 UTC on build efb4911; [4] is 2026-11-11 09:37 UTC; [4]-[55] ran on 2477c22, [56]-[71] on cd2cc91, [72]-[81] on 9f5b1da.
- I used `production-trace.md` (present in the audit folder) as a lead; where I rely on it I say so. Where the trace settles a point the text says so; "TRACE MUST CONFIRM" is kept only for what the trace export does not contain.

## Classification table

| Msg | Problem | On main | Mechanism / evidence |
|---|---|---|---|
| [48]→[49] | Arabic voice note transcribed as something else; agent asks the owner to write it | FAILS | No language is sent to speech-to-text when `reply_language` is empty (`packages/voice/src/lonora_voice/voice_notes.py:55-58`, `:72`; `packages/adapters/src/lonora_adapters/voice/stt.py:26`). Voice code on 2477c22 (the serving build) is byte-identical to main. Reproduced: `"language": null`. |
| [50]→[51] | Reply in Turkish, offer to continue in Turkish | FAILS | The context tells the model `"reply_language": "latest_owner_message"` (`packages/agent-runtime/src/lonora_agent/context/memory.py:131`) and the policy says to reply in "the language of the owner's latest message" (`packages/agent-runtime/resources/system/lonora.md:58`). The latest owner message was the Turkish transcript. No guard checks the reply language. Reproduced. |
| [10] | `symbol_not_found`, `broker_account_not_found` in the reply | FAILS | The code reaches the model as `{"ok": False, "code": ...}` (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:113`) plus a `recovery` block added for failed results (`packages/agent-runtime/src/lonora_agent/environment.py:204-210`; any code ending `_not_found` is classed `not_found` / `inspect_existing_state`, `environment.py:80-81`); production Part 4 #15 and #17 show exactly this (`production-trace.md`, run 1ae9a14c). The only server reply filter covers credentials, private paths and UUIDs (`packages/core/src/lonora_core/public_reply.py:37-51`). Reproduced: both codes stored unchanged. |
| [10] | Broker name, account number, server in the reply | FAILS (it is instructed) | The policy and the tool tell the model to show them: `lonora.md:49`, `packages/tools/src/lonora_tools/account.py:63-64`. |
| [59][65] | `waiting`, `owner_attention`, `routines`, `goals` | FAILS | Raw keys and values of the `agent_inspect` result (`packages/tools/src/lonora_tools/supervision.py:149-158`, `:220-255`); no filter. Reproduced. |
| [75][77] | `watch_cancel` | FAILS (observed: [72]-[81] ran on 9f5b1da) | The tool name is in the system text the model reads (`packages/agent-runtime/resources/constitution/trading-policy.md:7`, `lonora.md:434`); the reply filter deliberately ignores tool names (`public_reply.py:42`). Reproduced. |
| [20][22] | `**` shown raw (confirmed screenshot [22]) | FAILS on web | Different cause from root cause 10: a reply with an image attachment is rendered as a caption with `agent={false}`, i.e. with no Markdown at all (`apps/web/src/conversation/Message.tsx:402-409`, `apps/web/src/conversation/Markdown.tsx:277-281`). Well-formed bold would also show raw there. |
| [16][18][24][26][35][41][59][65] | `** text**` / `**text **` | PARTLY | No normalisation on the server (confirmed). But the web bubble and the mobile bubble use their own regex, which accepts inner spaces and makes these bold with a stray space (`Markdown.tsx:68`, `apps/mobile/components/markdown.tsx:22`). Raw `**` remains wherever text goes through the CommonMark renderer (`packages/chat-ui/src/markdown.web.tsx:20-21`, used by `apps/web/src/components/visual/RichResponse.tsx:103`, `:111`) and in image captions. |
| [41] | Garbled word «أغهِقه» | FAILS | Model output; no spelling or sanity check exists anywhere in the reply path. |
| [61][67] | Giant option icons (check, chevron) | FAILS on web; UNSURE on Expo | Web: `.opt-list` / `.opt-row` have no CSS rule in the repository, so the `<svg>` has no size (`apps/web/src/conversation/Cards.tsx:150-171`, `packages/ui-web/src/icons/icon.tsx:5-19`). Expo: the component on main sets `size={18}` and draws no chevron (`apps/mobile/components/conversation-question.tsx:88-90`). |
| [2] | «النموذج غير متاح حاليًا» | FAILS | The card text is chosen from the failure family; every `model_*` code, including `model_not_configured`, maps to family `model` (`packages/core/src/lonora_core/runtime_failure.py:50-51`) and shows «تعذّر الوصول إلى مزوّد النموذج…». Reproduced with the real router and no model configured. |
| [3] | Message unanswered for ~17 h | FAILS | A failed conversational run is never retried by the server; only the owner's «إعادة المحاولة» creates a new run (`packages/db/src/lonora_db/run_retry.py:79`, only caller `apps/api/src/lonora_api/routes/runs.py:73`). Reproduced, including the first message staying unanswered for good. |

Nothing in `git log aa50e8e..9f5b1da` adds a guard for any row above. One commit in that range made E worse (see E.2).

---

## E. Voice and language

### E.1 Path of a voice note, upload to model

1. The client uploads the audio as an artifact and posts a message whose `voice` field carries only `artifact_id`, `duration`, `peaks` (`packages/contracts/src/lonora_contracts/domain.py:96-99`, field at `:122`). There is no language or locale field in the contract. Route: `apps/api/src/lonora_api/routes/messages.py:92-101`.
2. `send_message` stores the message with empty content and a `voice` part (`packages/db/src/lonora_db/messages.py:386-391`) and admits no run; it writes a pending receipt instead (`messages.py:430-439`, key prefix `VOICE_NOTE_PENDING = "voice-note:"` at `:29`).
3. The gateway step `voice_notes` (every second, `packages/gateway/src/lonora_gateway/service.py:58-59`, `:230-238`) calls `transcribe_pending`.
4. `transcribe_note` reads the hint: `language = ... select(OwnerProfileRow.reply_language)` with the comment "The owner's chosen language is the hint; without one the provider detects it." (`packages/voice/src/lonora_voice/voice_notes.py:55-58`). It tries the owner's OpenAI STT route, then `gpt-4o-mini-transcribe`, then `whisper-1` (`voice_notes.py:31`, `:34-40`, `:70-75`) and passes `language=language` (`:72`).
5. The adapter sends the field only when it is set: `data={"model": model, **({"language": language} if language else {})}` (`packages/adapters/src/lonora_adapters/voice/stt.py:26`).
6. `settle_voice_note` writes the transcript into `message.content`, marks the part `done` or `failed`, sets the thread title from it, emits `message.updated`, then admits the run (`packages/db/src/lonora_db/voice_notes.py:63-67`, `:73-74`, `:77`, `:90`).
7. The model reads the transcript as an ordinary owner message: `model_content(row.content, row.rich_content)` (`packages/agent-runtime/src/lonora_agent/context/history.py:197`) returns the content as is when it is non-empty (`packages/core/src/lonora_core/message_preview.py:44-48`). Only a pending or failed transcript gets a server note (`message_preview.py:37-41`). So the model is not told the text came from speech recognition and may be wrong. Reproduced: the string "oice note" does not appear anywhere in the model request (`conv-EFG.out`, "E mentions of 'voice' in the model request": `[]`).

### E.2 Root cause 9: CONFIRMED, with two additions

- Hint = `OwnerProfileRow.reply_language`; empty means no `language` field and the provider guesses: confirmed at `voice_notes.py:55-58`, `:72`, `stt.py:26`. `reply_language` is nullable and only `ar`/`en` are allowed (`packages/db/src/lonora_db/schema.py:473`, `:483`). Production: the column is empty (lead's trace, point 9).
- `packages/voice/src/lonora_voice/transcription.py:8-11` passes no language (`adapter.transcribe(audio, stt.model)`). Addition: nothing in the repository imports this module (`grep -rn "lonora_voice.transcription\|from .transcription"` over the repository returns nothing), so it is dead code and not on the voice-note path.
- Addition, a regression: until commit ce92a10 (2026-11-10 07:04 UTC) the hint was a constant, `LANGUAGE = "ar"`. That commit replaced it with the profile lookup (`git show ce92a10 -- packages/voice/src/lonora_voice/voice_notes.py`: `-LANGUAGE = "ar"`). The module docstring still says "Arabic language hint" (`voice_notes.py:5`). ce92a10 is an ancestor of 2477c22, the build that served [48]-[51] (`git merge-base --is-ancestor`), and `git diff 2477c22 9f5b1da -- packages/voice packages/adapters/src/lonora_adapters/voice` is empty. The existing test asserts the hint equals the profile language (`tests/test_voice_notes.py:254`, `:265`) and has no case for an empty profile.

Reproduction (`conv-EFG.out`, section E): profile `reply_language` is `null`; the runtime called speech-to-text with `{"model": "gpt-4o-mini-transcribe", "media_type": "audio/webm", "language": null}`. After `PUT /owner/preferences {"reply_language": "ar"}` the same call carried `"language": "ar"`.

### E.3 Why the reply was Turkish ([51])

What decides the reply language is prompt text only:

- `packages/agent-runtime/resources/system/lonora.md:58`: "Reply in the owner profile's reply_language, else the language of the owner's latest message, unless asked otherwise."
- `lonora.md:59`: "An English background instruction, machine result, technical symbol, or confirmation label does not change that language."
- `packages/agent-runtime/resources/constitution/identity.md:1`: "Respond in the user language; Arabic is fully supported."
- The context section `owner_preferences` says "Reply in reply_language" (`packages/agent-runtime/src/lonora_agent/context/memory.py:27-34`) and fills the value with `preferences["reply_language"] or "latest_owner_message"` (`memory.py:131`).

With an empty profile the model is told, twice, to use the language of the latest owner message, and that message was the Turkish transcript «Bu korkuluklar nasıl hakkında» (lead's trace, seq 47). The Turkish reply follows the written policy. Reproduced: the model request contains `"reply_language": "latest_owner_message"` and its last owner message is the Turkish string; the SCRIPTED Turkish reply was stored unchanged (`"unchanged": true`).

Guard for reply language: none. The final reply passes only through the suggested-reply split, the financial-truth gate, the visual projection and `redact_private_reply` (`packages/agent-runtime/src/lonora_agent/model_runtime.py:195`, `:218-232`, `:242-248`); none looks at language.

Side effect on server-written text: the two server heuristics that pick Arabic or English read the owner's messages newest first and return English for any message with a space and at least 8 Latin letters (`packages/db/src/lonora_db/conversation_locale.py:27-33`, `packages/agent-runtime/src/lonora_agent/runtime_notices.py:84-93`). A Turkish (or any Latin-script) mis-transcription therefore also switches server notices and card locale to English until the owner writes Arabic again, when `reply_language` is empty.

### E.4 [49] «لم أفهم… اكتبها بالعربية»

Model output, not code. No such string exists in `apps`, `packages` or `scripts` (`grep -rn "اكتبها\|لم أفهم"` returns nothing). The server's own note for an untranscribable note is different English text addressed to the model ("…Tell the owner you could not hear it and ask them to send it again or write it.", `message_preview.py:38-41`) and is used only when the transcript is empty; here the transcript was the non-empty string «ımuz lazım birasta» (lead's trace, seq 45), so the model saw gibberish with Arabic history and asked for Arabic.

Settled by the trace (checker): (a) the stored content of seq 45 and 47 is the Turkish text above (`production-trace.md` Part 3, lines for seq 45 and 47; both rows are voice notes). A non-empty transcript is settled as `transcript_status: done` by `packages/db/src/lonora_db/voice_notes.py:63-67`; the part's stored status itself is not in the trace. (b) `ln_owner_profile.reply_language` is EMPTY (Part 2, Q6 block; Part 1 key findings). (c) Q7 shows `model_routing` = `{"mode": "unified", ..., "routes": {}}`, so there is no STT route; `transcription_models` (`voice_notes.py:34-40`, reading `model_routing` via `packages/providers/src/lonora_providers/routing_policy.py:6-10`) therefore tries `gpt-4o-mini-transcribe` first and `whisper-1` only after an error.

TRACE MUST CONFIRM: whether `gpt-4o-mini-transcribe` or the `whisper-1` fallback produced the two transcripts. Only the log line `voice_note_transcription_failed` (`voice_notes.py:74`) would show it, and logs before 10:37 UTC are gone (`TIMELINE_CORRECTION.md`), so this stays open. It does not change the verdict: neither call carried a language.

---

## F. Leaks and display

### F.1 Is there a server-side reply guard for codes, tool names, internal states?

No. I read every module on the reply path:

| Module | What it does to the reply text | Citation |
|---|---|---|
| `packages/core/src/lonora_core/public_reply.py` | Redacts credentials, private file locations and UUIDs that are not public broker ids. Its docstring: "Public capability names and ordinary diagnostic vocabulary are not credentials. Presentation is owned by the model's instructions, not a keyword veto on replies." The `tool_names` argument is discarded (`del tool_names`). | `:1-5`, `:10-25`, `:37-51`, `:42`, `:54-67` |
| `model_runtime.py` | Applies `redact_private_reply` to the final answer; comment "Style is model guidance, never a second generation or a failed user request"; metadata `"public_rewrite": False`. | `packages/agent-runtime/src/lonora_agent/model_runtime.py:239-248`, `:266` |
| `public_stream.py` | Stops incremental streaming when the text matches `EFFECT_CLAIM` or a privacy violation; it does not change the final text. | `packages/agent-runtime/src/lonora_agent/public_stream.py:11-19`, `:47-51` |
| `stream_publication.py` | Batches chunks; no content check. | `packages/agent-runtime/src/lonora_agent/stream_publication.py:23-37` |
| `uncertain_outcome.py` (PR #42) | Appends one fixed line when a financial result is uncertain; reads structured results only, "no wording of the owner or the model is read". | `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:1-10`, `:36-37`, `:134-152` |
| `loop_outcomes.py` | `final_answer` runs the Task stop gate and the uncertain line; no text filter. | `packages/agent-runtime/src/lonora_agent/loop_outcomes.py:155-184` |
| `stop_gates.py` | Applies only to a run bound to a Task (`task_id`); returns "do not continue" otherwise. No text is read ("No text classifier decides…"). | `packages/agent-runtime/src/lonora_agent/stop_gates.py:86-97`, `:153-155`, `:178-184` |
| `visual_response.py` | Compiles `lonora-ui` blocks and redacts private spans inside them. | `packages/agent-runtime/src/lonora_agent/visual_response.py:268`, `:687`, `:754` |

The policy asks the model to avoid such terms ("describe the useful result rather than narrating implementation details such as cards, tools, skills, runs…", `lonora.md:43`; "Do not quote an internal diagnostic verbatim…", `lonora.md:52`) but also says "Capability names and ordinary technical vocabulary are not secrets" (`lonora.md:44`) and "give exact public operation names if requested" (`lonora.md:50`). Enforcement is by prompt only.

Reproduction (`conv-EFG.out`, section F): a SCRIPTED reply containing `waiting`, `owner_attention`, `symbol_not_found`, `broker_account_not_found`, `routines`, `goals`, `watch_cancel`, malformed bold, the garbled word and one UUID was stored and published with exactly one change: the UUID became `[REDACTED]`.

Side finding from that run: when the privacy filter fires, it rewrites the whole reply through `normalized_text`, which drops every character of Unicode category `Mn` (`public_reply.py:29-34`, `:63`). Arabic diacritics are `Mn`, so they are stripped from the entire reply: «أغهِقه» came back as «أغهقه». Any Arabic reply that needs one redaction loses all its tashkeel.

### F.2 Source of each leaked term

| Term | Where the model got it | Citation |
|---|---|---|
| `symbol_not_found`, `broker_account_not_found` [10] | The `code` field of the failed tool results; the error result is `{"ok": False, "code": error.code}` (plus `issues` and `retryable` for argument errors, `tool_dispatch.py:114-116`) and the runtime then adds a `recovery` block (`environment.py:204-210`). Production Part 4 #15 and #17 (run 1ae9a14c) show `{"ok":false,"code":"symbol_not_found","recovery":{"category":"not_found","next_action":"inspect_existing_state","safe_to_retry":false,"schema_tool":"tool_environment",...}}`: no candidate symbols and no owner-language text. | `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:113`; `packages/agent-runtime/src/lonora_agent/environment.py:80-81`, `:204-210` |
| Broker / account number / server [10] | `list_accounts` returns `broker_identity` with `broker`, `login`, `server`, and its `guidance` field says "Present accounts to the user using broker_identity broker/login/server, never transport IDs as account numbers." The policy agrees: "Name the broker's real company, account login and server when verified". This is instructed behaviour, not an accident. | `packages/tools/src/lonora_tools/account.py:63-64`; `lonora.md:48-49` |
| `waiting` [59][65] | `agent_inspect`: overview `activity.state` (value `"waiting"` only when the agent is not paused, not degraded, has nothing needing the owner and nothing working, but has runs, watches or tasks: `packages/db/src/lonora_db/agent_state.py:540-564`) and each task's `status` (a task held for the owner is `status "waiting"`, `waiting_reason "owner_attention"`, `tasks.py:785`; production Q5 shows that ticket with `waiting_reason owner_attention`). A watch summary itself has no `waiting` value (its field is `lifecycle`, default `"pending"`), so «الحالة: waiting» attached to the EURUSDm watch in [59] is the agent's or the task's state applied to the watch by the model. | `packages/tools/src/lonora_tools/supervision.py:149-158`, `:220-227`; `packages/db/src/lonora_db/agent_state.py:562-564`, `:36-53` |
| `owner_attention` [65] | Task field `waiting_reason`, constant `OWNER_ATTENTION = "owner_attention"`, set when a Task is held for the owner. | `supervision.py:225`; `packages/db/src/lonora_db/tasks.py:20`, `:785` |
| `routines`, `goals` [65] | Top-level keys of the `agent_inspect` work page: `"watches"`, `"routines"`, `"tasks"`, `"goals"`. The tool description also lists "watches, routines, Tasks, goals". | `supervision.py:229-255`, `:600-603` |
| `watch_cancel` [75][77] | Not a tool result: `tool_environment` returned an empty list in that run (lead's trace, Part 4 #77). The name is in the system text every run receives: "A watch is cancelled with watch_cancel or changed with watch_update" (added by PR #42) and "Steer your own watches with watch_cancel, watch_pause, watch_resume and watch_update". | `packages/agent-runtime/resources/constitution/trading-policy.md:7`; `lonora.md:434`; tool defined at `packages/tools/src/lonora_tools/market_watch.py:254-255` |

TRACE MUST CONFIRM: the `view` argument and full result of the two `agent_inspect` calls (runs f51d1db6 and 049af207), to settle which field carried `waiting` in [59].

### F.3 Root cause 10 (Markdown): PARTLY CONFIRMED, and the confirmed screenshot has another cause

Confirmed: there is no Markdown normalisation anywhere on the server reply path (table in F.1; the reproduction stored `**المراقبة النشطة: **` and `** owner_attention**` unchanged).

Not confirmed as stated: the CommonMark flanking rule applies only where the CommonMark renderer is used. Main has three renderers and one path with no renderer (the caption, item 2):

1. Web conversation bubbles: `TextBody` → `mdInline`, a hand-written regex, `claim(/\*\*([^*\n]+)\*\*/g, …<strong>…)` (`apps/web/src/conversation/Markdown.tsx:68`, used from `apps/web/src/conversation/Message.tsx:393-400`). Text with block syntax (lists, headings, tables) goes through `md()` instead (`Markdown.tsx:270-276`), but `md()` renders every line, list item and table cell with the same `mdInline` (`Markdown.tsx:107`, `:180`, `:190`, `:204`, `:218`, `:232`), so the behaviour is the same. It accepts inner spaces. Applied to the lines of [16], [18], [35], [65] it produces `<strong> 0.24</strong>`, `<strong>الخلاصة العملية: </strong>` and so on: bold, with a misplaced space, and with the spaces around the bold run lost where the model put them inside the markers (`conv-EFG-markdown.out`).
2. Web image captions: when the reply has an image attachment and text, the text is rendered with `<TextBody text={text} agent={false} …/>` (`Message.tsx:402-409`; `images` is defined at `:344`). With `agent` false `TextBody` uses `richText`, which interprets links and mentions only (`Markdown.tsx:21-23`, `:277-281`). Every `**` in such a reply is shown raw, correct or not. [20] and [22] are exactly these messages (chart images attached), and [22] is the one the owner confirmed by screenshot. The same code was in the serving build (`git grep -n TextBody 2477c22 -- apps/web/src/conversation/Message.tsx` shows the identical lines `:393` and `:406`).
3. The CommonMark renderer: `ChatMarkdown` = `react-markdown` with `remark-gfm` (`packages/chat-ui/src/markdown.web.tsx:20-21`). On main it is reached only through `RichResponse` (`apps/web/src/components/visual/RichResponse.tsx:103`, `:111`, and for node text `:271`; the only importer is `apps/web/src/conversation/GenUiPart.tsx:2`), i.e. for replies that carry a generated UI part (`Message.tsx:336-341`, `:374-376`). There `** 0.24**` and `**3 صور **` stay raw, because an opening `**` followed by a space, or a closing `**` preceded by a space, is not a valid delimiter. None of the production replies had `rich_content` (lead's trace, Part 3: "rich_content is null on every row except the two voice notes"), so this renderer did not draw any of the listed messages.
4. Mobile (Expo) bubbles: a regex split on `\*\*[^*]+\*\*` (`apps/mobile/components/markdown.tsx:22`, `:38-43`, used at `apps/mobile/components/message-bubble.tsx:164`). Same tolerance as the web regex.

So on main: [20][22] show raw `**` on web because of the caption path; the other listed messages render bold with a stray or missing space on web and mobile; any of them would show raw `**` if delivered inside a generated-UI reply.

UNSURE: whether the spacing in the owner's export (`** 0.24**`, `إلى**انتظار**`) is the model's raw text or an artifact of the export. The pattern, a space moved to the wrong side of the marker, fits both. TRACE MUST CONFIRM: the raw `content` of the assistant rows for [16], [18], [22], [35], [65] (the lead's Part 3 summary strips the markers).

### F.4 Garbled word «أغهِقه» [41]

Model output (the lead's trace quotes the stored row: "ولم أغهِقه (sic)", seq 38). There is no spelling, script or sanity check in the reply path: none of the modules in F.1 inspects words. The only thing that can alter such a word is the diacritic stripping described in F.1, and only when a redaction happens.

### F.5 Root cause 11 (question card option icons): CONFIRMED for web, not found for Expo

Web:

- The card is `QuestionCard` (`apps/web/src/conversation/Cards.tsx:126`). Options are `<div className="opt-list">` with one `<button className="opt-row…">` each, holding the label and `<Icon name={chosen === choice.id ? "check" : "chev"} />` (`Cards.tsx:150-171`). These are the ✓ and ‹ of the screenshots.
- `Icon` renders an `<svg viewBox="0 0 24 24">` with no `width` or `height`; its comment says "its box is sized by CSS" (`packages/ui-web/src/icons/icon.tsx:5-19`).
- No stylesheet in the repository has a rule for `.opt-list` or `.opt-row` (`grep -rn "opt-" --include=*.css .` finds only `.pop-opt-body`, `apps/web/src/conversation/conversation.css:666`). The card's own rules stop at the kicker icon and the form (`conversation.css:294-349`; `.mcard-kicker svg` is sized at `:307-310`). The global icon rules target `.icon svg` and `.btn svg` only (`apps/web/src/shell/shell.css:475-477`, `:507-510`), and the option button has neither class.
- The reference design has the missing rules: `.opt-list{display:grid;…}`, `.opt-row{display:flex;…}`, `.opt-row svg{width:14px;height:14px;color:var(--faint);flex:none}` (`docs/ui-reference/Lonora-Desktop-37.html:2224-2228`). They were not carried over. An unsized SVG with a viewBox grows to the available width, which is the "giant icon" with the label still present.
- The component and the missing CSS are the same on the builds that served [61] and [67] (`git grep -n opt-row cd2cc91 -- apps/web/src` returns only `Cards.tsx:155`).
- A second, older web component exists with its own stylesheet (`apps/web/src/components/conversation-question.tsx:8`) but nothing imports it.

Expo: `ConversationQuestion` (`apps/mobile/components/conversation-question.tsx`, mounted at `apps/mobile/app/thread.tsx:1021-1022`) shows a letter, the label and, for the selected option only, `<NativeSymbol name="check" size={18} …/>` (`conversation-question.tsx:75-90`). It has an explicit size and no chevron. UNSURE: I found no dimension defect in this component by reading; the owner's screenshots show a chevron, which this component never draws, so they are from the web client. I did not render either client.

---

## G. Availability

### G.1 Where «النموذج غير متاح حاليًا» is composed

In the web client, not on the server. `AgentErrorCard` picks a title and a text from the run's failure family (`apps/web/src/conversation/Cards.tsx:69-83`):

- title for family `model`: "The model is not available right now" (`Cards.tsx:73`) → «النموذج غير متاح حاليًا» (`apps/web/src/i18n/locales/ar/messages.po:7332`);
- text: "The model provider could not be reached. Try another model or retry shortly." (`Cards.tsx:81`) → «تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.» (`messages.po:7336`);
- buttons «تغيير النموذج» (opens settings, `Cards.tsx:84`, `apps/web/src/conversation/Conversation.tsx:610-613`) and «إعادة المحاولة» (`Cards.tsx:96-118`).

The card is drawn under an owner message for each failed run of that message that has not been retried (`apps/web/src/lib/failed-replies.ts:4-21`, `Conversation.tsx:991-1001`).

The family comes from the server: `fail_run` stores `failure_family(code, reason)` (`packages/db/src/lonora_db/runs.py:452-469`; read back at `:40-47`). `failure_family` (`packages/core/src/lonora_core/runtime_failure.py:39-52`): provider reason `billing` → quota, `rate_limit` → rate, `timeout` → timeout; then by code: `model_billing_exhausted` → quota, `model_rate_limited` → rate, `*_timeout` → timeout, and "`value.startswith("model_") or value in MODEL_CODES`" → `model`.

Provider error classes that end as family `model` (codes from `packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:80-99`; reproduced in `conv-EFG.out`, "G1 failure_family per code"):

| Reason | Code | Family |
|---|---|---|
| overloaded, server_error, connection, unknown | `model_provider_unavailable` | model |
| timeout | `model_provider_unavailable` | timeout (by reason) |
| auth | `model_credentials_rejected` | model |
| permission | `model_access_denied` | model |
| model_not_found | `model_endpoint_unavailable` | model |
| content_policy | `model_content_blocked` | model |
| format_error, output_limit | `model_request_rejected` | model |
| truncated | `model_output_truncated` | model |
| invalid_response | `model_response_invalid` | model |
| not_configured | `model_not_configured` | model |
| context_overflow, payload_too_large | `context_limit_exceeded` | model |

So one sentence, "the model provider could not be reached", is shown for ten different codes (the table has eleven rows; the timeout row is family `timeout`, not `model`), most of which are not about reachability. The client has an accurate sentence for several of them, e.g. `model_not_configured` → "Connect a provider and choose a global model in Settings." (`apps/web/src/lib/user_error.ts:88-89`), but the card uses it only for family `other` (`Cards.tsx:82`).

Production (lead's trace, point 8): all five failed runs are `model_not_configured`; the installation had no model routing until 2026-11-11 09:37:25 UTC. The text «تعذّر الوصول إلى مزوّد النموذج» was therefore untrue. Note also that the standalone title «النموذج غير متاح حاليًا» is not in build efb4911: `git grep -n "النموذج غير متاح حاليًا" efb4911 -- apps` returns only two hits for a different string, «مزود النموذج غير متاح حاليًا. حاول مجددًا بعد قليل.» (`apps/mobile/lib/i18n.ts:606`, `apps/web/src/i18n/locales/ar/messages.po:6121`), while `git grep -n "AgentErrorCard" efb4911 -- apps` and `git grep -n "is not available right now" efb4911 -- apps` find nothing; at 2477c22 the standalone title is at `messages.po:7158`. The card is drawn by the client from the run's data, so the card the owner exported under «أمس» was drawn by a later client for the old failed run of [1]. Also, `packages/db/src/lonora_db/run_retry.py` does not exist at efb4911 or at aa50e8e (`git cat-file -e` fails) and exists at 2477c22: on 2026-11-10 the retry path was not in the serving build, which fits the retries only starting on 2026-11-11 (08:55 UTC, `production-trace.md` Part 1). UNSURE: what the efb4911 client showed under a failed run; I did not find an error card there.

Reproduction (G1, real router, nothing patched): model settings `{"mode": "unified", "unified": null, "routes": {}}`; the run for «مرحبا» ended `failed`, `error_code: "model_not_configured"`, `failure: {"family": "model"}` one step after `run.context_ready`.

### G.2 Fallback between configured models

It exists, inside one request, in `GlobalModelRouter`:

- Candidate chain: run choice, the agent's own primary, the global primary for the capability, the agent's fallbacks, the owner's `model_backups`, and, when the agent is in automatic mode or has no preference, every model the owner added (`packages/providers/src/lonora_providers/router.py:162-184`). An empty chain raises `model_not_configured` (`router.py:210-211`).
- `complete` walks the chain (`router.py:271-342`). After a failure it moves to the next candidate unless the reason's recovery says `fallback=False` (`router.py:326-328`).
- Recovery table (`packages/providers/src/lonora_providers/resilience.py:75-97`): every reason falls back except `CONTEXT_OVERFLOW` and `PAYLOAD_TOO_LARGE` ("Another model cannot shrink this request"). Same-provider retries are 0-2 depending on the reason; a failed candidate is benched (15 s to 900 s) only for reasons whose `bench_seconds` is set (auth, billing, permission, rate limit, overloaded, server error, timeout, connection, unknown, model not found; not content policy, format, output limit, truncated, invalid response, not configured; `resilience.py:75-97`).

When fallback is skipped or cannot help:

1. Only one model is configured (the production case after 09:37: "unified openai/gpt-5.4-mini", lead's trace): the chain has one entry.
2. No model is configured: no chain at all (`router.py:210-211`) — the cause of [2].
3. A candidate has no credentials: it is recorded as `NOT_CONFIGURED` and skipped (`router.py:274-280`).
4. A candidate is benched from an earlier failure: skipped without a call (`router.py:282-290`).
5. Context overflow: no fallback; the run compacts and retries (`resilience.py:87-88`, `packages/agent-runtime/src/lonora_agent/model_recovery.py:166-173`).
6. The agent chose its models explicitly (not automatic): the owner's other added models are not appended (`router.py:173-175`).

When the whole chain fails (`router.py:344-367`), the run decides (`packages/agent-runtime/src/lonora_agent/tool_loop.py:517-560`, `model_recovery.py:155-202`):

- transient reasons (rate limit, overloaded, server error, timeout, connection, unknown): the conversation run is re-queued with a deadline, 10 s base, 60 s cap (`model_recovery.py:59`), and after 3 consecutive failures it fails with the provider's code (`model_recovery.py:187-194`, `tool_loop.py:553-560`; `docs/provider-resilience.md:143-144`: "After 3 consecutive transient failures of a conversation Run, it fails with the provider's code, which the owner sees in the chat.");
- every other reason, including `model_not_configured`, auth, billing, model not found: `Decision("raise")` at once (`model_recovery.py:174-175`), the run fails on the first attempt.

`python -m pytest tests/test_provider_resilience.py` was not run by me; the behaviour above is from code and from the G2 reproduction.

### G.3 Why [3] waited about 17 hours: every mechanism checked

| Mechanism | Exists on main? | Consistent with a reply ~17 h later with no new owner message? |
|---|---|---|
| A previous failed run holds the thread | No. A new message joins an existing run only if that run is `queued`, `leased`, `running` or `waiting_input` (`packages/db/src/lonora_db/messages.py:516-526`, `:531-536`); a failed run is not active, so the message gets its own run (`messages.py:576-593`). Reproduced: second «مرحبا» → `same_run: false`. | No |
| The message's own run failed and nothing retries it | Yes. `retry_run` is called only from `POST /runs/{id}/retry` (`apps/api/src/lonora_api/routes/runs.py:63-73`), which only the card button calls (`Conversation.tsx:602-609`). No timer, startup hook or model-settings change creates a retry (`grep -rn "retry_run("` finds the route only). | Yes, with a button press. This is the production path. |
| Automatic retry after provider failure | Only for transient reasons and only three attempts within about a minute (G.2). `model_not_configured` is not transient. | No |
| Message queued behind a lease | A queued run waits while another run of the thread holds a live lease (`packages/db/src/lonora_db/runs.py:234-253`); leases are short and expire. | No (seconds to minutes) |
| Run in retry backoff holds later messages | Yes: a message sent during the backoff joins the same run and clears the deadline (`messages.py:562-569`, `packages/agent-runtime/src/lonora_agent/executor.py:282-291`). Reproduced in G2. The wait is at most the backoff. | No |
| Worker not running | Runs are claimed only by the gateway dispatcher (`packages/gateway/src/lonora_gateway/run_dispatch.py:50`). A `queued` run stays queued in the database until a worker claims it, with no expiry for ordinary messages. | Would fit in general (a queued message is answered when the worker comes back), but not here: the production runs were claimed and failed within one second (lead's trace, Part 1). |
| Recovery on restart / deploy | A `leased` or `running` run whose lease expired is re-claimed, up to 5 times (`runs.py:194-201`, `MAX_RUN_RECOVERIES = 5` at `:21`). A pending voice note is transcribed by the next gateway tick after a restart (`packages/db/src/lonora_db/voice_notes.py:23-31`). Failed runs are not touched by recovery. | Only for runs that were in flight or queued at the restart; not for failed ones. |
| Waiting for the owner (`waiting_input`) | A run waiting on a question stays until answered (`messages.py:572-573`). | No (not the case for a greeting) |

Conclusion from code: the only way a message whose run already failed gets a reply later, with no new owner message, is the owner pressing «إعادة المحاولة». The lead's trace agrees: the 2026-11-11 runs are `retry_of` the failed ones (08:55:57, 08:56:00, 09:05:37 failed again with `model_not_configured`; the one that succeeded at 09:37:44 came 19 seconds after the model was configured at 09:37:25).

Two consequences reproduced in G1:

1. A retry answers one message. Each failed run can be retried once, and the retry keeps the failed run's `input_seq` (`run_retry.py:87-90`, `:125-133`; `runs.py:270-277`). After the owner retried the second «مرحبا» the thread was: `seq 1 user: مرحبا`, `seq 2 user: مرحبا`, `seq 3 assistant: مرحباً. كيف أساعدك؟`; the run for seq 1 is still `failed`. The retried request did contain both greetings, so the model saw [1], but [1] keeps its error card. That is the production picture: [1], card [2], [3], reply [4].
2. The retry button of the card stays the only path even after the owner fixes the cause in settings; changing the model does not re-run anything. I found no caller of `/runs/{id}/retry` under `apps/mobile` (`grep -rn "/retry\|retryRun" apps/mobile`); UNSURE whether the Expo client offers any retry.

### G.4 Reproduction: provider unavailable, then a second message (G2)

SCRIPTED provider raising `ModelProviderError(FailureReason.CONNECTION)` on every call; the driver leases the run itself, so the backoff deadline is not waited for.

1. Owner: «طيب شو وضع الذهب». After attempt 1 the run is `queued` with `retry: {"reason_code": "model_provider_retry", "code": "model_provider_unavailable", "attempt": 1}` and a `not_before` about 12 s ahead; event `run.retry_scheduled`. No message and no card is written to the conversation at this point; the client only gets the event.
2. Owner sends «مرحبا؟» during the backoff: `same_run: true`; the run's `input_seq` moves from 4 to 5 and the deadline is removed.
3. Attempt 2: again `queued`, `attempt: 2`. Attempt 3: `status: "failed"`, `error_code: "model_provider_unavailable"`, `failure: {"family": "model"}`, `escalations: 1`. Three provider calls in total.
4. The card (same title and text as [2]) attaches to the message whose `seq` equals the run's `input_seq`, i.e. to «مرحبا؟» (seq 5). «طيب شو وضع الذهب» (seq 4) gets neither a reply nor a card of its own.
5. Next owner message «مرحبا»: `new_run: true`. Its model request contains all five earlier owner messages, including the two unanswered ones; nothing in the context marks them as unanswered, and nothing makes the run answer them.

So after an outage the second message is not lost from history, but the server neither answers the held messages by itself nor flags them: it is left to the model to notice, or to the owner to press retry on the one card.

### G.5 What the production trace must confirm for G

- SETTLED by the trace (checker): the run that answered at 09:37:44 UTC, d5b850bc, is `retry_of 7b86f6fb`; the chain is 603d1bb0 (11-10 16:48) -> cf008869 (08:56:00) -> 7b86f6fb (09:05:37) -> d5b850bc (`production-trace.md` Part 1, run list). `retry_of` is written only by `retry_run` (`packages/db/src/lonora_db/run_retry.py:132`; `grep -rn "retry_of" packages apps --include=*.py` shows no other writer) and that function is called only by `POST /runs/{id}/retry` (`apps/api/src/lonora_api/routes/runs.py:63-73`), so each link was a client retry request. The access log is not needed.
- SETTLED by the trace (checker): [1] was never answered: seq 1 has b1cea9d1 (failed) and e2bc2eae (`retry_of b1cea9d1`, failed) and nothing later (`production-trace.md` Part 1 run list and the line "seq 1 and 2 (yesterday, model_not_configured) got no reply; the retry at 09:37:44 answered seq 2 only").
- TRACE MUST CONFIRM: whether provider credentials existed at 16:44 UTC on 2026-11-10 (only routing missing, or keys too). Both give `model_not_configured` (`router.py:210-211` and `router.py:274-280`).
- TRACE MUST CONFIRM (low value): the stored `ln_runs.model_metadata.failure` of the five failed runs. The family does not depend on it: `failure_data` falls back to `failure_family(row.error_code)` at read time (`packages/db/src/lonora_db/runs.py:40-47`), which gives `model` for `model_not_configured` (`runtime_failure.py:50-51`), and the web card reads the family from the run payload.

---

## Root causes 9, 10, 11: verdicts

| # | Owner's statement | Verdict |
|---|---|---|
| 9 | Hint is `OwnerProfileRow.reply_language`; empty → provider guesses; `transcription.py` passes no language | CONFIRMED. Additions: `transcription.py` is unused; the hint was a fixed `"ar"` until ce92a10 (2026-11-10), which introduced the defect; the voice contract carries no client locale; the model is not told the text is a transcript; with an empty profile the policy itself tells the model to answer in the transcript's language. |
| 10 | No Markdown normalisation in the reply path; `** نص**` / `**نص **` not bold under CommonMark | PARTLY. No normalisation: confirmed. The CommonMark renderer is used only for generated-UI replies; ordinary web and mobile bubbles use tolerant regexes and do render these bold (with misplaced spaces). The screenshot-confirmed raw `**` ([22]) comes from the image-caption path, which renders agent text with no Markdown at all. |
| 11 | Question cards: option icon dimensions in web and Expo | CONFIRMED for web: the `.opt-list` / `.opt-row` rules of the reference were never added, so the option SVG has no size. Expo: no defect found in the component on main (explicit `size={18}`, no chevron); UNSURE without a render. |

## Money-safety check

Nothing above touches the executor, grants, approvals, journals or restrictions. Two points to keep in mind for whoever changes these areas: the run retry refuses any run with a financial effect or descendants (`packages/db/src/lonora_db/run_retry.py:91-103`), and a voice request stays provisional through a retry (`run_retry.py:134-136`); both must stay as they are.

---

## Verification log

Checker pass at code 9f5b1da. The repository HEAD is now 3f09572; `git diff 9f5b1da HEAD` touches only `docs/research/**`, so all code citations are at 9f5b1da. `git status --short` was clean before and after.

**Citations opened.** About 150 `path:line` citations, every one re-read in the repository (voice path, reply path, public_reply, stop gates, uncertain outcome, router, resilience, model recovery, tool loop, run retry, runs, messages, web Cards / Message / Markdown / RichResponse, mobile markdown and question component, CSS, reference HTML, policy text). All line numbers and short quotes matched except the items below.

**Corrected**
- F.2 and classification table row [10]: the claim that a failed tool result is `{"ok": False, "code": ...}` "and nothing else" was wrong. The runtime adds a `recovery` block (`environment.py:204-210`, classification `:80-81`), argument errors also carry `issues` and `retryable` (`tool_dispatch.py:114-116`), and production Part 4 #15/#17 show the `recovery` object.
- G.1: "eleven different causes" is ten: the table has eleven rows, one of which (timeout) is family `timeout`.
- G.1: the sentence that `git grep` for the title in efb4911 "finds nothing" was imprecise (it matches a different string by substring). Rewritten with the exact hits, plus the added fact that `run_retry.py` does not exist at efb4911 or aa50e8e.
- G.2: benching applies only to reasons with `bench_seconds` set, not to every failed candidate.
- F.3: "three renderers" followed by four numbered items; reworded. Added that `md()` (block text) also goes through `mdInline`, so lists in [16], [18], [35], [65] do not change the result, and that `RichResponse.tsx:271` is a further `ChatMarkdown` call.
- F.2 `waiting`: the overview state is `"waiting"` only when the agent is not paused, degraded, action-required or working (`agent_state.py:540-564`); stated precisely.
- Reproduction instructions: the driver is not idempotent (see the reproduction note at the top).

**TRACE MUST CONFIRM items checked**
- E.4 (a), (b), (c): (a) and (b) settled by the trace (seq 45/47 content; reply_language EMPTY); (c) narrowed by Q7 (no STT route, so `gpt-4o-mini-transcribe` first); only "did the whisper-1 fallback run" stays open, and the logs are gone.
- F.2 agent_inspect arguments and results: kept; Part 4 holds no `agent_inspect` call (only the reply text in Part 1).
- F.3 raw bubble text: kept (no raw assistant content in the trace).
- G.5: retry chain and "[1] never answered" settled by Part 1; credential presence at 16:44 kept (not in the trace); stored `failure` of the five runs downgraded to low value with the read-time fallback cited.

**Claims confirmed after trying to refute them**
- Root cause 9 (language hint = `OwnerProfileRow.reply_language`, empty gives no `language` field): confirmed, including `transcription.py` being unused (second grep over `.py/.md/.toml` for any import also finds none) and the ce92a10 regression (`-LANGUAGE = "ar"` in its diff; ce92a10 is an ancestor of 2477c22, not of aa50e8e; `git diff 2477c22 9f5b1da` over the voice and STT adapter paths is empty).
- No reply guard for language, codes, tool names or Markdown: re-read every module of the reply path; `git diff aa50e8e 9f5b1da` of `model_runtime.py` and `lonora.md` adds only suggested-reply handling, a generated-UI block, a @mention line and a reaction line. No counter-mechanism found.
- Raw `**` in [20]/[22] from the caption path (`Message.tsx:402-409` with `agent={false}`, `Markdown.tsx:277-281`): confirmed; both messages carry image attachments in the export.
- Option icons without size on web: `.opt-list`/`.opt-row` have no CSS in the repository (two greps: `grep -rn "opt-"` over css, and `grep -rn "opt-list\|opt-row"` over apps/packages/docs). The only global `button svg` rule is excluded inside `.app-shell` (`apps/web/src/styles.css:129`); `.mcard svg` rules exist only for the kicker (`conversation.css:307-310`). UNSURE: I did not render the page or confirm that the conversation is always inside `.app-shell` (the shell wrapper is `apps/web/src/shell/Shell.tsx:91`). The old `apps/web/src/components/conversation-question.tsx` is imported by nothing (grep of `conversation-question` over `apps/web/src`).
- [2]: all five failed runs are `model_not_configured` (trace Part 1); message composed in the web client (`Cards.tsx:73`, `:81`).
- [3]: only a client retry creates a new run for a failed message (`retry_of` has a single writer, `run_retry.py:132`).

**Reproductions rerun.** `conv_efg.py` on database 13 after truncating all tables: output identical to `runs/conv-EFG.out` apart from ids and timestamps (E: `"language": null` then `"ar"`; reply_language `latest_owner_message`; Turkish reply stored unchanged; F: only the UUID redacted and «أغهِقه» became «أغهقه»; G1 and G2 as described). Before truncating, a second run differed only in the E block as explained. `conv_efg_markdown.mjs`: output identical to `runs/conv-EFG-markdown.out`.

**Added**
- The `recovery` block and its content (above); production evidence that no candidate symbols were offered.
- Retry code absent at efb4911/aa50e8e, present at 2477c22.
- No STT route in production (Q7), so default models only.
- Note that the "F run metadata flags" output is not evidence.
- Expo: no caller of the retry endpoint found (UNSURE).

**Refuted or downgraded:** none of the nine classification rows was refuted. Downgraded: the "eleven causes" count, the "nothing else" claim about tool results, the unqualified `git grep` statement, the three TRACE MUST CONFIRM items now settled.
