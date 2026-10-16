# Lonora implementation specifications

All 18 source documents are preserved verbatim under their original filenames. Numbers identify documents, not execution order. The appended in-chat activation/device authorization in 03 is authoritative. The master orchestration instructions govern the entire set.

Base audited: `895eaa8`; integration branch: `feat/coherent-agent-foundations`. No merge into main is authorized for this program.

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
| [19_AGENT_OPERATING_ENVIRONMENT_AND_SELF_DIRECTED_RUNTIME.md](19_AGENT_OPERATING_ENVIRONMENT_AND_SELF_DIRECTED_RUNTIME.md) | Self-directed Agent loop: typed tool recovery, route memory, and same-runtime continuation |

## Implementation control

- [Requirement matrix](IMPLEMENTATION_MATRIX.md): behavior, existing implementation, missing work, shared dependencies and verification evidence.
- [Dependency graph](DEPENDENCY_GRAPH.md): capability ownership and safe integration waves.
- [Progress](PROGRESS.md): current wave, blockers, test evidence and next integration point.
- [Nanobot architecture study](NANOBOT_ARCHITECTURE_STUDY.md): source-based comparison for specification 19. No Nanobot code is vendored.

A source file being stored does not make its functionality implemented. VERIFIED requires an executed behavioral test. Native/device verification is reported independently of browser validation. Financial authorization, ownership, exact symbols, journal, reconciliation and global controls remain authoritative.

Additional authoritative review instruction: [Continue full implementation and fix review findings](CONTINUE_FULL_IMPLEMENTATION_01_18_AND_FIX_REVIEW_FINDINGS.md). It preserves the original 18 specifications and requires the five safety/correctness findings to be fixed before subsequent capability waves.

Implementation reference: [Signed device authorization and native public bindings](DEVICE_AUTHORIZATION.md).
