# accept/2-brief-week at 23b8aa1d (re-review of the new commit only)

- Branch: `accept/2-brief-week` (no PR number yet)
- Head: 23b8aa1d. Previous review: c2f7a490 (`PR-accept-2-brief-week-c2f7a490.md`).
- Rebased onto main 6cb4421d. `git range-diff`: 5af34b14 is identical to c2f7a490.
- Reviewed: 23b8aa1d.
- Verdict: **CLEAN**

## Previous findings
- **M1 resolved, by a correct explanation.** On main a new agent is analysis-level, and `require_operation_permission` refuses it with `agent_analysis_only` before any card is raised (`lonora_trading/agent_permission.py:34-35`, `lonora_tools/trade.py:380`). A pending Trade Approval therefore cannot be seeded until Ask mode lands, so my "main supports it" was wrong. The step's partial note now names the gap and why, and `until` lists `lonora_db.trading_mode:set_trading_mode`.
- **M2 resolved.** The note says the day's events come from Lonora's `economic_calendar_read` and that no harness source feeds it, so the gap is named.
- **L1 fixed.** 7a checks each report wake carries `weekly_report.WAKE_TEXT` (results, what it learned, what it changed) and that the next day's brief wakes no second report.
- **L2 fixed.** 4a judges the news agent. `judged()` now filters calls per agent.
- **L3 fixed.** The fixture is compact again (−320 lines).
- **L4 fixed.** Step 3 is marked by its code (`lonora_api.pdf_layers:extract`, from #116) and reports "not written".

## New in this commit: a defect on main, held strictly
- Step 5 now takes partial profit, so a position stays open, and checks the brief's open positions against the broker, including the agent that opened each.
- **On main this fails.** The brief reports Lonora's position as the owner's:
  `NO  open positions as the broker shows them (brief [('XAUUSDm','buy','0.01','owner')], broker [('XAUUSDm','buy','0.01','Lonora')])`
  The commit traces it to the brief matching a position's broker tag against raw operation ids (3.3.4, attribution).
- The harness reports step 5 as `known defect` rather than passing. That is correct, and it belongs to W-BRIEF (R-AGENT's area). **Flagged for the lead and W-BRIEF.**

## What I checked
- **`acceptance.py --offline`:**
  - 4a, 4c and 7a pass;
  - 5 is a known defect (above);
  - 3 is "not written";
  - 6 is void;
  - the rest are pending.
- **pytest:** `test_acceptance_scenario.py` + `test_agent_eval.py`: 169 passed.
- **Clock changes:** the 7a brief-time computation (last brief before the close, first after it, in the owner's zone) was read against the commit's 9-zone / 30-day DST check.
