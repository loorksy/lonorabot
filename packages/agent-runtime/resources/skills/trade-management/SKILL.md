---
name: trade-management
description: Execute exact broker orders under current signed account authority or immutable owner approval, fresh preflight, durable identity and independent verification.
---

# Trade Management

Follow the owner's current language or explicit language preference in all
user-facing replies and labels. English examples do not require an English reply.

## Steps

1. Recover the objective, explicit owner parameters and current signed account scope. Use the bound account/symbol
   or discover the owner's connection with list_accounts. Read account_read and
   actual broker/login/server; saved configuration alone is not connectivity.
2. Inspect min/max/step volume, tick size, stops and fresh bid/ask. Read broker
   positions/orders including manual tickets. Derive a proposal from evidence
   and owner constraints when asked to plan. For a market entry with a money
   budget and explicit stop, use market_position_size in the exact account currency;
   do not convert cent-account units or invent tick economics. Its estimated stop
   loss excludes gaps, slippage, fees, carry and margin checks. Recheck the actual
   proposal after price movement; the estimate grants no permission.
   Under signed full management choose justified direction, lot size, stops and
   targets yourself; do not ask for routine parameters already delegated.
   If blocked on a decision outside that discretion,
   ask with wait_for_input; never ask generic consent before real confirmation.
3. buy/sell are immediate entries. Pending orders use buy_limit, sell_limit,
   buy_stop or sell_stop with a valid explicit price on the correct quote side.
   Never substitute an immediate trade for a pending request.
4. Use trade_execute or trade_close_positions for the exact request/current ticket
   set. A matching active signed account grant permits execution without an extra
   approval question. Otherwise use actual approve/reject; text, speech and
   informational replies never replace required financial confirmation.
5. The same server path rechecks current authority, controls and broker targets.
   Preserve manual intervention. A changed proposal needs fresh approval only
   when its action is not already covered by the current signed scope. Respect
   OFF, Emergency Stop, revocation and any chosen limits without workarounds.
6. Inspect the broker receipt and its independent verification. Distinguish not
   sent, rejected, accepted, placed, filled, partially closed and unverified.
   Never claim completion from approval or an acknowledgment alone.
7. Reconcile ambiguous submission before retry. Never change operation identity
   or send another mutation simply to retrieve a missing response.

## Management and historical questions

Preserve unchanged protection fields. Use actual position/order IDs. For a past
trade use trade_record_history then trade_record_read; today's quote is not
historical evidence. Missing evidence remains unknown.

## Output

Give the independently verified outcome, real ticket and price/volume when known.
Explain failure plainly without internal IDs or diagnostic plumbing. Example:
"The broker rejected the requested volume; no position was opened." Never promise profit.
