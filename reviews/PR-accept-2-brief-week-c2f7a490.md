# accept/2-brief-week at c2f7a490 (W-ACCEPT: steps 5, 7a, 4a; no PR number yet)

- Branch: `accept/2-brief-week`
- Head: c2f7a490 (one commit)
- Base: 40183fb6. It merges cleanly with main 6cb4421d, with identical offline results.
- Verdict: **FINDINGS** (0 high, 2 medium, 4 low)

## Verified findings

### M1 (medium): step 5 never checks the pending approval, which main's brief already carries
- **Clause:** section 16 step 5 asks the brief to show "the pending approval with its reason". Only the *reason* waits for W-AUTH.
- **On main:**
  - Main's brief facts carry `pending_approvals` and `pending_approval_count` (`lonora_trading/morning_brief.py:222-238,295-296`).
  - An agent with no covering grant that calls `trade_execute` gets a pending `TradeApprovalRow` (`lonora_tools/trade.py:438`).
- **In this branch:** `morning()` (`scripts/agent_eval/acceptance.py:567-605`) has no check on them (grep: no `pending_approval` in `acceptance.py`).
- **Mutation:** with `brief_facts` returning `pending_approvals: []` and count 0, `acceptance.py --offline --steps 5` still passes.
- **Fix:**
  - Seed the euro agent's overnight `trade_execute` (no grant), so a Trade Approval is pending at brief time.
  - Assert `pending_approval_count == 1` and that the entry names the euro agent and its request.
  - Narrow the partial note to "the approval's reason (10.3) waits for W-AUTH".

### M2 (medium): step 5 leaves out "the day's events", and the note's reason hides main's path (0.4)
- **The note:** the fixture's partial note and `docs/acceptance-scenario.md:86` say "the brief's facts carry no calendar events". That is literally true.
- **Main's path:** main's brief wake tells Lonora to read events with its calendar tool (`morning_brief.py:425-427` `WAKE_TEXT`), and `economic_calendar_read` exists (`lonora_tools/market_analysis.py:241,386`).
- No `until` or `pending` entry tracks the gap.
- **Mutation:** removing the calendar sentence from `WAKE_TEXT` still passes step 5.
- **Fix:**
  - Either configure an `economic_calendar` integration over a local fake, script Lonora's brief run to call `economic_calendar_read`, and assert the seeded event came back in that run.
  - Or, at minimum, add a `pending` entry naming the gap and reword the note and the doc row to say events come from the calendar tool and are not exercised yet.

### L1 (low): step 7a does not check that the report asks what it learned and what it changed
- The runner checks wake, post, carry and once-a-week, but not that each `weekly_report` run's prompt carries `weekly_report.WAKE_TEXT`.
- **Mutation:** removing "what you learned, and what you changed in your method" from `WAKE_TEXT` still passes 7a.
- **Fix:** assert each weekly-report run's prompt contains `weekly_report.WAKE_TEXT`. Keep the model's words unasserted.

### L2 (low): step 4a judges the peers instead of the news agent
- **Where:** `acceptance.py:775-782` runs `judged()` (within authority, without asking, one line) on each peer's thread. The clause is about the news agent.
- **Effect:** a peer that asks the owner something fails 4a in live mode (more than the step says), while the news agent's own one-line explanation is never checked (less).
- **Fix:** `judged(stage, <news thread>, stage.ids["news"])`. Keep the plumbing checks (one message per peer, each woken in its own thread, framed as data).

### L3 (low): unrelated reformatting of the fixture
- `tests/fixtures/agent_eval/acceptance.json` is re-indented in untouched steps 1, 2, 3, 4b, 4c, 4d, 4e and 7b. That is most of the diff.
- **Fix:** keep the compact form for untouched steps.

### L4 (low): a stale pending mark after rebase
- W-METHOD #116 merged in 6cb4421d after this branch's base, but step 3 still says `{"pending": "W-METHOD: owner methods from files (5.6)"}`.
- **Fix:** on rebase, swap it for a `code` entry. Step 3 then needs a runner, or it reports "not written".

## What I checked
- **Real code paths:**
  - Step 5 drives `maintenance_account_recovery`, `brief_tick` at compressed times, `check_watches` and `execute_run`, and reads the facts from the real wake.
  - Step 7a drives `brief_tick` → `weekly_wait` → `wake_agents`.
  - Step 4a drives `dispatch_routines` → `peer_send` → peer runs.
- **New `code` needs:** they name features on main (W-BRIEF #93/#130, W-OWNER #113).
- **No vacuous passes found** (reviewer mutations):
  - dropping `since_last_brief` fails step 5;
  - dropping agent operations fails step 5;
  - not carrying the reports fails 7a;
  - raw text instead of `peer_content()` at `history.py:219` fails 4a.
- **Other:**
  - The partial mechanism still turns stand-ins into "not written" when their features land.
  - No trade choice is asserted.
  - No secret is printed.
  - Step 6 stays void.
- **Runs:**
  - `acceptance.py --offline`: 4a, 4c, 5 and 7a pass (partial); 6 void; the rest pending.
  - pytest `test_acceptance_scenario.py` + `test_agent_eval.py`: 169 passed.
