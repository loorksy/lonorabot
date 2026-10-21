# Agent operating policy

## Source and runtime

`packages/agent-runtime/resources/system/lonora.md` is the canonical first-party
manual. It contains mandatory behavior and concise capability-specific guidance.
Tool descriptions and input schemas are passed from the live runtime registry;
they are not duplicated in the manual. It describes existing capabilities, not
an implementation roadmap.

The external structural reference was read as reference material only:
<https://github.com/asgeirtj/system_prompts_leaks/raw/refs/heads/main/xAI/grok-bot.md>.
Its desktop, shell, software-installation, cloud coding and external-machine
abilities are not Lonora capabilities and were not transplanted.

The audit covers the actual registration in `lonora_tools.loader`, all registered
schemas/metadata and their domain handlers, the Agent context/tool loop, voice,
Gateway scheduling, database ownership/authorization, market/chart execution,
trade confirmation, journal/reconciliation and Web/Mobile result presentation.

| Domain | Authoritative implementation |
| --- | --- |
| Persistent identity and scope | `lonora_db.agents`, `agent_binding`, `agent_directory` |
| Context, work and steering | `lonora_agent.context`, `tool_loop`, `lonora_db.tasks`, `task_wait` |
| Market, watches and charts | `lonora_tools.market`, `market_watch`, `chart_state`, `chart_snapshot`; `lonora_market`, `lonora_charts` |
| Broker identity/history | `lonora_tools.account`, `lonora_adapters.brokers.metaapi` |
| Financial commands and consent | `lonora_tools.trade`, `trading_goal`, `lonora_trading.execution`, `lonora_db.trade_approvals` |
| Goals and device authorization | `lonora_db.super_bot`, `lonora_auth.devices`, `lonora_trading.goals` |
| Evidence and performance | `lonora_tools.trading_decision`, `relationships`, `opportunity`, `shadow` |
| Memory and procedures | `lonora_memory`, `lonora_agent.skills`, `lonora_tools.memory`, `scratchpad`, `skills` |
| Collaboration and groups | `lonora_agent.collaboration`, `lonora_tools.collaboration`, `message`, `subagent` |
| Research, files, configured connections | `lonora_tools.search`, `artifacts`, `mcp` |
| Voice | `lonora_voice.context`, `realtime`, `sessions`, existing backend delegation |

## Loading and cost

1. `load_constitution()` prepends the concise mandatory core before the six
   existing mandatory policy documents.
2. `build_context()` retains the existing scoped memory, procedure snapshots,
   bounded history, binding, task/goal evidence and routing context.
3. `model_turn()` projects at most three domain chapters selected by actual
   recent tool calls that are still available. It does not classify owner text
   by keywords or add a model call to choose instructions.
4. The working projection leaves canonical history/checkpoints unchanged and
   preserves complete tool request/result exchanges. A resumed legacy execution
   also receives the mandatory core before the next model request.
5. The mandatory core is capped at 16,000 characters and domain guidance at
   14,000 characters. The complete manual and an additional schema copy are not
   inserted into each turn; exposed schemas come from the live registry through
   the normal model tool-definition channel. Existing provider context budgeting remains authoritative;
   no mandatory financial law is silently dropped to fit a small model.
6. Realtime voice loads a short policy from the same manual alongside existing
   voice authority/delegation rules. The existing 7,500-byte voice-context cap
   remains; the long-term-memory excerpt is reduced to make room.

Native Anthropic requests mark only the immutable first-party core as an
`ephemeral` cache prefix. Owner instructions, memory, broker state, source
observations and conversation remain outside that cache breakpoint. This adds
no network call, stores no secret in the manual and changes no permission.
Other providers retain their current behavior and can use their own automatic
prefix caching where supported. Cache hits and latency depend on the provider;
Lonora does not promise a cache hit or a fixed cost reduction.

## Public communication

The mandatory policy requires concise result-first replies in the owner's
language, a single useful next suggestion, truthful evidence/status and no
narration of internal cards, tools, skills, runs, events or API plumbing.
Broker identity/tickets and financial outcomes remain useful public facts.
Ordinary clarification can include generated question-specific choices and a
free-text answer; it cannot replace the real financial confirmation controls.

## Contract maintenance

Run `.venv/bin/python scripts/export_agent_tool_reference.py` after changing a
registered tool or its routing domain. The exporter verifies that every live
tool maps to a policy chapter and updates the manual and manifest hashes. The
tool's actual description and JSON schema remain in the runtime registry. The
exporter never calls a broker or database.

`--check` is part of `scripts/build.sh`. Startup/resource validation rejects a
missing/corrupt policy, stale tool coverage or oversized instruction sections.
Both the monorepo production wheel and the standalone Agent distribution ship
manual and manifest under `share/lonora/system`.
`check_policy_distribution.py` builds the production wheel offline and exercises
the real installed-layout fallback; this is also part of `scripts/build.sh`.
No new runtime, permission engine, memory system or procedure registry exists.

## Verification limits

`tests/test_system_policy.py` checks compact language-neutral policy, live tool
routing coverage, reproducible export, mandatory policy loading,
operation-based selection, complete exchanges, bounded voice, cache boundaries
and fail-closed resource validation. Scripted HTTP transport checks native
provider payloads without sending private data externally.

These are deterministic regression checks. They do not mathematically prove
that an arbitrary external language model can never produce an unwanted word.
Financial authorization remains server-enforced regardless of prompt adherence.

## Clarification and continuation

Necessary owner decisions use the existing `wait_for_input` flow, with generated
question-specific options and free text. The Agent must recover prior answers,
continue already requested reversible analysis/planning, and avoid plain numbered
menus. Financial confirmation still uses the separate server-validated approval.
The history projection restores up to eight exact question option sets from the
existing durable Run records, within the same thread and visible message range.
This is lower-priority conversation content and grants no authority.
Resumed checkpoints receive the current first-party core in the model request,
without rewriting canonical history or replacing owner-specific instructions.

## Legacy experimental data cleanup

The 14 old ambiguous operations were permanently deleted from production on
2026-10-21 at the owner's explicit request as construction-time experiments.
Their stale account recovery projection was removed; the regular broker observer
then independently reported `connected` / `broker_reconciled` with no unresolved
operations. No financial mutation or replay was used for that verification.
This was a one-time data cleanup, not a new automatic expiry policy: future
ambiguous financial operations must still reconcile and must never blind-retry.
Historical conversation messages were not deleted by that cleanup.
