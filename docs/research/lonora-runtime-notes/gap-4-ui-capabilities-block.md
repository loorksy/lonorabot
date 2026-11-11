# Gap 4: the per-turn `<lonora_ui_capabilities>` block

Repository HEAD 9f5b1da, read-only. Causes only; no fixes proposed. Run output: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/GAP4-ui-block.txt`.

## 1. What the block is and when the model sees it

- The flag: `LONORA_GENUI_V2` is on only if it is one of `1/true/on/yes` (`packages/agent-runtime/src/lonora_agent/skills/visual_policy.py:21-22`). Note: the path in the assignment (`skills/visual_policy.py`) lives under `packages/agent-runtime/src/lonora_agent/`.
- The code comment says it is off by default and a server setting turns it on "only after the live evaluation passes" (`skills/visual_policy.py:15-17`).
- Per request, only when the flag is on, `model_turn` appends a system message after the cached prefix whose content is `VisualReplyProjector(context, messages).capabilities.block()` (`packages/agent-runtime/src/lonora_agent/model_runtime.py:81-90`). It is marked `context_origin="runtime_context"` (`model_runtime.py:87`).
- The block text is built at `packages/agent-runtime/src/lonora_agent/genui_capabilities.py:26-34`. The values are constants: `delivery: tuple[str, ...] = ("app",)` (`genui_capabilities.py:21`), routes `("market", "tasks", "usage", "files", "agents")` (`genui_capabilities.py:14`), intents `S_A01_INTENTS`, which prints as `ask, alert.create, alert.off` (run output below, and asserted at `tests/test_genui_projector.py:275-277`).
- The same flag also swaps in the long v2 policy text instead of the old one (`skills/visual_policy.py:76-78`). That text tells the model "Offer only the intents, channels and routes listed in <lonora_ui_capabilities>" (`packages/agent-runtime/resources/prompts/genui_v2.md:7`) and "Do not add a notification-method field to an alert; Lonora adds the owner's delivery row" (`genui_v2.md:9`). So with the flag on, the model is told to treat this block as the full list of what exists.

## 2. Was the flag on in production? UNSURE

- UNSURE. I could not confirm it. Evidence both ways:
  - `infra/compose/docker-compose.prod.yml:29-41` sets no `LONORA_GENUI_V2`, but the api service also loads `env_file: ../../.env` (`docker-compose.prod.yml:29`), which is not in the repo. `.env.example` has no such key (checked with `git grep -n "LONORA_GENUI"`, which finds only `visual_policy.py`, tests and docs).
  - `production-trace.md` has no system prompt text and no mention of `ui_capabilities` or `native_visual` (searched). So the trace cannot say whether the block was sent.
- Needed from the lead: the production `.env` value of `LONORA_GENUI_V2`, or one saved request for a production run (the trace export does not include system messages).
- The two other claims that "delivery is app-only" do not depend on the flag and were in every request: `packages/agent-runtime/resources/system/lonora.md:206` ("It is in-app only for now") and the `owner_notify` tool note "Off-app delivery (push, messaging channels) is not available yet." (`packages/tools/src/lonora_tools/incoming_call.py:29-31`). The block would be a third, repeated copy when the flag is on.

## 3. Mechanism A: `delivery: app` is a constant, and contradicts the code

- Constant: `genui_capabilities.py:21`. It is not read from integrations, owner settings or the gateway; `capabilities(...)` takes only `timezone` and `language` (`genui_capabilities.py:37-38`).
- Code that delivers off-app: the gateway forwards every assistant `message.created` of the configured thread and every `attention.ready` of importance `critical` or `action_required` to Telegram (`packages/gateway/src/lonora_gateway/event_dispatch.py:107`, `:124-130`, `:152`, `:171-172`; the "configured thread" filter was not re-checked by the verifier). This was found in J3-08 and the lines were re-read. UNSURE: whether the owner has a Telegram integration with `allowed_destinations` (no integration rows were inspected).
- The product decision behind the constant: "No delivery channels to the owner other than Lonora. Telegram remains an inbound agent channel" (`docs/ui-reference/OWNER_DECISIONS.md:92`). Where the doc/decision and the gateway code disagree, the code wins: the gateway code does send out. The block states the decision, not the code.
- Effect on the owner: the model is told, as a "capability" list, that delivery is `app` only. A model asked «ابعثلي على تيليجرام» or «نبّهني على جوالي» has this line, plus `lonora.md:206`, as its facts. UNSURE: that it would answer "I cannot" (no real model was run). UNSURE: "no tool sends to Telegram" is taken from J3-08 and was not re-verified here.
- The compiler also reads the same constant: the read-only "Delivery" row is built from `capabilities.delivery` (`packages/agent-runtime/src/lonora_agent/genui_compile.py:658-666`), and the compiler inserts that row itself, so the model cannot choose channels. (Correction: the document schema accepts channels `app`, `push`, `call` (`packages/contracts/src/lonora_contracts/genui.py:68`, check at `:605-608`); the test at `tests/test_genui_contracts.py:194-205` only shows `sms` is rejected by that schema, not that `capabilities.delivery` is enforced.) So an alert card can only ever show «داخل التطبيق», even when the gateway would also send a Telegram message for a critical attention item.
- Class: BUG (stale constant contradicts live code), producing a DEAD-END reply ("I can't reach you outside the app").

## 4. Mechanism B: reply language flips to `en` for any text without Arabic letters

- Code: `language="ar" if re.search(r"[\u0620-\u064a]", owner) or not owner else "en"` (`packages/agent-runtime/src/lonora_agent/visual_response.py:601-603`). `owner` is the newest user message with `context_origin == "conversation"` (`visual_response.py:586-593`). Only the characters U+0620 to U+064A count as Arabic.
- Result for Latin-script text: the model gets `language: en` (run output). I fed the two real voice transcripts from the production trace (`production-trace.md:140`: «ımuz lazım birasta» and «Bu korkuluklar nasıl hakkında») to the real `VisualReplyProjector`. Both produced `timezone: UTC · language: en`. The input text is taken from the trace; the projector code is real; nothing else is scripted.
- Same result for a bare ticker («XAUUSDm»), digits only («2400») and plain English. Not a bug for English. It is a problem for a message that carries no Arabic letters but is not English: a mis-transcribed voice note, a pasted symbol, a number.
- It conflicts with the standing rule in the system policy: "Reply in the owner profile's reply_language, else the language of the owner's latest message, unless asked otherwise." (`packages/agent-runtime/resources/system/lonora.md:58`). The block never reads `reply_language`; in production that row is empty (`production-trace.md:18`, `:78`), so nothing pins Arabic, and this block becomes a second steer toward English or whatever the transcript looks like. UNSURE: how much weight a real model gives a one-line `language:` hint against the policy text; I did not test a real model. And UNSURE whether the flag was on (section 2), so this may not have contributed to the Turkish reply at production-trace.md:18.
- Is `language` used for anything but display? No: the compiler reads `capabilities.intents` and `capabilities.routes` only (`genui_compile.py:551`, `:573`, and `:666` for delivery); I found no use of `capabilities.language` or `.timezone` in `packages/agent-runtime/src` (`git grep` returned only `genui_capabilities.py:32`). So `language` and `timezone` are display lines for the model only.
- Related: the v2 policy tells the model to write every card string "in the language of the owner's latest message" (`genui_v2.md:8`), so a Latin-script transcript steers card text the same way, independent of the block.
- Class: BUG. Voice-language fix belongs to the other session; this is one more place where "language" is decided from letters in the last message (listed here so that session finds it).

## 5. Mechanism C: owner-facing fallback strings pick English by the same test, with or without the flag

- The same constructor sets `self.failure` and `self.unavailable` from the same regex: Arabic «تعذر عرض هذا الجزء التفاعلي.» / «غير متاح», else "This interactive section could not be displayed." / "Unavailable" (`visual_response.py:594-599`).
- These are owner-visible: `self.failure` is written into the reply when a card is rejected (`visual_response.py:685`, `:831`, `:839`); `self.unavailable` replaces unbound numbers in prose (`visual_response.py:756`).
- It does not depend on `LONORA_GENUI_V2`: the projector is built for every reply (`model_runtime.py:110`, `:164`, and `visual_response.py:858`). So a Latin-script voice transcript makes a rejected card show an English sentence to an Arabic-speaking owner. If there is no owner message at all, the block says `ar` but the strings are English (run output "no_owner_message": `language: ar`, failure string English), an internal inconsistency.
- Class: BUG (small, owner-facing English in an Arabic product).

## 6. Mechanism D: timezone is always `UTC`

- `capabilities(language=...)` is called with no timezone (`visual_response.py:601`), so the default `timezone or "UTC"` applies (`genui_capabilities.py:37-38`). The run output shows `timezone: UTC` in every case. The module docstring says the block carries "the owner's timezone and language" (`genui_capabilities.py:5`), but no owner timezone is read. UNSURE where an owner-level timezone is stored; the earlier citation `packages/contracts/src/domain.ts:124` is a routine's timezone, not the owner's, and was removed.
- Effect: the model is told the owner's timezone is UTC. UNSURE what the model does with it; no code uses the field (section 4). Minor. Class: BUG (low).

## 7. Reproduction

Command: `cd /home/user/lonorabot && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 8 && .venv/bin/python /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/gap4_ui_block.py`

No model is called and no database is touched (the projector constructor only stores the context; SCRIPTED: the owner message text is the only input, I pass `None` as the context). Output, trimmed, verbatim:

```
LONORA_GENUI_V2 = None enabled: False
=== owner text: arabic
<lonora_ui_capabilities>
intents: ask, alert.create, alert.off
delivery: app
go: market, tasks, usage, files, agents
timezone: UTC · language: ar
</lonora_ui_capabilities>
failure string: تعذر عرض هذا الجزء التفاعلي. | unavailable: غير متاح
=== owner text: production voice transcript seq45 (from production-trace.md:140)
...
timezone: UTC · language: en
=== owner text: no_owner_message
timezone: UTC · language: ar
failure string: This interactive section could not be displayed. | unavailable: Unavailable
With LONORA_GENUI_V2=1: enabled True policy has <lonora_generative_ui>: True
Unset: policy has <lonora_generative_ui>: False
```

(The full file has every case; the Latin-text cases all print `language: en`, the English failure string and `delivery: app`.) What this does not show: the block inside a real request (it needs the flag on and a model call at `model_runtime.py:81-90`); that part is read from code, not run.

## 8. Count by outcome class

| Family | RECOVERABLE-NOT-LED | OWNER-NEEDED | DEAD-END | BUG |
|---|---|---|---|---|
| `<lonora_ui_capabilities>` block and its strings | 0 | 0 | 1 (off-app delivery claim, with BUG as root cause) | 4 (delivery constant, language flip, English fallback strings, UTC timezone) |

Nothing here is "needed for safety": none of these lines protects the money rules.

## 9. Corrections to earlier files

- J3-08 says the model is told off-app delivery is unavailable by `lonora.md:206` and the `owner_notify` note. Add: with `LONORA_GENUI_V2` on, a third statement (`genui_capabilities.py:21`, block line "delivery: app") says the same, and it is presented as a complete capability list (`genui_v2.md:7`). Flag state in production: UNSURE.
- No finding in `production-trace.md` is contradicted by this file.

## Verification log

- Citations opened: 58. Corrected: 3 (`visual_policy.py:71-78` -> `:76-78`; regex quote now shows the literal `\u0620-\u064a` escapes the source uses; `domain.ts:124` removed).
- Refuted: "a card whose Delivery channels are not in that list is rejected (test_genui_contracts)". The test checks the schema (`CHANNELS = ("app","push","call")`, `genui.py:68`), not `capabilities.delivery`.
- Refuted: `domain.ts:124` as "owner timezones". It is a routine's timezone.
- Downgraded to UNSURE: "will say it cannot" (no model run); "no tool sends to Telegram" (carried from J3-08, not re-checked); gateway "configured thread" filter.
- Confirmed: flag lines `visual_policy.py:21-22`, block at `model_runtime.py:81-90`, projector constructed at `:110`/`:164`, all `visual_response.py` and `genui_compile.py` lines, `genui_v2.md:7,9`, `lonora.md:58,206`, `incoming_call.py:29-31`, `OWNER_DECISIONS.md:92`, compose lines, production-trace lines 18/78/140. Absence check (no use of `capabilities.language`/`.timezone`): two greps (`capabilities\.(language|timezone)`, `\.timezone`) found only `genui_capabilities.py:32`. Rerun of the script reproduced the output (`language: en` for Latin text, English failure string with no owner message).
- Added: the `genui_v2.md:8` language rule and the `genui_capabilities.py:5` docstring/behaviour mismatch (both in body). Note the schema already admits `push` and `call` channels (`genui.py:68`).
- Section 8 counts re-checked: 1 DEAD-END, 4 BUG; unchanged.
