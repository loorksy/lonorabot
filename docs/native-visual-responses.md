# Native visual responses

Release evidence and practical limits: [verification report](native-visual-acceptance.md).

Lonora's existing Agent chooses whether an ordinary answer contains text,
interactive native components, or both. There is no presentation classifier,
second model, secondary conversation store or alternative financial executor.
The attached mandate is preserved at `lonora-specs/prompt 2.md`.

## Reused architecture and reference

The existing model runtime supplies tool results and composes the final reply.
The same leased Run/Task path publishes an assistant Message and its stream
settlement. PostgreSQL message history, Gateway events and existing client outbox
remain the source of conversation identity. Existing authenticated artifact and
chart services open real files/charts; financial confirmation and independently
verified broker execution retain their current services.

OpenUI was inspected at revision
`9d73d17d2bbac565672a85e78f6eb7740cb0d9ca`, including its real AgentInterface
Thread, Composer, column styling and scroll-follow implementation. Its narrow
reading column, quiet assistant messages, floating composer and manual-scroll
behavior are adapted into Lonora's shell. Its headless conversation engine and
custom executable rendering runtime are not dependencies. The MIT notice is in
`../THIRD_PARTY_NOTICES.md`.

## Ordinary model output

`resources/prompts/native_visual_response.md` exposes a compact stable vocabulary
immediately after the mandatory operating policy. The model may insert complete
`lonora-ui` fenced JSON documents between ordinary prose paragraphs. Prose-only
answers remain unchanged. The vocabulary is first-party instruction, not a tool
invocation or a forced response format. Old checkpoints receive the current
vocabulary in their request projection, without rewriting their saved history.
The mandatory operating-policy size bound remains separate and unchanged.

Native Anthropic prompt caching includes only the adjacent operating-policy and
native-vocabulary prefix. Owner instructions, memory, account observations and
history remain outside that explicit cache block. Other provider request paths
retain their existing caching behavior. No additional provider call is added.

`visual_response.py` compiles optional documents in the same model generation.
The compiler removes unsupported/malformed documents from public text, preserving
useful prose and a text fallback. Partial JSON is withheld from the public stream;
A finished frame may recover missing or transposed terminal container closers;
interior syntax, keys, values and strings are never rewritten. All recovered data
passes the same contract, grounding and authorization checks. Validated mixed
content is published atomically with its canonical message.
`content` remains the backward-compatible text representation and `rich_content`
is an ordered version-1 list of text/UI parts. Migration 0032 adds the nullable
message column. Waiting, resumed and peer-return paths use the same payload.

## Contract and grounding

Python's `lonora_contracts.visual_response` and TypeScript's
`@lonora/contracts/visual-response` define 26 bounded primitives: columns, rows,
grids, cards, containers, dividers, text, headings, badges, icons, metrics, tables,
lists, progress, timelines, diagrams, charts, images, disclosures, tabs, buttons,
selects, checkboxes, sliders, inputs and forms. Property allowlists reject
arbitrary styles, executable code, URLs and invented component/action names.
Documents are limited to 64KB, 120 nodes and depth 10; whole mixed replies are
bounded separately. Every node has a unique stable identity.

The draft's `mode` is explicit: `observed`, `example` or `estimate`. Observed
metric/table/chart values resolve exact current-request tool call IDs and JSON
Pointer paths, with `/length` for the number of items in an actually returned
array. Missing call/path references become unavailable cells only when the same
document retains an independently resolved non-null fact. Failed, private and
non-scalar references still reject the document. The compiler materializes bounded
provenance and available observation times only for resolved references.
Draft-supplied trusted source/facts maps are rejected. Arithmetic may derive
values from evidence. Null means unavailable. The renderer labels example and
estimate documents; these labels do not turn hypothetical values into evidence.
This is structural grounding, not a guarantee that arbitrary model-authored prose
or interpretations are correct. Ordinary financial-result verification remains
required before claiming execution.

Owned image, file and live-chart references use actual resource IDs and existing
owner/conversation/agent checks. The renderer's open action uses the same existing
authenticated resource endpoint. Native graphs are supplied-data visualizations;
they are distinct from the existing live TradingView chart.

## Local interaction and identity

`@lonora/core/visual-response` evaluates bounded expressions without `eval`,
networking or model calls. Supported operators cover scalar arithmetic,
comparisons, booleans and conditional values. Inputs update declared scalar state;
selectors, tabs, disclosures, filters and derived displays remain local. Persisted
local state is scoped to the owner, thread, message and document identity; it
cannot silently migrate into an unrelated response. Native and Web rendering use
the same shared contract/evaluation logic.

The only generated actions are `follow_up`, `open_chart` and `open_artifact`.
Follow-ups send normal text through the existing conversation flow. They are not
financial approvals. Generated controls cannot create grants, change trading
limits or call arbitrary endpoints. Forms group local controls and do not gain
submission privileges merely by existing.

`@lonora/ui-tokens` supplies the existing semantic dark/light appearance and shared
`visual` geometry/spacing/type/touch tokens. Renderers choose the actual native
styles. The model selects semantic tone and composition, not CSS or colors.
Arabic RTL, English LTR, visible labels and native accessibility are renderer
responsibilities. No WebView is required for ordinary native compositions.

## Lonora Design Skill

The built-in `lonora-design` procedure is named **Lonora Design Skill**. It uses
existing `skills_list`/`skill_view` discovery, immutable snapshots and the ordinary
skill registry. Its description is available without loading its full body.
Activation is explicit through model discovery/loading; there are no keyword
triggers and the procedure is not mandatory for ordinary visual replies.

The skill covers hierarchy, density, semantic tone, charts, diagrams, accessible
mobile layouts, Arabic/numeric content and bounded local interaction. It references
the central tokens instead of duplicating them. It also requires real instrument
specifications and stated assumptions before calling position-sizing arithmetic
applicable to a real account. Neither imported design guidance nor the bundled
procedure grants tools or financial authority.

## Verification and compatibility

Deterministic checks cover vocabulary loading and checkpoint refresh, draft
examples against the real contract, existing skill discovery/override boundaries,
installed wheel resources and prompt-cache separation. Runtime, persistence,
shared evaluator and actual renderer tests live alongside these checks. A rendered
fixture alone is not evidence of configured-model integration; real conversation
acceptance is recorded separately in the verification report for the release.

Older clients receive meaningful `content` text while newer clients use ordered
`rich_content`. Unsupported future versions must fall back to text. A document
cannot execute arbitrary HTML/JavaScript; richer downloadable analyses continue
through the existing file/workspace facilities. Native source and Expo Web checks
do not by themselves prove an installed Android APK was rebuilt or distributed.
