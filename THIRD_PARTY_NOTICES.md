Lonora incorporates modified UI primitives and design tokens from Rakazo.

Agent bootstrap profiles, retention instructions and description-first SKILL.md
organization adapt nanobot (https://github.com/HKUDS/nanobot), revision
fbb61a373f47769734a0d47d8f61935ffca84b84. Copyright (c) 2025-present Xubin Ren
and the nanobot contributors, MIT. The full notice is preserved in
packages/agent-runtime/resources/bootstrap/LICENSE.nanobot and distributed with
the runtime. Adaptations retain Lonora's existing PostgreSQL ownership,
financial approval, broker verification and versioned memory boundaries.

Progressive tool discovery adapts bounded catalog ranking from Hermes Agent,
https://github.com/NousResearch/hermes-agent, revision
c78ca093aa4b6759c055c3ed2bfbe7f741cf0292,
tools/tool_search_catalog.py. Copyright (c) 2025 Nous Research, MIT.
Adapted portions: BM25 corpus/scoring and bounded rare-term/coverage matching.
Changes: Unicode normalization/tokenization, existing Lonora typed registry,
native exact-name calls and current caller scope; no plugin runtime, English
stemmer or new dependency. The full MIT permission/warranty notice is retained
in lonora_tools/tool_discovery.py and ships in the wheel.

Stable tool exposure adapts the Tool Search design of Hermes Agent at revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a: tools/tool_search.py (an eager core
working set beside a stable bridge, so discovery never changes the tools array)
and tools/tool_search_validation.py (normalize_tool_call_entries: single-shape
name/arguments with JSON-string and empty arguments tolerated, bridge recursion
refused). Changes: the eager set is declared as per-tool exposure profiles in
Lonora's Tool metadata and frozen per Run in the fenced checkpoint; one
tool_call bridge (no tool_search/tool_describe split, no batches, no connector
routing) is resolved into the real call before every Lonora boundary observes
it, so receipts, guardrails, approvals and financial checks are unchanged;
used tools are remembered per agent in PostgreSQL. Copyright (c) 2025 Nous
Research, MIT. The full permission/warranty notice is preserved in
lonora_tools/registry.py and distributed in the Python wheel.

Continuous-work stop gates also adapt Hermes Agent at that same pinned revision,
agent/turn_stop_gates.py: the typed continue/stop verdict and bounded structural
terminal-protocol nudge. Changes: Lonora's existing Task/Run identity and durable
checkpoints, finite/continuous work semantics, real wait admission, owner controls
and market-wake recovery; no English intent classifier or separate Hermes engine.
Copyright (c) 2025 Nous Research, MIT. The full permission/warranty notice is
preserved in lonora_agent/stop_gates.py and distributed in the Python wheel.

The agent tool-execution core adapts Hermes Agent,
https://github.com/NousResearch/hermes-agent, revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a. Adapted portions:
agent/tool_dispatch_helpers.py (_plan_tool_batch_segments) and
agent/tool_executor.py (execute_tool_calls_segmented): ordered parallel/serial
segments of one tool-call block with bounded concurrency; agent/tool_guardrails.py
(ToolCallGuardrailController): exact-argument failure streaks, same-tool failure
counts, identical no-progress results, identical-call streaks and short call
cycles with warn/block/halt decisions; agent/chat_completion_helpers.py
(handle_max_iterations): one final tool-less report at the iteration limit.
Changes: admission to a parallel segment comes only from Lonora's server Tool
registry (read-only, non-financial, parallel_safe) with per-call durable intent
markers and checkpoint-ordered results; the guardrail state is pure JSON in the
fenced Run checkpoint, pollers are flagged by the registry, and an added
identical-effect streak ignores results so repeated financial effects stay
bounded; the final report is checkpointed before it is committed, financial
truth rules still apply, and unfinished Task work goes to owner attention. No
path scoping, terminal heuristics, plugin runtime or new dependency was ported.
Copyright (c) 2025 Nous Research, MIT. The full permission/warranty notice is
preserved in lonora_agent/tool_batch.py, lonora_agent/tool_guardrails.py and
lonora_agent/tool_loop.py and distributed in the Python wheel.

In-run context compaction adapts Hermes Agent,
https://github.com/NousResearch/hermes-agent, revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a: agent/context_compressor.py with
agent/context_compressor_prune.py and agent/context_compressor_summary.py
(deterministic pruning of old tool results outside a protected tail before any
model call, then a structured, iteratively updated summary of the middle that
never separates a tool call from its results, with a deterministic fallback),
and agent/model_metadata.py (_longest_key_match over a model-family context
window table). Changes: compaction is a view persisted in Lonora's fenced Run
checkpoint and applied per request, so canonical messages, receipts, recovery
and financial truth gates keep the complete record; placeholders keep effect
identities and reference the existing tool-result artifact store; the summary
uses Lonora-specific sections (open operations and commitments, evidence with
timestamps), runs through the global model router and is never trusted for
operational state, which is re-read from the database every turn; the family
window table is Lonora's own and conservative. Copyright (c) 2025 Nous Research,
MIT. The full permission/warranty notice is preserved in
lonora_agent/context_engine.py and distributed in the Python wheel.

Provider failure recovery adapts Hermes Agent,
https://github.com/NousResearch/hermes-agent, revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a: agent/error_classifier.py
(FailoverReason taxonomy and the ordered provider-type, HTTP-status and
message classification with retry/fallback/compress hints),
agent/fallback_cooldown.py (benching a failing provider until its declared
reset, otherwise with exponential backoff) and agent/retry_utils.py
(Retry-After parsing and decorrelated jittered backoff). Changes: a reduced
reason set and pattern tables of Lonora's own, stable owner-visible error
codes, an output-limit reason carrying the stated maximum, a process-local
bench keyed by model or credential fingerprint, and Run-level backoff on the
fenced checkpoint that never repeats an executed or uncertain effect; no
credential pools, provider profiles or plugin hooks were ported. Copyright (c)
2025 Nous Research, MIT. The full permission/warranty notice is preserved in
lonora_adapter_kit/model_errors.py and lonora_providers/resilience.py and
distributed in the Python wheel.

Granular memory edits and session recall adapt Hermes Agent,
https://github.com/NousResearch/hermes-agent, revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a: tools/memory_tool.py and
tools/memory_tool_store.py (add/patch/remove operation batches applied
atomically with the size limit checked on the final result, an overflow that
reports the shortfall, overlapping-span uniqueness and closest-entry hints) and
tools/session_search_tool.py (discovery, scroll around a hit, bounded read and
recent-session browse over actual stored messages without a model call).
Changes: Lonora keeps one versioned Markdown memory document with its USER.md /
MEMORY.md views, lease fence, optimistic revision and effect receipts; recall
uses PostgreSQL full-text search with a literal identifier match, scoped to the
calling Agent's own threads, member groups and decisions; no SQLite/FTS5 store,
threat scanner, approval staging or lineage walk was ported. Copyright (c) 2025
Nous Research, MIT. The full permission/warranty notice is preserved in
lonora_memory/edits.py and lonora_memory/sessions.py and distributed in the
Python wheel.

Source: https://github.com/elie222/rakazo
Revision: 2d666c4e98db201c1f7988e09e76a52db20cea69
Copyright 2026 Rakazo contributors. Apache License 2.0, included in LICENSE.
Changes: Python runtime, single-owner API, Arabic-first catalogs, market/trading/voice domains,
renamed workspace packages, and removal of desktop, billing and coding tools.

Lonora's replacement Web and Expo interface adapts Tampletgrok source.
Source: https://github.com/loorksy/Tampletgrok
Revision: 20fc9ac862bb833d1578968a7aba5ea18ff88a29
Copyright 2026 Tampletgrok contributors. Apache License 2.0, included in LICENSE.
Tampletgrok extracts the upstream interface at revision
c9375d4291d19ac35bbfe826255d19d976c81c38.
Rakazo is Copyright 2026 the Rakazo authors and is licensed under the Apache
License, Version 2.0. Upstream repository: https://github.com/elie222/rakazo.
Adapted portions: conversation shell/roster/To picker/command palette, resizable
context panel and panel preferences, transcript/composer presentation, artifact
grid, board columns/ticket dialog, search rows, and Expo inbox/thread navigation.
Modifications: Lonora identity and storage keys, Arabic/English RTL, real Python
API/session/event integration, responsive panel and file viewing, and removal
of simulated adapters, computer execution, public signup, billing and spaces.
No upstream ownership is claimed. Product branding is Lonora; these names
remain solely to preserve required source and copyright attribution.

UI primitives include shadcn/Base UI components (MIT); React (MIT), Lingui (MIT),
Tailwind CSS (MIT), lucide-react (ISC), react-markdown and remark-gfm (MIT).
Interactive charts use TradingView Advanced Charts v31.2.0 under the owner's
TradingView license. These proprietary vendor assets are not covered by Lonora's
Apache-2.0 license. The single distribution in apps/web/public/charting_library
retains shared assets and English/Arabic locale bundles. Its asset-manifest.json
records the exact build, source revision and SHA-256 inventory; verify with
`node apps/web/scripts/verify-chart-assets.mjs`. The former Lightweight Charts
Web dependency is no longer used.
Voice uses browser WebRTC and the OpenAI GPT-Live API.
Python dependencies retain their distributions' license notices.

Optional public-web research runs SearXNG as an independent private service,
using the upstream image pinned in infra/research/compose.research.yml.
Source: https://github.com/searxng/searxng . SearXNG is licensed under AGPL-3.0;
its source and license remain available from that upstream project and image.
Browser research uses the existing Playwright (Apache-2.0) dependency and system
Chromium, with their upstream license notices, through an isolated service.

MetaApiCloud SDK 29.1.1: Copyright 2020-2023 MetaApi DMCC. All rights reserved.
Service-use license: https://metaapi.cloud/terms . The adapter uses this SDK solely
with the MetaApi.cloud API service; the SDK license is not Apache-2.0.

Geist Variable font 5.3.0: Copyright 2024 The Geist Project Authors.
SIL Open Font License 1.1 is distributed with the Web assets at
apps/web/public/licenses/geist-OFL.txt (served as /licenses/geist-OFL.txt).
Source: https://github.com/vercel/geist-font ; packaged by @fontsource-variable/geist.

Pixel-grid loading and shimmer styling adapted from beautifului.dev (MIT).
Copyright (c) 2026 Turbo.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


## tiktoken

The request-budget estimator uses `tiktoken` 0.12.0 (MIT License, Copyright (c) 2022 OpenAI), distributed as a dependency with its license. Encoding data is fetched from OpenAI's published encoding URLs during setup/build and hash-verified by tiktoken; model requests use verified local cache data or an explicit conservative fallback. No reference Agent implementation code is included by this integration.

## Server chart captures

Python Playwright1.58.0 (Apache-2.0, Microsoft) supplies its licensed automation
driver as a distribution dependency. System Chromium is installed by the server
Docker build; its BSD-style and third-party notices remain in the Debian package
documentation. The service automates only the configured internal Lonora chart
renderer; no reference Agent implementation or arbitrary browser tool is bundled.

## OpenUI conversational experience

Source: https://github.com/thesysdev/openui
Revision: 9d73d17d2bbac565672a85e78f6eb7740cb0d9ca
License: MIT. Copyright (c) 2011-2024 Thesys Inc.

Adapted portions: packages/react-ui/src/components/AgentInterface conversation
column geometry, composer sizing/placement, unboxed assistant and rounded user
message treatment, manual-scroll following and latest-message affordance.
Modifications: Lonora's existing React conversation/outbox, stream fences,
steering, ownership, file/voice/chart/trading interactions, Arabic/English and
mobile layouts. No OpenUI headless conversation store, model client, gateway or
arbitrary executable rendering runtime is imported. Native visual documents use
Lonora's versioned Python/TypeScript contract and Web/React Native renderers.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

## Open Intelligent UI runtime repair patterns

Source: https://github.com/thesysdev/open-intelligent-ui
Revision: 16ef26475999e3a021a50b1607a03717c0721255
License: MIT. Copyright (c) 2026 Thesys Inc.

Adapted portions: `src/lib/components/controls.tsx` numeric draft/commit
separation, `layout.tsx` minimum-width responsive column geometry and
`table.tsx` numeric-column alignment. Modifications: Lonora's bounded scalar
contract, explicit unavailable values, locale-aware numeric drafts, shared
Web/React Native evaluation, existing central semantic tokens and native
accessibility. No Open Intelligent UI model client, browser conversation
storage, remote media services, arbitrary HTML or executable runtime is imported.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

## Pair icons (nvstly/icons)

Source: https://github.com/nvstly/icons ("Ticker Logos (Stocks, Cryptocurrencies, & Forex)"),
gathered, cropped, edited and compiled by the team at NVSTly (https://nvstly.com) and
contributors. Used: eleven marks, the country flags for USD, EUR, GBP, JPY, CHF, AUD, CAD and
NZD, gold (XAU), silver (XAG) and Bitcoin (BTC), reduced to 64x64 PNG and embedded as data URIs in
packages/ui-web/src/icons/pair-images.ts, as embedded in docs/ui-reference/Lonora-Desktop-37.html.
Licence: as of 2026-11-09 the upstream repository publishes no licence file (LICENSE, LICENSE.md,
LICENSE.txt, LICENCE, COPYING and License are absent on main) and its README states no licence
terms, so no licence is claimed here; this attribution is kept, and the terms of use are an open
owner question recorded in packages/ui-tokens/TOKENS.md. National flags are generally not subject
to copyright; the gold, silver and Bitcoin marks and the crops are NVSTly's compilation.
