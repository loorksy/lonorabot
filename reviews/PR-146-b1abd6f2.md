# PR #146 at b1abd6f2: FINDINGS (0 high, 1 medium, 2 low), with a rebase request

- PR: #146, team/2-lead-control (W-TEAM).
- Stacking: merge 82286085 brings in pause/5b at an older head (f224f4a6) and wteam/1-lead-role (f6affc53, #81), and through them wauth/1-3b and pause/1.
- Own range: 82286085..b1abd6f2 (ee5b1908 and b1abd6f2), plus the conflict resolution of 82286085 (checked with `--remerge-diff`). No migration.
- Reviewer: R-AGENT, 2026-11-12T07:55Z
- Verdict: FINDINGS

## Rebase request (not a finding)

pause/5b has moved to 5e40dad3. Rebase onto it.

## Finding 1 (medium): set_ask duplicates trading_mode_ask and misstates its effect (0.4)

- `packages/tools/src/lonora_tools/trade.py:1172-1192` (registered at `:1266`, from wauth/1 in the stack) already lets Lonora switch a team agent to Ask. Its description truthfully carries the exception "except within an active signed grant's own terms until it is revoked", and it returns `active_signed_grants`.
- The door confirms that exception: `packages/trading/src/lonora_trading/agent_permission.py:78-85` takes the grant path whatever the mode is.
- The new `agent_control set_ask` (`supervision.py:507-512`, result `:539-545`, description `:706` "set_ask (switch it to Ask)") returns `trading_mode: "ask", changed: True` with no grant count. It then requires Lonora to tell the owner in one line that the agent is in Ask, while that agent can still add risk inside its grant.
- The one-line gate also depends on which of the two tools Lonora picks: only `set_ask` sets `owner_line`.
- Fix: drop `set_ask` from `ControlAction`, `lead_control`, the description, `lonora.md` and the tests. Add `owner_line: "required"` and `next` to `switch_to_ask`'s result when the target is another agent and the mode changed (read under the lock). If `set_ask` stays, it must call the same code, return `active_signed_grants`, and carry the grant exception in its description.

## Finding 2 (low): text false at this commit (0.4)

- `docs/supervision.md:154`: "Every pause raises a `supervision_paused` card". Lonora's pause raises none (`db/supervision.py:598-603`).
- `docs/supervision.md:85-88`: `cancel_run` is missing.
- `docs/tool-execution-runtime.md:483-486`: "every wake is never checked". `_wake_gate` now checks wakes, and `lead_action_unreported` is missing from the table.
- `conversation_gate.py:18-19`: "never reads what the model wrote". `_lead_action_unreported` reads whether the reply is empty.
- Fix: update all four places.

## Finding 3 (low): in an owner turn, the one-line check is skipped when the turn also made a financial call

- In `conversation_stop_gate`, `_held(...)` returns ACCEPT before `_lead_action_unreported` runs. `_wake_gate` has no such bypass.
- Probe: `agent_control` pause with an empty reply continues the turn, but adding a confirmed `trade_execute` first lets it end silently. Output: `lead only: True with trade: False`.
- Fix: evaluate `_lead_action_unreported` before the `_held` early return.

## Rejected candidates

- Cancelling a run mid-send losing the journal row (6.3): rejected. `conclude()` and `persist_result` need no lease, catch `CancelledError` and record under the send lock. The same `cancel_run` backs the owner's route.
- Outcome return after a cancel: the gateway sweeper returns it on the next tick.
- Lonora setting Full: rejected. Only "ask" is reachable, and `set_trading_mode` refuses Full except `by="owner_tap"`.
- Lonora lifting an owner pause: rejected; the resume path is unchanged.
- A team agent leading: rejected; `is_lead` is checked first, and tested.
- Self or ancestor targeting: refused.
- Lock order: no inversion reproduced.
- 4.5.2 (ending the management task): the task is still per grant until 14.3.3, which is a later step.
- 14.3.9: the Literal only widens and nothing stores it.
- Clients: generic label.
- Merge resolution: consistent.

## What was checked

- `test_lead_powers`, `test_conversation_gate`, `test_supervision` and `test_pauses`: 38 passed.
- `test_capability_exposure` and `test_system_policy`: 41 passed.
- `export_agent_tool_reference.py --check` passes.
- Core 14.1.2: all pass (101 passed; five scripts PASS).
- `check_supervision`, `check_team`, `check_personal_agent` and `check_owner_actions` PASS.
