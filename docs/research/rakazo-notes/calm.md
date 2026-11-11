# rakazo: "calm on the surface, strict inside" — where it is stated and what makes it true

Repository: rakazo at commit cd7e20e (read-only study). Paths are relative to the rakazo root.
Marks: **(stated)** = only in docs or prompt text; **(implemented)** = confirmed in code I opened.
Short path aliases used below: `A/` = `packages/adapters/src/`, `C/` = `packages/core/src/`.

## Headline finding

rakazo does **not** filter the model's final reply for tool names, error codes or "internal" wording. There is no such filter anywhere in the reply path. The calm surface comes from four other things:

1. **Channel separation.** Tool calls, tool status lines and step lists are separate message blocks from reply text, and the clients hide those blocks by default.
2. **Tool failures are written as sentences for the model**, each ending in what to do next ("Don't retry; tell the user"). The machine code is attached out-of-band and goes only to logs.
3. **Run failures are not chat messages.** They are a run error, mapped to a short fixed summary with one recovery button; the raw text sits behind a "Details" toggle.
4. **Requests for help are structured cards** (question, approval, secret, takeover, connect-app) that pause the run, rather than prose at the end of a reply.

Reply wording itself rests on prompt text plus offline LLM-judged evals, not on runtime enforcement.

---

## 1. Where the principle is stated

### VISION.md (stated)
- `VISION.md:37-43`, section "Calm on the surface, rigorous underneath":
  > "Chat shows the bot's response, useful progress, results, and genuine requests for help rather than its internal tool lifecycle." (`VISION.md:39`)
  > "Frontends express intent and render state while the backend owns orchestration, authorization, validation, retries, recovery, and provider translation." (`VISION.md:41`)
  > "Implementation complexity is acceptable only when it protects a real boundary or makes the user experience simpler and more reliable." (`VISION.md:43`)
- `VISION.md:10`: "A bot works in the background, returns with a result, and asks for help only when it needs information, judgment, authorization, or protected input."
- `VISION.md:12`: "Useful work lands in the destination where it belongs instead of ending as an unsupported claim in chat."
- `VISION.md:49`: "an automated review that errors or is unsure asks rather than silently acting."
- `VISION.md:51`: "Important effects are verified independently…"
- `VISION.md:60`: a change should be resisted when it "exposes internal machinery as user burden".

### PRODUCT.md (stated)
- `PRODUCT.md:17`: "One bot has one continuous visible thread … while internal runs and attempts remain implementation detail."
- `PRODUCT.md:18`: "A pending question or approval card never blocks a chat…"
- `PRODUCT.md:22`: the chat list has a regular view and an Activity view.

### AGENTS.md (stated; rules for contributors, not for the bot)
- `AGENTS.md:6`: "Keep UI and copy minimal. Show advanced capability progressively … do not add explainer text that repeats the interface."
- `AGENTS.md:7`: "Treat every visible word as UI. Start UX work by asking what can be removed…"
- `AGENTS.md:15`: natural-language meaning is judged "with an LLM and an explicit, versioned rubric"; "do not grade free-form prose with keyword lists, regexes, or exact wording." This is the stated reason there is no regex reply filter.

### docs/tool-activity.md (stated, and implemented — see 2b)
- `docs/tool-activity.md:8`: "Off by default, so chats stay clean."
- `docs/tool-activity.md:20`: "With the setting off, tool calls are hidden and only the bot's written reply shows."
- `docs/tool-activity.md:22-23`: the setting only changes what the client renders; stored messages are the same.
- `docs/tool-activity.md:31`: mobile always hides tool activity.

### docs/bots-and-chats.md (stated)
- `docs/bots-and-chats.md:51-53`: "When a bot needs something from you, it posts a card in the chat: a question, an approval, or a request to take over its screen. Cards never block the chat; you can answer later."
- `docs/bots-and-chats.md:88-89`: Activity "lists every run … Use it to find a run that failed or is waiting on you."

### docs/run-execution.md (stated)
- `docs/run-execution.md:64-66`: for first-response timing, "Reasoning, working placeholders, activity-only progress, and hidden metadata do not [count]." It treats activity lines as not being a response. Nothing else on the calm principle in this file.

### The bot's own prompts
I grepped `packages/adapters/src`, `packages/core/src`, `packages/contracts/src`, `apps/api/src`, `packages/adapter-kit/src` for "tool name", "jargon", "error code", "don't/never mention", "plain language", "non-technical", "technical detail", "internal …", "narrat…".

**Not found:** no instruction anywhere tells the bot "do not mention tool names", "do not show error codes", "use plain language" or "do not explain your rules". The prompt in `A/run-instructions.ts` actually names tools freely to the model (e.g. `A/run-instructions.ts:313`, `:319`).

What the prompts do say (all stated in prompt text, and wired into the system instructions at `A/run-instructions.ts:418` and `A/executor.ts:1768`):
- Progress, `A/run-replies.ts:11`:
  > "Send progress updates only when the work will take minutes … never for quick replies and never to announce that you are starting. … at most a few brief updates (a sentence or two each), not one per tool call, and do not narrate routine steps. Thinking stays private."
- "Messages" reply mode, `A/run-replies.ts:15`:
  > "Text you write while working is private and never shown to the person. … Your final answer, the text you write after your last tool call, is shown."
- `message_user` tool description, `A/builtin-tools.ts:608`: "Do not dump tool logs, thinking, or a play-by-play of every call."
- Act rather than claim, `A/run-instructions.ts:416`: "Prefer tools over claiming you already did the work." Also `:370` "Never claim the space exists before the tool succeeds." and `:376` "Never claim a change without the tool."
- Pages, `A/run-instructions.ts:409`: "mention the page by its title; never paste its source."
- On tool errors, `A/task-catalog.ts:29`:
  > "If a tool returns an error, do not repeat the same tool call with the same arguments. Correct the specific field once as a separate attempt; if that attempt fails, stop and explain the blocker instead of narrating more retries."
- Verify before reporting, `A/task-catalog.ts:27-28`: "Never mark work done before verification." / "call schedule_list and only report success when the routine is present."
- Silence, `A/run-replies.ts:18`: a routine with nothing to report must reply exactly `NO_RESPONSE`, with "no meta note that you are staying silent".
- Messaging surface, `C/messaging-prompts.ts:8`: "Keep replies concise. They arrive as chat messages."
- Base system prompt fallback, `A/pi-runtime.ts:374`: "…Be concise."

---

## 2. From failure to the owner

### (a) What the model sees when a tool fails (implemented)

Three shapes:

1. **A refusal before the tool runs** — a plain object `{ error: "<sentence>" }`. Built by `refusal(code, sentence)` at `A/tool-refusal.ts:7`. The code is stored in a `WeakMap` beside the object, never inside it:
   > "A refusal the model reads, tagged with a fixed code for the logs. The sentence can name bots, arguments or sites the run was given, so only the code is ever logged." (`A/tool-refusal.ts:3-6`)

   So the model never sees `tool_disabled` or `approval_denied`; it sees the sentence. Examples of the sentences:
   - `A/run-tools.ts:142`: "This tool is disabled for this bot."
   - `A/run-tool-gate.ts:399`: "… is blocked in this space…. Don't try it another way; tell the user it's blocked."
   - `A/approval-effect.ts:417-418`: "The user denied this action. Do not retry or rephrase it; tell the user and ask what they want instead."
   - `A/run-tool-gate.ts:387`: "This would complete a purchase, which needs the user's approval, and a webhook run cannot ask. Don't retry; tell the user."
   - Caveat: several of these sentences interpolate the raw tool name (`${name}` at `A/run-tool-gate.ts:399`, `:207`, `:580`), so the model can still repeat a tool name to the user. Nothing stops that.
   The code goes to the log only: `logToolRefusal` at `A/tool-completion-audit.ts:163-183` ("Only the code is logged").

2. **A tool that ran and failed** — the handler returns `{ error: "<message>" }` or an MCP result with `isError: true`. Connector errors are cleaned by `sanitizeConnectorError` (`A/connector-safety.ts:22-30`): bearer tokens and known secrets are redacted and the text is cut to 2,000 characters. This is **secret redaction, not de-jargoning**: a connector's own raw message and codes reach the model as-is. The result is then serialised as JSON text for the model by `serializeToolResult` (`A/pi-runtime-tools.ts:739-761`) with the raw object kept in `details` (`A/pi-runtime-tools.ts:649-663`). Failure is detected for auditing without altering what the model sees (`A/tool-result-error.ts:7-11`, function at `:12`).

3. **A tool that throws** — the wrapper records the failure and re-throws (`A/pi-runtime-tools.ts:677-679`). **Unsure** what text the model then sees: that conversion happens in the external agent library (`@earendil-works/pi-*`), which is not vendored and `node_modules` was not installed, so I could not open it. Argument-validation errors are also produced there; the code comments confirm the model does see them ("a rejected object would echo its raw value in the validation error the model sees", `A/pi-runtime-tools.ts:399-400`).

Other model-visible results worth copying: a skipped call says "Skipped: tool-call limit reached." (`A/pi-runtime-tools.ts:521`); an uncertain earlier execution says "it may already have completed, so verify the destination before retrying" (`A/run-effects.ts:330-334`).

Note on file names in the brief: `A/pi-tool-call-guard.ts` is **not** a repeat detector. It only drops tool calls whose name never arrived from the provider (`A/pi-tool-call-guard.ts:3-8`, `:70`). Repeat detection is `A/tool-loop.ts`. `A/builtin-tool-bridge.ts` is the find_tool/use_tool indirection for rarely used tools (`A/builtin-tool-bridge.ts:16-21`), not error handling. The `packages/adapter-kit/src/*-errors.ts` files define error classes; I read only their sizes and `model-errors` usage, not their bodies.

### (b) What the chat UI shows for a failed tool call (implemented)

- **By default: nothing.** A tool call becomes a `steps` block or an `activity` progress line. `isToolActivityBlock` (`C/tool-activity.ts:8-10`) marks both. Web renders a `steps` block only when the user turned on "Show tool activity", and never renders activity progress blocks inside a message (`apps/web/src/lib/tool-activity-view.ts:9-15`, `:25-28`). The preference defaults to off: "Only a saved 'on' shows tool cards. Missing or unreadable storage stays off so chats stay clean." (`apps/web/src/lib/tool-activity-preference.ts:5-8`). Mobile always filters these blocks out (`apps/mobile/lib/message-presentation.ts:44`, `:51`).
- **While running**, the user sees one working line: the latest activity line, else "Working…" (`apps/web/src/pages/shell/transcript.tsx:241-242`; `C/events.ts:377-384`).
- **Tool names are translated to human labels in three places:**
  - Live status line: `describeToolActivity` (`A/pi-runtime-tools.ts:214-282`), e.g. "Searching the web: …" (`:266`), "Reading the page" (`:251`), "Saving a note to memory" (`:264`). A connector tool uses its own `label` (`:225`). Details are secret-scrubbed and cut to 90 characters (`:189`, `:227-232`). **Fallback leaks the raw name**: `Using ${toolName}` (`:281`) and "Using <server>: <tool>" for MCP tools (`:279-280`).
  - Step list labels: `humanizeToolName` only swaps underscores for spaces and capitalises (`C/events.ts:525-530`), applied at `A/run-turn.ts:520-528`. So an opted-in user sees "Web search", "Browser act".
  - Voice: `narrateTool` maps names to phrases like "searching the web", and returns nothing for names starting `error:` (`C/speech-text.ts:191-233`, `:195`).
- **Failure of a single call is recorded but not surfaced.** Each call's outcome (succeeded/failed/stopped) is stored on its step (`C/events.ts:386-419`; set at `A/executor.ts:1931-1932`; a non-zero exit code counts as failed, `A/tool-completion-audit.ts:45-58`). I found only one consumer of `outcomes`: the text the bot itself reads back from its history (`C/attachments.ts:206-219`, `:221-227`). I found no client code that draws a failed step (search for "outcomes" in `apps/` found none) — **unsure** whether the web step card shows it some other way; I did not read `ToolActivityDisclosure.tsx` in full.
- The failure is also written to an audit event `agent.tool.completed` with the sanitised error (`A/tool-completion-audit.ts:60-77`, `:105-129`). That is a thread event, not a chat message.
- **There is no small model summarising tool activity.** Labels are deterministic string templates. The only summarising model calls I found are history compaction (`A/history-compaction.ts:452`) and the approval reviewer.

### (c) What the user sees when the whole run fails (implemented)

Path: the error is caught in `A/executor.ts:1977-1990` → `failRun` (`A/run-turn.ts:1012`) → `userRunError` strips it → stored as the run's `error` (`A/run-turn.ts:1040`, `:1059-1070`) → the web composer shows `normalizeRunError(...).summary`, with the full text behind a "Details" toggle (`apps/web/src/pages/shell/composer-error.tsx:119-121`, `:172`, `:207-213`). Any reply text already streamed is kept as a partial reply above the error (`A/run-turn.ts:1041-1057`).

So a run failure is **an error banner on the composer, not a bot message**. The reason is written down:
> "Shown as a failed-run error, not an assistant message. Asking the user to continue stores that sentence as the reply, and the next 'continue' runs tools and misses a final answer again." (`A/pi-runtime.ts:143-145`)

Server-side cleaning, `userRunError` (`C/run-error.ts:90-110`): database errors collapse to "Internal server error"; stack-frame lines are dropped; server file paths become "[path]". Its comment is honest: "Provider messages pass through" (`C/run-error.ts:91-93`). Provider text is separately scrubbed for keys by `sanitizeProviderError` (`A/pi-runtime-errors.ts:68-80`, `:149-155`).

Client-side mapping, `normalizeRunError` (`C/run-error.ts:233-560`): "Keep provider diagnostics available without exposing them in the visible summary" (`C/run-error.ts:225-226`).

Categories (`C/run-error.ts:223`, plus `kind` values seen in the function): recovery = `connection` | `model` | `plan`; kind = `auth`, `output`, `context`, `model`, and quota kinds `key` / `credit` / `spending` (`C/run-error.ts:133-152`). On the server the same classifier ranks failures as transient / model output / account / server fault (`A/pi-runtime-errors.ts:128-147`).

User-facing strings (verbatim):
1. "Something went wrong. Try again." (`C/run-error.ts:301`) — what "Internal server error" becomes.
2. "The model provider returned an error." (`C/run-error.ts:382`) — default when nothing else matches.
3. "{provider} rejected the API key. Check your connection settings." (`C/run-error.ts:325`)
4. "{provider} is rate limiting requests. Try again shortly." (`C/run-error.ts:400`)
5. "{provider} is overloaded right now. Try again in a moment." (`C/run-error.ts:528`)
6. "{provider} took too long to respond. Try again." (`C/run-error.ts:544`)
7. "The model returned an unusable response. Try again." (`C/run-error.ts:353`)
8. "The tools finished, but the model did not write a final answer. Rephrase the request and try again." (`C/run-error.ts:11-12`)
Also: "Connect a model in Settings before running bots." (`C/run-error.ts:35`); wait expiry "Stopped. This was still waiting for an answer." (`C/stuck-work.ts:69`).
Each fixable failure carries exactly one button: "Choose a model", "Replace key" / "Connect a model", or a billing action (`apps/web/src/pages/shell/composer-error.tsx:133-151`).

Where raw text **is** shown:
- The "Details" toggle shows the stored error text, i.e. the provider's own message (`apps/web/src/pages/shell/composer-error.tsx:207-213`).
- The failure push notification body is the stored message, not the summary (`A/run-turn.ts:1142-1148`; same in `A/run-lifecycle.ts:127-133`). So a provider message can reach a phone notification raw (minus stack, paths, secrets).
- A bot that asked another bot gets "Could not complete the delegated request: <message>" (`A/run-turn.ts:1105`).

Non-run errors (API calls from the client) use `userErrorMessage` (`C/user-error.ts:104-114`): a list of "technical" patterns — stack frames, JSON, `…Exception`, HTTP status dumps, `ECONN…` codes, **bare internal codes** like `SOME_CODE` (`C/user-error.ts:33-46`, line 42) — is replaced by the caller's fallback copy; unreachable server becomes "Could not reach the server" (`apps/web/src/lib/user-error.ts:37`). This is a real code filter, but it applies to **client error toasts, not to bot replies**.

Stops that **are** written into chat as a bot message (and do name the tool):
- Loop stop: "I got stuck calling <Tool name> with the same input N times in a row without making progress, so I stopped early. Try rephrasing this, or ask me to try a different approach." (`A/tool-loop.ts:7-10`, `:24-27`; published as the final text block at `A/run-turn.ts:633-650`). Note this ends in an offer, and names a humanised tool.
- Tool budget: "I stopped after reaching the limit of N tool calls in this turn. Send another message to continue." (`A/pi-runtime-tools.ts:825-827`, appended at `A/pi-runtime.ts:1208-1217`).
- Owner-settings refusal: "I can't change that here. Make the change in Settings, or ask me again in a fresh chat." (`A/approval-effect.ts:11-12`).

`A/run-recovery.ts` is not about user-visible errors: it decides which interrupted runs are blocked by a computer lease (`A/run-recovery.ts:13-22`).

### (d) Is there a server-side filter on the final reply text? (implemented — and the answer is mostly no)

What exists, in full:
- **Secret redaction** on every text and step block (`A/run-messages.ts:32-56`), on streamed text (`A/run-turn.ts:302`), and a hard stop "refusing to persist a secret in the thread" (`A/run-turn.ts:895-897`).
- **Silence sentinel stripping**: `NO_RESPONSE` is removed or turns the reply into no message (`A/silent-reply.ts:68-86`, `:130-142`; applied at `A/run-turn.ts:865-873`); a lone dot or ellipsis counts as "meant to say nothing" (`A/silent-reply.ts:106-114`).
- **Empty-reply handling**: a missing final answer after tools is nudged up to 3 times, then the run fails with string 8 above (`A/pi-runtime.ts:114-119`, `:902-917`, `:1228-1243`).
- **Mid-turn text handling**: text written before a tool call is treated as narration, not as the answer (`A/pi-runtime.ts:885-890`). It becomes a durable interim message only on long turns, capped (see section 3); otherwise it is kept out of the reply as a note on the step (`A/run-progress.ts:252-289`).
- **Voice only**: markdown is turned into speakable prose (`C/speech-text.ts:39-60`).
- **Thinking** never enters reply text: only "thinking started/stopped" flags cross the boundary (`A/pi-thinking-activity.ts:4-7`).

What does **not** exist: nothing strips or rewrites tool names, error codes, internal state names, rule explanations, or broken markdown in the final reply. I read `A/run-replies.ts`, `A/run-messages.ts`, `A/silent-reply.ts`, the reply path in `A/run-turn.ts` (lines 811-931) and grepped `A/pi-runtime-stream.ts`; none does this. **Calm replies rest on prompt + channel separation + UI defaults, not on a reply filter.** If the model writes "symbol_not_found" in its final answer, rakazo will show it.

---

## 3. How progress is shown without the tool lifecycle (implemented)

- **One live working line.** On each tool start the runtime emits a progress event with `activity: true` and the human label (`A/pi-runtime.ts:828-842`); the server forwards it as a `thread.progress` event (`A/run-turn.ts:309-341`); clients show it as the working indicator (`apps/web/src/pages/shell/transcript.tsx:241-242`). It is transient and never part of the stored reply.
- **The bot's own note can replace the tool label.** If the bot wrote a sentence before a step, that sentence (cut to 60 characters) becomes the working line (`A/user-progress.ts:13-22`; `A/run-progress.ts:320-341`), and stays until the bot writes again (`A/run-turn.ts:315-316`).
- **Durable interim messages are rationed.** Only after the turn has run 60 seconds, and at most 3 per run (`A/user-progress.ts:10-11`, `:54-55`, `:62-66`; `A/run-progress.ts:98-104`). Text over 500 characters is not promoted (`A/user-progress.ts:8`; `A/run-progress.ts:272-275`). An extra `message_user` call is accepted but not posted, and the model is told: "This update was not posted. The chat already has enough interim messages for this run…" (`A/run-tools-messaging.ts:276-286`). One exception: an immediate heads-up when browser/desktop work starts (`A/run-progress.ts:116-128`).
- **Routines and background runs show no progress at all** until the outcome is known (`A/run-progress.ts:225-234`; `A/run-turn.ts:314`).
- **No empty bubble**: if interim messages were posted and the final message would hold only hidden step blocks, it is dropped (`A/user-progress.ts:148-159`).
- **Thinking**: only an on/off indicator (`A/pi-thinking-activity.ts:4-7`, body `:8-29`).
- **Activity view**: a list of runs sorted into needs-attention / working / unread; "A question or forgotten queue wins over work, and an unread failure is something to look at." (`C/activity-sections.ts:10-20`).
- **Phone status card**: one row per bot with its latest step line (`A/work-activity.ts:16-36`).
- **No model is used to summarise activity** (see 2b). `A/coding-agent-activity.ts` is unrelated to chat: it checks whether a coding CLI on the bot's computer wrote session files recently, used by idle-sleep logic (`A/coding-agent-activity.ts:3-6`; caller `A/computer-idle.ts:498`).

---

## 4. "Genuine requests for help": the mechanisms (implemented)

| Need | Tool | What the owner sees | Where |
|---|---|---|---|
| A decision | `ask_user` | Question card with 2-4 tappable options, optional detail; run pauses (`waiting_input`) and a push "<Bot> needs an answer" is sent | definition `A/builtin-tools.ts:585-603`; pause `A/run-turn.ts:398-445` |
| Permission for an action | none (automatic) | Approval card "Review before <action>" with Allow once / Always allow / Deny | gate `A/run-tool-gate.ts:151`; card `A/run-tool-gate.ts:788-842`, `A/approval-ask.ts:53-65`, `:194-226` |
| A password or key | `request_secret` | Masked-field card; the model never sees the value | `A/builtin-tools.ts:43-50`, `:626-636` |
| The owner at the screen (CAPTCHA, payment, passkey) | `request_takeover` | Takeover card + push "<Bot> needs you on the screen" | `A/builtin-tools.ts:564-571`; `A/run-turn.ts:503-509` |
| An unconnected app | `connect_app` | Inline connect card | `A/builtin-tools.ts:574-582` |
| A short heads-up, no answer needed | `message_user` | A normal short chat message; does not end the turn | `A/builtin-tools.ts:605-609` |

Text the bot wrote just before asking is posted whole, ahead of the card, because "a paused run never reaches the final reply that would bring held notes back" (`A/run-progress.ts:291-318`). Unanswered waits get one reminder after 4 hours and are cancelled after 24 (30 minutes for takeover) (`C/stuck-work.ts:5-13`).

Leak worth knowing: the default approval card title and push body use the **raw tool name**: `Review before ${summary}` where summary falls back to `toolName` or `toolName → target` (`A/approval-ask.ts:199`, `:253-254`; push body `A/run-tool-gate.ts:837`), and the card detail lists every argument as `key: value` lines (`A/approval-ask.ts:303-306`). Fleet tools get a purpose-built title instead (`A/approval-ask.ts:67-72`).

Prompt rules on **when to ask versus act** — these are thin and scattered; there is no single "act first, never offer" rule:
- `A/builtin-tools.ts:587`: "Use this instead of asking them to type when two to four concise choices are enough."
- `A/run-instructions.ts:313`: "Use connect_app when an app needs connecting or the user asks to connect one, then wait for them."
- `A/run-instructions.ts:319`: "Use request_takeover when the user must provide protected input or human judgment, or operate the screen."
- `A/run-instructions.ts:227`: "Never ask for a raw credential in chat or inject it into shell commands."
- `A/run-instructions.ts:251`: "Do not wait to be asked about open loops. … Never follow up on something the user declined."
- `A/run-instructions.ts:11` (voice): "do not use ask_user unless you truly cannot proceed."
- Automatic nudge after a silent tool turn, `A/pi-runtime.ts:118`:
  > "If you need information or a decision from the user, ask them instead of guessing; otherwise use any remaining tools needed, then give the user the final answer."
- After a denial, `A/approval-effect.ts:418`: "…tell the user and ask what they want instead."
- `VISION.md:10` gives the four legitimate reasons to ask: information, judgment, authorization, protected input (stated).

---

## 5. "Strict inside": enforcement the user never sees (implemented unless marked)

- **Tool gating and approval classification** — `A/run-tool-gate.ts:147-155`: every resolved call is decided as run / ask the owner / reviewed by a model / refused, and its effect is recorded first. Blocked calls are refused with a sentence and no card (`A/run-tool-gate.ts:391-402`). Before the gate, `A/run-tools.ts:125-179` refuses disabled tools, tools not allowed for the run type, and name collisions. Every consequential call is written to the audit log with success/failure (`A/run-tools.ts:182-192`; `A/run-tool-gate.ts:689-690`).
- **Automatic review fails closed** — a reviewer that errors on a consequential action becomes "ask" (`C/action-approval.ts:621-628`; catch branch `A/run-tool-gate.ts:943-951`). Matches `VISION.md:49`.
- **Repeat detection** — `A/tool-loop.ts:37-42`: 6 identical failing calls in a row, or 25 near-identical ones, mean "stuck"; calls whose answers keep changing restart the count (`A/tool-loop.ts:111-117`). More than 24 actions in one computer/browser batch is refused, and 4 such batches in a row end the run (`A/tool-loop.ts:45-49`). Enforcement at `A/run-turn.ts:552-583`. A repeat of an action the user denied is refused outright (`A/run-tool-gate.ts:498-507`).
- **Tool-name guard** — `A/pi-tool-call-guard.ts:3-8`: nameless tool calls from a gateway are dropped before the next request so the provider does not reject the transcript.
- **Limits** — `A/pi-runtime-limits.ts:6`, `:8`, `:14`: 120 s to first headers, 30 s connect, 180 s stream silence; tool result text is cut at 12,000 characters (`A/pi-runtime-limits.ts:69`). Optional per-turn tool-call cap via `MAX_TOOL_CALLS_PER_TURN` (`A/pi-runtime-tools.ts:65-68`, `:925-935`).
- **Effect records and idempotency** — `A/run-effects.ts:25-26` tracks each side effect through approved / executing / uncertain / completed; a superseded attempt is refused before its tool runs (`A/run-effects.ts:289-290`); an uncertain earlier execution tells the model to verify the destination before retrying (`A/run-effects.ts:330-334`). An approved action that the model then fails to run is a run failure: "The model did not run the approved action. Try again." (`A/approval-effect.ts:77`; `C/run-error.ts:15-16`). I did not read `A/approval-effect.ts` beyond lines 9-50, 77 and 417-418.
- **Verification of effects (stated)** — `docs/agent-verification.md:171-172`: "Grading reads the website's own records … and Rakazo state …; the bot's claims are not evidence." `:259-260`: "A model's claim of completion is not sufficient." This is the offline test harness, not a runtime check.
- **Parameter validation and repair** — arguments are coerced per tool before validation, e.g. a missing `ask_user` options list is left invalid on purpose "so schema minItems can reject it" (`A/pi-runtime-tools.ts:383-410`); remote schemas the validator cannot express "degrade to a permissive object instead of failing every turn for the whole bot" (`A/pi-runtime-tool-parameters.ts:50-51`); provider-incompatible schemas are normalised at the adapter boundary (`A/openai-tool-parameters.ts:1-9`).
- **Recovery** — setup failures retry up to 8 times with back-off before the run fails (`A/run-lifecycle.ts:167-168`, `:199-209`); lease fencing stops an old attempt writing (`A/run-turn.ts:249-273`); `A/run-recovery.ts:13-22` keeps resource waits intact and expires abandoned takeover holds. Model-side fallback and continuation after a cut reply live in `A/pi-runtime-fallback.ts`, which I only grepped.

---

## 6. Does rakazo detect bad replies at runtime? (searched honestly)

Searches run over `packages/adapters/src`, `packages/core/src`, `apps/api/src`, `scripts` for: "unsupported claim", "overclaim", "claimed", "claims done/completion", "if you want", "would you like me", "offer", "inability", "can't do that".

- **A reply that claims "done" without a successful tool result: not found at runtime.** No code compares the final reply against tool outcomes. The closest runtime pieces are indirect: (1) per-step outcomes are stored and fed back into the bot's own history so a later turn knows what really happened (`C/attachments.ts:206-227`); (2) prompt rules "Never claim … before the tool succeeds" (`A/run-instructions.ts:370`, `:376`, `:416`) (stated); (3) `schedule_create` guidance to list and confirm before reporting (`A/task-catalog.ts:28`) (stated).
- **A reply that ends in an offer instead of acting: not found.** No detector, and no prompt rule against it. rakazo's own loop-stop message ends with an offer (`A/tool-loop.ts:9-10`).
- **A claim of inability when a tool exists: not found at runtime.** The nearest thing is the prompt telling the bot to consult `task_catalog` "before claiming a task or skill exists" (`A/builtin-tools.ts:1227`) (stated).
- **What does exist: the opposite direction, structurally.** A turn that used tools and then wrote nothing is nudged, then failed (`A/pi-runtime.ts:902-917`, `:1233`); a delegated turn whose only text is the synthetic empty notice is failed rather than reported as success (`A/run-replies.ts:100-104`; `A/run-turn.ts:898-907`).
- **Offline only:** an LLM-judged eval suite grades replies for overclaiming, false confession, unprompted doubt, and "a reply laid out as a log of tool steps" (`packages/testkit/src/evals/recall.ts:74-75`, `:118`, `:122-123`; described in `docs/agent-verification.md:555-570`). This runs in tests against real models, never on live replies, and `AGENTS.md:15` forbids doing it with keywords or regexes.

---

## What this means for Lonora (inferred from the above, not a rakazo claim)

- The symptom "error code in the reply" is prevented in rakazo mainly at the **tool-result** layer: the model is handed a sentence with a next step, and the code is kept out of the object entirely (`A/tool-refusal.ts:3-7`). A model cannot repeat a code it never saw.
- The symptom "explains its guard rules" is reduced because refusals are short and end in an instruction ("Don't retry; tell the user"), and because run-level failures never become assistant text (`A/pi-runtime.ts:143-145`).
- The symptom "ends with an offer" has **no** rakazo answer in code or prompt. The only lever rakazo has is the offline judge suite.
- rakazo still leaks raw tool names in three user-visible places: the `Using <tool>` fallback (`A/pi-runtime-tools.ts:279-281`), the default approval card and push (`A/approval-ask.ts:199`, `:253-254`; `A/run-tool-gate.ts:837`), and model-facing refusal sentences (`A/run-tool-gate.ts:399`).

---

## Not read / unsure

- **External agent library** (`@earendil-works/pi-ai`, `pi-agent-core`): not present on disk. Unsure exactly what text the model receives when a tool throws or when argument validation fails.
- `packages/adapter-kit/src/*-errors.ts`: bodies not read (only sizes, and `model-errors` via its use in `A/pi-runtime-errors.ts`).
- `A/pi-runtime-stream.ts` and `A/pi-runtime-fallback.ts`: grepped, not read in full. I found no reply-text filter in either, but did not read every line.
- `A/approval-effect.ts`: read lines 9-50, 77, 417-418 only. `A/run-effects.ts`: read the outline and lines 320-334 only.
- `A/run-tool-gate.ts`: read lines 147-230, 380-420, 495-585, 788-980; the middle (approval-plan computation, lines 230-380 and 585-690) not read.
- `A/work-activity.ts`: read lines 1-120 only; how the step "line" is derived was not traced.
- `apps/web/src/components/ToolActivityDisclosure.tsx`: only grepped. Unsure whether the opted-in step card shows a failed marker; I found no client use of `outcomes`.
- Mobile clients: only `apps/mobile/lib/message-presentation.ts:44-51` and one line of `thread-screen.tsx` checked. Messaging-app delivery (Slack, SMS, etc.) of run errors not traced.
- Built-in skills, bot templates and the "Rakazo skill" text (`A/builtin-skills.ts`, `C/bot-templates.ts`) were not read for reply-style rules; a targeted grep for "plain", "jargon", "technical", "step log" in adapters/core found none.
- `docs/agent-verification.md` (833 lines): read lines 166-176, 256-280, 552-572 only. `docs/run-execution.md`: read lines 56-100 only.
- `docs/zh-CN`, `docs/th-TH`, `docs/evals`, `apps/www`: not read.
- Line numbers for `A/run-instructions.ts` long lines were read truncated to ~1,400-1,700 characters; quotes come from the visible part of each line.
