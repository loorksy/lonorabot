# Conversation groups B and C-part-1: offers instead of action, short approvals ignored, claims with no effect, conditions not turned into triggers, stale reads. Root cause 8.

Repository `/home/user/lonorabot`, `main` at `9f5b1da`. Read-only audit; nothing under the repository was changed (`git status --short` is empty after every run). All paths are relative to the repository root. Messages of the production conversation are cited as `[n]`.

No production run trace was available. Conclusions come from the code and from scripted runs against the real runtime. Anything only the production database can settle is marked **TRACE MUST CONFIRM**.

## 0. Method and evidence files

| What | File |
| --- | --- |
| Offer count over the chat export | `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/bc_count_offers.py`, output `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/bc_count_offers.out` |
| Scripted runs (real `execute_run`, real tool registry, real gates, PostgreSQL database `audit_j10_test`, simulation broker, signed full delegation for the Personal Agent) | driver `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/bc_offers_conditions.py` |
| Its output on a freshly migrated database | `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/bc_offers_conditions.clean.out` (cited below as `clean.out:<line>`) |
| Its output when run a second time on the same database (shows tool promotion) | `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/bc_offers_conditions.second.out` (`second.out:<line>`) |
| The one text pattern about effect claims, tested on the chat's sentences | `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/bc_effect_claim_regex.py`, output `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/bc_effect_claim_regex.out` |

In the scripted runs every model turn is written by the driver and labelled SCRIPTED. The evidence is what the runtime did with it: the tool list it offered, the tool results, the runtime notices (none), the committed reply and the stored rows. The scripted runs do not show what a real model would choose; they show what the harness allows, blocks or changes.

What changed between PR #42 (`aa50e8e`) and `9f5b1da` in the mechanisms of this report: nothing in `stop_gates.py`, `uncertain_outcome.py`, `loop_outcomes.py`, `context/financial_result.py`, the six constitution files, the bootstrap files, the `Watch` and `TradeRequest` contracts (`git diff --stat aa50e8e 9f5b1da` over those paths lists none of them). New on `main` after `aa50e8e`: the next-reply suggestion (`packages/agent-runtime/src/lonora_agent/suggested_reply.py`, `packages/agent-runtime/resources/prompts/suggested_reply.md`; both absent at `aa50e8e`), taint marks on watches, and `web_search` exposure per chat. So for groups B and C-part-1 the classification on `main` does not depend on which of the two builds production served, with one exception noted in 2.3.

---

## 1. How many replies end with an offer

Counted by script over the export (`runs/bc_count_offers.out`), then checked by reading each reply.

- Lonora text replies (cards and the system notice excluded): **37**: [4] [6] [8] [10] [12] [14] [16] [18] [20] [22] [24] [26] [29] [31] [33] [35] [37] [39] [41] [43] [45] [47] [49] [51] [53] [55] [57] [59] [63] [65] [69] [71] [73] [75] [77] [79] [81]. This matches the owner's 37.
- Replies whose last paragraph is an offer: **26 of 37**.
  - **22** carry an explicit marker («إذا تريد», «إذا أردت», «قل لي فقط», Turkish «İstersen»): [10] [14] [16] [18] [20] [22] [24] [26] [29] [35] [37] [41] [51] [53] [55] [59] [63] [65] [71] [75] [77] [81].
  - **2** are conditional offers without that marker («إذا تقصد … أبحث … فورًا», «إذا قصدك إيقاف المتابعة، أوقفها الآن»): [12] [45].
  - **2** offer alternatives with «أقدر …» and no marker: [31] [73].
- Not offers (11): [4] [6] [8] [33] [39] [43] [47] [49] [57] [69] [79]. Of these [39] [43] [47] [57] are claims of an automatic close or of monitoring, and [69] is a promise («سأحذف»).

The owner's "about 25 of 37" is confirmed: 22 by the strict marker, 26 with the four unmarked offers.

What the offered step was, for the offers in groups B and C-part-1:

| Reply | Offered step | Kind of step |
| --- | --- | --- |
| [14] | current price and direction | read |
| [16] | buy/sell/wait reading | read and analysis |
| [18] | conditional entry plan | analysis |
| [20] [22] | more charts, read the charts | read |
| [24] | "give me a lot size and I execute" | financial, inside the signed delegation (group D) |
| [26] | follow it, or add stop/target | watch (not financial) or `modify_position` (inside the delegation) |
| [29] | "review the current price" | read |
| [35] [37] | "conditional close order" or follow it | watch, or `modify_position` (inside the delegation) |
| [41] [53] | put it under a follow-up until +100 | watch |
| [45] [55] | stop following / another level | watch control / parameter |
| [59] [63] | review gold now | read |

Every offered step in this table is either a read, a non-financial watch, or a position change inside the signed full delegation. None needed a new permission.

---

## 2. What in the code pushes toward offers

### 2.1 Policy text that is always in the prompt

The mandatory core (`packages/agent-runtime/resources/system/lonora.md:9-165`) and the six constitution files are in every request.

Lines that teach or allow the offer ending:

- `packages/agent-runtime/resources/system/lonora.md:33`: `Give at most one specific useful next suggestion when a suggestion is warranted.` This is the shape of «إذا تريد، …» at the end of 22 replies: exactly one next suggestion.
- `packages/agent-runtime/resources/system/lonora.md:30`: `Start with the result, the actual finding, or the single fact preventing completion.`
- `packages/agent-runtime/resources/system/lonora.md:163`: `Report the practical failure and one concrete next step, preserving the distinction between unavailable and uncertain.`
- `packages/agent-runtime/resources/system/lonora.md:36`: `An acknowledgment is not completion; finish the actual work or state its precise remaining obstacle.` (stating an obstacle is given as an equal way to end).
- `packages/agent-runtime/resources/bootstrap/SOUL.md:10`: `Stay friendly and curious — I'd rather ask a good question than guess wrong.`
- `packages/agent-runtime/resources/system/lonora.md:119`: `For a direct factual question, answer it directly when grounded information is already available.` (relevant to [29], section 6).
- `packages/agent-runtime/resources/system/lonora.md:143`: `Once a decision is pending, do not execute the dependent action speculatively.` (does not separate reads from financial actions).

Lines that push the other way, all prompt-only:

- `packages/agent-runtime/resources/bootstrap/SOUL.md:7`: `Solve by doing, not by describing what I would do.`
- `packages/agent-runtime/resources/system/lonora.md:34`: `Do not end every answer with a question or a menu of possible follow-ups.` ("every" leaves room for "most"; 26 of 37 did.)
- `packages/agent-runtime/resources/system/lonora.md:35`: `Continue authorized work without asking whether to begin or making the owner repair internal arguments.`
- `packages/agent-runtime/resources/system/lonora.md:135`: `Do not ask the owner whether to perform analysis, inspect a chart or build a plan they already requested: do that reversible work first.` (limited to work "they already requested").
- `packages/agent-runtime/resources/constitution/tool-policy.md:3`: `Understand natural language intent and continue the already requested reversible work in the same turn.`
- `packages/agent-runtime/resources/system/lonora.md:130`: `A short reply continues the preceding request; do not treat it as an isolated new task or forget a previously chosen side.` This is the only text about short replies. It says "continues the preceding request"; it does not say "is consent to the offer you just made".

Missing, stated plainly: there is no line in any loaded prompt that says "when the next step is a read, or is inside the signed delegation, and serves the owner's open request, do it in this turn instead of offering it", and no line that says "a short yes after your offer means do that offered step". A case-insensitive search for `if you want`, `would you like`, `إذا تريد`, `إذا أردت`, `قل لي` over `packages/agent-runtime`, `packages/tools` and `packages/core` (`*.py`, `*.md`) returns no hit, so there is also no counter-example of the offer ending.

### 2.2 The financial-authority section and the watch wording

These are money-safety text and must stay, but two of them are written so that a model can read "a watch cannot lead to a close":

- `packages/tools/src/lonora_tools/market_watch.py:239` (the `watch_create` description): `It wakes this agent to reassess and never trades.`
- `packages/agent-runtime/resources/system/lonora.md:620`: `Persist a relevant watch or Task timer wait before promising monitoring. Wake, inspect fresh evidence and decide again; a condition or wake never submits a trade by itself.`
- `packages/agent-runtime/resources/system/lonora.md:237`: `A watch detecting a price condition wakes reassessment; it is not automatic permission to trade.`
- `packages/agent-runtime/resources/skills/market-watch/SKILL.md:18`: `A trigger wakes analysis, never execution directly.`
- `packages/agent-runtime/resources/system/lonora.md:108`: `Do not turn an analysis/watch step into a trade step silently.`

All five are true of the watcher process (it only creates a run). None of them adds the other half that the code also makes true (section 5.3): the woken run has the agent's full authority and can close the position under the signed delegation. Nothing in the prompt tells the model "to close at a profit level, create a position watch whose prompt carries the close instruction, or set a take-profit". The reply [41] «أضعه تحت متابعة حتى يصل +100 USD ثم أتعامل معه» is consistent with a model that knows a watch only "wakes to reassess".

Where these lines live also matters. `lonora.md:237` is in the `market` chapter and `lonora.md:433-435` (`Use watch_create/watch_list for supported market/account/position/calendar/composite conditions.`) is in the `tasks` chapter. Chapters are added only after a tool of that chapter was called within the last 16 messages of the same run (`packages/agent-runtime/src/lonora_agent/skills/system_policy.py:134-142`). On the first model turn of a chat run there is no chapter, so the first turn that reads «راقبه بس صار ربح 100 دولار سكره» has only the core lines `lonora.md:38` (`Never fabricate progress, percentages, waiting times, or a continuing check that is not scheduled.`) and `lonora.md:127` (`Use actual watches, schedules or task waits for future work; do not promise to remain awake by thinking continuously.`).

### 2.3 `suggested_reply`: a mechanism that rewards the offer ending (new on `main` after PR #42)

- Prompt, added to every run the owner starts by typing (`packages/agent-runtime/src/lonora_agent/context/builder.py:129-131`): `packages/agent-runtime/resources/prompts/suggested_reply.md:2`: `You may end a conversational answer with one trailing tag on its own last line: <suggested_reply>what the owner would most likely say next</suggested_reply>. … add it only when one natural next reply is clear. Never add it after a card, an approval, a question you asked, a generated interface or a refusal, and never more than one.`
- Code: `packages/agent-runtime/src/lonora_agent/suggested_reply.py:31-43` strips the tag and keeps a trailing suggestion of at most 60 characters; `packages/agent-runtime/src/lonora_agent/model_runtime.py:222-224` drops it when the turn has tool calls; `packages/db/src/lonora_db/runs.py:336-357` stores it on the message only for a conversational answer with no card.

Effect: the one reply shape for which "one natural next reply is clear" is a reply that ends with an offer (the natural next reply is «ياريت» / «نعم»). The feature gives that shape a visible one-tap chip. It is stored as display data on the message (`packages/db/src/lonora_db/messages.py:70`); no code reads it back as "the offer that is waiting" when the owner's next message arrives (the only readers are the listed files). So `main` adds an incentive for the offer ending and still has no handling of its acceptance.

This file did not exist at `aa50e8e`. **TRACE MUST CONFIRM** which build served the conversation; if it was `aa50e8e`, the 26 offer endings happened without this prompt, and on `main` the pressure is higher, not lower.

### 2.4 `stop_gates.py`: what the gates check today

`packages/agent-runtime/src/lonora_agent/stop_gates.py` has exactly two gates, and both apply only to a run that belongs to a Task:

- `task_stop_gate` returns "do not continue" at once when the run has no Task: `task_progress` returns `None` when `run.model_metadata.get("task_id")` is empty (`packages/agent-runtime/src/lonora_agent/stop_gates.py:153-155`), and `task_stop_gate` then returns `StopGateVerdict(continue_turn=False)` (`packages/agent-runtime/src/lonora_agent/stop_gates.py:178-181`).
- For a Task run: a continuous Task that ends with text and no saved wait gets the nudge `CONTINUOUS_NUDGE` (`packages/agent-runtime/src/lonora_agent/stop_gates.py:45-54`, code `task_wait_required`), and a finite Task with unfinished declared steps gets `_steps_nudge` (`packages/agent-runtime/src/lonora_agent/stop_gates.py:72-83`, code `task_steps_incomplete`); at most `MAXIMUM_STOP_NUDGES = 2` (`packages/agent-runtime/src/lonora_agent/stop_gates.py:41`), then the Task is handed to the owner (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:175-178`).
- The module states its own limit: `No text classifier decides whether monitoring exists: the successful wait path settles it.` (`packages/agent-runtime/src/lonora_agent/stop_gates.py:95-96`). The gates never read the reply text.
- The test `tests/test_continuous_stop_gate.py:19` is named `test_finite_work_and_conversations_keep_their_completion_semantics`: a conversation run is deliberately left ungated.

Is there a gate for "the reply ends with an offer of a read-only step"? **No.** No gate reads the reply, no gate knows which tools were available, and for a chat run no gate runs at all.

How a chat run ends, in code: when a model turn returns text and no tool call, the loop calls `final_answer` (`packages/agent-runtime/src/lonora_agent/tool_loop.py:590-611`). `final_answer` applies the Task gate (no Task, so nothing), then the uncertain-outcome line (section 3), and returns the text as the outcome (`packages/agent-runtime/src/lonora_agent/loop_outcomes.py:170-184`).

Reproduced: a SCRIPTED reply that is only an offer is committed unchanged with zero tool calls and zero runtime notices (`clean.out:65-74`).

---

## 3. "تم" with nothing done, and "automatic close" with nothing armed

### 3.1 Every check that touches a final reply, and what each one reads

| Check | Where | Reads | Fires when |
| --- | --- | --- | --- |
| Task stop gates | `packages/agent-runtime/src/lonora_agent/stop_gates.py:86-129` | Task state only | the run belongs to a Task (section 2.4) |
| Uncertain-outcome line (PR #42) | `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:78-112` | structured results of `trade_execute`, `trade_close_positions`, `goal_step_execute` in this request | a financial call was made and its latest status or code is one of `ambiguous`, `operation_ambiguous`, `tool_execution_uncertain`, `submitted`, `reserved`, `broker_result_ambiguous` (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:23-33`); only in a run the owner started (`:22`, `:47`) |
| Financial-truth gate | `packages/agent-runtime/src/lonora_agent/model_runtime.py:218-238`, `packages/agent-runtime/src/lonora_agent/context/financial_result.py:70-126` | proposed financial calls of this turn, and the results of financial calls since the owner's last message | the turn proposes a financial call (text is emptied, `model_runtime.py:225-228`), or a financial result is `confirmed` but not `verified` (text is replaced, `model_runtime.py:229-232`, `financial_result.py:110`) |
| Privacy redaction | `packages/agent-runtime/src/lonora_agent/model_runtime.py:246`, `packages/core/src/lonora_core/public_reply.py:54-67` | the reply text | credentials, private paths, private resource ids |
| Effect-claim pattern | `packages/agent-runtime/src/lonora_agent/public_stream.py:11-19`, `:47-51` | the partial reply text while streaming | a phrase such as «تم تنفيذ», «تم شراء», «فتحت صفقة», `Done.`: it only switches off incremental streaming for that turn; the final text is still published (`packages/agent-runtime/src/lonora_agent/model_runtime.py:288-291`) |
| Policy sentence (PR #42) | `packages/agent-runtime/resources/constitution/trading-policy.md:7` | nothing; it is prompt text | never enforced: `Say something was done only when a successful tool result in this request shows it.` |

What `uncertain_outcome.py` does, exactly: its own header says `Structured results only: no wording of the owner or the model is read.` and `The reply and its card are never replaced.` (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:3`, `:9`). It appends one line, `LINE_AR = "نتيجة العملية غير مؤكدة بعد؛ أتحقق منها ولن أعيد إرسالها."` (`:36`). It builds its set of calls only from the three financial tool names (`:85-90`). With no financial call in the request there is nothing to inspect and `uncertain_line` returns `None` (`:115-118`).

So there is **no guard for a claim without a tool result**. Each existing guard starts from a tool result that exists. A reply that claims an effect with no tool call at all gives none of them anything to read:

- [37] «تم.» after «طيب»: no tool call, or only a read. Not a Task run, no financial call, no financial result. Nothing fires.
- [39] «ما زال بعيدًا عن الإغلاق الآلي حسب الخطة»: same.
- [43] «مراقب… إذا وصل لهذا المستوى، أغلقه فورًا», [47] «فأنا أتابعه», [57] «أراقب XAUUSDm»: `watch_create` is not in `FINANCIAL_EFFECTS` or `FINANCIAL_CALLS` (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:23`, `packages/agent-runtime/src/lonora_agent/context/financial_result.py:9`), and no check compares "I am watching" with the stored watches.

The effect-claim pattern does not match any of these sentences either (`runs/bc_effect_claim_regex.out`): [37], [39], [43], [47], [57], [63] give `EFFECT_CLAIM matches: False`; only the true [26] «تم شراء…» matches, and even there the pattern only delays streaming.

### 3.2 Reproduction

All on the real loop, Personal Agent, signed full delegation, open 0.01 XAUUSDm buy.

1. Owner «هدف ربح 2 دولار، وخسارة 1 دولار»; SCRIPTED reply ends with the offer «إذا تريد، أضع لك أمر إغلاق مشروط أو أتابعه لحظة بلحظة على هذا المستوى.» Committed unchanged (`clean.out:65-74`).
2. Owner «طيب»; SCRIPTED reply «تم. المركز الآن ربحه +1.14 USD. الهدف: +2 USD. الحد: -1 USD.» with **no tool call**. Result: run `completed`, `reply_outcome: answered`, tool calls `[]`, runtime notices `NONE`, the text committed unchanged, `did any guard change or hold the reply?: False` (`clean.out:76-86`). After it the position has `stop_loss=None take_profit=None` and there are 0 watches (`clean.out:111`).
3. Owner «تمام»; SCRIPTED `account_read`, then «تم التحقق: … ما زال بعيدًا عن الإغلاق الآلي حسب الخطة.» Committed unchanged; 0 watches, no stop, no target (`clean.out:113-125`).
4. Owner «راقبه بس صار ربح 100 دولار سكره»; SCRIPTED `account_read`, then «مراقب. … إذا وصل لهذا المستوى، أغلقه فورًا.» with **no `watch_create`**. Committed unchanged; `watches after the claim: []`; `did any guard change or hold the reply?: False` (`clean.out:127-140`).

No guard fired in any of the four.

### 3.3 Why PR #42 did not catch them

PR #42 added (a) the uncertain-outcome line, which needs a financial call with an uncertain status, and (b) one policy sentence (`packages/agent-runtime/resources/constitution/trading-policy.md:7`, shown by `git diff aa50e8e^1 aa50e8e`). Reply [73] («ولا أقدر أدّعي الإلغاء بدون رد أداة ناجح») paraphrases that sentence, which suggests the PR #42 prompt was live at 11:53 Damascus time. **TRACE MUST CONFIRM** the deployed build. If it was live, then [37], [39], [43], [47] show the sentence did not stop the claims an hour earlier: it is advice to the model, not a check.

---

## 4. Short approvals: «طيب», «تمام», «ياريت», «تم», 👍

What the runtime does with a short message, in code terms:

- It is an ordinary owner message. If no run is active it starts a new run with trigger `user`; the context is rebuilt from the thread's prose history. The offer is present only as the previous assistant message. Reproduced: the request for «طيب» ends with `assistant: "إذا تريد، أضع لك أمر إغلاق مشروط…"`, `user: "طيب"`, and contains no structured pending-offer field (`clean.out:87-110`).
- The only instruction is `lonora.md:130` (quoted in 2.1). Nothing checks that the run after a short approval performs the offered step, or any step.
- A 👍 reaction by the owner ([41], [43]) is stored and nothing else: the route calls `owner_reaction` (`apps/api/src/lonora_api/routes/messages.py:76-78`), which writes the reaction row (`packages/db/src/lonora_db/reactions.py:94-104`). It starts no run. The agent's history is built from message content (`packages/agent-runtime/src/lonora_agent/context/history.py:194-198`); reactions are loaded only for client pages (`packages/db/src/lonora_db/messages.py:112-116`). So the agent never sees the owner's 👍.
- A tap on a card follow-up button is stored with origin `ui_follow_up` (`packages/db/src/lonora_db/messages.py:89-91`) and is shown to the model as `[owner_via_card]` (`packages/agent-runtime/src/lonora_agent/context/history.py:22-23`), deliberately not as the owner's own words (`packages/db/src/lonora_db/owner_words.py:5-8`). This is a money-safety choice for owner-words checks (full delegation, supervision). It also means the two existing "one tap" paths (follow-up button, suggested reply) carry no record of which offer they accept.

In the conversation:

| Short message | Offer it followed | What the next reply did |
| --- | --- | --- |
| [15] «ياريت» | [14] price and direction | [16] gave price and direction, then offered again |
| [17] «ياريت» | [16] buy/sell/wait reading | [18] gave it, then offered again |
| [36] «طيب» | [35] conditional close order, or follow it | [37] «تم» plus a status read; no order, no watch |
| [38] «تمام» | [37] follow and close at +2 / -1 | [39] a status read and "automatic close per the plan" |
| [42] «تمام» (and 👍 on [41]) | [41] put under a follow-up until +100 | [43] «مراقب… أغلقه فورًا»; [59] later shows no watch on XAUUSDm |
| [44] «تم» | none ([43] was a claim) | [45] read it as a possible request to stop following |
| [54] «طيب» | [53] follow until the target, or a nearer close point | [55] no read («آخر ربح متحقق»), asks for another number |

[15] and [17] were honoured, but each cost the owner one extra message for a read. [36], [38], [42], [54] were not honoured. [44] shows the reverse risk: with no record of what is pending, a bare «تم» has nothing to attach to.

---

## 5. «راقبه بس صار ربح 100 دولار سكره» [40] [46] [52]: root cause 8

### 5.1 Root cause 8 is confirmed: the tools exist

| Claim of the brief | Evidence |
| --- | --- |
| `watch_create` supports `kind=position` | `packages/contracts/src/lonora_contracts/market_watch.py:15` |
| `position_id` | `packages/contracts/src/lonora_contracts/market_watch.py:37`; required for a position watch: `:74-75` (`watch_position_required`) |
| `metric=profit` | `packages/contracts/src/lonora_contracts/market_watch.py:36`; a position watch accepts `profit` or `volume`: `:83-88` |
| `condition=above` + `level` | `packages/contracts/src/lonora_contracts/market_watch.py:24-27`; evaluated as `current > level`: `packages/core/src/lonora_core/market_watch.py:7-8` |
| `prompt` | `packages/contracts/src/lonora_contracts/market_watch.py:28` (1 to 8000 characters) |
| The watcher reads the live position's profit | `packages/market/src/lonora_market/watchers.py:308-318` (`broker.positions()`, the position by id, `payload.get(config.metric, 0)`) |
| `trade_execute` supports `action=modify_position` with `stop_loss` / `take_profit` | `packages/contracts/src/lonora_contracts/trading.py:18-29`, `:33-34`; tool `packages/tools/src/lonora_tools/trade.py:752-768` |
| `trade_close_positions` exists | `packages/tools/src/lonora_tools/trade.py:770-784` |
| `watch_list`, `watch_cancel` exist | `packages/tools/src/lonora_tools/market_watch.py:245-259` |

One fact the brief does not state: a single position close also goes through `trade_execute` with `action=close_position` (`packages/contracts/src/lonora_contracts/trading.py:25`), which is a native tool. `trade_close_positions` (close all, or all of one symbol) is not needed for [40].

### 5.2 Were the tools visible to the Personal Agent?

Rule: the Personal Agent's chat run gets the profiles `core`, `market`, `coordination` (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:43-48`). `watch_create` is declared `eager=eager_for("market")` (`packages/tools/src/lonora_tools/market_watch.py:243`), `trade_execute` likewise (`packages/tools/src/lonora_tools/trade.py:767`). `watch_list`, `watch_cancel` and `trade_close_positions` have no eager profile (`packages/tools/src/lonora_tools/market_watch.py:245-259`, `packages/tools/src/lonora_tools/trade.py:770-784`).

Measured, Personal Agent with a signed full delegation, freshly migrated database (`clean.out:21`, `clean.out:30-31`): 22 native tools:

`peer_send, memory_read, memory_write, session_search, skills_list, skill_view, market_instrument, market_quote, market_candles, market_snapshot, market_sessions, watch_create, market_decision_record, market_decision_history, chart_snapshot, list_accounts, account_read, trade_execute, wait_for_input, agent_inspect, tool_environment, tool_call`

| Tool | Native in that run | Otherwise |
| --- | --- | --- |
| `watch_create` | yes | |
| `trade_execute` (buy, `modify_position`, `close_position`) | yes | |
| `account_read` | yes | |
| `trade_close_positions` | no | named in the inventory, callable through `tool_call` |
| `watch_list`, `watch_cancel`, `watch_update`, `watch_pause` | no | named in the inventory, callable through `tool_call` |
| `task_start` (durable continuous work) | no | named in the inventory, callable through `tool_call` |

The inventory is a system message in every model turn. It lists all 126 names by family and begins: `Your native tool list is this Run's working set, not the full set of abilities. … Call any other capability below with tool_call … and before claiming an ability is absent.` (`clean.out:32-49`; the `market:` line lists `watch_cancel, watch_create, watch_list, watch_pause, watch_resume, watch_update`). Names only; no descriptions and no schemas.

So for [40] the needed tools were not discovery-only: `watch_create` and `trade_execute` are in the native list from the first turn, in both builds (the declarations are unchanged since `aa50e8e`).

One extra finding: the native list depends on the agent's history. A tool used successfully once outside the native list is remembered (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:167-177`) and promoted into later runs, up to 6 tools within 4,100 schema characters (`packages/tools/src/lonora_tools/registry.py:84-85`, `:290-304`). Reproduced: on the second driver run `watch_cancel` and `watch_list` are native (24 tools; `second.out:21`, `second.out:30-31`) because the first run had used them through `tool_call`. **TRACE MUST CONFIRM** the stored `tool_exposure.native` and `tool_exposure.promoted` of the production runs for [41], [43], [47], [53] (and whether `watch_list` or `watch_cancel` had been promoted before [59]–[77]).

### 5.3 Can a watch that fires later close the position under the delegation?

Yes. Traced in code and reproduced.

1. **Storage.** `watch_create` stores the watch for the calling agent and its conversation thread (`packages/tools/src/lonora_tools/market_watch.py:98-102`, `:129-135`). It is not a financial tool (`financial=False`, measured from the registry) and needs no grant.
2. **Evaluation.** The watcher reads the position from the broker and takes its `profit` (`packages/market/src/lonora_market/watchers.py:308-318`); `condition_met("above", level, current, previous)` is `current > level` (`packages/market/src/lonora_market/watchers.py:594-598`, `packages/core/src/lonora_core/market_watch.py:7-8`).
3. **Wake.** When it matches and the cooldown allows (`packages/market/src/lonora_market/watchers.py:633-635`), the watcher creates a run for the same agent and thread with `trigger="watch"` and `prompt=config.prompt`, the watch's own prompt (`packages/market/src/lonora_market/watchers.py:675-701`), once per observation (`:636-637`).
4. **Authority of the wake run.** The scope of a run is `helper` for a subagent, `observe_only` when its metadata has `authority: observe_only`, otherwise `full` (`packages/tools/src/lonora_tools/base.py:53-58`). The watcher's metadata has no `authority` key (`packages/market/src/lonora_market/watchers.py:686-699`), so the scope is `full` and financial tools are permitted (`packages/tools/src/lonora_tools/base.py:92-94`). The executor refuses only subagent or observe-only origins (`packages/trading/src/lonora_trading/execution.py:81-85`). The wake run therefore has exactly the agent's current permission: with an active signed grant, `trade_execute` runs through `account_authorized_execution` at the single executor, with the same journal and independent verification (`packages/tools/src/lonora_tools/trade.py:577-618`); without one it raises an approval card. No rule is bypassed: the money moves through the signed grant at the single executor.
5. **What the wake run is told.** Only the watch's prompt, as the last user message (`clean.out:208-219`). If the prompt says "re-check and close", the run can do it. If it only says "check the position", nothing in the wake carries the owner's instruction except the thread's prose history.

Reproduction (`clean.out:157-221`):

- Owner «راقبه بس صار ربح 100 دولار سكره»; SCRIPTED `watch_create` with `kind=position`, `position_id`, `metric=profit`, `condition=above`, `level=100`, and a prompt that says to re-read and close. Result `ok: true`; stored row: `kind: position, symbol: XAUUSDm, metric: profit, condition: above, level: 100, enabled: True` (`clean.out:157-169`).
- `check_watches` with the position's profit at 0: `triggered: 0`. After the simulated position's profit is set to 120.5: `triggered: 1` (`clean.out:187-188`).
- The created run: `trigger=watch`, `authority: None`, `scope: full`, its prompt is the watch's prompt (`clean.out:189-191`).
- SCRIPTED wake run: `account_read`, then `trade_execute` with `action=close_position`. Result: `authorization: account_authority | status: confirmed | verification: verified | approval card raised: False` (`clean.out:198-203`). Broker positions after it: `[]` (`clean.out:220`). The reply is delivered into the owner's chat (`clean.out:221`).
- The other route of root cause 8 also works under the delegation: SCRIPTED `trade_execute` with `action=modify_position`, `stop_loss=4049.819`, `take_profit=4052.819` returns `authorization: account_authority | status: confirmed | verification: verified`, no card, and the position then has `stop_loss=4049.819 take_profit=4052.819` (`clean.out:171-184`).
- `watch_list` and `watch_cancel` work for the Personal Agent through `tool_call` (`clean.out:224-238`).

Limits of this path, from the code:

- The close depends on the wake run's model following the prompt. The harness does not carry an action with the watch; `Watch` has no action field (`packages/contracts/src/lonora_contracts/market_watch.py:11-43`). A broker-side take-profit (`modify_position`) does not depend on any later model turn.
- A watch stays enabled after it fires; an `above` watch can fire again after `cooldown_seconds` (default 300, `packages/contracts/src/lonora_contracts/market_watch.py:30`; `packages/market/src/lonora_market/watch_control.py:6-11`). In the reproduction it stays `enabled: True` after the close (`clean.out:222`). Once the position is gone its profit reads as 0 (`packages/market/src/lonora_market/watchers.py:314-318`), so it does not fire again, but it remains listed until cancelled.
- The uncertain-outcome line of PR #42 is not added in a wake run (`OWNER_TRIGGERS = frozenset({"user", "group"})`, `packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:22`); the financial-truth gate still applies there (`packages/agent-runtime/src/lonora_agent/model_runtime.py:229-232`).
- **TRACE MUST CONFIRM** that the watcher process was running in production and that a wake run of the Personal Agent was not blocked by another active run in the same thread.

### 5.4 Why the condition was not turned into a trigger

Nothing in the harness maps "when X happens do Y" to a trigger. The decision is the model's alone, and the model received:

- a native `watch_create` whose description ends `and never trades` (`packages/tools/src/lonora_tools/market_watch.py:239`);
- core lines that forbid promising monitoring without a saved watch (`lonora.md:38`, `lonora.md:127`), which is advice with no check behind it for a chat run (section 2.4);
- no line that says a position watch with a close instruction, or a take-profit, is how "close it at +100" is done (section 2.2);
- no stop gate for a chat run: the continuous-work nudge (`This responsibility is continuous. A text answer does not complete it or save monitoring.`, `packages/agent-runtime/src/lonora_agent/stop_gates.py:45-47`) exists only for a Task run, and the tool that would start one, `task_start`, is not native in a chat run.

So [41] did a one-off read and offered a follow-up; [43] and [47] claimed one. [59] and [65] later list only EURUSDm watches. **TRACE MUST CONFIRM** for the runs of [41], [43], [47], [53]: the tool calls made (expected: `account_read` only, or none in [43]), and that no `watch_create` call or XAUUSDm watch row exists.

---

## 6. [29]: status from "the last check" instead of a live read

Policy on live reads exists, as prompt text only:

- `packages/agent-runtime/resources/system/lonora.md:76`: `Current market or account claims require actual returned evidence, not memory or plausible numbers.` (core, always loaded).
- `packages/agent-runtime/resources/constitution/identity.md:1`: `Use tools for current facts.`
- The note on carried evidence: `They are historical observations of what was known at observed_at, not live market or broker truth: prices, positions, orders and balances may have changed. Re-read before acting or before claiming current state; reuse them to avoid repeating a lookup only when their age is acceptable.` (`packages/agent-runtime/src/lonora_agent/context/run_evidence.py:73-80`).

Against it: `packages/agent-runtime/resources/system/lonora.md:119` (`answer it directly when grounded information is already available`), and the note's own last clause (`reuse them to avoid repeating a lookup only when their age is acceptable`) with no number for "acceptable".

Is prior tool output kept in context so the model can answer from it? **Yes.** A new run starts from the prose of earlier replies plus a projection of earlier tool results: the last 4 runs of the same agent and thread, up to 12 entries and 8,000 characters (`packages/agent-runtime/src/lonora_agent/context/run_evidence.py:25-27`), written for the stated purpose that `a follow-up re-fetches what was just observed or trusts its own paraphrase` otherwise (`:3-7`). Reproduced: the request for «شو وضعه» contains the earlier `account_read` result with the position (id, `open_price`, `profit`) inside the user-role context message, section `recent_tool_evidence`, with the note above (`clean.out:152-155`).

No check forces a read. Reproduced: owner «شو وضعه»; SCRIPTED reply «وضعه الآن: المركز مفتوح، والنتيجة وقت آخر تحقق كانت -0.24 USD.» with no tool call is committed unchanged, zero notices (`clean.out:142-151`).

In the conversation [29] says «وقت آخر تحقق كانت -0.24 USD», the figure from [26] 20 seconds earlier, and then offers the live read («إذا تريد، أراجع لك السعر الحالي»). [43] («الربح الأخير المعروف +0.53 USD») and [55] («آخر ربح متحقق كان +0.38 USD») are the same pattern. **TRACE MUST CONFIRM** that the runs of [29], [43], [55] made no `account_read` or `market_quote` call.

---

## 7. [57] against [59]

- [56] «اي زوج عم تراقب ؟» → [57] «أراقب XAUUSDm على حساب Exness-MT5Trial16.»
- [58] «و المهمة الشغالة على اي زوج ؟» → [59] «المهمة الشغالة الآن على EURUSDm، وليس على الذهب. المراقبة النشطة: EURUSDm تحت مستوى 1.11305. الحالة: waiting».

In code terms: [59] reads like stored state. The word `waiting` is a value of the agent's live state (`packages/contracts/src/lonora_contracts/agent_state.py:34`), which `runtime_status` returns (`packages/tools/src/lonora_tools/runtime_control.py:41-60`) and which lists the agent's own enabled watches (`packages/db/src/lonora_db/agent_state.py:343-347`); `watch_list` is also limited to the calling agent (`packages/tools/src/lonora_tools/market_watch.py:148-157`). [57] reads like a continuation of the model's own earlier sentences ([43] «مراقب», [47] «فأنا أتابعه»), which are in the thread history as plain prose.

Both replies can be produced because nothing compares a statement about monitoring with the stored watches. The contradiction is the visible result of section 3: the claims of [43] and [47] were never checked, stayed in history, and were repeated in [57]; the first reply that looked at stored state ([59]) showed no gold watch.

**TRACE MUST CONFIRM**: (a) the run of [57] made no tool call; (b) which tool the run of [59] called (`runtime_status`, `watch_list` or `agent_inspect`); (c) whether any enabled watch row with symbol XAUUSDm existed for this owner between 10:51 and 10:56 Damascus time (expected: none); (d) which agent owns the EURUSDm watches (if [59] used `watch_list` or `runtime_status`, they belong to the Personal Agent itself).

---

## 8. Thread state for a "pending offer" (principle 4) or "open requests" (principle 9)

**There is none.**

- Search: case-insensitive `pending_offer`, `pending offer`, `last_offer`, `open_request`, `open request`, `unfinished request`, `standing request` over `packages/agent-runtime`, `packages/tools`, `packages/db`, `packages/contracts`, `packages/core`, `packages/session`, `packages/gateway` (`*.py`, `*.md`, tests excluded): no hit.
- The thread row has `context_summary`, `summary_seq`, `purpose`, `title`, `next_seq`, `options` (`packages/db/src/lonora_db/schema.py:220-240`), and `options` holds one key, `web_search` (`packages/db/src/lonora_db/threads.py:13-16`).
- The first-turn request of a chat run contains none of those terms (`clean.out:57-62`).

What exists and is close, with the reason it does not serve:

| Existing state | Where | Why it is not a pending offer or an open request |
| --- | --- | --- |
| `suggested_reply` on a message | `packages/db/src/lonora_db/runs.py:336-357` | display chip of what the owner might say; never read back when the owner answers |
| `pending_input_request` in a run checkpoint | `packages/agent-runtime/src/lonora_agent/tool_loop.py:367-379` | only for a question published with `wait_for_input` (a card); belongs to one run; a new owner message supersedes it |
| Task steps and the Task stop gates | `packages/agent-runtime/src/lonora_agent/stop_gates.py:132-146` | only when the model started a Task with declared steps; a chat request is not a Task |
| `recent_tool_evidence` | `packages/agent-runtime/src/lonora_agent/context/run_evidence.py:25-27` | past tool results, not requests |
| Thread prose history and `context_summary` | `packages/agent-runtime/src/lonora_agent/context/history.py:16` (`HISTORY_WINDOW = 100`) | the only carrier of offers and unfinished requests; free text the model may or may not act on |
| Prompt line | `packages/agent-runtime/resources/system/lonora.md:130` | text, no state |

Consequence for this conversation: the request of [40] was never recorded as open, so [46] and [52] had to repeat it and nothing resumed it; the offer of [35] was never recorded as pending, so «طيب» [36] had only prose to refer to.

---

## 9. Classification on `main` (`9f5b1da`)

FAILS = the same owner message can still produce the problem; no mechanism on `main` prevents it. FIXED = a mechanism prevents it. PARTLY = part is prevented.

No message of groups B and C-part-1 is FIXED. No commit between `aa50e8e` and `9f5b1da` touches the mechanisms involved, except the new `suggested_reply`, which works against group B (section 2.3).

| Message | What happened, in code terms | On `main` | Evidence | Trace must confirm |
| --- | --- | --- | --- | --- |
| Group B: 26 of 37 replies end with an offer ([10] [12] [14] [16] [18] [20] [22] [24] [26] [29] [31] [35] [37] [41] [45] [51] [53] [55] [59] [63] [65] [71] [73] [75] [77] [81]) | A chat run ends on the first model turn that has text and no tool call; no gate reads the reply; the prompt asks for "one next suggestion" | **FAILS** | `tool_loop.py:590-611`; `stop_gates.py:153-155`, `:178-181`; `lonora.md:33`, `:163`; `suggested_reply.md:2`; `clean.out:65-74`; count in `runs/bc_count_offers.out` | Per reply: number of model turns and the tool calls of its run |
| [14]→[15] «ياريت»→[16]; [16]→[17] «ياريت»→[18] (question [9] answered only at [18]) | Each offered step was a read; each «ياريت» started a new run that did the read and offered the next one | **FAILS** | same as above; `lonora.md:135` is limited to work "they already requested" | Tool calls of the runs of [14], [16], [18] (expected: quote and candle reads only in [16] and [18]) |
| [20], [22] (charts) | Request done, then a read offered | **FAILS** (offer ending only; the request itself was served) | same | none |
| [26] | Buy executed and verified; stop/target and follow-up offered, not proposed with numbers | **FAILS** (offer ending) | `clean.out:17-29` shows the entry path works under the delegation | Result of the `trade_execute` call of [26] |
| [28]→[29] | Status answered from the previous run's tool result carried in context; live read offered instead of done | **FAILS** | `run_evidence.py:25-27`, `:73-80`; `lonora.md:76` and `lonora.md:119`; `clean.out:142-155` | That the run of [29] made no `account_read` / `market_quote` call |
| [35]→[36] «طيب»→[37] «تم» | New run; the offer exists only as prose; the reply claims done; no financial call, so no guard has anything to read | **FAILS** | `uncertain_outcome.py:85-90`, `:115-118`; `model_runtime.py:218-238`; `clean.out:76-111`; `runs/bc_effect_claim_regex.out` | Tool calls of the run of [37] (expected: `account_read` and/or `market_quote`, no `trade_execute`, no `watch_create`); position has no stop/target after it |
| [38] «تمام»→[39] «الإغلاق الآلي حسب الخطة» | A read, then a claim of an automatic close with no stop, target or watch stored | **FAILS** | `clean.out:113-125`; no check compares the claim with stored state (section 3.1) | No `modify_position` in the journal and no watch row for the position before [39] |
| [40]→[41] | Condition answered by a one-off read; a follow-up offered. `watch_create` and `trade_execute` were native | **FAILS** | `market_watch.py:239`, `:243`; `clean.out:30-31`; `clean.out:127-140`; working path `clean.out:157-221` | Stored `tool_exposure.native` of the run; tool calls (expected: `account_read` only) |
| [42] «تمام» (+👍)→[43] «مراقب… أغلقه فورًا» | Claim of monitoring and a promise to close, with no `watch_create`; the 👍 never reaches the agent | **FAILS** | `clean.out:127-140`; `apps/api/src/lonora_api/routes/messages.py:76-78`; `history.py:194-198` | That the run of [43] made no tool call or only a read; no XAUUSDm watch row |
| [44] «تم»→[45] | No record of what is pending; the reply guesses the owner wants to stop a follow-up that does not exist | **FAILS** | section 8 | Tool calls of the run of [45] |
| [46] «لا انو تابعه»→[47] «فأنا أتابعه» | Second statement of the same request; a read and a claim | **FAILS** | as [43] | Tool calls of the run of [47]; no watch row |
| [52] «بس وصلت 100 سكره»→[53] | Third statement; a read and another offer to follow it | **FAILS** | as [41] | Tool calls of the run of [53] |
| [54] «طيب»→[55] | Short approval of [53]'s offer; no read («آخر ربح متحقق»), no watch, asks for another number | **FAILS** | sections 4 and 6 | That the run of [55] made no tool call |
| [56]→[57] «أراقب XAUUSDm» against [58]→[59] | [57] repeats unverified prose from history; [59] reports stored state, which has no gold watch | **FAILS** | `agent_state.py:343-347`; `market_watch.py:148-157`; section 7 | Items (a)–(d) of section 7 |
| Root cause 8 | The tools exist and work for the Personal Agent under a full delegation; the failure is in the harness and the behaviour, not a missing tool | **CONFIRMED** | section 5; `clean.out:157-238` | Production exposure lists (section 5.2); watcher running (section 5.3) |

What would have to be true on `main` for any row to be FIXED, and is not: a gate on a chat run's final reply; a check of a completion or monitoring claim against the tool results of the same run or against stored watches; a record of the pending offer; a record of open requests; a rule that a status question triggers a live read. None of the five exists.

---

## 10. Money-safety notes for whoever changes this area

Facts from the code that a fix must keep:

- A watch never moves money by itself; it creates a run (`packages/market/src/lonora_market/watchers.py:675-701`). The run trades only through `trade_execute` at the single executor under the signed grant, or raises a card (`packages/tools/src/lonora_tools/trade.py:577-618`). The reproduction closed the position with `authorization: account_authority` and no card (`clean.out:203`).
- Closing a position is an exit; `independent_exits` keeps closes independent of each other (`packages/tools/src/lonora_tools/trade.py:266-280`).
- Observe-only wakes and subagents cannot execute (`packages/trading/src/lonora_trading/execution.py:81-85`); a normal watch wake is not observe-only (`packages/tools/src/lonora_tools/base.py:53-58`).
- The existing reply guards replace or extend text only from structured financial results (`packages/agent-runtime/src/lonora_agent/uncertain_outcome.py:3`); they do not read wording. A claim check built on tool results of the same run fits that design; none exists today.
- Owner-words checks treat card taps as not the owner's words (`packages/db/src/lonora_db/owner_words.py:5-8`). A "short approval executes the pending offer" mechanism must not let a stored offer stand in for the owner's own words where those checks apply (full delegation, supervision, limits).

## 11. Open points (UNSURE)

- UNSURE: whether the production runs of [37], [39], [43], [47] made read calls or no call at all. The reply texts contain fresh numbers in [37], [39], [41], [47], [53] (a read is likely) and "last known" wording in [29], [43], [55] (no read is likely). Only the trace settles it.
- UNSURE: whether the EURUSDm watches of [59] and [65] belong to the Personal Agent or to another agent, and why two have the same level. Outside this part; items (b) and (d) of section 7 settle the first point.
- UNSURE: whether a real model, given the same prompt on `main`, would choose `watch_create` for [40]. The scripted runs show the harness accepts both the correct path and the false claim without any difference in treatment; they do not measure model choice.
