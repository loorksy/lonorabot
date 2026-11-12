# PR #86 — W-RECEIPT 1: the Execution Receipt, one per broker-confirmed operation

- Head: bc22fcd8 (wreceipt/1-execution-receipt)
- Base reviewed against: d6b4a41 (W-AUTH stack), own commits d058aed..bc22fcd
- Reviewer: R-MONEY
- Verdict: **FINDINGS** (0 high, 2 medium, 2 low)
- Rebase request: the branch stacks on d6b4a41, and `wauth/3b-provenance` is now 8704653. Against that it conflicts in `apps/web/src/i18n/locales/{ar,en}/messages.po`. CI "build" on the head is red (it failed in 2 s, which looks like setup, not tests).

## Findings

### M1. A reconciled fill can show the position's current volume as the fill volume (10.3, 6.4)
- `receipt_facts` (`packages/db/src/lonora_db/execution_receipts.py:61-65`) shows `details.volume` and `details.price` as the fill.
- MetaApi reconciliation searches `current + deals + orders` (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:1033-1037`). When it matches the still-open position, it writes `"volume": found.get("volume")` and `"price": found.get("price", found.get("openPrice"))` (`:1082-1083`). That is the position's volume now, not the volume filled, even when the IN deal with the real fill volume is in the same evidence.
- The subagent's probe reproduced it: a buy of 1.00 filled, the position now holds 0.40, and deal `d1` holds 1.0. `reconcile` returned `{'deal_id': None, 'volume': 0.4}` and `receipt_facts` returned `{'kind':'fill','volume':'0.4'}`. I confirmed both sites in the code.
- The PR's open point 2 discloses the limitation. But the summary and the letter-check row say "the volume and fill price the broker reported", which is untrue for this path, and the card labels 0.4 a broker-confirmed fill.
- Fix, on the receipt side, leaving 6.3 code untouched: in `receipt_facts`, when `details.get("reconciled")` is true and `details.get("deal_id")` is empty, set `volume` and `price` to None so the card shows no number it cannot vouch for. Add a test with a reconciled position whose volume was reduced. Preferring the deal match in the adapter can follow after a demo check.

### M2. 10.3 "The agent can never draw 'confirmed' itself" is listed as implemented but is open (10.3, 6.10, 0.4)
- The PR lists 10.3 under "Mandate clauses implemented", and its letter-check row cites check 6, which only tests the owner's Settle answer.
- The GenUI kind `receipt` is still taught: `packages/agent-runtime/resources/prompts/genui_v2.md:33` has `{"kind":"receipt","title":"Alert active",…,"icon":"check"}`, and `packages/contracts/src/lonora_contracts/genui.py:53,65` lists it.
- The fixed card has no trust frame. An agent can compose a look-alike titled «أكّده الوسيط» over a trade that is still ambiguous. Open point 1 admits this. This PR makes the gap live, because a real fixed receipt now exists to imitate.
- Fix, either of:
  - move that sentence of 10.3 (and 6.10) from "implemented" to step 3 in the PR text; or
  - close it here minimally: rename the GenUI kind, and refuse GenUI facts sourced from a trading result whose status is not `confirmed`.

### L1. A receipt whose placement failed is shown in no conversation
- `execution_receipts.py:144-151` stores `thread_id=None` on a placement failure, and conversation deletion SET-NULLs it.
- `apps/web/src/conversation/Conversation.tsx:194-199` hides every confirmed journal row. So that operation has neither a receipt nor an order line anywhere.
- The stored state is reproduced (`thread_id=None` with the journal confirmed).
- Fix: fall back to Lonora's conversation instead of None. Alternatively, hide a confirmed journal row only when this thread lists its receipt.

### L2. Dead branches after the confirmed filter
- `apps/web/src/components/trading/TradeApprovals.tsx` and mobile `trade-approval.tsx` keep the `status === "confirmed" ? "ok"` and check-icon branches after `.filter(status !== "confirmed")`.
- Fix: delete them.

## Rejected (one line each)
- No receipt for a pending order's later fill at the broker: the PR does not claim it, and whether a broker-side fill is "an operation the broker confirms" (10.3) is for the lead to decide. Reported to the lead.
- The fallback insert in the `except` branch could itself raise and turn a confirmed send into ambiguous: not reproduced; needs a DB-level failure that would also fail the journal write. Hardening only (own savepoint).
- A deleted agent's receipt shows "Lonora" as sender: not reproduced; `delete_agent` refuses while an operation is unsettled.
- `trading.receipt_posted` has no gateway consumer: the gateway renders no trading cards today; 11.4 needs no push.

## What was checked
- **Only broker evidence confirms.** `persist_result` is the only writer of `confirmed`, and its only caller of `post_receipt` (every writer grepped). Model text, GenUI and the owner's Settle never reach it: `resolve_operation` sets `resolved`, and check 6 covers that.
- **One receipt per operation.** The receipt's primary key is the operation id, written with ON CONFLICT DO NOTHING. A concurrency probe ran 4 parallel settles and got 1 receipt. Terminal rows never move.
- **Every confirming path posts:** the door's send, the approved card, the owner's order, reconciliation, and restart recovery (checks 1-3, 5, 7).
- **A placement failure keeps the confirmation.** A probe forced an FK violation inside the savepoint: the result was still confirmed and the receipt was kept without a conversation (check 8).
- **No push (11.4).** `trading.receipt_posted` is not an attention kind.
- **3.1.2.** No FK to the agent; the thread link is SET NULL (check 9).
- **Migration 0100.** It is in range and chained to 0061. The backfill covers only anchored confirmed rows; the upgrade refuses if the old table holds rows; the downgrade and re-upgrade work. Journal rows are untouched (14.3.9), and an ambiguous-before-migration row reconciles with 0 resends.
- **6.1-6.9 unchanged.** No edits to `execution.py`, the adapters or admission. No assertion was weakened, and no prompt, tool or manifest changed.
- **Language and ids.** All new strings have Arabic on web and mobile, and no operation id or JSON is shown.
- **Runs** (fresh databases): the five core `check_*.py`, `check_execution_receipts` (9/9) and `check_execution_receipts_migration` all pass. The six core pytest files plus `test_execution_receipts`: 106 passed. The JS and Playwright specs were not run (no `node_modules` in the worktree).
