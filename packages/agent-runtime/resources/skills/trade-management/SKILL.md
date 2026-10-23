---
name: trade-management
description: Prepare exact broker orders through immutable owner approval, current preflight, durable identity and independent result verification.
---

# Trade Management

## Steps

1. Recover the request, chosen side and loss limit. Use the bound account/symbol
   or discover the owner's connection with list_accounts. Read account_read and
   actual broker/login/server; saved configuration alone is not connectivity.
2. Inspect min/max/step volume, tick size, stops and fresh bid/ask. Read broker
   positions/orders including manual tickets. Derive a proposal from evidence
   and owner constraints when asked to plan. For a market entry with a money
   budget and explicit stop, use market_position_size in the exact account currency;
   do not convert cent-account units or invent tick economics. Its estimated stop
   loss excludes gaps, slippage, fees, carry and margin checks. Recheck the actual
   proposal after price movement; the estimate grants no permission.
   If blocked on a business decision,
   ask with wait_for_input; never ask generic consent before real confirmation.
3. buy/sell are immediate entries. Pending orders use buy_limit, sell_limit,
   buy_stop or sell_stop with a valid explicit price on the correct quote side.
   Never substitute an immediate trade for a pending request.
4. Use trade_execute for the immutable proposal or trade_close_positions for the
   frozen current ticket set. Financial controls accept approve/reject; typed
   yes, spoken yes and informational answers are not financial confirmation.
5. The same server path rechecks controls and targets after approval. Preserve
   manual intervention. Changed payloads need fresh approval. Respect OFF,
   Emergency Stop, scope and limits without workarounds.
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
"رفض الوسيط الحجم المطلوب؛ لم تُفتح صفقة." Never promise profit.
