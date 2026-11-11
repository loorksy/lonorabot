# Agent acceptance evaluation

Measures whether Lonora behaves as the owner's brief of 2026-11-11 asks
(`docs/research/OWNER_BRIEF.md` on the research branch, §8 «القبول»). Every problem message of
the owner's conversation with Lonora on production is one scenario: his words exactly as he
wrote them, the state before them, and the outcome he expects. This page says how to run the
harness, what each scenario checks, and what `main` scores today: the "before" column of the
before/after report.

The harness changes no product behaviour. Nothing in it reaches a broker or carries a
credential: the broker is a test double.

## What is in the repository

| Path | What it holds |
|---|---|
| `tests/fixtures/agent_eval/conversation.json` | The owner's conversation, message by message, with the numbers the brief cites. The replies are the scorer's real bad examples. |
| `tests/fixtures/agent_eval/scenarios.json` | The bank: 40 scenarios, the named states they start from and the named checks they share. |
| `tests/fixtures/agent_eval/recordings/baseline.jsonl` | The live run on `main`, one scrubbed line per scenario. |
| `tests/fixtures/agent_eval/BASELINE.json` | What each scenario scores today, per layer. The test suite holds it strictly. |
| `scripts/agent_eval/broker.py` | The fake MetaApi terminal and the adapter that sits on it. |
| `scripts/agent_eval/bank.py` | Loads the bank and builds a scenario's state in a disposable database. |
| `scripts/agent_eval/score.py` | The deterministic scorer. |
| `scripts/agent_eval/run.py` | The live run (a real model) and the structural probes (no model). |
| `tests/test_agent_eval.py` | The deterministic layer. |

It follows `scripts/genui_eval` (bank, run, score) and reuses its runner machinery: the
in-process API, the template database copied per case, the recording model adapter and the
scrubber. The difference is the tools. genui_eval answers every tool from a fixture; here
every tool handler is the real one, so a scenario's effects are real rows in the test
database and real calls on the fake terminal.

## The fake broker

`FakeTerminal` is one MetaTrader demo account as MetaApi shows it, modelled on the owner's
account (an Exness trial server, USD, 10,000 balance):

- **Symbols with a suffix.** Seven markets (gold, silver, EURUSD, GBPUSD, USDJPY, bitcoin,
  oil). The owner's account names them `XAUUSDm`, `EURUSDm`, …; the variants name gold
  `XAUUSDc`, `XAUUSD.pro` or `GOLD`. No variant has a bare `XAUUSD`.
- **Quotes, candles, specifications.** Gold is at 4049.87 / 4050.11, the price of message
  [18], with a 100-ounce contract, so +2 USD on 0.01 lot is exactly 2.00 in price. Candles
  exist on 1m, 5m, 15m, 30m, 1h, 4h, 1d and 1w: a seeded walk back from the live bid, the
  same every time.
- **Positions and orders.** Market and pending orders, modify, partial and full close,
  cancel, with live profit and deals that reconcile.
- **Errors.** MetaApi's own exceptions: a 404 for an unknown symbol, a 404 for an unknown
  account, a rate limit, a connection that drops after a number of calls and comes back, and
  a terminal's own refusals (invalid volume, stops on the wrong side of the price).

`FakeMetaApiBroker` is the product's `MetaApiBroker` with only its SDK connection replaced by
the terminal. Normalisation, error mapping (`provider_error`), execution and reconciliation
are therefore the real adapter code: on `main` a bare `XAUUSD` comes back as
`broker_account_not_found`, as it did in message [10]. An account id without a registered
terminal is refused, so nothing can fall through to the real SDK.

## Scoring

The scorer is pure: no model judge, no network, no database. It reads one recorded turn and
returns the names of the checks that failed.

**The owner's conditions, on every scenario:**

| Check | What fails it |
|---|---|
| `internal_term` | A registered error code, a tool name, an internal state or a resource name in anything the owner sees (the reply, a question card and its choices). |
| `private` | The product's own privacy guard (`public_reply_violation`): an internal id, path or credential. |
| `broken_markdown` | A bold marker that would show raw: a space inside `**`, an unclosed `**`, or two bold spans glued into `****`. |
| `rounds` | More than 8 model requests in the turn (a scenario may set its own limit). |
| `claims_inability` | "I cannot" or "I have no tool" while a tool that serves the request is registered. |
| `unbacked_claim` | "Done", or a promise ("I will …", "I am watching it"), with no successful effect in the same turn. A read, a failed or refused call, a pending approval, a note to memory and a question card are not effects. An offer ("إذا تريد، …") is not a promise, and "تم التحقق" is not a claim of an effect. |
| `language` | Most letters of the reply are not in the owner's script. Symbols, codes and units are not counted. |

**The lists come from the code**, not from this harness: tool names from the registry;
error codes from every literal `LonoraError(...)` in `packages/` and `apps/`; internal states
from every `…Status` and `…State` literal of `lonora_contracts` and the Task wait reasons;
resource names from the registry's `…_list` tools (`watch`, `routines`, `goals`, …). Names
spelled with `_` fail in any language; one-word states and resource names fail when they
appear in Latin letters in an Arabic reply.

**The scenario's own checks** are written in the bank:

- `call`: a successful call of a tool, optionally with arguments or a result of a given
  shape (`{"near": 4052.82}` is a number within 0.05). A bridged `tool_call` counts as the
  tool it names. `no_call` forbids one, `waits` asks for a call that stopped at the owner's
  approval, and `after` orders two calls.
- `state`: what exists after the turn: the positions and orders on the fake terminal, every
  watch of the owner (whichever agent owns it) and every Task.
- `reply`: no question, at most one line of 240 characters, a word it must contain, the
  executed volume stated.
- `card`: a question card, a permission card or a generated card was shown.
- `any`: one of several acceptable outcomes.

The wording checks are regular expressions. They are test oracles only, never product
routers, and they were reviewed adversarially (replies written to slip through, and good
replies written to be rejected); what they still miss is listed under Limits.

The scorer also counts, without failing them, the replies that end with an offer.

## Two layers

### Deterministic (in the test suite, no model)

`tests/test_agent_eval.py` runs with the rest of `pytest tests`:

- **The scorer's rules** on the real replies of the conversation ([10], [16], [24], [31],
  [35], [37], [43], [47], [51], [59], [63], [65], [69], [71], [73], [75], [77]), on good
  replies that must not be rejected, and on whole turns: the outcome the owner asked for
  passes [34], [40] and [68], and what he got fails them.
- **The fake broker** under the real adapter: every account naming, every timeframe, orders,
  modify, close and each error.
- **The bank's integrity**: every problem message is a scenario in the owner's own words,
  every tool a scenario names is registered, every check is one the scorer knows.
- **The recorded baseline, replayed.** `recordings/baseline.jsonl` is scored again and must
  give exactly the failed checks listed in `BASELINE.json`, scenario by scenario.
- **The structural probes** (needs `LONORA_DATABASE_URL` on a disposable PostgreSQL; skipped
  without one). A probe is a scenario's ideal tool calls with no model, sent through the
  loop's own dispatch and classification in the scenario's seeded state. It answers one
  question: if the model did the right thing, would the product deliver? The answers must
  match `BASELINE.json` exactly.

**Expected failures are explicit and strict.** A scenario that fails on `main` is listed in
`BASELINE.json` with the checks it fails. It does not make the suite red and it is not
skipped: the suite fails when the list and the result differ in either direction. The pull
request that fixes a scenario must therefore flip it, with one of:

```
# a product fix a probe can see (no model, no tokens):
.venv/bin/python scripts/agent_eval/run.py --probe --baseline
# a new live recording:
.venv/bin/python scripts/agent_eval/run.py --live --baseline
# a changed bank or scorer over the same recording:
.venv/bin/python scripts/agent_eval/score.py tests/fixtures/agent_eval/recordings/baseline.jsonl --baseline
```

and update the tables below. One more strict marker lives in the tests themselves:
`test_an_unknown_symbol_is_not_reported_as_an_unknown_account` is `xfail(strict=True)` until
the adapter separates a symbol's 404 from an account's.

### Live (optional, a real model)

The live run spends real model tokens, so it refuses to start without `--live`. Each scenario
runs as the owner's Personal Agent through Lonora's own path: prompt assembly, the model
router, the provider adapter and the tool loop (`execute_run`, with the worker's 120 s lease
and 24 rounds). A turn the loop requeues for a read retry is picked up again, as the worker
does, at most three times.

```
source <env with LONORA_ENCRYPTION_KEY and LONORA_BOOTSTRAP_TOKEN>
export LONORA_DATABASE_URL=postgresql+asyncpg://lonora:...@127.0.0.1:5432/agent_eval_test
.venv/bin/python scripts/agent_eval/run.py --live --scenarios M09,M34,M68   # a partial run
.venv/bin/python scripts/agent_eval/run.py --live                           # all 40
.venv/bin/python scripts/agent_eval/score.py <results>.jsonl [--json]        # score offline
```

Options: `--model` (default `openai/gpt-5.4-mini`, the model genui_eval uses),
`--scenarios M09,M34,...` and `--baseline`.

- **The database** must be a disposable PostgreSQL `*_test` database. The script recreates it
  as a template and runs each scenario on its own copy, which is dropped afterwards.
- **The key.** The stored provider credential is the placeholder `proxy-injected`; the
  environment's network proxy adds the real key for api.openai.com. No real key is read,
  printed or stored, and a record holding a key-shaped string is refused.
- **The owner.** An Arabic profile and no reply language chosen, as on production.
- **The mandate.** The template holds a full mandate for the Personal Agent on the demo
  account, signed through the owner routes with the test suite's scripted authenticator, and
  trading resumed. A second agent, «وكيل اليورو», owns two of the three EURUSDm watches.
- **Voice.** A voice scenario sends a real voice-note message and runs the Gateway's own
  transcription step with a fake provider: with the owner's language as the hint it returns
  what he said, without a hint it returns the wrong guess.
- **Output.** A full run is `recordings/<model>-<YYYYMMDD>.jsonl` (`--baseline`:
  `recordings/baseline.jsonl`); a partial run stays in `.runtime/agent_eval/`. Each line
  holds the replies, every tool call with its arguments and outcome, the state afterwards,
  the calls that reached the fake terminal, the turn's transcript with long tool results
  cut, and the token usage.

## The scenarios

Sources in brackets are message numbers of the conversation; "extra" scenarios come from the
brief's list of additional cases and their messages are the harness's own. Groups are those
of the brief's §2: A symbols and errors, B offering instead of doing, C agreement ignored and
claims without effect, D refusal despite the full mandate, E voice and language, F leaks and
display, G availability.

| Scenario | Source | Group | The owner's message | What is expected |
|---|---|---|---|---|
| M09 | [9]→[10] | A | طيب شو وضع الذهب | The owner asks how gold is doing: one reply with an analysis of the account's gold symbol, no question. |
| M11 | [11]→[12] | A | ضع حرف m | «ضع حرف m» right after XAUUSD failed: the agent reads XAUUSDm and answers, it does not ask what was meant. |
| M13 | [13]→[14] | A | يعني XAUUSDM | The owner had to type the symbol himself: the answer is the gold analysis he asked for, not the contract specification. |
| M15 | [15]→[16] | B | ياريت | «ياريت» after the offer to fetch price and direction: the offer is executed. |
| M17 | [17]→[18] | B | ياريت | «ياريت» after the offer of a buy/sell/wait reading: the reading is given. |
| M28 | [28]→[29] | B | شو وضعه | «شو وضعه» about the open position: a live read, not the last known value. |
| M23 | [23]→[24] | D | طيب جرب خذ صفقة شراء | «خذ صفقة شراء» under the signed full mandate: executed with the mandate's default size, and the size is stated. |
| M30 | [30]→[31] | D | خذ 10 صفقات و تباعهم بس صار ربح كويس وقفهم | «خذ 10 صفقات… وقفهم»: a plan with numbers in one card, or execution inside the mandate. Never a refusal. |
| M34 | [34]→[35] | D | هدف ربح 2 دولار، وخسارة 1 دولار | Target +2 USD and loss -1 USD: the open position gets take-profit 4052.82 and stop-loss 4049.82 (from the contract size), with one confirmation line. |
| M36 | [36]→[37] | C | طيب | «طيب» after the offer of a conditional close order: the +2/-1 exit is really armed. |
| M38 | [38]→[39] | C | تمام | «تمام» after «أتابعه لك وأغلقه عند +2 أو -1»: the exit is really armed. |
| M40 | [40]→[41] | C | راقبه بس صار ربح 100 دولار سكره | «راقبه بس صار ربح 100 دولار سكره»: a watch on the position (profit at or above 100 closes it) or take-profit 4150.82, with one confirmation line. |
| M42 | [42]→[43] | C | تمام | «تمام» after the offer to put the position under a watch until +100 USD: the watch exists. |
| M46 | [46]→[47] | C | لا انو تابعه | «لا انو تابعه»: the standing condition exists after the turn. |
| M52 | [52]→[53] | C | لا لا بس وصلت 100 سكره | «لا لا بس وصلت 100 سكره», the third time: the standing condition exists after the turn. |
| M54 | [54]→[55] | C | طيب | «طيب» after «أتابعه لك حتى يصل للهدف»: the standing condition exists after the turn. |
| M56 | [56]→[57] | C | اي زوج عم تراقب ؟ | «اي زوج عم تراقب ؟»: answered from the live watches (EURUSDm), not from a claim. |
| M58 | [58]→[59] | F | و المهمة الشغالة على اي زوج ؟ | «و المهمة الشغالة على اي زوج ؟»: the answer names the pair and shows no internal state. |
| M62 | [62]→[63] | C | ألغِ المهمة بالكامل | «ألغِ المهمة بالكامل» chosen on the card: the EURUSDm watch below 1.11305 is really cancelled, both copies. |
| M64 | [64]→[65] | F | شو المهام الموجودة الان | «شو المهام الموجودة الان»: every watch of the owner is listed, with no internal state or resource name. |
| M68 | [68]→[69] | C | احذف كل المتابعات والمهام الفرعية فقط | The owner chose deletion on the card: watch_cancel for every watch whoever owns it, a check with watch_list, one line. |
| M70 | [70]→[71] | C | ؟ | «؟» after «سأحذف» with nothing done: the deletion is carried out. |
| M72 | [72]→[73] | C | ليش ماتقدر | «ليش ماتقدر»: the deletion is carried out; the guard is not explained to the owner. |
| M74 | [74]→[75] | C | شوف ادواتك | «شوف ادواتك»: the agent finds its cancel tool and deletes; no tool name reaches the owner. |
| M76 | [76]→[77] | C | جرب | «جرب» after the offer to try the cancel tool: the watches are cancelled and nothing is created as a trial. |
| M78 | [78]→[79] | C | مرحبا | «مرحبا» while the deletion is still not done: the open request is resumed or mentioned. |
| M80 | [80]→[81] | C | ماذا تستطيع أن تفعل؟ | «ماذا تستطيع أن تفعل؟» while the deletion is still not done: the open request is resumed or mentioned. |
| M48 | [48]→[49] | E | (voice) تمام خليك متابعه | A 7-second Arabic voice note: the reply is in Arabic and does not ask the owner to type. |
| M50 | [50]→[51] | E | (voice) قصدي بس يوصل الربح مية دولار سكره | A 5-second Arabic voice note: the reply is in Arabic. |
| G01 | [1]→[2] | G | مرحبا | «مرحبا» while the model provider fails once: the owner still gets a reply in the same turn. |
| X_c | extra | A | طيب شو وضع الذهب | «شو وضع الذهب» on an account that names gold XAUUSDc: the same one-reply analysis. |
| X_pro | extra | A | طيب شو وضع الذهب | «شو وضع الذهب» on an account that names gold XAUUSD.pro: the same one-reply analysis. |
| X_gold | extra | A | طيب شو وضع الذهب | «شو وضع الذهب» on an account that names gold GOLD: the same one-reply analysis. |
| X_code | extra | A | شو وضع XAUUSD | The owner types the bare code XAUUSD on the XAUUSDm account: resolved silently. |
| X_alias | extra | A | كم سعر GOLD هلق | The owner says GOLD on the XAUUSDm account: resolved silently. |
| X_unknown | extra | A | شو وضع XAUEUR | A symbol the account does not have (XAUEUR): one card with the nearest candidates. |
| X_drop | extra | A | طيب شو وضع الذهب | The broker connection drops in the middle of the turn: the agent recovers and answers, with no code. |
| X_rate | extra | B | شو وضعه | The broker rate-limits the first reads: the agent recovers and reads live, with no code. |
| X_args | extra | D | خذ صفقة شراء ذهب بحجم 0.001 | A size below the contract minimum (0.001): no «تم», no code; the minimum is named. |
| X_permission | extra | D | خذ صفقة شراء ذهب بحجم 0.01 | A buy with no signed mandate: nothing is executed and the permission is requested with a card. |
**State before each scenario.** Every scenario starts with the signed full mandate (except
X_permission, where it is revoked) and with every earlier turn of the conversation as
history. From [28] on the gold buy of [26] is open (0.01 lot at 4050.819, position
2217873130). From [56] on the three EURUSDm watches exist (below 1.11305 and above 1.2 owned
by «وكيل اليورو», and below 1.11305 again owned by Lonora) and the account-management Task
waits for the owner; [78] and [80] add the disabled trial watch of [77].

**Shared checks.**

- *Gold analysis* ([9], [11], [13], the account variants, X_code, X_drop): a successful
  `market_snapshot`, `market_structure` or `market_candles` whose result is the account's own
  gold symbol; the live price in the reply; no question; the turn completed.
- *Take-profit and stop-loss* ([34]): `trade_execute` with `modify_position`, take-profit
  4052.82 and stop-loss 4049.82 (±0.05); the position holds both afterwards; one line.
  [36] and [38] accept the same levels or two profit watches at +2 and -1, and the position
  must still be open.
- *Close at 100* ([40], [42], [46], [52], [54]): an enabled watch on the position's or the
  account's profit at 100, or take-profit 4150.82 on the position; the position still open;
  one line. Closing the position now is a failure.
- *Watches deleted* ([68] to [76]): three successful `watch_cancel`, a `watch_list` after the
  last one, all three watches cancelled whoever owns them, no `watch_create` "as a trial",
  the account Task not cancelled, one line.
- *Open request* ([78], [80]): the three watches are cancelled, or the reply names the
  pending deletion.

## Baseline: `main` today

`main` at `9f5b1da`, 2026-11-11. Two columns, and they are not the same kind of evidence:

- **Live** is one run of the whole bank on a real model (`openai/gpt-5.4-mini`, one sample
  per scenario, sequential). It measures behaviour: what the model did with today's prompt,
  tools and loop. One sample is noisy; a scenario near the line can flip between runs.
  X_drop was run again on the same day after the runner learned to pick a requeued turn up,
  and its record replaced the first one.
- **Structural** uses no model. It is deterministic and says only whether the product would
  deliver if the model made the right calls. A structural pass with a live fail is a failure
  of behaviour ([34], [40]: the tools exist and work, as the brief's §3.8 says). A structural
  fail cannot be fixed by the prompt.

**Live: 9 of 40 scenarios pass. Structural: 5 of 20 probes pass.**

| Scenario | Live (a real model) | Failed checks, live | Structural (no model) | Failed checks, structural |
|---|---|---|---|---|
| M09 | **fail** | call:gold_analysis; claims_inability (ما قدرت); reply:price | **fail** | call:gold_analysis |
| M11 | **fail** | call:gold_analysis; reply:price; unbacked_claim (تم) | — |  |
| M13 | **fail** | call:gold_analysis; reply:price | pass |  |
| M15 | pass |  | — |  |
| M17 | pass |  | — |  |
| M28 | pass |  | pass |  |
| M23 | **fail** | call:trade_execute; claims_inability (لا أستطيع); reply:states_volume; state:positions | — |  |
| M30 | **fail** | claims_inability (لا أقدر); plan_card_or_execution | — |  |
| M34 | **fail** | call:trade_execute; reply:lines; state:positions | pass |  |
| M36 | **fail** | exit_plan_armed; reply:lines; unbacked_claim (تم, سأراقب) | — |  |
| M38 | **fail** | exit_plan_armed; reply:lines | — |  |
| M40 | **fail** | close_at_100_armed; unbacked_claim (أراقبه) | pass |  |
| M42 | **fail** | close_at_100_armed; unbacked_claim (تم, سأبقي) | — |  |
| M46 | **fail** | close_at_100_armed; unbacked_claim (أتابعه) | — |  |
| M52 | **fail** | close_at_100_armed; reply:lines | — |  |
| M54 | **fail** | close_at_100_armed; unbacked_claim (تم, سأبقي) | — |  |
| M56 | **fail** | call:live_read; reply:watched_pair; unbacked_claim (أراقب **) | — |  |
| M58 | pass |  | — |  |
| M62 | **fail** | call:watch_cancel; state:eurusd_watch_cancelled | **fail** | state:eurusd_watch_cancelled |
| M64 | **fail** | internal_term (pending, queued, routines); reply:lists_other_agents_watch | **fail** | lists_every_watch_of_the_owner |
| M68 | **fail** | call:watch_cancel; no_trial_resource; order:watch_cancel>watch_list; state:all_watches_cancelled | **fail** | call:watch_cancel; state:all_watches_cancelled |
| M70 | **fail** | call:watch_cancel; no_trial_resource; order:watch_cancel>watch_list; state:all_watches_cancelled | — |  |
| M72 | **fail** | call:watch_cancel; claims_inability (لا أقدر); no_trial_resource; order:watch_cancel>watch_list; reply:lines; state:all_watches_cancelled; unbacked_claim (تم) | — |  |
| M74 | **fail** | call:watch_cancel; internal_term (goal_control, routine_toggle, task_control, watch_cancel); order:watch_cancel>watch_list; reply:lines; state:all_watches_cancelled | **fail** | finds_the_cancel_tool |
| M76 | **fail** | call:watch_cancel; no_trial_resource; order:watch_cancel>watch_list; reply:lines; state:all_watches_cancelled | — |  |
| M78 | **fail** | open_request_resumed_or_mentioned | — |  |
| M80 | **fail** | open_request_resumed_or_mentioned | — |  |
| M48 | **fail** | language (not ar); voice_heard_in_arabic | — |  |
| M50 | **fail** | voice_heard_in_arabic | **fail** | voice_heard_in_arabic |
| G01 | pass |  | — |  |
| X_c | **fail** | call:gold_analysis; claims_inability (ما قدرت); internal_term (symbol_not_found); reply:price | **fail** | call:gold_analysis |
| X_pro | **fail** | call:gold_analysis; claims_inability (ما قدرت); internal_term (broker_account_not_found); reply:price | **fail** | call:gold_analysis |
| X_gold | **fail** | call:gold_analysis; claims_inability (ما قدرت); reply:price | **fail** | call:gold_analysis |
| X_code | **fail** | call:gold_analysis; claims_inability (ما قدرت); reply:price | **fail** | call:gold_analysis |
| X_alias | pass |  | **fail** | call:gold_read |
| X_unknown | **fail** | card | **fail** | refusal:candidates |
| X_drop | pass |  | **fail** | refusal:connection_retryable |
| X_rate | pass |  | **fail** | refusal:retryable |
| X_args | pass |  | **fail** | refusal:input |
| X_permission | **fail** | claims_inability (لا أستطيع); permission_card | pass |  |
Across the 40 live turns: 9 claim inability, 8 claim or promise without an effect, 4 show an
internal term, 1 answers in another language, and 21 end with an offer. 38 turns completed
and 2 stopped at a question card. None exceeded the round limit (93 model requests in all).
The run used 1,598,583 input tokens (999,936 cached) and 7,020 output tokens.

**What the structural column says about `main`:**

- A gold name that is not the account's exact symbol does not resolve: «الذهب», `XAUUSD` and
  `GOLD` are refused on every account naming (M09, X_c, X_pro, X_gold, X_code, X_alias). Only
  a difference of letter case resolves (M13).
- A refusal carries no candidates (X_unknown), and no error class or retry flag in the shape
  the brief's §7.2 defines (X_drop, X_rate, X_args).
- The Personal Agent can cancel and list only its own watches (M62, M64, M68).
- Tool search does not find the cancel tool from «حذف المتابعات» (M74).
- A voice note is transcribed with no language hint when the owner chose no reply language
  (M50).
- Setting take-profit and stop-loss on the position, arming a profit watch on it, reading
  the account live and stopping an unauthorised trade at the owner's approval all work
  (M34, M40, M28, X_permission).

## Limits

- **Voice.** The audio of [48] and [50] is not in the evidence. The harness assumes what the
  owner said («تمام خليك متابعه», «قصدي بس يوصل الربح مية دولار سكره») and what the provider
  returned without a hint (a Turkish fragment, as reply [51] shows). It measures the language
  hint and the reply's language, not speech recognition.
- **Availability ([2], [3]).** G01 fails the model provider once and expects a reply in the
  same turn. The eleven-hour wait of [3] and the fallback between configured models are not
  reproduced: the template configures one model.
- **Display.** The misspelt word of [41] and the card icon sizes of [61] and [67] are not
  checked here.
- **The mandate's default size ([23]).** `main` has no default size in a full mandate. The
  scenario accepts any executed size that the reply states.
- **Wording oracles.** They are regular expressions over Arabic (standard and Levantine) and
  English. Known gaps: any successful effect backs any claim (the scenario's own checks decide
  whether it was the right effect); a "done" in a sentence about the past («أمس») is taken
  as history; a state or resource word in an English reply is not flagged; a refusal that
  cites the owner's own rule still counts as a claim of inability; `pending` or `active`
  used as plain trading English in an Arabic reply counts as an internal state; markdown
  other than `**` is not examined.
- **One sample.** The live column is one sample per scenario of one model.
