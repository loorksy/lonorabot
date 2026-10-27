# Chat runtime repair: implementation and evidence

This report covers the [prompt3 mandate](lonora-specs/prompt3.md), against baseline
`1ab6953a897c3566d8ea78aa2f4175423662ebe4`. It separates source changes, controlled
regressions, configured-model acceptance and production verification. The earlier
[native visual acceptance report](native-visual-acceptance.md) records a previous
release; its successful fixtures and model journeys do not prove this repair works.

**Release acceptance is in progress.** Exact release identity, final test results,
new stage measurements and deployed-client acceptance must be added to the
verification section before this report is treated as completion evidence.

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
still needs verification again for the final repair and its client assets.

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
| Submit → optimistic user bubble | 12.9 ms in controlled delayed-ACK browser scenario | Already local on Web; verify no regression. Native previously lacked a chat outbox. |
| Submit → HTTP dispatch | 72 ms in the same controlled scenario | Separate client event/request work from provider time. |
| Submit → server ACK | 4,111 ms with an intentionally injected 4,000 ms POST delay | Controlled network delay, not a measured claim about normal production latency. |
| Submit → composer clear | 4,128.3 ms in that scenario | 14.8 ms after repair with the same injected delay; the defect followed HTTP ACK instead of safe local enqueue. |
| Submit → activity | Header 4,202 ms; current-run activity 5,843.8 ms, with delayed run projection | Current-run activity appeared at 4,115.8 ms with the same delays, directly after the 4,108 ms ACK; the extra GET dependency is removed. The independent header metric was 4,275.8 ms; no header improvement is claimed. |
| Queue delay | Historical production sample of 16 runs: 17–273 ms | Source stage instrumentation added; matched new samples pending. |
| Leased → running | Historical production sample: 6–19 ms | Distinct from model/provider initialization. |
| Running → reply started | Most historical samples 0.99–1.66 s; two 11.86/12.39 s outliers | Outliers precede the provider request; cause is not established by this sample. Do not attribute them to embedding or inference without correlated phases. |
| Reply started → first admitted delta | Historical sample 1.37–3.09 s | Provider first text and first publication now measured separately. New correlated results pending. |
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
tool calls and provider inference time. The matching repair run and public-route
release verification remain pending and must be reported separately.

## Verification record

The following focused checks were executed for this documentation/guidance slice:

| Check | Result |
| --- | --- |
| Generated vocabulary against live contract | Passed, 6,449 characters |
| `tests/test_native_visual_policy.py` | 9 passed; resource/cache boundary, registry/exact discovery, examples, generated drift, English/budget and dynamic binding semantics |
| Ruff for generator and native policy tests | Passed |
| Independent reproduction of split credential/binding and unfinished prose defects after fixes | Rejected unsafe rich compositions, no sensitive output; prose explicitly unavailable; requested literal code preserved |
| Compiler, public stream, incremental publication and delta-batching focused suite | 112 passed in 2.68s after the composed-value and final-binding fixes |

Full runtime, persistence, Web, native, configured-model, build and production
results are separate acceptance work. The release owner must record exact counts,
artifact paths, source/client hashes, selected provider/model, repeated real-model
scenarios and any failed/skipped cases here before marking the mandate complete.

Required acceptance scenarios remain the mandate's A–L: simple English; Arabic
conversation; actual multi-tool work; mixed text/UI; local calculator; malformed
UI; unresolved binding; delayed model; network interruption; Android browser;
React Native; and actual configured model through the normal backend/transport
and renderer. A fixture, replay, direct Agent call or Expo Web test alone does
not establish the entire deployed path.

No physical Android device was connected during initial inspection. Installed
AVDs had no available hardware acceleration (`/dev/kvm` absent). Native source,
type checks, shared reducers and Expo Web are useful evidence, but do not prove
that the signed Android app works on a physical device. Device/emulator acceptance
must be identified explicitly if it is performed later.

No live broker order or financial-authority change is required for chat acceptance.
Temporary acceptance identities must have no trading account or management grant.
Report their cleanup, production revision and Web/OTA asset identity separately.

### Final source checks before release

- `bash scripts/build.sh`: passed Ruff, formatting, full Pyright, packaged policy/resource checks, generated vocabulary drift, Biome, all seven TypeScript checks and all seven builds.
- Full Python suite against a temporary migrated PostgreSQL database: **1,343 passed**, 53.50 seconds (`.runtime/prompt3-full-pytest-final.log`).
- Full Web/native TypeScript unit suites: **144 passed**, no failures or skips (`.runtime/prompt3-ts-tests.log`).
- Web chat browser scenarios: **17 passed**: 16 in the final combined run, plus the corrected-contract preview scenario's focused rerun. The first preview fixture used unsupported node types and was correctly rejected; its corrected actual-contract fixture passed (`.runtime/prompt3-web-browser-final.log`, `.runtime/prompt3-web-preview.log`).
- Visual browser regressions: **8 passed**, EN/AR, light/dark, numeric drafts, local-only interactions, reload, narrow tables/diagrams and reduced motion (`.runtime/visual-repair.log`).
- Native lifecycle/WS unit checks: **8 passed**; native-component Expo Web bridge: **6 passed**, including durable WebSocket delivery, immediate enqueue, retries, preview settlement and calculator edits (`.runtime/native-prompt3-browser.log`). These are not device-level claims.
- Controlled 4,000 ms POST / 6,000 ms runs-GET comparison: optimistic bubble **12.9 → 14.8 ms**, composer clear **4,128.3 → 14.8 ms**, HTTP dispatch **72 → 64 ms**, ACK **4,111 → 4,108 ms**, current-run activity **5,843.8 → 4,115.8 ms**. The separate header metric **4,202 → 4,275.8 ms** did not improve. Thread A → B → A now restores the unsent draft; baseline lost it (`.runtime/chat-after.jsonl`).
- Provider-stage instrumentation distinguishes router configuration, context preparation, credentials/adapter creation, generation admission, actual provider first text/request time, overall turn request time and first durable publication. These durations are measured on the server clock, independently of browser render timings.
- A fresh software Android API24 emulator booted, and the existing signed 0.2.8 APK installed successfully. Verification of this release's downloaded JS update remains a separate pending device check.

Public deployment, compatible signed OTA activation and the matching real-model repair run are still pending at this source checkpoint.
