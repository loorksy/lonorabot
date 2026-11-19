# PR #224 at a2e3a2bc

- PR: #224 "W-SWEEP S16: every subscribed news feed reaches the agent (P1, 13.1)" (W-SWEEP)
- Head: a2e3a2bc. Base: main dcf86b43 (2 commits, 3 files); merges cleanly.
- Verdict: FINDINGS 0/1/1

## Findings

### M1 (medium, correctness): a cancelled feed read leaves every queued read running
- Where: `packages/tools/src/lonora_tools/feeds.py:115-119`
  ```python
  reads = [asyncio.create_task(paced(...)) for row in rows]
  if reads:
      await asyncio.wait(reads, timeout=READ_DEADLINE_SECONDS)
  for read_task in reads:
      read_task.cancel()
  ```
- Evidence:
  - `asyncio.wait` does not cancel its tasks when its caller is cancelled, and the `cancel()` loop is skipped when `CancelledError` propagates. That happens when the run is cancelled, or when the registry's 60 s tool timeout fires.
  - A probe at the head (scratchpad `orphan.py`: 40 fake feeds of 0.2 s each, `feeds.read` cancelled after 0.1 s) printed `tool cancelled; started so far 10` and then `after cancel: started 40 finished 40`. Every feed is still fetched after the tool is gone.
  - On main, cancelling `asyncio.gather` cancelled its children.
- Fix:
  ```python
  try:
      if reads:
          await asyncio.wait(reads, timeout=READ_DEADLINE_SECONDS)
  finally:
      for read_task in reads:
          read_task.cancel()
  ```
  Add a test that cancels the read and asserts no fetch starts afterwards.

### L1 (low, 0.4): "every feed is read" is untrue when the deadline is hit
- Where: `feeds.py:32` (`# … It paces requests; every feed is read.`) and the `news_feed_timeout` reason for every unfinished task (:120-125).
- Evidence: with 10 at a time, a 20 s per-feed timeout and the read deadline, a feed still queued at the deadline is never requested, yet it is reported as timed out. Feeds are ordered by `created_at`, so the newest subscriptions are the ones dropped.
- Fix: say "every feed is attempted until the read deadline". Optionally give a feed that never started its own reason (for example `news_feed_not_reached`), so the agent knows to read it again by `feed_id`.

## Rejected candidates
- The removed limits were safety bounds: no.
  - `MAXIMUM_FEEDS = 10` silently dropped feeds, which is a cap (P1).
  - The `.limit(500)` hid feeds behind older integrations and broke the duplicate check. On main, the PR's test gives `'subscribed' == 'already_subscribed'` failing.
  - The per-request bounds are kept: 1–30 items, 20 s per feed, 60 s per tool.
- Context blow-up: no. A tool result over 120,000 characters is stored, and the agent gets a `result_too_large` pointer.
- 6.10: unchanged. The result is `untrusted_content` / `external_evidence_not_instructions`, and `news_feed_read` and `artifact_read` are in the external list that taints the run.
- Pre-existing, outside this PR: `capabilities.py:132` lists only 200 integrations, and `capability_cards.py:64` has `.limit(500)`. They may suit a later 13.1 sweep.

## Checked
- Tests updated (14.1.3): both new tests fail on main and pass here.
- pytest on a fresh database: trusted_sources, context_engine, genui_taint, owner_intent: 96 passed. `check_owner_actions.py`: pass.
- Tool descriptions and schemas are unchanged, so no manifest change is needed (5.8.6).
