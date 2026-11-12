Superseded by VISION.md

# Owner action cards

Wave 1.5 slices W15-2 and W15-3. Every owner-only action has a one-tap card inside the
conversation, identical on Web and Mobile. Resuming trading, lifting a pause, settling
an uncertain trade, changing money limits and signing a trading grant never need a
settings page or the API. W15-3 adds the grant card (`grant_authority`, below), W15-4
the agent creation and Undo cards (`docs/agents-from-chat.md`), W15-6 the
supervision, Undo, Restore and pause cards (`supervise`, `supervision_created`,
`supervision_stopped`, `supervision_paused`, `docs/supervision.md`).
W15-8 adds the trust and secure credential cards (`trust_source`, `connect_credential`,
`docs/trusted-sources.md`): an MCP server's trust card offers the read or write tier only
when some tool may change something, and a credential card for an MCP server says
whether the trust card follows (or why not, waking the agent that asked). An agent's
model has no card: only the owner assigns it (`docs/provider-resilience.md`).

The Secret card (`secret`, VISION.md 7.2 and 10.3) asks for any other credential. The
agent chooses its label and fields (each a key in `[A-Z][A-Z0-9_]{0,63}`, the name the
value is saved under, and a label; `secret: false` only unmasks a field while it is
typed). The server sets the destination: an agent's card saves to the owner's
`workspace` secrets. Its values never pass the decision route: the card's own route,
`POST /owner-actions/{id}/secret`, stores them encrypted and settles the card in one
transaction, and the card, its events, the conversation and the agent's next run keep
only the keys. A second submit shows the card as it is and writes nothing.

A card is never a second authority path. It stores one exact effect, and the owner's
tap runs the existing owner function for that effect, in the owner's session.

## The record

`ln_owner_actions` (migration `0038_owner_actions`) holds one row per card:

| Field | Meaning |
| --- | --- |
| `kind` | `lift_restriction`, `resolve_operation`, `set_account_limits`, `grant_authority`, `create_agent`, `agent_created`, `supervise`, `supervision_created`, `supervision_stopped`, `supervision_paused`, `trust_source`, `connect_credential` or `secret` |
| `payload`, `payload_hash` | The exact, server-validated effect, and its hash. A passkey challenge is bound to the hash. |
| `subject` | The record the card acts on: `restriction:<id>`, `operation:<id>`, `account:<id>`, `grant:<agent>:<account>` |
| `source` | `agent` (proposed through the tool) or `system` (raised from a runtime event) |
| `agent_id`, `thread_id`, `run_id` | Where it is shown and who raised it. Ids are kept as values; a deleted conversation sets `thread_id` to null. |
| `status`, `status_reason` | `pending`, `confirmed`, `cancelled`, `expired` or `superseded`, with why |
| `timeline_seq` | The conversation sequence when it was raised; clients anchor it there, like a trade approval |
| `expires_at`, `decided_at`, `decided_via` | Single use with expiry; `tap` or `passkey` |
| `result` | What the confirmation did (the attested outcome, the stored limits) |

Lifetimes: limit and grant cards 24 hours, resolve cards 7 days, Lift cards 31
days and never longer than the restriction itself. Expiry needs no scheduler: a pending
card past `expires_at` reads as expired and is settled as expired when next touched.

## How cards appear

- **An agent proposes one** with `owner_action_propose(kind, …)` (toolset `trading`,
  long-tail, not financial). The server validates it against current state (the
  restriction is active or scheduled; the operation is `ambiguous`; the
  account is the owner's and the limit change is valid and not a no-op), dedupes it per
  agent and exact effect (a repeat returns the card already shown, also enforced by a
  unique index on pending cards) and caps pending agent cards at five per agent. A
  crash-replayed call returns the same card. The tool result says the owner must tap
  and that nothing has changed yet.
- **The runtime raises one with no model involved** (`lonora_gateway.owner_cards`,
  called by the attention projection for each event before its notification):
  - `trading.restriction_created`: a Lift card in the conversation whose run created
    the restriction, or in Lonora's conversation when the owner created it or the
    creating agent is gone.
  - `trading.operation_updated` moving to `ambiguous`: a three-button resolve card in
    the responsible agent's conversation, or Lonora's for the owner's own orders. The
    same event is the owner's `operation_uncertain` attention item (`action_required`,
    one per operation).
  - Runtime cards have ids derived from their record, so replaying an event never adds
    a second card.
- **Cards follow their record.** A lifted or ended restriction and a settled operation
  supersede the pending cards about them. Confirming a card supersedes
  any other pending card with the same exact effect. A settled operation also withdraws
  its `operation_uncertain` item. While its resolve card waits for an answer (or its
  `operation_uncertain` item is still open), the watchdog's later `operation_unresolved`
  alert for the same operation is not raised: the owner is asked once.
- **A delete settles them.** Deleting an agent, a conversation or a broker connection
  (`prepare_delete`) supersedes the pending cards that agent raised, that conversation
  shows, or that act on that account (`agent_deleted`, `conversation_deleted`,
  `account_deleted`). A card the owner is tapping at that moment is skipped rather than
  waited on; its decision finishes on its own.

## What the owner sees

Clients render one shared spec (`packages/core/src/owner-actions.ts`,
`ownerActionCard`), on Web (`components/owner-actions/OwnerActionCard.tsx`) and Mobile
(`components/owner-action-card.tsx`), in the owner's language with tickers, numbers and
times isolated for Arabic. Every fact comes from `facts`, which the server reads at
request time from the records the card names: global trading, the restriction's class,
scope, window and who set it (never its reason text, which an agent may have written),
the operation's action, volume, symbol, time and agent, and the account's current and
proposed limits. No ids, codes or JSON are shown; the account is named only when the
owner has several. The one stored text a card quotes is a creation card's task: it
becomes the new agent's standing instructions, so the card shows it word for word,
isolated and labelled as the agent's task ("Its task: …"), never as Lonora's words.

A limits card shows one line for every field its change touches
(`LIMIT_CHANGE_NAMES`): each limit, the currency ("Currency: USD → EUR") and the
trading day ("Trading day starts at midnight in: UTC → Asia/Riyadh"). A passkey never
signs an effect the owner did not see, such as a moved daily-loss window bundled with a
lower limit. If the account's limits changed so the card's change no longer fits them,
the card says "This no longer applies" and can only be dismissed; no passkey is asked.

| Card | Buttons | Needs |
| --- | --- | --- |
| New entries paused (Only exits allowed, Trading frozen) | Lift pause / Keep it | one tap |
| The broker did not confirm this trade | It executed / It did not execute / Unknown: release the hold, optional note and broker ticket | one tap |
| Change money limits | Apply (or Confirm with passkey) / Cancel | one tap when it allows no more risk; passkey otherwise |
| Create an agent? (an agent proposed it without an owner message) | Create agent / Not now | one tap; the agent gets no money authority |
| Agent created | Undo / Keep it | one tap; Undo removes an agent that has done nothing yet, otherwise pauses it |

Any answer on a resolve card, "Unknown" included, settles the operation and releases
the hold it puts on its market; the hint and the settled line say so. An owner who is
not sure yet leaves the card unanswered, and the hold stays.

A settled card shows one line instead of buttons ("Pause lifted.", "This pause
already ended. Nothing changed."). After a confirmation the server also writes one
line into the conversation, in the conversation's language, so the agent sees what
changed on its next run. It is built from fixed texts (`attention_messages.json`,
`owner_action_*`) chosen from the state after the effect (`still_holding`): after a lift
or an answer it adds what still holds new risk there — "Other pauses still apply there" (a pause in force over the same market and agents),
"A trade without a confirmed broker result still holds new risk there" — and only when
nothing does, "New trades are admitted again within each agent's level and your
limits". It never contradicts the header's safety line. A card whose agent was deleted
is confirmed in Lonora's name.

## The decision

`GET /owner-actions?thread_id=…`, `POST /owner-actions/{id}/challenge` and
`POST /owner-actions/{id}/decision` (`apps/api/src/lonora_api/routes/owner_actions.py`)
require the owner's session; no tool reaches them. A decision:

1. Locks the card. A card that is no longer pending answers from its record: the same
   decision again is idempotent, a conflicting one is `owner_action_already_decided`.
2. Settles a card past its expiry as `expired`, and re-validates the effect against
   current state: a stale card becomes `expired` with its reason
   (`restriction_already_ended`, `operation_already_settled`, `limits_already_set`) and changes nothing.
3. Runs the existing owner function in the same transaction:
   - Lift: `revoke_restriction`, the owner's lift.
   - Resolve: `attest_operation`, the T2 owner attestation. The note is optional; without
     one the statement reads "Owner attested via chat card; not broker confirmation."
     It emits `trading.operation_resolved`, clears the scoped block and never resends.
   - Limits: `store_execution_policy` with the card's exact changes applied to the
     account's current limits (other limits stay as they are). The account row is locked
     before the limits are read, the lock the policy route takes too, so the change is
     judged against and merged into the limits as they are now. A limit amount in a
     currency the account does not report is refused first, as on the policy route.

Raising or removing a money limit, lowering or removing the free-margin floor,
re-denominating set amounts and moving the trading day of a daily-loss limit widen what
may be lost. Such a card needs a user-verified passkey assertion: the client asks
`/challenge` (bound to the card id and payload hash, through the existing device
challenge store) and sends the proof with the decision. Without it the decision is
`owner_action_passkey_required` (403) and the card stays pending; a proof for another
card or a used challenge is refused. The first time on a device, the card registers it
inline (account password, then the passkey). Lowering or adding a limit, lifting a pause
and resuming take one tap and no passkey.

## The grant card (W15-3)

One sentence delegates trading: "let the gold agent trade my account on its own, 2%
daily loss". The agent proposes `owner_action_propose(kind="grant_authority", …)` with
only what the owner said; the tool resolves the rest on the server into a stored
`GrantDraft` (`lonora_contracts.owner_actions`) and nothing grants anything yet:

| Field | Default (owner decision D1) |
| --- | --- |
| `agent_id` | the proposing agent; only Lonora (the Personal Agent) proposes for another agent |
| `account_id` | the only connected account, or the agent's focus account; with several, the agent asks one question (`owner_action_account_required`) |
| markets | the owner's exact broker symbols; else all pairs for Lonora; else the agent's focus pair; else all pairs for a flexible agent |
| `actions` | every action (full management) |
| `duration` | until the owner stops it |
| `allow_manual_positions` | false: positions the owner opened are excluded unless switched on |
| `daily_loss` | the owner's amount or percentage; else, only when the account has no daily loss limit, a suggested 3% of current equity (rounded down to cents, in the account currency). An account that has its own limit keeps it: nothing is suggested over it |

### Custom or Full delegation

The card's list of options starts with one choice, never a separate button: **مخصص /
Custom** (selected by default) or **تفويض كامل / Full delegation**. The choice is part of
the stored draft (`GrantDraft.delegation`):

| Choice | What the card signs |
| --- | --- |
| Custom | The draft above with its D1 defaults: the markets, actions and duration the owner's sentence gave, the daily loss line, and the owner's own positions only when switched on |
| Full delegation | Every pair on the account (`symbol_scope` account), every action (open, close fully or partly, pending orders, change stop loss and take profit, cancel), until the owner stops it (no expiry), the owner's own positions included, no cap of its own and no daily loss limit from the card (`FULL_TERMS`) |

Under the selected choice the card says plainly, in Arabic and English, what it means
(`customMeaning`, `fullMeaning`); for Full it also says that money limits the owner set on
the account elsewhere stay in force and that removing them is a separate step with the
passkey (`fullLimits`). Under Full the own-positions switch and the daily loss opt-out are
gone (a line says the owner's positions are included; the card sets no daily loss limit).

Switching is the owner's decision on the card: `POST /owner-actions/{id}/decision` with
`{"decision": "choose", "delegation": "full" | "custom"}` (owner session only, the same
locks as any decision). It rewrites the stored draft and its hash: Full stores
`FULL_TERMS` and keeps the Custom terms in `custom`, so switching back restores them
exactly. It settles nothing and signs nothing, withdraws a proposal an earlier challenge
prepared for the other choice (its assertion then never confirms the card:
`owner_action_challenge_required`), and settles another pending card of the same agent
that already asks for exactly the chosen draft (`same_choice_on_another_card`). The next
challenge builds the envelope from the stored draft only, and confirming still needs the
same passkey ceremony; nothing about Full is weaker.

The challenge is bound to what the owner's screen shows. It names the choice the card
showed (`OwnerActionChallenge.delegation`, which Web and Mobile always send; the
own-positions switch, which only Custom shows, also means Custom). When the stored choice
differs, because the owner chose the other one on another screen or the answer to a choice
was lost, the challenge is refused with `owner_action_card_changed` (409) before anything
is prepared, and Web and Mobile read the card again (`rereadOwnerAction`) so it shows the
current choice, with the shared Arabic and English line saying so. The passkey therefore
never signs Full while the card shows Custom, or the reverse. Under Full the card shows no
own-positions switch, so a challenge that sends one is refused
(`owner_action_full_delegation_terms_fixed`). The choice is the only part of a grant
card's draft that changes after it is raised, and Custom is restored exactly, so the
choice binds the whole draft.

Full is offered only to an agent whose grant may cover every pair on the account (Lonora
or a flexible root agent; `full_available`). A fixed-market agent's card shows no choice,
and choosing Full for it is refused (`owner_action_full_delegation_unavailable`).

An agent may preselect Full with `delegation: "full"` only when the owner's own message
asked for full delegation, and the server checks it rather than leaving it to the model:
it preselects Full only in a Run that answers the owner's message and has read nothing
anyone else wrote (`owner_message_id`), only when the owner's words (that message, or one
he added while the Run worked, as W15-10 reads them for a model switch) ask for full
delegation, and only for an agent that can hold it. The words check
(`lonora_core.delegation_words.asks_full_delegation`) looks, in Arabic and English, for a
delegation word (تفويض, فوّض, صلاحيات, تحكم, delegate, control, authority, ...) within two
words of a fullness word (كامل, بالكامل, مطلق, كل, full, fully, complete, everything,
...): "تفويض كامل", "كل الصلاحيات", "full delegation" and "delegate everything" count;
"trade gold for me" and "تحليل كامل للذهب" do not. It is a word check, not a reading of
intent; a message it does not recognize only opens the card on Custom, where the owner
can still pick Full. Otherwise the card opens on Custom and the tool result says why
(`full_delegation_not_preselected`: `owner_message_required`,
`owner_did_not_ask_full_delegation` or `fixed_market_agent`). When the owner also named a
daily loss, a card opened on Full does not carry it (Full sets no daily loss limit; the
Custom choice keeps it), and the result says `requested_daily_loss_needs_limits_card` so
the agent proposes a `set_account_limits` card for it (adding a limit is one tap) or tells
the owner that Custom carries it. The owner still sees both choices and signs. Cards
stored before the choice existed read as Custom, and grants already signed are never
changed by it.

Signed Full delegation reads as such everywhere: the confirmation line adds
`owner_action_grant_full`, the settled card's first line is "Full delegation", the
readiness line reads "Trades on its own · Full delegation · until you stop it" with the
account's daily loss limit or "No money limit set", the safety sheet names the grant "Full
delegation", and the permission frame marks the scope `full_delegation` (every pair, every
action and the owner's positions until stopped; the account's limits and pauses still
bind it). It is recognized from the signed terms (`full_delegation` in
`lonora_contracts.account_authority`), so the envelope format is unchanged. The label
follows those terms, not the name of the choice: a grant signed from Custom with exactly
Full's terms (every pair, every action, until stopped, the owner's own positions switched
on), including one signed before the choice existed, reads as Full delegation on the
readiness line, the safety sheet, the permission frame and its own settled card alike.
What it may do is exactly what it signed; only the label is shared. Its confirmation line
still says what that card did (for Custom, the daily loss limit it set), and a Custom card
the owner dismissed shows no such line.

A card is raised only when authority is missing: a draft an active grant already covers
(same or wider markets and actions, full management without numerical limits, a validity
at least as long) is refused with `owner_action_not_needed_grant_already_active`. The
card shows, from server facts: the agent, the account, the markets, the actions in plain
words, until when, one daily loss line, the account's other money limits (or "No money
limit set"), other agents already trading an
overlapping market on that account on their own, the agent's own grant it replaces, and
on the owner's first grant the one rule of the previous vision.

The daily loss line is exactly what confirming does: the amount the card sets on an
account without one ("Daily loss limit: 300.00 USD (suggested: 3% of equity)"), the
owner's own lower amount from one to the other ("Daily loss limit: 500 → 300 USD"), or
the account's current limit unchanged ("Daily loss limit: 500 USD"). When the owner asked
for more than the current limit, the card keeps it and says that raising it needs a
limits card with the passkey; the tool result tells the agent the same
(`daily_loss_above_current_needs_limits_card`).

The replaced grant is described in full in one line: its markets, actions, every
numerical cap, the bounded protections (a stop loss on every entry, never loosened), its
expiry and the owner's own positions, then the new grant's side of each one that changes
("Replaces its current grant: all pairs · max 0.5 lots per order · max 3 positions →
XAUUSD · no volume, position or activity caps"), so a tap never removes a cap the card
did not show.

Its switches are the owner's choices: include my own positions (signed: it is sent with
the challenge and becomes part of the envelope; while the card waits the switch is the
only place that states it, and a settled card shows it as a line), "No money limit (my
choice)" ("No daily loss limit (my choice)" when other limits are set) where the card
would set a first limit, "Keep my current limit" where it would lower one, and per
conflicting agent "Stop <agent> trading on its own
on this account" (it revokes that agent's whole grant there, every market of it;
otherwise both keep trading and the account's limits bind them together). Lists use the
English comma in English and the Arabic comma in Arabic (`listSeparator`).

Signing runs the existing account-authority ceremony from inside the card:

1. `POST /owner-actions/{id}/challenge` takes the owner cards lock, the card, the
   owner's devices lock and then the agent's (the same order as the decision), builds
   the full-management `AccountAuthorityProposal` from the stored draft only
   (`grant_proposal`: the agent's own conversation as its thread, the draft's markets,
   actions and duration, no numerical limits), stores it with the existing `propose`
   and returns `begin_activation` options bound to its envelope hash. For the same
   choices the envelope is byte-identical to the permission composer's proposal. With no
   enrolled device it answers `device_registration_required` and the card registers the
   device inline, as every card does.
2. `POST /owner-actions/{id}/decision` with the proof runs `finish_activation`; an
   assertion for any other proposal is refused and the transaction rolls back. Then the
   card's choices, none of which widens anything: revoke each chosen conflicting grant
   (narrowing) and the daily loss limit, which the card
   sets only when the account has none and lowers only to an amount the owner asked for
   (`daily_loss_change`; it never raises one, never tightens the owner's own limit unasked
   and never converts a currency).
3. Dismissing a card revokes the pending proposal its challenge prepared.

The confirmation line says it is signed, that anything outside the grant comes back as
an approval card, and what else changed (the daily loss limit set, no limit by choice or
the current limit kept by choice, the other agent or agents stopped on this account).
The settled card names the agents it
stopped. A card for an agent that is deleted is superseded with it.

## No model cards

The former `agent_model` and `agent_model_changed` kinds are gone: only the owner assigns
an agent's model, in its settings or by naming the model in chat, and nothing about a
model waits on a card (`docs/provider-resilience.md`). Migration
`0131_agent_model_owner_only` settled the pending ones (`superseded`,
`model_cards_removed`) and moved every one to `ln_owner_actions_model_retired`, which
nothing reads.

## The raw execution-policy route

`PUT /trading/accounts/{id}/execution-policy` still accepts any change that allows no
more risk (adding or lowering a money limit or an execution cap, a tighter freshness
bound) in one owner request. A change that `policy_widens` is refused with
`execution_policy_passkey_required` (403): raising or removing a money limit
(`widens`), raising or removing an execution cap the executor enforces
(`max_positions`, `max_pending_orders`, `max_symbol_direction_volume`, `max_spread`,
`max_entry_drift_stop_fraction`), or accepting an older quote or account state
(`quote_max_age_seconds`, `account_max_age_seconds`). The owner signs it with
`POST …/execution-policy/challenge` (the exact policy, bound to
`hash(account, policy)`) and `POST …/execution-policy/verify` with
`{policy, proof}`, which stores exactly the signed policy. A proof for a different
policy, or a used challenge, is refused.

## Agent policy

The permission frame says only the owner lifts a restriction, attests an uncertain
outcome, changes a limit or signs a grant, and that the agent proposes the matching card
(`owner_action_propose`) when the owner asks for one, a grant only when no active scope
covers it.

## Known limits

- A grant card signs one account at a time; several accounts take one card each (a
  combined multi-account signature is Wave 2).
- A grant card's daily loss limit never raises or removes an existing one; that stays a
  limits card with the passkey, which the agent proposes separately. Full delegation sets
  none and removes none: the account's own limits stay in force.
- Full delegation is offered only to Lonora and flexible root agents; a fixed-market
  agent's grant stays on its pair.
- A runtime card is raised by the gateway's attention projection, so it appears when the
  gateway runs (within a tick); the API alone never raises one.

## Verification

- `tests/check_owner_actions.py` (PostgreSQL, simulation broker): no tool can confirm and an anonymous decision is
  refused; a restriction raises a Lift card in its conversation and the agent's reason
  never reaches it; lifting an ended restriction leaves the card expired with its reason;
  a pause lifted elsewhere supersedes its card; lowering a limit is one tap while raising
  or removing one needs a bound passkey; an uncertain trade raises `operation_uncertain`
  and a resolve card whose answer emits `trading.operation_resolved`, clears the hold and
  sends nothing; an agent's uncertain operation lands in that agent's conversation; the
  cap, expiry and crash replay; a moved trading
  day shown on the card and refused without the passkey.
- `tests/test_owner_actions.py`: classification, the widening matrix with a visible line
  for every differing field, proposal fields, no tool importing a decision, runtime-card
  idempotency and expiry, the confirmation line per post-decision state in English and
  Arabic, delete settlement and the fallback speaker, and the single uncertain-trade
  alert.
- `tests/web/owner-actions.test.ts` (tsx): the shared spec in both languages, Arabic
  arrows and isolation, currency and trading-day lines, the Unknown label and hint,
  settled lines, timeline anchoring, Web/Mobile parity.
- Playwright `tests/web/owner-actions.spec.mjs` and `tests/mobile/owner-actions.spec.mjs`:
  render and tap in Arabic and English (RTL button order), the resolve answer in the
  journal, and Lift from the header safety sheet.
- Grant cards: `tests/check_grant_card.py` (PostgreSQL, simulation broker, scripted
  authenticator) covers the resolved draft, the passkey and inline enrollment, the
  composer-identical envelope, the daily loss limit on confirm, the conflict
  note and stopping the other agent, no card for covered scope, Lonora's all-pairs
  default, withdrawal on dismiss, and the execution-policy passkey;
  `tests/test_grant_card.py` the pure rules; `tests/web/owner-actions.test.ts` the shared
  spec and switches; Playwright signs a grant card with a virtual authenticator on Web
  (Arabic and English, registering the device inline) and renders it on Mobile.
- Full delegation: `tests/check_full_delegation.py` (PostgreSQL, simulation broker,
  scripted authenticator) covers Custom with D1 defaults by default, switching back and
  forth through the decision route, the passkey still required, the account-wide
  envelope (every action, own positions, no expiry, no caps, no card daily loss),
  withdrawal of a prepared proposal on switching, a challenge for the other choice than
  the stored one refused both ways (`owner_action_card_changed`, nothing prepared), the
  readiness line and permission frame, the account's per-trade risk limit, position cap
  and a daily loss limit the owner set elsewhere still refusing under Full (exits still
  allowed), the preselection only from the owner's own words (a message that asks only
  for trading opens on Custom), the requested daily loss flagged on a Full card, the
  fixed-market refusal and a card stored before the choice; `tests/test_grant_card.py`
  the draft rules and the Arabic and English words check;
  `tests/web/owner-actions.test.ts` the shared choice, texts, the challenge naming the
  choice, re-reading a changed card, the settled label following the signed terms and
  Web/Mobile parity; Playwright chooses and signs Full on Web, chooses on Mobile, and on
  both refuses a stale card's tap and shows the current choice, in Arabic and English.
