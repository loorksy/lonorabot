# Gap 0: memory, semantic recall, conversation recall and run evidence (Part 1.6)

Repository `/home/user/lonorabot` at `9f5b1da` (checked-out HEAD `0a03960` differs only by docs under `docs/research/`; no code differs). Read-only on the repo; `git status --short` is clean after all runs.

Scope assigned: `packages/memory/src/lonora_memory/{retrieval,semantic,evidence,conversation,compaction,profile,store,markdown_memory}.py`, `packages/agent-runtime/src/lonora_agent/context/{builder,run_evidence,memory,history,compaction}.py`, `docs/agent-memory-and-recall.md`, `tests/check_memory_provenance.py`, `tests/check_conversation_recall.py`.

Ground truth used: `production-trace.md` (36 tool calls; `memory_read` called once at 09:37:56 in run 0afe5ea8, trace line 92; **no `memory_write` call anywhere** in the trace's tool events, `memory_write` only appears in the offered-tools list, trace line 20), `lonora-chat.md`, `TIMELINE_CORRECTION.md`.

---

## 0. Short answers

1. **Does recall or recent-tool evidence feed old failure replies back into later runs?** Yes, by three different paths, and nothing anywhere filters failure-shaped text:
   - Conversation recall returns the Agent's own old assistant messages, including «ما قدرت أقرأ الذهب… symbol_not_found…», as recall items once the thread has a summary (J-M1-A, J-M4). It selects any assistant message of this Agent (`packages/memory/src/lonora_memory/conversation.py:96`); the only filter is for hidden card submissions (`packages/db/src/lonora_db/owner_words.py:29`).
   - Before any compaction, and while the thread fits the 100-message window, recall is empty (`no_compacted_history`) but the whole thread, failure replies included, is already in the transcript (`packages/agent-runtime/src/lonora_agent/context/history.py:110-122`, window 100 at `history.py:16`) (J-M1-B). Once a thread passes the window without a summary, the builder passes `unloaded_through=gap.last_seq` (`builder.py:203`, `:206`) and recall then also reaches the messages beyond the window (`conversation.py:69`).
   - Run evidence drops **failed reads** (the raw `symbol_not_found`) and keeps only successes (`packages/agent-runtime/src/lonora_agent/context/run_evidence.py:158-159`), but keeps **failed effect-tool calls with their code** (`run_evidence.py:49`, `:159`) (J-M5), and forgets everything older than 4 runs (`run_evidence.py:25`, `:220`) (J-M2).
2. **Is this the cause of the owner's example?** No, and the report says so plainly. In the production thread the 78 messages were all inside the 100-message history window, so [12] «محتاج أوضح المقصود من "ضع حرف m"» was produced with [10] fully visible in the transcript. Recall added nothing to or against that outcome. The memory/recall layer matters for what happens **after** the thread is summarised, and for **learning**: nothing writes a learned symbol (`XAUUSDm`) anywhere durable (section 3).
3. **doc line 393-394** («recall covers only the current thread») is true for the conversation arm only and misleading as a whole: the memory-document arm and the semantic-note arm are agent-wide (`evidence.py:192-196`, `:222`). A symbol learned in another thread is recalled **only if it was saved to MEMORY.md or as a knowledge note**; the other thread's messages are never recalled (J-M3). Code wins.
4. **doc line 397-400** is stale: `owner_notify` is registered (`packages/tools/src/lonora_tools/incoming_call.py:129`). The doc says (lines 397-398) «Until the `owner_notify` tool (W15-7) lets an Agent raise an inbox alert, `notify` behaves like `message`…»; that tool now exists. The tool's own text still says «Delivery is in-app only for now.» (`incoming_call.py:132`), which agrees with the first half of doc line 397. Code wins.
5. Both never-run checks were run and pass (section 2).

---

## 1. How to rerun (environment, caveats)

All journeys use database 7 (`audit_j7_test`). That database already holds an owner created by another agent (`trace-guards@example.com`), so a run needs that email; the driver script sets it by default.

```
cd /home/user/lonorabot && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 7 \
 && .venv/bin/python /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/gap0_memory.py M1   # M1 .. M5
```

Raw output of each run: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/GAP0-M1.txt` .. `GAP0-M5.txt`, and `GAP0-check_memory_provenance.txt`, `GAP0-check_conversation_recall.txt`. The driver is `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/gap0_memory.py` (outside the repo).

What is real, seeded and scripted:

| Label | Meaning |
|---|---|
| REAL | API app, PostgreSQL, `build_context` (history, recall, run evidence), `retrieve_evidence`, the tool loop and tool dispatch (M2, M5), a real `MetaApiBroker` object over a fake SDK (M2, from `scripts/j1_lib.py`). |
| SEEDED | Message rows inserted with `MessageRow`, copying the owner's production messages [9]-[18] from `lonora-chat.md` (shortened where the export had `...`), the same technique `tests/check_conversation_recall.py:30-60` uses. `summary_seq` is set by hand to represent "after background compaction"; no model summary text exists in those runs. |
| SCRIPTED | Model turns (M2, M5 only): the script chooses the tool calls. A scripted final reply is never evidence of what a model says. M1, M3, M4 call no model at all. |

Driver artifact to ignore: in M1 the context ends with the owner's message twice, because the driver both stores the message and passes it as the run prompt (`builder.py:180-186` appends an explicit prompt). The production message route (used in M2/M5) does not do this.

---

## 2. The two checks that were never run

Command (database 7; the e-mail override is needed only because another agent's owner already exists there):

```
cd /home/user/lonorabot && source .../env.sh 7 && export LONORA_UI_TEST_EMAIL=trace-guards@example.com
PYTHONPATH=tests .venv/bin/python tests/check_memory_provenance.py
PYTHONPATH=tests .venv/bin/python tests/check_conversation_recall.py
```

Output (verbatim):

```
PASS owner-provided and Agent-authored revisions have actual Run/event provenance; legacy unknown remains unknown and no content grants authority
PASS PostgreSQL conversation recall: direct scope, roles/authors, exact symbols, Arabic, summary/input/next-sequence cutoffs, one neighbor, edits/deletes, query/candidate/output limits
```

What they prove, and the two assertions that matter for this audit:

- `tests/check_conversation_recall.py:95`: `assert not (await recall("XAUUSD")).items`. The recall of the exact token `XAUUSD` finds nothing in a message that says `XAUUSDm`. This is **by design** (`retrieval.py:15-24`, `:44-45`: a token with a contiguous uppercase run is an identifier and must match exactly). It is the memory-layer twin of the owner's problem: `XAUUSD` and `XAUUSDm` are different strings everywhere.
- `tests/check_conversation_recall.py:98`: with no scope (`None`) nothing from the conversation is returned: recall never reaches another thread by itself. The checks use `group_id` and wrong-owner/wrong-agent cases (`:145-150`, group case, and the loop above it) to prove the privacy cut-offs. These are **needed for safety** (private memory per Agent).
- `tests/check_memory_provenance.py:68`: Agent writes carry `source == "agent_authored"`, so recalled memory never reads as owner fact.

Neither check exercises failure text feeding back; they test authorisation and bounds. Nothing in the repo tests "an old failure reply must not mislead a later run".

---

## 3. Reading map of the memory/recall layer (code wins over doc)

### 3.1 What is injected on every run (not "recall")

`packages/agent-runtime/src/lonora_agent/context/memory.py`: the owner profile (`owner_preferences_section`, priority 90), the owner's goals/links, the Agent's operating notes and the Agent's own memory document (`read_memory_context`), all in the user-role context message, never system. These are always present; they do not depend on the query.

### 3.2 What the automatic per-turn recall is

`builder.py:187-189` takes the **query** from the explicit prompt, else the newest user message in the transcript. `builder.py:192-213` calls `retrieve_memory` with a `ConversationRecallScope` only when the thread belongs to this Agent, has no group and `purpose == "conversation"` (`builder.py:208-211`). The recalled text goes into the section `recalled_evidence` (`builder.py:259-261`), priority 40 (the lowest of the data sections, so it sheds first under a small window).

`retrieve_evidence` (`packages/memory/src/lonora_memory/evidence.py`) fuses up to three arms:

| Arm | Source | Scope | Cite |
|---|---|---|---|
| conversation | old messages of the **current** conversation thread, only those at or below the summary cut-off | one thread | `evidence.py:182`, `conversation.py:67-70` |
| memory document | chunks of this Agent's MEMORY view | agent-wide | `evidence.py:192-196` |
| semantic notes | `ln_semantic_memory` rows of this Agent | agent-wide | `evidence.py:222` |

Facts that shape behaviour:

- **Only compacted (or beyond-window) history is recalled.** The cut-off is `min(before_seq, covered, input_seq - 1, next_seq - 1)` (`conversation.py:70`) and `covered = max(summary_seq, unloaded_through)` (`conversation.py:69`). With `summary_seq == 0` and no gap the cut-off is below 1 and the answer is `no_compacted_history` (`conversation.py:72`). The `before_seq` passed by the builder is `gap.last_seq if gap else thread.summary_seq` (`builder.py:203`).
- **Compaction starts late.** `compact_history` returns without summarising until the thread has 80 unsummarised messages (settled mode) or more than 48,000 characters (`context/compaction.py:19`, `:69-74`; called from the gateway at `packages/gateway/src/lonora_gateway/history_maintenance.py:51`). The production thread had 78 messages (TIMELINE_CORRECTION). UNSURE: the trace does not carry `summary_seq`, so I infer, not observe, that no summary existed; the export is about 20 KB for 81 numbered messages, so the 48,000-character trigger probably did not fire either.
- **Query = newest owner message only.** A one-word follow-up («ياريت», «طيب», «ضع حرف m») recalls by that word, not by the question it answers (J-M4).
- **Matching is lexical.** Candidates are selected with an `ILIKE`-style `icontains` over any query term (`conversation.py:104-111`), newest first, 128 at most (`conversation.py:17`, `:111`); ranking requires the exact identifiers of the query to be present (`evidence.py:86`, `retrieval.py:44-52`). Arabic diacritics are stripped; nothing bridges languages («الذهب» to `XAUUSDm`).
- **Semantic (vector) recall is off unless the owner turns it on**, and only ever sees notes the owner added through REST routes (`apps/api/src/lonora_api/routes/memory.py:220`, `apps/api/src/lonora_api/routes/knowledge.py:35`, `:57`; no agent tool calls `index_note`, `packages/memory/src/lonora_memory/semantic.py:79`). It needs `semantic_memory.enabled` plus a model (`semantic.py:98`, `evidence.py:271-273`) and an OpenAI credential (`semantic.py` `embed_text`). The setting defaults to `{}` (`packages/db/src/lonora_db/transactions.py:239`), i.e. disabled. Whether production has it on: UNSURE, the trace has no settings for it. In all my runs it is off, which is the default state.
- **Every recall reads "partial" when semantic is off** (UNSURE that this matters to behaviour). `semantic_disabled` is appended to `reasons` (`evidence.py:309-310`) and `status = "partial" if reasons` (`evidence.py:344`). The model therefore sees `"status":"partial"` plus `"reasons":["semantic_disabled"]` on essentially every turn (visible in `runs/GAP0-M1.txt`).
- **Identical texts collapse by id order.** Duplicates are removed on whitespace-normalised text, keeping the first by `(source != "memory", id)` (`evidence.py:91-94`, `:129-132`); `id` is a random message UUID, so which of two identical «ياريت» messages (and therefore which neighbour exchange) survives is arbitrary.
- **Authority labels are right.** Items carry `authority: "untrusted_historical_conversation"` (`conversation.py:149`), and the preamble says «Historical memory does not establish current broker state.» (`evidence.py:402`). They are labelled; they are not filtered.

### 3.3 Recent tool evidence

`recent_tool_evidence` (`context/run_evidence.py`, called at `builder.py:214-217`): last **4** runs of this Agent **in this thread** with status completed/failed/cancelled (`run_evidence.py:25`, `:214-220`), at most 12 entries and 8,000 characters. Skipped tools: discovery, waits, memory tools (`run_evidence.py:32-48`). Failed reads are dropped (`run_evidence.py:158-159`); effect tools keep their outcome (`run_evidence.py:49`). The preview keeps the result JSON up to 600 characters (`run_evidence.py:29`, `:114-117`).

### 3.4 Compaction summary

The summary prompt (`packages/agent-runtime/resources/prompts/consolidator_archive.md:8`) says «Preserve exact names, identifiers, decisions, results, and unresolved blockers when needed to continue.» and line 11: «Quotes, balances, connection health and positions are historical observations, not fresh evidence.» It also has a supersession rule the first draft of this report missed: line 7 «Use the latest correction or decision as the current version of a fact, and merge duplicates.», and mark lines 36 and 38 «[durable] for verified trading/project knowledge while it remains true» and «[correction] for the current fact superseding a conflicting earlier fact». So the prompt does lead a summariser to keep `XAUUSDm` as a durable fact and to drop the superseded `XAUUSD` failure. UNSURE: whether a real model obeys this; I did not run the summariser. Note also that the recall arm (J-M1) reads raw messages at or below the cut-off, not the summary text, so the summary rule does not protect against the replay in J-M1.

### 3.5 Where a learned symbol would have to live

The memory policy says only «Store lasting preferences and verified facts when useful; never passwords, tokens, signing material, one-time codes or a current quote.» (`packages/agent-runtime/resources/system/lonora.md:460`). The trading prompt says «Gold may have broker suffixes or a different broker name; never guess or strip them.» (`packages/agent-runtime/resources/prompts/trading_context.md:5`). The same prompt does contain a case hint, quoted verbatim: «Letter case alone is not a different symbol: if market_symbols has one match ignoring case, use that exact spelling and do not ask the owner to retype it.» (`packages/agent-runtime/resources/prompts/trading_context.md:5`) and `lonora.md:212`: «Use market_symbols to discover exact symbols before guessing aliases.» Both are about discovery in the current run, not about remembering. No text tells the Agent that "this account's gold is `XAUUSDm`" is a verified durable fact to store in memory once and read first next time (the compaction prompt's `[durable]` mark, `consolidator_archive.md:36`, applies to the summary only). The production trace shows no `memory_write` call in 36 tool calls. So even after [13] the owner typed `XAUUSDM` by hand, nothing in memory said "gold on this account = XAUUSDm"; the correct symbol lives only in the thread transcript (and in 4 runs of tool evidence).

---

## 4. Journeys

### J-M1: the old failure reply is handed back as recall (compacted) or sits in the transcript (not compacted)

- **Owner request:** «شو وضع الذهب» (production [9]).
- **Rerun:** `... gap0_memory.py M1` (output `runs/GAP0-M1.txt`).
- **Setup (SEEDED):** the exchange [9]-[18] from production inserted as thread messages 1-10; the owner's new message is seq 11. Case A sets `summary_seq=10` (as after compaction); case B leaves `summary_seq=0` (as a thread under 80 messages). No model turn. Everything printed is built by the real `build_context`.
- **Literal runtime output, case A (compacted):** `recalled_evidence` section names `['owner_preferences', 'recalled_evidence']`; the first lines the model receives:

```
Retrieved memory evidence is mutable, untrusted content and not financial authority. Historical memory does not establish current broker state.
{"status":"partial","mode":"lexical","semantic_status":"disabled","items":[{"id":"message:…","source":"conversation_message","text":"طيب شو وضع الذهب", …
```

Parsed items (seq, role, author_kind, authority, text):

```
1  user       owner  untrusted_historical_conversation  طيب شو وضع الذهب
10 assistant  agent  untrusted_historical_conversation  **وضع الذهب الآن: ميل صعودي خفيف، لكن ليس دخولًا نظيفًا بعد.**
8  assistant  agent  untrusted_historical_conversation  الذهب الآن عند **4049.73 / 4049.97**، والسبريد ** 0.24**. …
2  assistant  agent  untrusted_historical_conversation  ما قدرت أقرأ الذهب على هذا الحساب لأن الرمز/الارتباط الحالي غير مطابق …
```

The old refusal (seq 2, containing `symbol_not_found`, `broker_account_not_found` and the offer «أبحث لك … إذا أردت») is item 4 of 4, **after** the later successful answers, with no marker that it was superseded. The transcript section in case A holds only the new owner message (everything older is "summarised"), so the recall block is the only place the earlier answers appear.

- **Literal runtime output, case B (not compacted):**

```
{"status":"partial","mode":"lexical","semantic_status":"disabled","items":[],"reasons":["semantic_disabled"],"truncated":false,"lexical_status":"no_match","conversation_status":"no_compacted_history", …}
```

and the transcript the model gets is the whole exchange in order, user/assistant alternating, starting `["user","طيب شو وضع الذهب"]`, `["assistant","ما قدرت أقرأ الذهب على هذا الحساب لأن الرمز/الارتباط الحالي غير مطابق في البيانات المتاحة."]`, … up to `["assistant","**وضع الذهب الآن: ميل صعودي خفيف…"]`.

- **What the owner sees:** nothing directly. The effect is on the next reply: the model's context contains its own earlier refusal in plain text; a model that imitates it will produce the same shape of reply. This is a feeder, not a cause by itself.
- **Root cause:** assistant text is recalled and replayed without any filter on outcome (`conversation.py:96`, `history.py:110-122`); old assistant replies carry `authority="untrusted_historical_conversation"` (`conversation.py:149`), which prevents instruction-following but not imitation.
- **Class:** leak (internal codes carried forward in context) / recoverable-not-led (no marker says "this was resolved by the later `XAUUSDm` turn").
- **Honest limit:** this does not explain the production reply at [10] or [12]; both were produced with no failure text yet in the thread, or with it fully in the transcript (case B).

### J-M2: tool evidence keeps the success, forgets the failure, and forgets both after 4 runs

- **Owner request:** «شو وضع الذهب», then five more owner messages.
- **Rerun:** `... gap0_memory.py M2` (output `runs/GAP0-M2.txt`).
- **Setup:** REAL tool loop over a real `MetaApiBroker` object with a fake SDK (catalog `BTCUSDm, EURUSDm, USOILm, XAGUSDm, XAUUSDm`). **SCRIPTED turns** in run 1: (1) `market_snapshot {symbol: "XAUUSD"}`; (2) `market_snapshot {symbol: "XAUUSDm"}`; (3) a final text. Runs 2-5: one scripted plain reply each; run 6 the same. The evidence shown is built by the runtime, not scripted.
- **Literal runtime tool results (run 1):**

```
market_snapshot XAUUSD  -> {"ok": false, "code": "symbol_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}
market_snapshot XAUUSDm -> {"ok": true, "methodology": "closed_bar_market_snapshot_v1", … "symbol": "XAUUSDm", …
```

- **`recent_tool_evidence` the model received at the first request of each run:**

```
RUN1  (no recent_tool_evidence section)
RUN2  [market_snapshot, args …"symbol": "XAUUSDm"}, ok true]     <- the failed XAUUSD call is absent
RUN3  same one entry
RUN4  same one entry
RUN5  same one entry
RUN6  (no recent_tool_evidence section)                           <- 5 runs later it is gone
```

- **What the owner sees:** nothing at the time. Effect: from run 6 on, the Agent has no tool-level memory that gold is `XAUUSDm` on this account; it has to rediscover it from the transcript, recall (compacted only) or tools again. In production the conversation had 20+ runs after [13], so the evidence window was long past the first success.
- **Root cause:** `EVIDENCE_RUNS = 4` and `.limit(EVIDENCE_RUNS)` (`run_evidence.py:25`, `:220`); a failed non-effect result is skipped (`run_evidence.py:159`); the thread filter makes it per-thread (`run_evidence.py:214`).
- **Class:** recoverable-not-led (the success that would prevent the next failed lookup ages out; the failure that explains why is never carried).
- **Note on direction:** dropping the failed read is partly good (the model does not see `symbol_not_found` again, so this path does not feed the leak of J-M1). The cost is the lost lesson.

### J-M3: a symbol learned in another thread, or in Arabic, or without the exact case, is not recalled

- **Owner request (the situation):** the Agent learned in a work thread that gold is `XAUUSDm`; later the owner asks in the conversation «الذهب» / the model searches `XAUUSD`.
- **Rerun:** `... gap0_memory.py M3` (output `runs/GAP0-M3.txt`).
- **Setup (SEEDED):** a second thread of the **same Agent**, `purpose = "work"` (the DB allows only `conversation` and `work`, `packages/db/src/lonora_db/schema.py:225`) holding the assistant message «Verified on this account: gold is XAUUSDm, XAUUSD does not exist.»; the Agent's MEMORY.md written through the real API with «Gold on the Exness trial account is XAUUSDm (verified).»; the conversation thread holds 12 compacted filler messages. Semantic memory disabled (the default). No model turn.
- **Literal runtime output** (`retrieve_evidence` in the conversation thread; conversation arm status was `no_match` for all four):

```
query "XAUUSDm"      -> items: [ memory | "## Trading Context\n- Gold on the Exness trial account is XAUUSDm (verified)." ]
query "XAUUSD"       -> items: []
query "الذهب"        -> items: []
query "gold symbol"  -> items: [ memory | the same MEMORY.md chunk ]
```

- **What it shows:**
  1. The work-thread message is **never** recalled: the conversation arm is bound to the one conversation thread (`conversation.py:67`, `builder.py:208-211`). Only MEMORY.md and semantic notes cross threads (`evidence.py:192-196`, `:222`). Doc line 393-394 is therefore true for conversation text and false for memory/notes. Reaching the work thread needs the model to choose `session_search` (`packages/agent-runtime/resources/system/lonora.md:466`; scope includes work threads, `packages/memory/src/lonora_memory/sessions.py:3`).
  2. Exact-identifier rule: the query `XAUUSD` does not find `XAUUSDm` (`retrieval.py:15-24`, `:44-45`; asserted by design at `tests/check_conversation_recall.py:95`). The Agent that tried `XAUUSD` first (the production failure) cannot be corrected by recall.
  3. No language bridge: «الذهب» does not find `Gold … XAUUSDm`; only the English word `gold` does. Semantic recall is the intended bridge and is off by default (section 3.2).
- **Root cause:** lexical-only recall with exact identifier matching and a thread-bound conversation arm (`retrieval.py:15-52`, `conversation.py:67`); no tool or prompt makes an Agent store a verified symbol (`lonora.md:460`).
- **Class:** recoverable-not-led (the data exists; nothing leads the model to it); the thread isolation itself is **needed for safety** (private threads, `docs/agent-memory-and-recall.md:10-49`).

### J-M4: a short follow-up is recalled by one word, and «طيب» recalls the old refusal

- **Owner request:** the short replies of the production chat: «ضع حرف m» [11], «ياريت» [15][17], «طيب» [36], «تمام» [42].
- **Rerun:** `... gap0_memory.py M4` (output `runs/GAP0-M4.txt`).
- **Setup (SEEDED):** the same ten messages, `summary_seq=10`, input seq 12, `include_neighbor=True` (what the builder uses, `builder.py:200-207`). Each query is the last owner message alone, as `builder.py:187-189` does. No model turn.
- **Literal runtime output** (items as `seq, role, text`):

```
«ضع حرف m»   -> 4 assistant (listed first in the rerun) and 3 user "ضع حرف m"; the assistant item is "محتاج أوضح المقصود من “ضع حرف m” حتى أكمل بشكل صحيح…"
«ياريت»      -> 7 user "ياريت";    8 assistant "الذهب الآن عند **4049.73 / 4049.97**…"     (seq 9 is an identical «ياريت»; the earlier one is shown)
«طيب»        -> 1 user "طيب شو وضع الذهب"; 2 assistant "ما قدرت أقرأ الذهب على هذا الحساب لأن الرمز/الارتباط الحالي غير مطابق …"
«تمام»       -> (no items; conversation_status no_match)
«شو وضع الذهب» -> 1, 10, 2, 8 (the refusal is third of four)
«XAUUSDm»    -> 6 assistant "نعم، الرمز الصحيح هنا هو **XAUUSDm**…"; 5 user "يعني XAUUSDM"
```

- **What the owner sees:** nothing directly. The model, replying to a bare «طيب», is handed the **first refusal** (seq 2) and the question that caused it as its recalled context, instead of the question that «طيب» actually answers.
- **Root cause:** the query is only the newest owner message (`builder.py:187-189`); matching is "any term" (`conversation.py:104-109`); duplicates keep an arbitrary survivor (`evidence.py:91-94`). The recall ignores the assistant message the short reply answers, which is the one thing that disambiguates it.
- **Class:** recoverable-not-led limitation (short owner replies drive recall by a single word, so the match is a lexical coincidence). UNSURE whether to call it a bug: it is the documented lexical design (`retrieval.py:15-52`), and the transcript, not recall, carries the previous turn.
- **Production caveat:** in the production thread this arm was `no_compacted_history` (inferred, section 3.2), so it did not run on the owner's messages; the transcript did the work. It will start to run on this owner's messages once his thread passes the compaction threshold.

### J-M5: a failed effect-tool call stays in the context for four runs

- **Owner request:** «اشتري ذهب» (SCRIPTED model proposes a buy).
- **Rerun:** `... gap0_memory.py M5` (output `runs/GAP0-M5.txt`).
- **Setup:** REAL tool loop on a fresh Agent with no broker. **SCRIPTED turn 1:** `trade_execute {action:"open_position", symbol:"XAUUSDm", side:"buy", volume:0.01}` (deliberately wrong shape). Run 2: one scripted plain reply. This run proves the carrying path, not a money refusal: no order was possible.
- **Literal runtime tool result (run 1):**

```
{"ok": false, "code": "tool_arguments_invalid", "issues": [{"path": ["account_id"], "type": "missing"}, {"path": ["action"], "type": "literal_error"}, {"path": ["side"], "type": "extra_forbidden"}], "retryable": true, "recovery": {"category": "invalid_tool_arguments", "next_action": "inspect_schema_and_repair", "safe_to_retry": false, "schema_tool": "tool_environment", …}}
```

- **`recent_tool_evidence` at the first request of run 2 (verbatim, trimmed):**

```
{"tool":"trade_execute","arguments":"{…}","observed_at":"…","time_basis":"observed","run_id":"…","ok":false,"identities":{"code":"tool_arguments_invalid"},"result":"{\"ok\":false,\"code\":\"tool_arguments_invalid\",\"issues\":[…]…"}
```

- **Root cause:** every `trade_execute`, `trade_close_positions` and `goal_step_execute` outcome is kept (the code comment: «every effect outcome keeps its identity», `run_evidence.py:158`; the set is at `:49`), including pure schema failures that never reached the executor, and the code is copied into `identities` (`run_evidence.py:175-178`).
- **Class:** leak (internal code carried forward) of low severity; keeping effect identities (order ids, approval ids) is **needed for safety** (do not double-submit), but keeping argument-validation failures adds no safety.
- **UNSURE:** I did not reproduce a money refusal (`agent_analysis_only`, approval needed) being carried; the code path is identical for any `ok:false` result of these three tools, but I only ran the schema-failure case.

---

## 5. Classification of every failure outcome in the memory/recall layer (16 outcomes)

Outcomes are the status strings and reasons the model sees in the recall JSON (`evidence.py:56-72`, `:309-346`, `conversation.py:67-114`), plus the one unavailable path (`evidence.py:385-395`). Per-family count after verification: **needed for safety 7, recoverable-not-led 5, owner-needed 3, bug 0, dead-end 0, UNSURE 1** (16 total).

| # | Outcome (where) | Class | Why |
|---|---|---|---|
| 1 | `conversation_status: scope_unavailable` (`conversation.py:67-68`) | needed for safety | Group/peer/other-Agent thread: private by design. |
| 2 | reason `conversation_scope_unavailable` (`evidence.py:189-190`) | needed for safety | Same event, repeated as a reason. |
| 3 | `conversation_status: no_compacted_history` (`conversation.py:71-72`) | recoverable-not-led | Says nothing about "the thread is in your transcript" or "use session_search". |
| 4 | `no_match` (conversation, lexical, overall: `conversation.py:105-106`, `:113-114`, `evidence.py:344`) | recoverable-not-led | An empty result gives no next step; `session_search` is mentioned only in the system policy (`lonora.md:466`). |
| 5 | `semantic_disabled` (`evidence.py:271`, `:310`) | owner-needed | Owner must enable it, choose an embedding model and have an OpenAI key; default is off. |
| 6 | `semantic_unconfigured` (`evidence.py:271`) | owner-needed | Enabled flag without a model. |
| 7 | `semantic_no_embeddings` (`evidence.py:273`) | owner-needed | No notes indexed; only the owner's REST/knowledge routes index (`routes/memory.py:220`, `routes/knowledge.py:35`). |
| 8 | `semantic_timeout` (`evidence.py:283-284`, 1.5 s at `semantic.py:14`) | recoverable-not-led | Falls back to lexical silently; model is not told to try again or search. |
| 9 | `semantic_unavailable` (provider/credential error, `evidence.py:285-286`; raised at `semantic.py` `embed_text` as `semantic_source_unavailable`) | recoverable-not-led | Same. |
| 10 | `invalid_embeddings` (`evidence.py:304-308`) | needed for safety | Defensive validation of stored vectors (size cap `MAX_VECTOR_DIMENSIONS`, `evidence.py:33`, `:297`). Not a bug; not observed. UNSURE whether any repair path exists. |
| 11 | reason `candidate_limit` (`evidence.py:244-245`) | needed for safety | Bounded SQL work. |
| 12 | reason `conversation_candidate_limit` (`evidence.py:187-188`) | needed for safety | Bounded SQL work. |
| 13 | reason `evidence_limit` (`evidence.py:341-342`) | needed for safety | Bounded model context. |
| 14 | reason `query_limit` (`evidence.py:311-312`) | needed for safety | Bounded query. |
| 15 | `status: unavailable` / `memory_source_unavailable` (`evidence.py:385-395`, `:345-346`) | recoverable-not-led | Database error is hidden from the model on purpose (good), but the model gets no instruction. |
| 16 | `status: "partial"` whenever semantic is off (`evidence.py:309-310`, `:344`) | UNSURE (label noise, not confirmed as a bug) | Every ordinary recall reads "partial". The hedging effect on a model is a guess: no prompt I found explains the word (`grep partial` over the system and prompt resources finds only trade wording) and I observed no behaviour change. |

Other families in the same layer, covered elsewhere or not failure outcomes for the owner: `memory_write` codes (`memory_edit_no_match`, `memory_edit_ambiguous`, `memory_edit_heading_protected`, `memory_too_large`, `memory_authority_claim_refused`, `memory_user_section_moved`, `memory_edit_content_required`, `memory_edit_old_text_required`, `version_conflict`, `owner_profile_requires_owner_message`; `edits.py:92`, `:185`, `:188`, `:254`, `:258`, `:272`, `:314`, `commit.py:27`, `packages/tools/src/lonora_tools/memory.py:96` for `owner_profile_requires_owner_message`, `:140`/`:149` for `version_conflict`) are tool errors the model repairs itself and are **needed for safety** where they guard authority text; owner-API codes of `index_note` (`memory_note_required`, `memory_too_large`, `semantic_model_required`, `knowledge_note_not_found`; `semantic.py:79-136`) are owner-needed (settings), never agent-facing.

---

## 6. Doc versus code

| Doc claim | Code | Verdict |
|---|---|---|
| `docs/agent-memory-and-recall.md:393-394`: «Automatic per-turn recall still covers only the current thread; other threads are reached through `session_search`.» | Conversation arm: current conversation thread only (`conversation.py:67`, `builder.py:208-211`). Memory document and semantic notes: agent-wide (`evidence.py:192-196`, `:222`). Run evidence: current thread only (`run_evidence.py:214`). | Partly true. Wrong for memory and notes. Correct sentence would be: conversation text and tool evidence are per-thread; MEMORY.md and notes are per-Agent. The doc also never says that conversation recall exists only after a summary (`conversation.py:69-72`) and that compaction starts at 80 messages (`context/compaction.py:69`). |
| `docs/agent-memory-and-recall.md:397-400`: reach-me `notify` "behaves like `message`" until `owner_notify` exists | `owner_notify` is registered (`packages/tools/src/lonora_tools/incoming_call.py:129`); its text says «Delivery is in-app only for now.» (`incoming_call.py:132`) | Stale. Code wins: the tool exists, delivery is still in-app only. |
| The doc never describes the automatic recall's ranking, the 4-run evidence window, the lexical-only default or the exact-identifier rule. | `retrieval.py:15-52`, `run_evidence.py:25`, `evidence.py:271-273` | Missing, not contradicted. |

---

## 7. Corrections to earlier audit files

- `journey-j4-background.md` J4-07 says semantic recall was not examined; it is examined here. Its default-off state and owner-only indexing mean semantic recall cannot have helped in the production conversation unless the owner configured it (UNSURE for production).
- The lead's trace point 3 (recovery block without candidates) is unaffected: this gap found no path in which memory supplies the candidate (`XAUUSDm`) after `symbol_not_found`.

## 8. Causes only (no fix design)

1. Failure and refusal text is replayed to later runs as ordinary history or as recall, unmarked (`conversation.py:96`, `history.py:110-122`).
2. Recall queries by the newest owner message alone, with "any term" candidate selection (`builder.py:187-189`, `conversation.py:104-109`), and starts only after compaction (`conversation.py:69-72`, `context/compaction.py:69`).
3. Lexical-only, exact-identifier matching by default; vector recall off by default and owner-indexed only (`retrieval.py:15-52`, `evidence.py:271-273`, `routes/memory.py:220`).
4. Evidence window of 4 runs drops the lesson (`run_evidence.py:25`); failed effect calls are kept including schema errors (`run_evidence.py:159`).
5. No prompt or tool makes an Agent store "this account's gold symbol" as a verified durable fact (`lonora.md:460`, `trading_context.md:5`); no `memory_write` call occurs in the 36 production tool calls (`production-trace.md` line 20 lists the tool; no TOOL EVENTS entry calls it).
6. UNSURE (minor): every recall is labelled "partial" when semantic is off (`evidence.py:309-310`, `:344`).

---

## Verification log

Independent check, code at the same tree (the only difference between `9f5b1da` and `0a03960` is docs under `docs/research/`, confirmed with `git diff --name-only`; repo `git status` clean).

- Citations opened and compared to the source: about 115 (every `path:line` in sections 0 to 8, plus the quotes).
- Citations corrected: 5. `history.py:116-119` (3 occurrences) was a fragment of the query; the full select and `limit(HISTORY_WINDOW)` is `history.py:110-122`. `tests/check_conversation_recall.py:147` is the group update; the assertion is at `:149-150`, now cited `:145-150`. Section 5's memory-write codes cited only `edits.py`/`commit.py`; two of them live in `packages/tools/src/lonora_tools/memory.py:96`, `:140`, `:149` (added).
- All verbatim quotes checked (doc 393-394 and 397-400, `incoming_call.py:132`, `lonora.md:460`, `:466`, `trading_context.md:5` fragment, `consolidator_archive.md:8`, `:11`, `evidence.py:402`, `run_evidence.py:158`): exact.
- Journeys M1 to M5 and both check scripts rerun. M1 to M5 reproduced the claimed outputs (recall order in M1, absent `recent_tool_evidence` in run 1 and run 6 of M2, the `XAUUSD` no-match in M3, per-query items in M4). One cosmetic difference: in M4 for «ضع حرف m» the assistant item is listed before the user item; text claim unchanged. Rerun output: `runs-chk/GAP0-M1.txt` to `GAP0-M5.txt` in the same audit directory.
- Claims refuted or downgraded:
  1. Section 3.4 (compaction "nothing tells the summariser to drop a resolved outcome"): REFUTED. `consolidator_archive.md:7`, `:36`, `:38` carry a latest-correction rule and `[durable]`/`[correction]` marks. Rewritten.
  2. Section 3.5 "no text tells the Agent ... " was incomplete: `trading_context.md:5` also says «Letter case alone is not a different symbol...» and `lonora.md:212` says use `market_symbols`. Added (these are discovery hints, not storage hints, so the main claim stands).
  3. Section 0 / 3.2 "recall is empty before compaction": imprecise. Recall also covers messages beyond the 100-message window through `unloaded_through` (`builder.py:203`, `:206`). Qualified.
  4. Section 5 row 10 `invalid_embeddings` labelled "bug": downgraded to needed for safety (defensive validation, `evidence.py:33`, `:297`); not a bug.
  5. Section 5 row 16 `partial` labelled "bug" with a claim that it teaches the model to hedge: downgraded to UNSURE; no evidence of behavioural effect.
  6. J-M4 class "bug": downgraded to a recoverable-not-led limitation, UNSURE as a bug; heading softened (for «ضع حرف m» recall actually returned the right exchange).
  7. Section 5 totals changed from 6/5/3/2/0 to 7/5/3/0/0 plus 1 UNSURE (still 16 rows; recounted by hand).
- Missed by the author and added: the summariser's supersession rule (item 1), the trading-context case-insensitivity hint (item 2), the beyond-window recall path (item 3).
- Not confirmed (left as UNSURE by the author, still unconfirmed): `summary_seq` of the production thread; whether production has semantic memory on; real-model behaviour of the summariser.
