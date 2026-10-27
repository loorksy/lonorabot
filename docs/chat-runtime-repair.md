# Chat runtime repair: implementation and evidence

This report covers the [prompt3 mandate](lonora-specs/prompt3.md), against baseline
`1ab6953a897c3566d8ea78aa2f4175423662ebe4`. It separates source changes, controlled
regressions, configured-model acceptance and production verification. The earlier
[native visual acceptance report](native-visual-acceptance.md) records a previous
release; its successful fixtures and model journeys do not prove this repair works.

**Implementation merged through [PR #5](https://github.com/loorksy/lonorabot/pull/5)
and follow-ups [PR #6](https://github.com/loorksy/lonorabot/pull/6) and [PR #7](https://github.com/loorksy/lonorabot/pull/7).** Final
runtime source `d98b16ef0c77010e7829d0f949a972e4d7f0e328` is deployed healthy. Twelve actual configured-model repair conversations and separate public stream/asset probes are recorded below. The compatible signed OTA is active and independently verified. Its exact update ID has also launched successfully on a genuine Android emulator; the final chat interaction record follows below.

## Confirmed causes

| Reported problem | Cause and affected source | Repair and verification boundary |
| --- | --- | --- |
| A/B: slow Send and text remains in composer | Web `chat-context.tsx` awaited `onSend`, while `useThreads.send` awaited HTTP delivery after local enqueue. A local bubble could exist while the old draft remained disabled. Native `app/thread.tsx` awaited HTTP then a multi-resource refresh, with no persistent chat outbox. | Local enqueue is the acceptance boundary. The submitted revision clears independently of HTTP/model time; failed delivery remains an identifiable outgoing item with explicit retry. The stable nonce is reused. Verify delayed ACK, failure/retry, duplicate taps, newer draft and conversation switching separately. |
| C: generic or missing activity | Web did not immediately project the acknowledged run and could wait for a slow GET. Native chat did not subscribe to durable chat events; broad polling and a separate status projection could lag the actual turn. | ACK/queued event carries the real run; shared `turn-activity.ts` projects actual run/tool lifecycle, without invented reasoning. Both clients scope current activity to its actual run and place it beside the current reply. Connectivity state is separate. |
| D: text appears only at completion | `model_runtime.py` disabled incremental publication when the advertised tool list contained a financial operation, even if no such operation ran. `public_stream.py` treated generic words such as buy/sell and ordinary candle closure as past execution claims. | Advertising a tool no longer suppresses ordinary text. Actual unverified financial execution and uncertain outcomes still withhold unsupported completion claims. Tests distinguish ordinary analysis from completed-trade assertions. |
| D: forwarding pauses and all UI waits | Provider delta callbacks awaited durable progress writes. The compiler stopped at the first visual frame and withheld later independent prose until the full reply finished. | Bounded `StreamPublication` coalesces accepted text without blocking provider reads on every DB write. `VisualReplyProjector` admits independently complete validated frames and their surrounding prose; an unfinished later frame does not hold an earlier completed one. Lease, generation, sequence and terminal settlement remain authoritative. |
| D/E: final content can move or rewind | Final projection stripped/joined text differently from the incremental prefix. A client had to reconcile two different text projections. | One cached projection preserves source prose whitespace and frame order for provisional and final output. Published rich parts are cumulative, validated and ordered. Canonical settlement replaces the matching provisional reply, rather than appending a second one. |
| E: literal `{{symbol}}` etc. | Production inspection found two affected responses among the latest 100 assistant messages. Both were explicitly example-mode documents with seven declared state keys; text-node `.text` fields contained display placeholders. Only `follow_up.action.text` had interpolation semantics. | Dynamic display text uses typed `concat`/state expressions. A narrow legacy adapter translates known declared scalar bindings in old text/badge nodes without mutating history or guessing prices. Unknown markers fail validation. Outside legitimate code, unbound prose markers become explicitly unavailable; raw unfinished protocol remains private. |
| F: oversized mobile forms | At narrow widths CSS collapsed every row/grid to one column, even where two compact values fit. Large spacing compounded unnecessary generated controls. | Responsive minimum-width columns, compact central tokens and progressive disclosure preserve readable density and touch targets. The Design Skill discourages large forms for simple questions. Geometry and all controls require browser verification in both directions/themes. |
| G: number editing corrupts input | Renderers parsed/clamped/snapped each keystroke. Intermediate `-`, `1.` and partial values below a minimum were rewritten before typing finished. A default step of one also erased decimals. | Numeric editing has a transient string draft and a separately validated scalar value. Partial/invalid drafts do not become fabricated numeric observations. Shared draft parsing preserves supported decimal input; valid commit/blur and step interactions have distinct semantics. |

The historical UI defect was not a stale API/Gateway release: both production
containers reported the baseline revision during inspection. Deployment identity
was independently verified again for the repaired server and its exact public client assets.

## Reference inspection and integration decisions

Pinned source checkouts used for inspection:

| Reference | Revision | Actual source reviewed |
| --- | --- | --- |
| [Open Intelligent UI](https://github.com/thesysdev/open-intelligent-ui/tree/16ef26475999e3a021a50b1607a03717c0721255) | `16ef26475999e3a021a50b1607a03717c0721255` | `src/app/page.tsx`, `api/chat/route.ts`, `src/lib/chat-handler.ts`, chat storage, library, prompt options, actions, every component/function module, generated spec/prompts, gallery and benchmark runner |
| [OpenUI](https://github.com/thesysdev/openui/tree/9bc3192b894c4f002aa3f9192176b7f16f5dea2a) | `9bc3192b894c4f002aa3f9192176b7f16f5dea2a` | `lang-core` lexer/parser/materializer/runtime/prompt, `react-lang` renderer, `react-headless` stream adapters/reconciliation/stores, AgentInterface, server relay/abort/autofix and devtools replay/errors |
| [Official development Skill](https://github.com/thesysdev/skills/tree/bcd93adc9185e333bc9a83b29f7d81d67ab1935f/skills/openui) | `bcd93adc9185e333bc9a83b29f7d81d67ab1935f` | `SKILL.md` and applicable existing-app, component-library, AgentInterface, language, reliability, theme, artifact and direct-provider guidance |

The mandate's `src/app/shell.css` and `src/lib/response-theme.ts` do not exist in
the inspected Open Intelligent UI revision. Actual styles are
`src/app/globals.css`, `src/lib/components/components.css` and
`src/lib/components/theme.css`. Its chat route delegates the actual streaming
implementation to `src/lib/chat-handler.ts`; inspecting the route alone misses it.

OpenUI's latest revision differs from the earlier `9d73d17` reference in three
runtime telemetry modules and five documentation/showcase files. Its parser,
headless reconciliation and AgentInterface code are unchanged between these pins.
No telemetry package or external diagnostic transmission is added to Lonora.

Classification uses the mandate's five categories. Direct reuse is deliberately
limited: the reference is a Web application with a different model protocol,
conversation store and execution model.

| Subsystem / source | Classification | Lonora decision |
| --- | --- | --- |
| Numeric draft lifecycle, `components/controls.tsx` | Reusable through adaptation | Adapt separation between editable text and committed numeric state to bounded shared Web/native semantics. Avoid per-keystroke clamping and default integer snapping. |
| Responsive grid geometry, `components/layout.tsx` | Reusable through adaptation | Adapt minimum-child-width column layout within existing Lonora tokens and node bounds. |
| Numeric table alignment, `components/table.tsx` | Reusable through adaptation | Adapt content-based numeric alignment while retaining bounded scalar rows, explicit missing values, RTL and local filtering/sorting. |
| Compact hierarchy, spacing, theme CSS | Architectural reference | Keep Lonora palette and central `@lonora/ui-tokens`; reduce nested forms and preserve touch/accessibility. |
| `page.tsx` AgentInterface shell | Architectural reference; prior shell adaptation retained | Preserve Lonora's established roster, composer, chart/voice/files and mobile navigation. Repair lifecycle in its existing components. |
| Reference `chat-storage.tsx` browser store | Not suitable as canonical storage | PostgreSQL and authenticated APIs retain authoritative messages. Local drafts/outbox/component state are scoped recoverable projections, not another conversation database. |
| `chat-handler.ts` streaming and abort propagation | Architectural reference | Keep existing Python provider adapters and cancellation. Decouple provider reads from durable publication and verify proxy/SSE buffering independently. |
| `lang-core` streaming parser and materializer | Architectural reference | Use independently complete validated units and explicit incomplete/error states. Retain backward-compatible fenced JSON v1; do not introduce a JS parser/evaluator into Python or force old messages into a second language. |
| `react-headless` adapters, tool pairing, message reconciliation | Architectural reference | Extract Lonora's existing sequence/generation reducer into portable core for both clients. Preserve canonical IDs, lease fences, actual tool events and cancellation. |
| Reference reactive expressions and `@Set` | Reusable through adaptation | Bounded scalar expressions, local tabs/filters/controls and useful derived displays. No arbitrary JS, object mutation, query bridge or model call for a slider. |
| Reference artifact actions | Existing Lonora services retained | Owned chart/file actions use existing authenticated resources. Generated UI cannot call arbitrary endpoints or grant financial authority. |
| `server` Autofix / second inference correction | Not suitable for this repair | No mandatory correction-model round trip, external model Gateway or duplicate server. Keep deterministic bounded validation and readable fallback. |
| `devtools` error/replay concept | Architectural reference | Safe structural paths and error codes, generation/sequence diagnostics and sanitized local replay. No external cloud collection of conversations. |
| Generated component spec and model prompt | Reusable through adaptation | Generate compact vocabulary directly from actual Python allowlists, enums, operator arities and limits; build checks drift. |
| Gallery and `scripts/bench` scenarios | Architectural reference | Repeat representative real-model conversations and renderer cases; distinguish model-generated tests, saved replay, fixtures and actual deployed acceptance. |
| Python Gateway, DB, memory, tasks, auth, trading services | Already implemented and authoritative | No second Agent, conversation engine, provider requirement or financial executor. Fix message delivery and presentation around them. |

The new adapted control/grid/table portions retain the MIT attribution and full
license in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Reference source is
not vendored into the runtime, and no `@openuidev/*` dependency is introduced.

### Component audit

Open Intelligent UI's registered library contains 55 component definitions; Lonora
retains 26 deliberately bounded component types. Names below are capabilities,
not an assertion that similarly named components share an implementation.

| Category | Reference capabilities | Lonora support and decision |
| --- | --- | --- |
| Layout | Col, Row, Box, Grid, Card, Carousel, Popover, Divider, Spacer | `column`, `row`, `container`, `grid`, `card`, `divider`; `disclosure` supplies progressive detail. Carousel/popover/arbitrary size/style props are not added. |
| Text | Title, Text, Caption, Label, Badge, Link, List, ListItem, Markdown, Quote, Code, Math | `heading`, `text`, `badge`, `icon`, `list`; ordinary message Markdown/code remains outside UI documents. No arbitrary navigation URL from generated markup. |
| Controls | Button, IconButton, Pressable, Input, TextArea, Select, SegmentedControl, Slider, Checkbox, RadioGroup, DatePicker, Timer, Form | `button`, `input`, `select`, `slider`, `checkbox`, `tabs`, `form`. Native labeled controls/local calculations repaired; no timer/clock/date state or arbitrary pressable action language added. |
| Data | Table, Chart | `metric`, `table`, `progress`, `timeline`, `chart` with line/bar/pie. Filters, sorting, tabs and derived scalar values remain local. Area/donut/scatter are not claimed as supported. |
| Media | SearchImage, Image, Icon, Map, MapMarker, YouTube | Owned `image` artifacts and actual live-chart references. No image search, map routing, third-party embed or remote media dependency. |
| Drawing and special widgets | Svg, G, Circle, Ellipse, Rect, Line, Path, Polyline, Polygon, SvgText, HtmlView, Flashcard, Celebration | Bounded `diagram` vertices/edges and supplied-data charts. Arbitrary SVG/HTML, scripts, WebViews, games and animation loops are not introduced. |
| Financial information | General primitives composed into dashboards | Existing evidence-backed metrics/tables/graphs can show account, position, exposure and performance data if retrieved. This repair does not claim new broker data or invent a dedicated calculator for every instrument. |

Every native node still has an allowlisted type/properties and a stable unique ID.
Resource opening is owner/conversation/agent checked. Observed values must cite
successful current-request evidence; example/estimate labels never authorize
invented observations or broker completion claims.

### All 59 custom functions evaluated

The reference has 59 custom functions in six modules, in addition to framework
builtins such as arithmetic, `@Each`, `@Filter` and `@Set`.

| Module / count | Actual custom functions | Decision |
| --- | --- | --- |
| Lists / 19 | Append, Prepend, Concat, Remove, RemoveAt, Update, Toggle, Includes, Find, IndexOf, Take, Slice, Unique, Reverse, Range, Pick, Shuffle, Flatten, Chunk | Do not add arbitrary collection/object state or mutation. Existing scalar controls, tabs and bounded table filtering cover current needs. Random Pick/Shuffle are intentionally excluded. Reference list `Concat` is not Lonora's scalar text `concat`. |
| Numbers / 9 | Pow, Sqrt, Random, Clamp, Percent, Lerp, Allocate, Payment, Convert | Add finite typed scalar `pow`, `sqrt`, `clamp`, `percent`; `floor`/`ceil` extend existing arithmetic. No Random, financial allocation/payment model or generic unit conversion is claimed. |
| Text / 12 | Format, Join, Plural, Pad, Upper, Lower, Trim, Capitalize, Split, Replace, Duration, Default | Add bounded scalar `concat` for dynamic previews. Keep existing renderer formatting; no arbitrary format language or string/list transforms. Do not import `Default` or unknown-currency-to-USD fallback. |
| Colors / 1 | MixColor | Exclude arbitrary generated colors; central semantic tones own appearance. |
| Dates / 8 | Now, Today, FormatDate, AddDays, AddMonths, DaysBetween, MonthsBetween, StartOf | No local clock/date engine added. Returned timestamps and schedules remain actual backend facts. Viewer time zones cannot become invented market session evidence. |
| Data / 10 | GroupBy, Pivot, Top, Between, Bucket, Cumulative, MovingAvg, Change, Histogram, Stats | Add finite typed scalar `change`. No list aggregations/statistics engine added; existing analysis tools supply observations. Do not silently fill missing returns, series or empty summaries with zero. |

Eight new operators are enabled: `floor`, `ceil`, `sqrt`, `pow`, `clamp`,
`percent`, `change`, `concat`. Python text projection and TypeScript local
interaction share these semantics: finite typed inputs, bounded arity/depth,
null for invalid domains or zero denominators, and no coercion of missing data
to zero. `concat` accepts at most eight scalar arguments and 4,000 output
characters. Invalid clamp bounds remain unavailable rather than being swapped.

## Working message and stream boundaries

1. The client snapshots the current draft, reply target and uploaded attachment
   identities, then safely enqueues a nonce-addressed outgoing message.
2. The optimistic message appears and only that submitted draft revision clears.
   A later edit or another conversation's draft is preserved.
3. HTTP submission carries the same nonce on retry. Backend message/run creation
   remains idempotent; ACK reconciles the local item with its canonical identity.
   ACK includes the actual run projection before a separate history refresh.
4. Gateway claims the existing durable run. Real lifecycle/tool events determine
   current activity, independently of unrelated background tasks.
5. The configured provider streams into the existing Python Agent. Public prose
   admission, visual compilation, grounding and financial-truth checks remain
   server responsibilities. There is no presentation-model call.
6. The compiler admits a closed, valid, authorized frame without waiting for a
   later unfinished frame. A bounded coalescing publisher sends accepted updates
   through the existing leased progress writer and durable events.
7. `run.reply_started` defines a stream generation. `run.delta` adds admitted text
   and may carry a changed cumulative `rich_content`; `run.rich_partial` carries
   validated rich content without a text delta. Sequence, fence, run and turn
   identity remain shared across both event kinds.
8. Web SSE and native authenticated WebSocket read the durable owner event feed.
   A shared reducer rejects old generations, duplicate events and sequence gaps;
   canonical run/message snapshots repair reconnect/gap cases. The native live
   handshake establishes a current cursor; explicit resume keeps its saved cursor.
9. Final canonical Message settlement replaces its matching provisional stream.
   Cancellation/failure retains accepted preview and explicit terminal state;
   it never manufactures a completed assistant Message or repeats a privileged
   action. Reload recovers canonical messages plus actual remaining stream state.

Older clients continue receiving readable text content. New clients render an
ordered rich projection instead of duplicating its compatibility text. Validated
UI state remains scoped to owner, thread, message and document identity; local
controls neither refresh evidence nor contact the Agent without an explicit
follow-up. Existing financial approvals, emergency stop and broker verification
remain outside generated presentation.

## Model guidance and Skill

`scripts/export_native_visual_reference.py` generates the marked registry block in
`resources/prompts/native_visual_response.md` from actual contract definitions.
It validates the examples, English source and 6,500-character maximum. The build
command is:

```bash
.venv/bin/python scripts/export_native_visual_reference.py --check
```

A contract/property/enum/operator/limit change requires regenerating this block;
a manual parallel vocabulary is not treated as authoritative. The current
vocabulary is 6,449 characters excluding terminal whitespace. It remains part of
the stable first-party prefix and the existing explicit Anthropic cache boundary;
mutable owner memory, instructions and account observations remain outside it.

Source inspection found a concrete reason for the drift check: the reference's
`components/text.tsx` describes `md` as the card title size, while its committed
`generated/system-prompt.txt` still says `lg`. Lonora generates its allowed
vocabulary from the actual registry rather than copying this stale example.

`lonora-design` version 1.0.2 remains optional and description-first, using the
existing registry and `skill_view`. Its English source is below its 8,000-character
budget. Applicable official coding-Skill knowledge is adapted into compact
hierarchy, responsive density, local useful interaction, honest missing data,
progressive disclosure and evidence-backed trading displays. Developer setup,
OpenUI Cloud keys, telemetry installation and Gateway migration instructions are
not trading-agent capabilities and are not installed in its runtime Skill.

A literal display string is not a template language. New dynamic previews use
`value: {op: "concat", args: [...]}`; mustaches are limited to declared scalar
keys in an explicit follow-up action. The compiler preserves legitimate requested
code/examples, and never guesses actual prices, symbols or account values to
populate a missing binding.

Independent review also exercised composed-value boundaries: joining separately
safe fragments must not reconstruct a credential or an unbound placeholder.
Server compilation now rejects such compositions, including initially hidden
nodes, and shared client display evaluation protects later local state changes.
Malformed or unfinished prose bindings become unavailable at final settlement;
literal code remains literal. These checks supplement validation of individual
string fields rather than assuming that individually safe fragments compose safely.

## Performance evidence

These stages must remain distinct. Provider latency is not a local Send metric.

| Stage | Baseline evidence | Repair evidence / interpretation |
| --- | --- | --- |
| Submit → optimistic user bubble | 12.9 ms in controlled delayed-ACK browser scenario | 14.8 ms in the matched repair scenario. Both are immediate; no provider-speed improvement is claimed. Native previously lacked a chat outbox. |
| Submit → HTTP dispatch | 72 ms in the same controlled scenario | 64 ms in the matched repair scenario; separate from provider time. |
| Submit → server ACK | 4,111 ms with an intentionally injected 4,000 ms POST delay | 4,108 ms with the same injected delay. This is a controlled network delay, not normal production latency. |
| Submit → composer clear | 4,128.3 ms in that scenario | 14.8 ms after repair with the same injected delay; the defect followed HTTP ACK instead of safe local enqueue. |
| Submit → activity | Header 4,202 ms; current-run activity 5,843.8 ms, with delayed run projection | Current-run activity appeared at 4,115.8 ms with the same delays, directly after the 4,108 ms ACK; the extra GET dependency is removed. The independent header metric was 4,275.8 ms; no header improvement is claimed. |
| Queue delay | Historical production sample of 16 runs: 17–273 ms | Final-image sample: queued → running 81.81 ms; leased → running 44.95 ms, measured from actual durable event timestamps. |
| Leased → running | Historical production sample: 6–19 ms | Distinct from model/provider initialization. |
| Running → reply started | Most historical samples 0.99–1.66 s; two 11.86/12.39 s outliers | Outliers precede the provider request; cause is not established by this sample. Do not attribute them to embedding or inference without correlated phases. |
| Reply started → first admitted delta | Historical sample 1.37–3.09 s | Actual provider first text 777.59–2662.53ms and first-text callback → durable publication 37.03–244.59ms are now separated below. These have different measurement origins; do not compare their sum directly to the historical event interval. |
| Consecutive admitted deltas | Typical historical gaps 208–229 ms, with several 1.1–6.76 s gaps | Coalescing removes DB-await backpressure; cannot eliminate genuine provider pauses. |
| Visual density | Frozen baseline source at 390px: six fields plus two metrics occupied 961.3125px in one 322px column, English and Arabic | Repair: 503.796875px, two 156px columns, 44px controls and no 390px viewport overflow; 47.59% less height. Separate artifacts: `.runtime/visual-frozen-baseline.jsonl` and `.runtime/visual-density-after.jsonl`. |
| Numeric interaction | Frozen baseline typing `-1.25` with step1 became `-15`; typing `250` with minimum100 became `10000`; trailing `1.` became `1` | Repair browser checks preserved signed decimals, Arabic digits, transient drafts and bounds. Local control changes made no Agent request. |

Client monotonic timestamps cannot be subtracted directly from server clocks.
Correlate nonce/request/run/turn/generation identity and use same-clock durations;
transport receipt/render timings need their own client measurements. Diagnostics
must exclude raw model context, tool arguments, credentials and private values.

### Actual configured-model baseline

The six cases below exercised the deployed baseline API container's normal
message API, Gateway worker, configured model, durable SSE and actual Chromium
chat renderer. The harness created an isolated, migrated temporary database and
copied only encrypted model-provider configuration. It copied no account,
conversation history or financial authority, and created no broker connection,
management grant or trading journal.

This is actual model-to-transport-to-browser evidence, not hand-authored component
fixtures, a recorded response replay or a direct Agent call. Its boundary is the
deployed baseline container and local acceptance route; it does **not** verify the
public reverse-proxy route, a physical Android browser or the signed native app.
Evidence: `.runtime/prompt3-real-baseline.log`.

| Case | Locale / viewport | User bubble | Composer clear | First assistant display | Total | Visible updates / delta events | Final UI documents |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | English / 1440px | 108 ms | 530.2 ms | 6085.1 ms | 7.56 s | 2 / 3 | 0 |
| Capabilities | Arabic / 390px | 36.1 ms | 111.9 ms | 2068.7 ms | 7.30 s | 7 / 12 | 0 |
| Tool-using analysis | English / 1440px | 41.2 ms | 199.5 ms | 6286.0 ms | 9.46 s | 6 / 10 | 0 |
| Mixed response | English / 390px | 33.9 ms | 89.0 ms | 2566.4 ms | 8.71 s | 2 / 4 | 1 |
| Educational calculator | English / 390px | 26.9 ms | 116.3 ms | 2733.1 ms | 5.19 s | 3 / 3 | 1 |
| Binding scenario | Arabic / 390px | 41.9 ms | 125.2 ms | 2619.3 ms | 13.67 s | 4 / 6 | 0 |

All six baseline runs completed, each with one canonical user and assistant
message and two restored DOM messages. No raw protocol, viewport overflow or
browser error was detected. The calculator supplied two functional controls;
changing a value changed its result with zero additional POST requests. The tool
case observed real `tool.started`/`tool.completed` events. The binding case's
model chose ordinary text, so that case does not prove generated binding UI.

No case emitted partial rich events in this baseline. Model metadata did not yet
include the new per-stage stream timings; empty baseline timing fields cannot be
reported as zero duration. These samples establish actual baseline behavior, not
a before/after speed guarantee: fresh model generations have different output,
tool calls and provider inference time. The matching repair runs and separate public stream/asset probes are recorded
below. These public probes do not prove every real-model browser case traversed
the public reverse proxy.

The controlled before/after browser evidence is retained separately in
`.runtime/chat-baseline.jsonl` and `.runtime/chat-after.jsonl`. Switching A → B → A
restores the unsent A draft after repair; baseline restored an empty draft. These
controlled timings prove local acceptance and ACK projection behavior under the
same injected delays; they are not configured-provider inference measurements.

## Verification record

The following focused checks were executed for this documentation/guidance slice:

| Check | Result |
| --- | --- |
| Generated vocabulary against live contract | Passed, 6,449 characters |
| `tests/test_native_visual_policy.py` | 9 passed; resource/cache boundary, registry/exact discovery, examples, generated drift, English/budget and dynamic binding semantics |
| Ruff for generator and native policy tests | Passed |
| Full Python suite against disposable migrated PostgreSQL | 1,343 passed in 53.50s |
| TypeScript unit suite | Initial complete command 144 passed; native-follow-up complete command 145 passed, including 9 native unit cases |
| Web conversation browser regressions | 17 passed: 16-case full run plus the corrected actual fixture case in a focused run |
| Web generated-visual browser regressions | 8 passed; English/Arabic, light/dark, 390px and narrow overflow, local controls, transient numeric drafts, dense tables/charts/diagrams |
| Native implementation browser bridge | 6 passed; bridge verification is not signed-device acceptance |
| Native focused unit cases | Initial 8 passed; native follow-up 9 passed, contained in complete TypeScript totals |
| GitHub CI | Job did not start: GitHub annotation reports the account is locked because of a billing issue. No CI-green claim. |
| Independent reproduction of split credential/binding and unfinished prose defects after fixes | Rejected unsafe rich compositions, no sensitive output; prose explicitly unavailable; requested literal code preserved |
| Compiler, public stream, incremental publication and delta-batching focused suite | 112 passed in 2.68s after the composed-value and final-binding fixes |

Focused counts are not additive with complete-suite counts. The Web corrected
case fixed invalid test data rather than hiding a product failure. The report
must retain actual failed/skipped outcomes if further acceptance exposes any.

`bash scripts/build.sh`: passed again after the native follow-up; all seven build
targets succeeded in 31.533s, alongside lint, formatting, full type checks, resource
checks and generated vocabulary drift checks.

Actual repair-model results and separate public probes are recorded below.
Final native, OTA and cleanup evidence is recorded in the final release sections; it remains distinct from the earlier Web/backend source checkpoint.

The mandate's A–L acceptance scenarios were checked through the separately identified runtime, browser and native paths: simple English; Arabic
conversation; actual multi-tool work; mixed text/UI; local calculator; malformed
UI; unresolved binding; delayed model; network interruption; Android browser;
React Native; and actual configured model through the normal backend/transport
and renderer. A fixture, replay, direct Agent call or Expo Web test alone does
not establish the entire deployed path.

No physical Android device was connected. Hardware acceleration was unavailable
(`/dev/kvm` absent), but a software Android API24 emulator subsequently booted.
The signed 0.2.8 APK installed, and its downloaded update subsequently launched and authenticated to an isolated QA server. Exact update identity and device interaction evidence are recorded below, separately from source/type checks and Expo Web.

No live broker order or financial-authority change is required for chat acceptance.
Temporary acceptance identities must have no trading account or management grant.
Report their cleanup, production revision and Web/OTA asset identity separately.

### Final source checks before release

- `bash scripts/build.sh`: passed Ruff, formatting, full Pyright, packaged policy/resource checks, generated vocabulary drift, Biome, all seven TypeScript checks and all seven builds.
- Full Python suite against a temporary migrated PostgreSQL database: **1,343 passed**, 53.50 seconds (`.runtime/prompt3-full-pytest-final.log`).
- Full Web/native TypeScript unit suites initially passed **144** cases (`.runtime/prompt3-ts-tests.log`); the native follow-up subsequently passed **145**, including **9** native unit cases. These totals overlap; they are not 289 distinct tests.
- Web chat browser scenarios: **17 passed**: 16 in the final combined run, plus the corrected-contract preview scenario's focused rerun. The first preview fixture used unsupported node types and was correctly rejected; its corrected actual-contract fixture passed (`.runtime/prompt3-web-browser-final.log`, `.runtime/prompt3-web-preview.log`).
- Visual browser regressions: **8 passed**, EN/AR, light/dark, numeric drafts, local-only interactions, reload, narrow tables/diagrams and reduced motion (`.runtime/visual-repair.log`).
- Native lifecycle/WS unit checks initially passed **8**, and the initial native-component Expo Web bridge passed **6** (`.runtime/native-prompt3-browser.log`). Follow-up runs passed **9** native unit cases and **3** lifecycle bridge cases plus **4** visual bridge cases (7 reported case passes overlapping prior coverage). These are not device-level claims.
- Controlled 4,000 ms POST / 6,000 ms runs-GET comparison: optimistic bubble **12.9 → 14.8 ms**, composer clear **4,128.3 → 14.8 ms**, HTTP dispatch **72 → 64 ms**, ACK **4,111 → 4,108 ms**, current-run activity **5,843.8 → 4,115.8 ms**. The separate header metric **4,202 → 4,275.8 ms** did not improve. Thread A → B → A now restores the unsent draft; baseline lost it (`.runtime/chat-after.jsonl`).
- Provider-stage instrumentation distinguishes router configuration, context preparation, credentials/adapter creation, generation admission, actual provider first text/request time, overall turn request time and first durable publication. These durations are measured on the server clock, independently of browser render timings.
- A fresh software Android API24 emulator booted and installed the signed 0.2.8 APK. Downloaded-update and authenticated native chat checks were subsequently performed; see the final device record.

The Web/backend deployment, matching real-model repair runs and public stream/asset
probes are recorded below, followed by the final native OTA and device evidence.


## Repair-model acceptance and production publication

### Actual configured model after repair

The repair harness executed eight initial conversations plus two focused repeat
conversations with **OpenAI `gpt-5.1`**, through the normal API, Gateway worker,
Agent loop, durable SSE and Chromium chat renderer. Like the baseline, these ran
inside the deployed API container against an isolated migrated temporary database
with encrypted provider configuration only: no owner conversation history,
account connection, financial authority or trading journal was copied/created.
This is actual inference-to-browser evidence, not a fixture, replay or direct
Agent call. It is separate from the public reverse-proxy probes below.

Artifacts: `.runtime/prompt3-real-after.log` (8 conversations) and
`.runtime/prompt3-real-calculator.log` (2 focused conversations).

| Case | Locale / width | Bubble = composer clear | First assistant display | First native UI | Total | DOM updates / text delta events | Result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Hello | English / 1440px | 75.5 ms | 7031.9 ms | — | 8.54 s | 1 / 2 | Plain text, completed |
| Capabilities | Arabic / 390px | 30.9 ms | 3282.6 ms | — | 12.46 s | 22 / 35 | Plain text, completed |
| Tool analysis | English / 1440px | 56.0 ms | 8475.0 ms | — | 14.24 s | 15 / 21 | Actual tool lifecycle, completed |
| Mixed response | English / 390px | 44.5 ms | 2546.0 ms | 11404.5 ms | 12.43 s | 2 / 4 | Valid UI, 2 rich publications |
| Calculator, first probe | English / 390px | 50.8 ms | 2698.8 ms | 6384.6 ms | 7.37 s | 1 / 3 | Valid UI; old numeric selector found zero controls |
| Bindings, initial generation | Arabic / 390px | 54.5 ms | 2538.4 ms | — | 12.27 s | 2 / 3 | One frame rejected safely; readable fallback |
| Hello repeat | English / 1440px | 75.0 ms | 2951.3 ms | — | 4.51 s | 2 / 3 | Plain text, completed |
| Arabic repeat | Arabic / 390px | 40.4 ms | 2544.3 ms | — | 8.77 s | 17 / 22 | Plain text, completed |
| Calculator, corrected probe | English / 390px | 141.2 ms | 3178.6 ms | 6374.1 ms | 7.26 s | 2 / 3 | 2 functional controls, result changes, zero POSTs |
| Bindings repeat | Arabic / 390px | 31.7 ms | 3283.0 ms | 12731.5 ms | 13.66 s | 2 / 4 | Valid reactive UI, 2 rich publications |

All ten runs completed with exactly one canonical user and one assistant message,
then two restored DOM messages. No raw protocol, viewport overflow or browser
error was observed. This does not mean all model output was valid: the initial
binding generation produced `visual_frame_rejected`, showed safe readable
fallback and retained ordinary conversation. The repeat generated valid UI with
no visual diagnostic. Four conversations produced a valid native UI document;
five chose plain text and one used the rejected-frame fallback.

The first calculator interaction probe used the old `input[type=number]`
selector. New editable numeric controls intentionally use a text input with
`role=spinbutton`, so that probe's `controls:0` was a test-selector mistake, not
proof of a broken or absent calculator. The corrected role-based probe ran a
fresh actual-model conversation, found two controls, changed the calculated
result and measured zero follow-up POSTs. Both results are retained above.

The mixed/calculator/binding repeat cases published validated rich content before
canonical final settlement. The earliest native-UI DOM timestamps are recorded
separately from introductory prose. Tiny English greetings may fit one visible
update; these samples do not claim per-character updates or a fixed provider
response duration. Arabic repeats and the tool case showed multiple real DOM
updates while their delta events arrived.

### Correlated timings observed after repair

These ranges use the ten actual repair conversations and must not be combined
into one latency number:

| Boundary | Observed duration | Interpretation |
| --- | --- | --- |
| Actual provider request → provider first text | 777.59–2662.53 ms | Provider inference only; excludes model context/credential/admission preparation. |
| Turn first text callback → first durable publication | 37.03–244.59 ms | Same server clock; includes admission/coalescing/compilation/publication. Calculated as `first_publication_ms - turn_first_text_ms`. |
| Browser first SSE text delta → first assistant DOM display | 24.4–71.7 ms | Same browser clock; includes handler/render and observation sampling. |
| First batch cold model-context preparation | 1996.70 ms | Separate preparation cost before the provider call. |
| Remaining first-batch warm model-context preparation | 10.74–23.42 ms | Seven conversations in the same acceptance process. Focused binding repeat was 9.39 ms. |
| Focused calculator context preparation | 211.74 ms | Separate fresh focused process; do not hide it inside the 9–23 ms warm range. |
| Agent context construction | 567.52–971.35 ms | Earlier Agent context building is distinct from router/model-context preparation. |

Observed initial-model context cost does not establish the cause of historical
11.86/12.39s preparation outliers. New timings make the actual boundary visible;
no universal speedup or inference-duration guarantee is claimed. In particular,
the first new Hello sample took longer than the baseline, while its repeat was
shorter. Output length, tool work, process warmth and actual inference vary.
The controlled Send test is the evidence that draft clearing no longer waits for
HTTP ACK.

### Public server and assets

The initial API/Gateway server image
`e55bb308ac1a8cb361cca812276f5106eb766bd9` was deployed healthy and used for the
recorded backend/Web repair acceptance. The native-only follow-up then deployed
final runtime source `11dee12b835f938af348f42d71fa6c3a3d084912`; database, API and
Gateway are healthy, and `/health`, `/ready` and `/app/` return `200`. The restricted
Gateway numerical-image probe also passed without creating financial authority
(`.runtime/prompt3-final-deploy-status.log`). The public index and main Web asset
matched the exact tested release SHA256 identities:

| Public asset | SHA256 |
| --- | --- |
| `index.html` | `b00d0f1ac2cfdde8fa32a5837036168f5b560dd487384af1cce7ffe4fecefba3` |
| `chart-runtime/assets/app-DFOxsNLk.js` | `1921eb376e74e1c3488c2e11659663c1b9199107118901a206b0b3475dfe5423` |

An authenticated public SSE connection became ready in **158.32 ms**, without
buffered history replay; its temporary probe session was removed. This is stream
connection readiness, not first-token latency or a public-route model conversation.
Evidence: `.runtime/prompt3-public-verify.log`.

Migration 0031 and all four valid event indexes were verified. Actual query probes
reported replay 42.81ms, unpublished-event lookup 0.062ms, context lookup 11.093ms
and run lookup 2.236ms using their expected indexes. The public/index probe
created no trading action or conversation.

### Native follow-up verification checkpoints

[PR #6](https://github.com/loorksy/lonorabot/pull/6) merged a native-only refresh
pending-flag repair and additional native regression coverage. Its final runtime
source is `11dee12b835f938af348f42d71fa6c3a3d084912`; the earlier e55 identity
identifies the backend/Web configured-model acceptance above. The initial verified OTA
`d0598f6a-8b1d-471e-8fb2-44bd4928fed0` was activated before the contrast follow-up. Public certificate, signature, manifest, runtime, every immutable asset hash, current-update response and incompatible-runtime handling all passed. The original APK and certificate remain unchanged.

| Verification boundary | Evidence / status |
| --- | --- |
| `bash scripts/build.sh` | Passed again; seven build targets succeeded in 31.533s with required source checks |
| Repair-model API/Gateway/SSE/Chromium | 10 actual OpenAI gpt-5.1 conversations recorded above, including one safe fallback and corrected calculator-selector probe |
| Correlated timing stages | Actual provider, model preparation, durable publication and browser rendering recorded above |
| Public API/Gateway revision and schema | Final `11dee12` implementation deployed healthy after native-only follow-up; all health/readiness/app probes return `200`; prior Migration 0031/event-index probes passed |
| Public Web asset identity | Public index/main asset match exact frozen release SHA256 |
| Public stream readiness | Authenticated SSE ready in 158.32 ms; no history replay; actual model conversations exercised the isolated normal runtime route |
| Native-only PR #6 final source identity | `11dee12b835f938af348f42d71fa6c3a3d084912`, merged and deployed |
| Initial compatible signed Android OTA | `d0598f6a-8b1d-471e-8fb2-44bd4928fed0` was active before the final contrast release; pinned-certificate signature, manifest/runtime, all asset hashes and update replay/compatibility checks passed |
| Updated emulator / physical device | Genuine software Android API24 installed the signed 0.2.8 APK, authenticated only to an isolated QA server, and loaded exact final OTA d0598f6a-8b1d-471e-8fb2-44bd4928fed0: successful launches=1, failed launches=0. Final interactive chat record is recorded below; no physical-device claim. |
| Temporary acceptance identity cleanup | Isolated acceptance created no broker connection, financial authority or trading journal. all three migrated temporary model-acceptance databases dropped in finally; final database/staging check recorded below |
| Backup/staging boundary | final deployment checks confirm no backup directory or wheel/Web/OTA upload staging remains |

The ignored `.runtime/prompt3-native-post-freeze.patch` preserved two regression
tests added after the initial e55 freeze. It must remain distinguishable from
the separate PR #6 native runtime fix; do not attribute that runtime change to a
test-only patch or silently change the already verified server image identity.

### First verified signed native update

- Native reconnect checkpoint implementation: `11dee12b835f938af348f42d71fa6c3a3d084912`.
- Compatible Android runtime: `e4a51ffd7874ea0b8a4fc201e1c39ca376e826ca`; APK remains version 0.2.8 / versionCode 26102101.
- First verified signed update: `d0598f6a-8b1d-471e-8fb2-44bd4928fed0`; superseded by the final contrast update below.
- Launch bundle SHA256: `c2247b8b44b5382408e7c056677d297311464e802975b960a14d6a6915423919`.
- Pinned certificate SHA256: `c1c250cfe7572058e6f3488206299db884d03caa16463a3de50e847506ddfa49`.
- Public update protocol verification passed: exact signed manifest, runtime/release, every immutable asset hash, already-current response and incompatible-runtime response (`.runtime/prompt3-final-ota-public.log`).
- Read-only Expo Updates metadata on the genuine software Android emulator confirmed the exact final update ID, one successful launch and zero failed launches (`.runtime/prompt3-native-final-ota-loaded.json`). This is updated native-code evidence, not an Expo Web simulation.
- The dedicated emulator used the cloud session's approved proxy and public session CA trust, with TLS verification retained. This environment setup did not change production trust or ship a certificate change in the application.
- The final public authenticated SSE probe became ready in **609.57 ms**, in addition to the earlier 158.32 ms probe. Both verified the exact public index/main asset hashes; neither timing is model first-token latency (`.runtime/prompt3-final-public-verify.log`).

### Final Android chat record

The signed Android app ran in a genuine software Android API24 emulator, with its exact downloaded update verified independently in read-only Expo Updates metadata. Under a deliberately delayed four-second API acknowledgement, frame0 showed the optimistic outgoing message, cleared composer and Sending state. Frame2 showed Writing plus a partial sentence; frame4 showed the validated calculator while the same turn remained running. These are actual ADB screen captures, not an Expo Web rendering or a replay.

Changing the example amount 1000 to 250 changed its derived value 2000 to 500 before canonical commit. The value 250/result 500 survived the ordinary canonical handoff, with exactly one outgoing message and no raw markers. The fixture deliberately held the preview for 180 seconds because software-emulator accessibility dumps were slow; that hold is not a production latency measurement.

The first attempt exposed an isolated QA Origin mismatch (`localhost` versus `10.0.2.2`), was excluded from acceptance, and its orphaned diagnostic turn/thread was removed. Correcting that local test configuration retained strict Origin and bearer checks; no production authentication check was weakened. The successful fresh attempt is recorded in `.runtime/prompt3-native-hardware-probe.jsonl`, `.runtime/prompt3-native-stream-frame-{0..4}.png` and `.runtime/prompt3-native-calculator-canonical-500.png`.

This device fixture's producer is explicitly **scripted**, using the actual API, durable event writer, authenticated WebSocket and app renderer, with no broker or financial authority. It proves native delivery/interaction/handoff and is not counted as an LLM run. Configured-model evidence remains the separate actual-provider Web path above.

### Measured transport and native contrast follow-up

[PR #7](https://github.com/loorksy/lonorabot/pull/7) addresses two defects exposed by the real acceptance, without replacing the transport or the Agent:

- The durable event reader always waited 500ms when no row was immediately available. The final-image probe below observed regular 470.9–582.6ms gaps interspersed with rapid batched DOM updates. Active subscriptions now poll at 100ms for five seconds after actual events, then return to the original 500ms idle rate. Deterministic tests verify both delivery and idle backoff; cursor/scope handling is unchanged.
- Genuine Android testing found that rich responses followed the OS light palette while the application's native conversation remained dark. The resulting black prose on a dark surface was unreadable. Native rich content now uses the application's actual dark palette; the browser retains its independent light/dark page theme. The signed follow-up update is verified below.

The final runtime implementation is `d98b16ef0c77010e7829d0f949a972e4d7f0e328`. The final full Python suite passed **1,345 tests**, 62.09s (`.runtime/prompt3-transport-full-pytest.log`), including the two new event-delivery regressions. `bash scripts/build.sh` again passed all checks and seven builds after the native contrast change, 33.917s (`.runtime/prompt3-delivery-contrast-build.log`). The previous145 TypeScript unit cases cover unchanged shared/client logic; device screenshots directly verify the native-only palette branch.

### Final-image configured-model timing sample

An additional actual OpenAI gpt-5.1 Arabic conversation exercised deployed source11dee12 through the normal isolated API/Gateway/SSE/Chromium path (`.runtime/prompt3-real-final.log`). It completed with one canonical user and assistant message,15 visible progressive updates and22 durable text events; reload restored both messages. No raw protocol, browser error or viewport overflow appeared. This sample supplements the ten earlier repair conversations; it does not retroactively change their output.

| Same-clock boundary | Measured result |
| --- | ---: |
| Local user visibility / composer clear |67ms /67ms |
| API / authentication / message transaction |125.94 /11.42 /107.42ms |
| Queued → running |81.81ms |
| Leased → running |44.95ms |
| Running → reply started |930.51ms |
| Agent context construction |658.33ms |
| Router model-context preparation |663.31ms |
| Actual provider request → first text |2342.81ms |
| Turn first text callback → durable publication |49.19ms |
| Browser first SSE delta → DOM |66.4ms |
| First assistant display / total |5194.5ms /11.16s |
| Consecutive visible update gaps before transport follow-up |14.9–582.6ms, including500ms event-reader batches |

The post-follow-up public stream/model sample is recorded below. Real provider output time still varies; no statement promises instantaneous inference, trading success or universal latency improvement.

### Final deployed stream cadence and signed Android release

Final implementation `d98b16ef0c77010e7829d0f949a972e4d7f0e328` is active in API and Gateway. Health, database, Gateway readiness and public Web asset identity passed again. The latest authenticated public SSE readiness probe was **176.94ms** (`.runtime/prompt3-delivery-public-verify.log`).

One further actual OpenAI gpt-5.1 Arabic conversation exercised this final image through the ordinary isolated runtime and real browser (`.runtime/prompt3-real-delivery-final.log`). It produced **29 visible progressive updates  / 29 durable text events**, with one canonical user and assistant message, both restored after reload; no raw syntax, browser error or horizontal viewport overflow occurred. Its 12.19s total includes actual generation/output length and is not a universal speedup claim.

| Final-image boundary | Measured result |
| --- | ---: |
| User visibility / composer clear |42.6ms /42.6ms |
| API / authentication / message transaction |75.97 /6.39 /64.22ms |
| Queued → running / leased → running |86.09 /26.28ms |
| Running → reply started |1369.75ms |
| Agent context / router model-context preparation |1132.14 /360.33ms |
| Actual provider request → first text |2053.79ms |
| Turn first text → durable publication |138.95ms |
| Browser first SSE text → DOM |22.5ms |
| Consecutive visible update gaps |121.3–368.2ms; median 238.80ms |
| First assistant display / total |4297.4ms /12.19s |

The reader's active-versus-idle behavior is deterministic and directly tested. Model generations/output lengths differ across real samples; the measured update cadence does not imply a guaranteed total-response or financial outcome.

The **final active Android OTA** is `17fbe8aa-c812-4ca4-9e6f-bdf37810f183`, built from final source `d98b16ef0c77010e7829d0f949a972e4d7f0e328`, on unchanged runtime `e4a51ffd7874ea0b8a4fc201e1c39ca376e826ca`. APK version 0.2.8/code26102101 and the pinned certificate are unchanged. Launch-bundle SHA256 is `72ca0b26d45a57f929ba63d506b8f006cf7a979bbd1e73108a38bbf06c551be1`. The public signature, exact manifest/runtime/release and every immutable asset hash passed, including current-update and incompatible-runtime handling (`.runtime/prompt3-contrast-ota-public.log`).

Read-only native metadata confirmed this exact final update: **one successful launch, zero failed launches** (`.runtime/prompt3-native-contrast-ota-loaded.json`). After a cold app reopen into this update, the previously committed 250→500 calculator state remained, the outgoing message appeared once, no raw markers appeared, status returned to ready, and prose/card/input contrast was readable. The release owner visually inspected `.runtime/prompt3-native-final-readable-reopened-500.png`. No further message or 180-second fixture hold was needed to prove persisted state and the corrected palette.

### Verification boundaries and cleanup

- Mobile Web tests use an actual Chromium browser with mobile/touch emulation, narrow viewports, both reading directions and themes. Native testing additionally uses a genuine Android OS emulator and the signed app. A physical handset and a separately installed Android Chrome APK were not exercised; neither is claimed.
- The actual configured-model tests use deployed images and normal API/Gateway/transport/rendering in isolated temporary databases. Separate authenticated public probes verify reverse-proxy/SSE and exact public Web/OTA bytes. No test sends an experimental trading instruction into the owner's live conversation or account.
- Closed validated frames can publish before later frames or prose complete. A single large JSON frame still needs its closing boundary; no invalid partial tree is rendered. Model output can fail validation, as the one observed safe-fallback case demonstrates.
- Earlier historical 11.86/12.39s pre-provider outliers were not reproduced in these fresh acceptance conversations; correlated instrumentation is included, without an unsupported claim that inference/embedding caused those old delays.
- Final no-backup/staging/database checks and local QA/emulator cleanup are recorded below. The source/verification-only commit containing this report may follow the immutable runtime release; executable source remains identical.

### Final cleanup and file summary

Final production verification passed: runtime `d98b16e`, API/Gateway running and application readiness healthy, schema 0032, no remaining `lonora_prompt3_*_verify` database, no `/opt/lonora/backups`, no release-context directory, and no wheel/Web/OTA upload staging. The final signed OTA 17fbe8aa remains active; only this task's temporary model-image artifacts were removed (`.runtime/prompt3-final-cleanup-verify.log`).

Before local QA cleanup, its ledger contained exactly one user message, one assistant message, one completed Run and one receipt pointing to that same Run. The current-thread message POST count was one; broker accounts and management grants were zero. The local calculator edit created no extra intent/Run (`.runtime/prompt3-native-final-ledger-proof.json`).

The QA wrapper was gracefully stopped; its matched isolated database, private credential file and port 8831 listener were removed. Only the newly created dedicated emulator, proxy forwarder, AVD state and ephemeral trust setup were stopped/removed. Existing user AVDs and shared services were preserved; sanitized screenshots and JSON evidence remain (`.runtime/prompt3-native-qa-cleanup.json`, `.runtime/prompt3-native-hardware-summary.json`).

The executable release changed **97 files**, with 9,464 additions and 1,399 removals against baseline. This includes the 1,980-line verbatim mandate, regression tests and reference documentation; those totals are not the runtime prompt size. This verification-only report update adds no executable behavior.

Selected file sizes in the shipped source:

| File | Lines |
| --- | ---: |
| `packages/agent-runtime/src/lonora_agent/stream_publication.py` | 64 |
| `packages/agent-runtime/src/lonora_agent/display_bindings.py` | 59 |
| `packages/agent-runtime/src/lonora_agent/visual_response.py` | 714 |
| `packages/agent-runtime/resources/prompts/native_visual_response.md` | 38 |
| `packages/agent-runtime/resources/skills/lonora-design/SKILL.md` | 111 |
| `packages/core/src/reply-stream.ts` | 196 |
| `packages/core/src/turn-activity.ts` | 168 |
| `apps/mobile/lib/outgoing-messages.ts` | 221 |
| `apps/mobile/lib/events.ts` | 115 |
| `apps/web/src/components/visual/VisualNumberInput.tsx` | 69 |
| `packages/bus/src/lonora_bus/durable_events.py` | 27 |
| `tests/test_durable_event_delivery.py` | 89 |
