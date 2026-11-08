# Owner action cards

Wave 1.5 slice W15-2. Every owner-only action has a one-tap card inside the
conversation, identical on Web and Mobile. Resuming trading, lifting a pause, settling
an uncertain trade and changing money limits never need a settings page or the API.
Later slices add cards for grants (W15-3), agent creation and supervision (W15-4,
W15-6), trusted sources and credentials (W15-8).

A card is never a second authority path. It stores one exact effect, and the owner's
tap runs the existing owner function for that effect, in the owner's session.

## The record

`ln_owner_actions` (migration `0038_owner_actions`) holds one row per card:

| Field | Meaning |
| --- | --- |
| `kind` | `resume_trading`, `lift_restriction`, `resolve_operation` or `set_account_limits` |
| `payload`, `payload_hash` | The exact, server-validated effect, and its hash. A passkey challenge is bound to the hash. |
| `subject` | The record the card acts on: `trading`, `restriction:<id>`, `operation:<id>`, `account:<id>` |
| `source` | `agent` (proposed through the tool) or `system` (raised from a runtime event) |
| `agent_id`, `thread_id`, `run_id` | Where it is shown and who raised it. Ids are kept as values; a deleted conversation sets `thread_id` to null. |
| `status`, `status_reason` | `pending`, `confirmed`, `cancelled`, `expired` or `superseded`, with why |
| `timeline_seq` | The conversation sequence when it was raised; clients anchor it there, like a trade approval |
| `expires_at`, `decided_at`, `decided_via` | Single use with expiry; `tap` or `passkey` |
| `result` | What the confirmation did (the attested outcome, the stored limits) |

Lifetimes: Resume and limit cards 24 hours, resolve cards 7 days, Lift cards 31 days
and never longer than the restriction itself. Expiry needs no scheduler: a pending
card past `expires_at` reads as expired and is settled as expired when next touched.

## How cards appear

- **An agent proposes one** with `owner_action_propose(kind, …)` (toolset `trading`,
  long-tail, not financial). The server validates it against current state (trading is
  stopped; the restriction is active or scheduled; the operation is `ambiguous`; the
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
- **Cards follow their record.** A lifted or ended restriction, a settled operation and
  resumed trading supersede the pending cards about them. Confirming a card supersedes
  any other pending card with the same exact effect. A settled operation also withdraws
  its `operation_uncertain` item.

## What the owner sees

Clients render one shared spec (`packages/core/src/owner-actions.ts`,
`ownerActionCard`), on Web (`components/owner-actions/OwnerActionCard.tsx`) and Mobile
(`components/owner-action-card.tsx`), in the owner's language with tickers, numbers and
times isolated for Arabic. Every fact comes from `facts`, which the server reads at
request time from the records the card names: global trading, the restriction's class,
scope, window and who set it (never its reason text, which an agent may have written),
the operation's action, volume, symbol, time and agent, and the account's current and
proposed limits. No ids, codes or JSON are shown; the account is named only when the
owner has several.

| Card | Buttons | Needs |
| --- | --- | --- |
| Resume trading | Resume trading / Not now | one tap |
| New entries paused (Only exits allowed, Trading frozen) | Lift pause / Keep it | one tap |
| The broker did not confirm this trade | It executed / It did not execute / Still unknown, optional note and broker ticket | one tap |
| Change money limits | Apply (or Confirm with passkey) / Cancel | one tap to lower or add; passkey to raise or remove |

A settled card shows one line instead of buttons ("Trading resumed.", "This pause
already ended. Nothing changed."). After a confirmation the server also writes one
fixed line into the conversation, in the conversation's language
(`attention_messages.json`, `owner_action_*`), so the agent sees what changed on its
next run.

## The decision

`GET /owner-actions?thread_id=…`, `POST /owner-actions/{id}/challenge` and
`POST /owner-actions/{id}/decision` (`apps/api/src/lonora_api/routes/owner_actions.py`)
require the owner's session; no tool reaches them. A decision:

1. Locks the card. A card that is no longer pending answers from its record: the same
   decision again is idempotent, a conflicting one is `owner_action_already_decided`.
2. Settles a card past its expiry as `expired`, and re-validates the effect against
   current state: a stale card becomes `expired` with its reason
   (`restriction_already_ended`, `operation_already_settled`, `trading_already_running`,
   `limits_already_set`) and changes nothing.
3. Runs the existing owner function in the same transaction:
   - Resume: `apply_controls` with `{enabled: true, emergency_stop: false}`.
   - Lift: `revoke_restriction`, the owner's lift.
   - Resolve: `attest_operation`, the T2 owner attestation. The note is optional; without
     one the statement reads "Owner attested via chat card; not broker confirmation."
     It emits `trading.operation_resolved`, clears the scoped block and never resends.
   - Limits: `store_execution_policy` with the card's exact changes applied to the
     account's current limits (other limits stay as they are). A limit amount in a
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

## Agent policy

The permission frame says only the owner lifts a restriction, resumes trading, attests an
uncertain outcome or changes a limit, and that the agent proposes the matching card
(`owner_action_propose`); while trading is stopped it offers a Resume card. A grant is
still signed in the permission selector until W15-3 adds the grant card.

## Known limits

- The owner's raw `PUT /trading/accounts/{id}/execution-policy` is unchanged: an owner
  session may still raise a limit there without a passkey. The card path is the one the
  agent and the clients use.
- A runtime card is raised by the gateway's attention projection, so it appears when the
  gateway runs (within a tick); the API alone never raises one.
- Cards in a deleted conversation stay in the record with no conversation and expire.

## Verification

- `tests/check_owner_actions.py` (PostgreSQL, simulation broker): Resume changes nothing
  until the tap and is idempotent; no tool can confirm and an anonymous decision is
  refused; a restriction raises a Lift card in its conversation and the agent's reason
  never reaches it; lifting an ended restriction leaves the card expired with its reason;
  a pause lifted elsewhere supersedes its card; lowering a limit is one tap while raising
  or removing one needs a bound passkey; an uncertain trade raises `operation_uncertain`
  and a resolve card whose answer emits `trading.operation_resolved`, clears the hold and
  sends nothing; an agent's uncertain operation lands in that agent's conversation; the
  cap, expiry and crash replay.
- `tests/test_owner_actions.py`: classification, the widening matrix, proposal fields,
  no tool importing a decision, runtime-card idempotency and expiry.
- `tests/web/owner-actions.test.ts` (tsx): the shared spec in both languages, Arabic
  arrows and isolation, settled lines, timeline anchoring, Web/Mobile parity.
- Playwright `tests/web/owner-actions.spec.mjs` and `tests/mobile/owner-actions.spec.mjs`:
  render and tap in Arabic and English (RTL button order), the resolve answer in the
  journal, and Lift from the header safety sheet.
