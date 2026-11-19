# PR #183 re-review at e52ecaa5 (0d1ffcde merges receipt/2-settle; e52ecaa5 moves batch-14 callers to the card)

- Reviewer: R-MONEY.
- Verdict: **FINDINGS** (0 high, 1 medium, 0 low). M1 is carried from #96; fix it there and merge it forward.

## M1. A tool description is untrue at this commit (0.4)
- **Where:** `packages/tools/src/lonora_tools/owner_actions.py:253`, in the `owner_action_propose` description: the owner "answers executed / not executed / unknown, and any answer releases its hold".
- **Why it is wrong:** since 5c0df247 (this PR), Unknown keeps the card pending and the operation ambiguous and held (`keep_pending`). `check_owner_actions` asserts it: `unknown["status"] == "pending"`, journal `ambiguous`.
- **Impact:** the agent is told a false fact about the hold, and could pass it on to the owner.
- **History:** confirmed at eacb3806, e52ecaa5, cbbb1ac2 and 5c0df247. My CLEAN reviews of 5c0df247 and cbbb1ac2 missed it.
- **Fix:**
  - say "answers executed / not executed / unknown; Executed or Not executed releases its hold, Unknown keeps it held and the card pending), ";
  - regenerate the manifest (5.8.6).

## The merge
0d1ffcde keeps `move_to_lonora`, `OperationResolution` without `broker_reference`, and the removed route and form. It drops the unused `ExecutionPolicy` import and deletes `check_trading_restrictions.py`, as batch 14 does.

## No caller of the removed route is left
- In `apps/`, `packages/` and `tests/`, the only hit is `check_execution_recovery.py:484`, which asserts the retired route returns 404/405.
- e52ecaa5 is not weaker:
  - `check_owner_actions` "settled elsewhere" now settles through reconciliation's `persist_result` plus `operation_event`. It still asserts the card becomes `superseded/operation_already_settled`, and adds `status == "failed"`.
  - `safety-truth.spec.mjs` changes only its `finally` cleanup, to `settleCard()`.

## Note
55922ef0 and batch 14's 64a02ef1 and 42b8acb2 are not in this head. They merge cleanly and do not touch W-RECEIPT.

## Checks
- The core list: five checks pass; the six core pytest files, 101 passed.
- The same receipt, owner-actions and migration checks as on #96 pass; pytest 37 passed, 2 skipped.
- `node --check` on both specs: OK. Manifest OK.
