# Lonora implementation specifications

Latest product clarification: [Simple autonomous trading teammate — all 27 owner requirements](AUTONOMOUS_TRADING_PRODUCT_REQUIREMENTS.md). Extends the existing mandate with one-time bounded authority, discretionary sizing and management, multi-position goals, chart reasoning and peer collaboration. The mapping is an acceptance target, not a completion claim.

Current additional mandate: [Agent-first simplification, workspace, autonomous authority and native voice](<prompt 1.md>), preserved verbatim as supplied on 2026-10-21. See the latest entry in [Progress](PROGRESS.md) and [ADR 0001](../architecture/decisions/0001-agent-first-evolution.md). Its newer compact-policy direction supersedes the earlier line-count target; original reference documents remain intact.

All 19 source documents are preserved verbatim under their original filenames. Numbers identify documents, not execution order. The appended in-chat activation/device authorization in 03 is authoritative. The master orchestration instructions govern the entire set.

Initial01–18 audit: `895eaa8` on `feat/coherent-agent-foundations` (historical). The S19 extension was subsequently merged and deployed. Current environment work begins on `feat/trading-agent-environment` from `80b0ff9`; see PROGRESS.md for current evidence.

| Reference | Domain |
| --- | --- |
| [01_SKILLS_RUNTIME_REFACTOR.md](01_SKILLS_RUNTIME_REFACTOR.md) | Validated selective skills, policies and playbooks |
| [02_MOBILE_CHAT_UX_AND_STATE_RELIABILITY.md](02_MOBILE_CHAT_UX_AND_STATE_RELIABILITY.md) | Canonical chat timeline, native voice safety, scrolling and inbox reliability |
| [03_SUPER_BOT_MARKET_INTELLIGENCE_AND_DYNAMIC_WATCH_ENGINE.md](03_SUPER_BOT_MARKET_INTELLIGENCE_AND_DYNAMIC_WATCH_ENGINE.md) | Market evidence, detectors, dynamic watches, Super Bot and device authorization |
| [04_LONG_RUNNING_TASK_RUNTIME_AND_CONTEXTUAL_STEERING.md](04_LONG_RUNNING_TASK_RUNTIME_AND_CONTEXTUAL_STEERING.md) | Durable tasks, concurrent conversation, contextual steering and recovery |
| [05_PERSONAL_AGENT_AND_ACCOUNT_WIDE_TRADING_CONTEXT.md](05_PERSONAL_AGENT_AND_ACCOUNT_WIDE_TRADING_CONTEXT.md) | Personal Agent, explicit scope and account event ownership |
| [06_CROSS_AGENT_COLLABORATION_AND_GUEST_AGENTS.md](06_CROSS_AGENT_COLLABORATION_AND_GUEST_AGENTS.md) | Durable collaboration sessions, provenance and Guest Agents |
| [07_AGENT_MENTIONS_AND_DIRECT_IN_THREAD_ADDRESSING.md](07_AGENT_MENTIONS_AND_DIRECT_IN_THREAD_ADDRESSING.md) | Stable identity mentions and session-scoped addressing |
| [08_SHADOW_TRADING_AND_TRADING_PERFORMANCE_INTELLIGENCE.md](08_SHADOW_TRADING_AND_TRADING_PERFORMANCE_INTELLIGENCE.md) | Shadow execution isolation and performance intelligence |
| [09_EXECUTION_QUALITY_AND_PRE_TRADE_REVALIDATION_ENGINE.md](09_EXECUTION_QUALITY_AND_PRE_TRADE_REVALIDATION_ENGINE.md) | Fresh pre-trade revalidation and measured fill quality |
| [10_PORTFOLIO_EXPOSURE_AND_CROSS_MARKET_INTELLIGENCE.md](10_PORTFOLIO_EXPOSURE_AND_CROSS_MARKET_INTELLIGENCE.md) | Account-wide exposure and measured market relationships |
| [11_OPPORTUNITY_MEMORY_THESIS_LIFECYCLE_AND_MARKET_TRANSITIONS.md](11_OPPORTUNITY_MEMORY_THESIS_LIFECYCLE_AND_MARKET_TRANSITIONS.md) | Durable opportunities, thesis evolution and regime transitions |
| [12_MANUAL_TRADING_INTELLIGENCE_AND_OWNER_INTERVENTION.md](12_MANUAL_TRADING_INTELLIGENCE_AND_OWNER_INTERVENTION.md) | External broker changes and owner intervention priority |
| [13_MARKET_DATA_INTEGRITY_AND_TRADING_RUNTIME_HEALTH.md](13_MARKET_DATA_INTEGRITY_AND_TRADING_RUNTIME_HEALTH.md) | Market/account integrity and runtime health |
| [14_INTELLIGENT_ATTENTION_AND_NOTIFICATION_ENGINE.md](14_INTELLIGENT_ATTENTION_AND_NOTIFICATION_ENGINE.md) | Durable attention decisions, deduplication and channel ownership |
| [15_VOICE_TRADING_AGENT_EXPERIENCE.md](15_VOICE_TRADING_AGENT_EXPERIENCE.md) | Same-agent voice, final utterances and safe interaction |
| [16_TRADING_EXPLAINABILITY_AND_DECISION_REPLAY.md](16_TRADING_EXPLAINABILITY_AND_DECISION_REPLAY.md) | Historical decision evidence, versioning and replay |
| [17_BROKER_RECOVERY_AND_DEGRADED_MODE.md](17_BROKER_RECOVERY_AND_DEGRADED_MODE.md) | Reconciliation-first broker recovery and degraded behavior |
| [18_UNIFIED_TRADING_UI_UX_AND_LIVE_AGENT_STATE.md](18_UNIFIED_TRADING_UI_UX_AND_LIVE_AGENT_STATE.md) | Shared authoritative live state and progressive Web/Mobile UI |

| [19_AGENT_OPERATING_ENVIRONMENT_AND_SELF_DIRECTED_RUNTIME.md](19_AGENT_OPERATING_ENVIRONMENT_AND_SELF_DIRECTED_RUNTIME.md) | Persistent Agent environment, typed tool recovery, durable continuation and same-Agent voice |

## Implementation control

- [Requirement matrix](IMPLEMENTATION_MATRIX.md): behavior, existing implementation, missing work, shared dependencies and verification evidence.
- [Dependency graph](DEPENDENCY_GRAPH.md): capability ownership and safe integration waves.
- [Progress](PROGRESS.md): current wave, blockers, test evidence and next integration point.
- [Professional trading Agent environment build plan](NANOBOT_PARITY_AND_RELIABILITY_PLAN.md): selective Hermes Agent, gbrain, Rakazo, and Nanobot patterns integrated into Lonora's existing owners; seven waves, B01–B08 delivery requirements, R01–R07 architecture/product requirements, and C01–C11 TradingView/Chart Use requirements covering per-Bot scope, live drawings, on-demand visual sessions, observation/correction, Follow Agent/Free Browse, and English/Arabic bottom-sheet UX. AiChart is a visual reference only. The filename is retained for existing links; this is a proposal, not an implementation completion claim.

A source file being stored does not make its functionality implemented. VERIFIED requires an executed behavioral test. Native/device verification is reported independently of browser validation. Financial authorization, ownership, exact symbols, journal, reconciliation and global controls remain authoritative.

Additional authoritative review instruction: [Continue full implementation and fix review findings](CONTINUE_FULL_IMPLEMENTATION_01_18_AND_FIX_REVIEW_FINDINGS.md). It preserves the original 18 specifications and requires the five safety/correctness findings to be fixed before subsequent capability waves.

Implementation reference: [Signed device authorization and native public bindings](DEVICE_AUTHORIZATION.md).


Historical S19 kickoff: `feat/agent-operating-environment` from `21293ad`; see [kickoff](S19_IMPLEMENTATION_KICKOFF.md). That work was subsequently merged and deployed. Current branch and verification are recorded in PROGRESS.md.

Current environment capability cards: [Build capability cards](BUILD_CAPABILITY_CARDS.md). New implementation remains on its integration branch until an explicit merge/deployment instruction.

First context integration: [Global model context budgeting](CONTEXT_BUDGETING.md), including preparation, authenticated policy API, diagnostic interpretation, and remaining limits.
