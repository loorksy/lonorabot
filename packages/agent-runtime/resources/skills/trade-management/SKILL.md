---
name: trade-management
description: Execute exact broker orders in the agent's trading mode, with exact owner approval where the server asks for it, fresh preflight, durable identity and independent verification.
---

# Trade Management

## Steps

1. Recover the objective and explicit owner parameters. Use the bound account/symbol
   or discover the owner's connection with list_accounts. Read account_read and
   actual broker/login/server; saved configuration alone is not connectivity.
2. Inspect min/max/step volume, tick size, stops and fresh bid/ask. Read broker
   positions/orders including manual tickets. Derive a proposal from evidence
   and owner constraints when asked to plan. Before choosing, view the trading
   skills this decision needs (structure, planning, risk, the instrument's family).
   For a market entry with a money
   budget and explicit stop, use market_position_size in the exact account currency;
   do not convert cent-account units or invent tick economics. Its estimated stop
   loss excludes gaps, slippage, fees, carry and margin checks. Recheck the actual
   proposal after price movement; the estimate grants no permission.
   Choose justified direction, lot size, stops and targets yourself; do not ask
   for routine parameters. If blocked on a decision only the owner can make, ask
   with wait_for_input; never ask generic consent.
3. buy/sell are immediate entries. Pending orders use buy_limit, sell_limit,
   buy_stop or sell_stop with a valid explicit price on the correct quote side.
   Never substitute an immediate trade for a pending request.
4. Use trade_execute or trade_close_positions for the exact request/current ticket
   set. Whether it executes or waits for the owner's Trade Approval follows
   trading-policy; its result says which.
5. The same server path rechecks current authority, controls and broker targets.
   Preserve manual intervention. A changed proposal is a new request. Respect
   pauses without workarounds.
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

- The independently verified outcome, real ticket and price/volume when known.
- A failure in plain words, with what did not happen, without internal IDs or
  diagnostic plumbing.
- No profit the account does not show.
