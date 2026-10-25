# Runtime acceptance audit — 2026-10-25

A healthy API and passing scripted unit tests do not establish that the real model
can discover an operation, execute it, verify the outcome and deliver it. This
ledger separates those kinds of evidence. It does not declare the whole product
verified.

## Confirmed defects and changes

- Fresh runs advertised four bootstrap schemas without a complete capability
  inventory. Actual failed production requests discovered zero additional tools;
  an unmodified Personal Agent denied terminal and public-repository access.
  The Agent now receives a bounded inventory generated from its current permitted
  registry on every model turn, including resumed checkpoints. Exact schemas are
  still loaded progressively; permission and backend readiness remain separate.
- Real catalog search returned a thesis lifecycle operation for `terminal`, and
  omitted execution for `place order`. Actual operation descriptions now name their
  supported business actions. No user-intent keyword router was added.
- **Root response-boundary repair:** the former filter classified presentation,
  operation names and diagnostic vocabulary as security failures. A request to
  list capabilities therefore contradicted the server's own delivery rule. This
  combined veto and its second-model rewrite are removed. The model owns useful
  presentation, including explicit capability questions. The server deterministically
  redacts actual credential patterns, private resource IDs and local paths; verified
  broker IDs remain usable. Financial verification precedes this transformation,
  so another model cannot rewrite uncertainty into a success claim. Reply streaming
  and clarification questions use the same privacy-only boundary.

## Evidence matrix

| Capability | Evidence | Current limit |
| --- | --- | --- |
| Discovery and scoped inventory | Real106-tool catalog tests; compact4-schema surface retained | Model selection also needs actual-model journeys below |
| Response boundary | Full real106-operation catalog and technical wording accepted with one model call; credential/private-ID/path redaction and financial truth regressions | Style remains model guidance; recognized-pattern privacy does not claim universal secret detection |
| Workspace isolation and durable execution |12 disposable PostgreSQL integration groups | Production execution must also complete a natural-language journey |
| Procedure creation and progressive loading | Existing skill creation/progressive integration checks | No external repository package was installed |
| Market-to-Agent-to-trade loop | `check_agent_market.py`, real executor and simulation broker | Model choices scripted; no live order sent |
| Chart state/drawings/indicators/image | `check_chart_tools.py`, durable state/replay/concurrency/ownership | Native device display not exercised in this audit |
| Approvals/execution/reconciliation | `check_trade_approvals.py`, immutable review, ambiguous receipt, crash verification, exact no-resend | Simulation broker only |
| Actual connected broker reads | Read-only probes against all3 enabled saved MetaApi connections | **BLOCKED_EXTERNAL:** each returned `broker_account_undeployed`; no account/quote or execution readiness claimed |
| Real-model natural journeys | **VERIFIED_REAL_MODEL:** repository read, computed report, requested capability list despite stale denial, and two-turn topic switch | Latest production results:29.18s /13.19s /6.84s /4.10s. Nonfinancial allowlist; temporary state cleaned |
| Web SSE/timeline/failure notice | Prior7 actual Chromium/API/PostgreSQL cases and public authenticated SSE verification | Does not establish native Android/voice behavior |
| Android, voice, continuous watches and live financial outcomes | No new claim in this audit | Need separate device/live-runtime verification; no live-money tests |

## Repeatable real-model acceptance

`scripts/verify_agent_journeys.py --allow-live-model` exercises the actual model,
normal context, discovery, Agent loop, registered handlers, persisted final message
and verified attachment bytes. It runs four natural Arabic journeys: capability discovery despite stale denial; a two-turn subject switch; inspect the
supplied public GitHub repository without installation; compute a result with
actual Python and deliver a real report attachment.

The acceptance identity is temporary and has a24-hour runner-owned lease, with a
bounded per-journey timeout and cleanup. Discovery, execution and the model-return
boundary independently exclude financial operations, delegation and installation;
broker/trading services are denied. Real provider tokens are consumed. A crashed
outer process must clean its diagnostic identity before the lease expires. Do not
run this script implicitly as an offline CI check.

No provider deployment state was changed. An owner-stopped external terminal is
not silently restarted. The saved connections need activation at the provider
before their actual account/market/trading paths can be verified.
