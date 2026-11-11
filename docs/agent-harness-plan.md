# Agent harness plan

Phase 2 of the owner's brief of 2026-11-11 (`docs/research/OWNER_BRIEF.md`): what Lonora must gain to
be a complete agent, where each piece lands in the existing code, and in which pull request. It is
built on three research reports (`docs/research/nanobot.md`, `docs/research/rakazo.md`,
`docs/research/lonora-runtime.md`) and on the acceptance harness (`docs/agent-eval.md`).

Nothing here rewrites the runtime. Every item names the module it extends.

## 1. Where things stand

`main` at `792d30d`, 2026-11-11.

| Merged | What it changed |
|---|---|
| #59 | `bash scripts/build.sh` passes again. |
| #60, phase 0 | An instrument is resolved from the account's own symbol list (names in Arabic and English, broker affixes); orders name the listed symbol exactly and a refusal carries the candidates and the next call; a symbol's 404 is not reported as a missing account; tool search finds a tool from everyday Arabic and English words; error results carry `class` and `retryable`; a call that names no account means the agent's one account; voice notes are transcribed in the owner's language; bold markers; the question card's rows. |
| #57 | A default model is chosen once when a key exists and no routing; a reply that failed for lack of a model is answered when one is connected (never for an agent holding a signed grant); a cancelled or completed Task stops its watches; `watch_list`, `watch_cancel` and `trade_close_positions` are offered beside their creators. |
| #58 | The acceptance harness: 42 scenarios from the owner's conversation, a fake MetaApi terminal, a deterministic scorer. |

Measured by the harness, structural layer (no model): 8 of 22 probes passed before, 18 of 22 now. The
four that fail are in phase 3a and 3d below. The live layer (a real model) scored 7 of 42 before the
fixes; it is run again for the final report, because the later phases are what change behaviour.

## 2. Decisions

These settle the points the research left open. Each is the lead's decision under the owner's
instruction to decide without asking; each can be reversed by the owner.

**D1. The model does not receive machine codes.** The full error envelope
(`ok, code, class, retryable, hint, candidates, next_actions`) stays in the Run record, the logs and
the harness, where recovery and classification need it. What the model reads is `class`, `retryable`,
an authored `hint`, `candidates` and `next_actions`. A model cannot repeat a code it never saw. The
reply guard of principle 12 is then the second line of defence, not the only one. Every error without
its own hint gets its class's general hint.

**D2. No check reads the wording of a reply or of the owner's message.** PR #42 wrote wording guards
and removed them in the same pull request because they failed in both directions; nanobot has none;
rakazo forbids them. Three kinds of check are allowed: exact lookups against closed lists (tool
names, codes, state names), structural conditions on the Run (what was called, what succeeded, what
was promised in structured form), and the provenance of numbers. A judgment of meaning by a second
model is not added: the owner decided against a separate classifier call
(`docs/ui-reference/OWNER_DECISIONS.md`). After phases 3b and 3c the live evaluation measures how many
replies still end in an offer; if the number is not near zero the question returns to the owner with
that measurement.

**D3. An offer the agent cannot simply carry out is a card, and a card is an obligation.** A question
or offer is stored with the exact action each choice stands for. The owner's choice, or a short
consent in chat, makes that action an obligation of the next Run, which is checked against the Run's
successful results, not against its words.

**D4. Owner scope belongs to the personal assistant alone, in a Run the owner started.** Lonora may
act on any resource the owner owns (another agent's watch, task, routine) when the Run was started by
the owner's own message and has read no outside content since. Every other agent keeps today's rule
(own and supervised). The rule is enforced in the tools on the server.

**D5. The safe direction is direct; the risky direction is a card.** Stopping, pausing, cancelling,
revoking and lowering are done by a tool on the owner's message. Resuming, raising, connecting,
granting and anything that spends or reveals is a card the owner confirms. Signing a grant and
approving a trade stay the owner's own act.

**D6. No computer for the agent in this work.** Rakazo's sandboxed computer is its largest and least
safe part, and no failure in the evidence needed it.

**D7. A late Run is told it is late.** Any Run started by something other than a fresh owner message
(a retry, a wake, a resumed open request) carries when the request was made and what changed since.

**D8. Nothing is copied from nanobot or rakazo.** Ideas are re-implemented in Lonora's modules;
`THIRD_PARTY_NOTICES.md` does not change.

## 3. Gaps, ordered by their effect on the owner

Message numbers are those of the evidence conversation. "Now" is `main` at `792d30d`.

| # | Capability | nanobot | rakazo | Lonora now | Decision | Lands in | PR |
|---|---|---|---|---|---|---|---|
| 1 | A failure result carries the fix ([10], [12]) | Error strings that name the fix and list valid names; no structure | A sentence for the model with the next call and real nearby names; the code kept aside | Symbol errors carry `hint`, `candidates`, `next_actions`; other errors only `class` and `retryable`; the model still sees `code` | Complete the contract for every error; D1 | `tool_dispatch.py`, `environment.py`, each raising tool | 3a |
| 2 | The loop recovers by itself before the model writes ([10]-[13]) | Fallbacks inside tools, below the model | Corrects once, then stops and explains | Transient reads are retried; a resolution error needs a model round | A single candidate on a read repeats inside the tool; `resolution` and `connection` results with a named next step continue the turn, bounded | `symbols.py`, `tool_block.py`, `stop_gates.py` | 3a, 3b |
| 3 | A turn ends with a result, or continues ([12], about 25 replies ending in an offer) | Only in opt-in goal mode, keyed on a stored flag, unbounded | "Narration is not an answer"; a labelled nudge, three times | The stop gate works for Tasks only (`stop_gates.py:178`) | A bounded gate for conversations, keyed on structure (D2) | `stop_gates.py`, `loop_outcomes.py` | 3b |
| 4 | "Done" and promises match what ran ([63], [43], [47], [57]) | Prompt only | Verify by listing; offline grading | Only financial results are checked (`uncertain_outcome.py`) | The same structural check for every effect class; a failed check replaces the claim with a fixed true sentence | `uncertain_outcome.py`, `model_runtime.py` | 3b |
| 5 | A condition becomes a standing trigger ([40], [46], [52]) | Time triggers only | A watch with no model call, confirmed after it is seen in the list | Watches on a position's profit exist and were not used | A promise is valid only with a saved trigger in the same Run; the confirmation line states the computed level | policy text, `stop_gates.py` | 3b |
| 6 | An accepted offer is carried out ([36] «طيب», [68], [76] «جرب») | Nothing | Cards pause the Run and the answer resumes it | An answered question leaves no obligation (`messages.py:537`) | D3: the offer record and its obligation | thread state, `executor.py`, context builder | 3c |
| 7 | An unfinished request is kept ([78]-[81]) | A flag and a note, with "resume only if asked" | An open-work list always in context | `reply_outcome: "limited"` exists; nothing is carried to the next turn | An open-request record per conversation, shown on the next turn with "resume or mention" | thread state, context builder, `loop_outcomes.py` | 3c |
| 8 | No claim of inability while a tool exists ([71], [75]) | Every schema in every request | A search that cannot come back empty | The search gate is fixed and the counterparts are native; nothing checks that a found tool was used | A found tool that was never called continues the turn; an empty search says so and lists the group | `tool_discovery.py`, `registry.py`, `stop_gates.py` | 3b |
| 9 | Lonora acts on every resource of the owner ([62]-[77]) | Single user | Only in a Run the owner started that read no outside content | Cancel, extend and create are tied to the calling agent | D4 | `market_watch.py`, `tasks.py`, `routine.py`, `trading_goal.py` | 3d |
| 10 | Every owner action has a tool or a card (68 gaps) | n/a | n/a | 50 covered by tools, 12 by cards, 68 gaps | Section 5; D5 | tools, `owner_actions.py` | 3d, 3e |
| 11 | No internal word reaches the owner ([10], [65], [71]) | Raw errors reach users | Routing, not filtering; codes kept from the model | Redaction of secrets only; "registry names are intentionally not private" | An exact-match guard on tool names, codes and state names, replaced from fixed owner-facing labels; D1 | `public_reply.py`, `model_runtime.py` | 3f |
| 12 | Missing parameters inside a signed mandate ([23], [30]) | Asks | Asks with a card | Refuses or asks in prose | A default size from the mandate and risk policy, stated in the confirmation; a vague request becomes one plan card with numbers | `trade.py`, `account_authority.py`, `owner_actions.py` | 3g |
| 13 | A status answer is read live ([29], [56], [58]) | A cached value only after a freshness check | Nothing | "Use tools for current facts" in the prompt only | Numbers in a reply come from this Run's results (the rule cards already obey) | the number rule of `genui_compile.py`, applied to plain replies in `model_runtime.py` | 3f |
| 14 | What was learned is kept ([14]) | A two-hourly rewrite by a model: rejected | Nothing | The resolution is cached in memory per process | The resolver writes the account's symbol map durably | `symbols.py`, account settings | 3a |
| 15 | The owner's language, always ([50]) | Nothing | Nothing | The voice hint follows the owner's writing; the reply follows the model | A reply whose script differs from the owner's is re-asked once; the client sends its language with a voice note | `model_runtime.py`, voice upload | 3f |
| 16 | The answer to the question asked ([9]→[18]) | "Keep responses short" | Prompt | The policy text | Policy text and the live evaluation; no mechanism | `resources/system/lonora.md` | 3g |

## 4. The sixteen principles

How each binding principle of the brief is met. "Done" means merged and held by a test.

1. **Resolution first.** Done for instruments (#60). Phase 3a extends the same resolver shape to the
   other references a tool takes: account (by broker name or number), agent (by name), watch, task,
   routine and position (by what the owner called them). One module, one result shape: exact, one
   candidate, several, none.
2. **One error contract with automatic recovery.** Fields are in place (#60). Phase 3a completes
   them for every error and applies D1; 3b adds the bounded recovery in the loop.
3. **Do, do not offer.** Phase 3b: the conversation gate. It continues the turn when the Run's last
   result is a failure whose next step is a read or a repeat that was not taken, when a search found
   a tool that was not called, or when an obligation (principle 4) is unmet. Two nudges at most, each
   marked as automated; never past a permission result or an approval.
4. **A short consent carries out the offer.** Phase 3c (D3).
5. **A condition becomes a trigger.** Phase 3b: a watch, a routine or a broker-side stop saved in the
   same Run is what makes a promise true. The profit watch on a position and `modify_position`
   already exist; the policy text shows the two forms and the confirmation line.
6. **Inside a signed mandate.** Phase 3g.
7. **No claim of inability without evidence.** Phase 3b, the structural half. The other half is
   removing the causes: done for search and the counterpart tools (#60, #57); 3d and 3e remove the
   real inabilities.
8. **No "done" and no promise without a successful result; no trial calls.** Phase 3b. A tool that
   creates a resource cannot be called with a placeholder: the watch and routine tools refuse
   `enabled: false` on creation and a prompt that is not the owner's task.
9. **Open requests are durable.** Phase 3c.
10. **Owner scope.** Phase 3d (D4).
11. **Live reads for state.** Phase 3f, by the provenance of numbers.
12. **Reply guard on the server.** Phase 3f. Bold markers are done (#60).
13. **Answer the question asked.** Phase 3g, policy and evaluation.
14. **Remember what was learned.** Phase 3a.
15. **The owner's language.** Voice hint done (#60); phase 3f adds the reply check and the client's
    language.
16. **Power is not bypass.** Unchanged and tested in every phase: the executor, approvals, mandates
    and restrictions are not touched by any item here, and every recovery rule excludes the
    `permission` class.

## 5. Parity inventory

Every action the owner can take in the interface, against the tool or card an agent has for it. The
full table (130 actions with routes, tools and citations) is in `docs/research/lonora-runtime.md`.

| | Count |
|---|---|
| Owner actions | 130 |
| Covered by a tool | 50 |
| Covered by a card | 12 |
| Gaps | 68: no tool 45, own agent only 13, read gaps 10 |

Left to the owner by nature, and not counted as gaps: signing in, enrolling a passkey, signing a
grant, approving or rejecting a trade, deciding a card, answering a call, first-time setup.

### 5.1 Own agent only (13): closed by D4, phase 3d

For the personal assistant, in a Run the owner started: create, cancel and extend a watch of any
agent; create and cancel a task; create a routine; pause, resume and cancel a trading goal; read
another agent's alerts and scratchpad. Editing another agent's memory, and creating, switching or
rolling back its skills, change what that agent is: they become a card the owner confirms.

### 5.2 Read gaps (10): closed by read tools, phase 3d

Another agent's task detail, a routine's run history, another agent's goal decisions, the alerts of
all agents and their history, memory and profile revisions, owner-wide search over files, skills and
tasks, the file list, usage and cost, the owner-wide activity log. Reads carry no authority; the
personal assistant gets them owner-wide, other agents for themselves and those they supervise.

### 5.3 No tool (45): phase 3e

| Action | Decision |
|---|---|
| Stop all new trades (the brake) | Tool. Stopping is the safe direction and must never need a tap. Resuming stays a card. |
| Revoke a grant | Tool, on the owner's message. |
| Change the trading level | Lowering: tool. Raising: card. |
| Change an agent's market | Card. |
| Disconnect a broker account | Card. |
| Test a connection | Tool. |
| Complete, delete a task | Tool, on the owner's message. |
| Edit, delete a routine | Tool, on the owner's message. |
| Delete a watch record | Tool, with cancel. |
| An agent's light goals | Tools. |
| Wake a goal step now | Tool. |
| Mark alerts seen | Tool. |
| Alert policy and per-agent rules | Tool, on the owner's message. |
| Edit an agent (name, instructions, avatar) | Card. |
| Knowledge notes and links | Tools. |
| Semantic memory on or off and its model | Card. |
| Undo a memory or profile change | Tool, on the owner's message. |
| Owner name and form of address | Tool (the existing preferences tool gains the two fields). |
| Stop a Run, retry a Run | Tool. |
| Pin, mute, archive, mark unread a chat; lists; "keep archived"; web search for a chat | Tool. |
| Clear a chat | Card. |
| Create, edit a group | Create: card. Edit: tool, on the owner's message. |
| Block a skill version | Tool. |
| Revoke, restore a trusted source | Revoke: tool. Restore: card. |
| Remove a news feed | Tool. |
| Connect, disconnect Telegram | Connect: card. Disconnect: tool, on the owner's message. |
| Save a model provider key | Card (the key is typed by the owner into the card, never into chat). |
| Default model routing | Card. |
| Edit, delete a text file | Tool, on the owner's message. |
| Load a simulation snapshot | Not closed: the route is a leftover of the removed shadow trading and is retired. |

"On the owner's message" is the existing rule of `restrictions.py`: the tool acts directly only in a
Run the owner's typed message started; otherwise it raises a card.

## 6. Phase 3 pull requests

One focused branch and pull request each. Each lists the scenarios of `scripts/agent_eval` that must
flip, and `bash scripts/build.sh` passes before it opens.

| PR | Scope | Main files | Must flip |
|---|---|---|---|
| 3a | The error contract for every error; D1; one resolver for accounts, agents, watches, tasks and positions; the durable symbol map; single-candidate reads repeat inside the tool | `tool_dispatch.py`, `environment.py`, `symbols.py`, new `lonora_tools/resolve.py`, raising tools | X_unknown, X_rate, X_args (structural) |
| 3b | The conversation gate; the effect check for "done" and promises; no trial calls; a found tool must be used | `stop_gates.py`, `loop_outcomes.py`, `uncertain_outcome.py`, `market_watch.py`, `routine.py` | M36, M40, M42, M46, M52, M54, M62, M68, M76 (live) |
| 3c | The offer record and its obligation; the open-request record | thread state (one migration), `executor.py`, `messages.py`, context builder | M36, M38, M68-M80 (live) |
| 3d | Owner scope for the personal assistant; the owner-wide reads | `market_watch.py`, `tasks.py`, `routine.py`, `trading_goal.py`, `supervision.py` | X_owner (structural), M62-M76 (live) |
| 3e | The 45 actions with no tool: tools and cards as in 5.3 | `lonora_tools/*`, `owner_actions.py`, `capability_cards.py`, client cards | new parity probes, one per action |
| 3f | The reply guard by exact lookup; the provenance of numbers; the reply's language | `public_reply.py`, `model_runtime.py`, voice upload | M64, M70, M74 internal_term; M28, M56, M58 live read; M50 language (live) |
| 3g | Mandate defaults and the plan card; the policy text for "answer the question asked" | `trade.py`, `account_authority.py`, `owner_actions.py`, `resources/system/lonora.md` | M11, M23, M30, M34 (live) |
| Final | The live evaluation on a real model; the same conversation on the demo account; the before and after report | `scripts/agent_eval`, `docs/agent-eval.md` | all 42 |

Order: 3a, 3b, 3c, 3d, 3f, 3e, 3g. 3e is the largest and does not block the others.

## 7. Rules that hold in every pull request

- Money moves only through a signed grant or an approval card, at the one executor. No item adds a
  path to an order.
- An exit is always admissible. No resolver, gate or guard may hold back a close.
- Nothing new wakes an agent. The gate continues a Run that is already running; it starts none.
- The journal and the authority records are append-only.
- Every recovery and continuation rule excludes the `permission` class: a refusal by a rule is never
  something to route around.
- Each gate is bounded (two continuations) and records what it did in the Run state, so a production
  trace shows why a turn continued.

## 8. What is rejected

From nanobot: an unrestricted shell and file system, no approval model, unbounded goal mode, a
model rewriting shared memory, raw provider errors shown to the user, exception text passed to the
model, silent fallbacks. From rakazo: the sandboxed computer (D6), a checker model for the meaning of
replies (D2), "correct once, then stop and explain", the fallback "Using ‹tool name›". The reports
give the reason and the citation for each.
