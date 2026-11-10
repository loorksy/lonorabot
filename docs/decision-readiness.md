# Decision readiness

`market_decision_record` extends the existing market tools, deterministic
detectors, decision ledger and artifact store. It creates no trading authority and
does not replace the executor's final checks.

## Three distinct decision projections

`market_decision_record` preserves its existing immutable evidence and legacy
action/gate behavior while adding optional `readiness`:

- Market assessment is an explicitly labeled model interpretation: BULLISH,
  BEARISH, NEUTRAL or INSUFFICIENT_EVIDENCE. It needs matching fresh broker
  observations, a rationale and a supporting condition independently evaluated
  by the existing detector. Available prices or a requested BUY alone do not
  manufacture a directional assessment. Confidence is not calibrated.
- Entry readiness separately records whether the supplied concrete detector
  condition is confirmed, unconfirmed or lacks evidence. A forming candle
  pattern is not confirmed. A market bias alone creates no entry.
- Execution readiness is BLOCKED or REVALIDATION_REQUIRED, never executable
  permission. Controls, broker recovery, account state and evidence failures
  remain visible; the executor must recheck current authorization, instrument,
  exposure, risk, quality, idempotency and reconciliation immediately before any
  mutation.

An unrelated account/order read failure can block execution without erasing a
grounded market interpretation. Read-only transient observations have one
bounded retry through the shared broker manager. Financial mutations are never
retried by this recorder. Historical reads and comparisons use the recorded
readiness and evidence, not current prices. Old records without `readiness`
remain readable and retain their original operation identities.

## Strategy backtesting is excluded

The owner mandate (section 5, "Explicit Exclusion: Backtesting") excludes
strategy backtesting from Lonora. This document previously also described a
bounded SMA-cross historical research engine with walk-forward folds and seeded
Monte Carlo stress, exposed as `market_strategy_research` and
`market_research_history`. The engine (`lonora_market.research`), both tools,
their operating-policy lines and their tests were removed. No dependency was
added for them, so none was removed, and no web or mobile UI existed.

No backtest is a prerequisite for creating or changing a strategy or for agent
autonomy. Operating-policy chapters load only after a tool from their domain is
called, and the always-loaded core policy is at its size limit, so the exclusion
is stated in the chapters a backtest request most likely loads: broker market
evidence (after a candle or quote read), files (workspace analysis of historical
market data must not turn into one) and intelligence. The agent must
not build or run a historical strategy simulation, or present an old one as
validation or as a basis for authority; reading an old saved report on request
is allowed. Historical market observations remain ordinary analysis evidence;
see market structure, relationships and decision replay. Learning comes from
real recorded outcomes. Decision replay and relationship evidence are not
backtesting and are unchanged (Shadow trading is removed, Q57).

Data written while the engine existed is inert:

- Report attachments (`strategy-research.json`) remain ordinary owner files. They
  can still be listed, downloaded and read with `artifact_read`. Nothing reads
  their `state.research_result`, `research_scope`, `research_request_sha256` or
  `research_summary` keys any more. No migration rewrites or purges them, and the
  owner can delete them like any other attachment.
- A checkpointed call to either removed tool name gets the same outcome as a
  call to any unknown tool. If it was still pending, the Run tool loop does its
  usual checkpoint work (receipt lookup, Skill authority check, in-flight
  marker), then the registry refuses it with `tool_not_allowed`; no handler,
  broker or file access happens. If it was in flight when the upgrade
  interrupted its Run, the resumed loop cannot tell what it did and reports
  `tool_execution_uncertain`, recording the route as ambiguous
  (`reconcile_before_any_resend`). That is the conservative default for every
  interrupted unknown tool and is kept on purpose. Both removed tools had no
  broker effect, so there is nothing to reconcile at the broker; at most the
  interrupted call saved a report attachment, which is inert as described above.
  Old conversation history that contains such a call loads no policy guidance
  for it.

`tests/test_backtesting_excluded.py` enforces all of this. It checks that the
engine, the tools and any backtesting term are gone from the live catalog and
manifest, that the policy mentions backtesting only to exclude it, and that no
other shipped resource (skills, playbooks, constitution, prompts, bootstrap)
mentions it. It checks that the registry refuses the removed names and, against
PostgreSQL, that a Run interrupted mid-tool-block by the upgrade gets exactly the
two outcomes above when it resumes on the new catalog, and that a legacy report
attachment stays readable and inert.

## Verification

`tests/test_decision_readiness.py` covers independent opinion, entry and execution
readiness, stale or missing observations, forming candles, controls and old
records. `tests/check_decision_readiness.py` exercises the canonical tools over
four symbol classes and timeframes, bounded read recovery and immutable history.
It also runs a real owner-approved simulation request that still cannot bypass
reconciliation.
