Superseded by VISION.md

# Lonora generative UI today (read-only survey, checkout /home/user/lonorabot @ 3737fc5, main)

Scope: what exists now, how it flows, what it may trigger, and where it differs from the reference
(docs/ui-reference/Lonora-Desktop-37.html "aa_genui" engine) and the owner decisions (Q27, Q36, D5, D6).
Paths are repo-relative to /home/user/lonorabot unless absolute.

## 0. TL;DR

- Lonora already has a generative UI called "native visual responses". The model writes fenced
  ```lonora-ui``` JSON documents between prose paragraphs in its ordinary reply. There is NO tool the
  model calls to emit UI; the vocabulary is a system-prompt block, not a function.
- The server compiles each fenced document (validate against a 26-node allowlist, resolve tool evidence,
  check owned resources, scrub private text), stores the result as `ln_messages.rich_content`
  (`RichContent v1 = ordered parts: text | ui(VisualDocument)`), and keeps `content` as a plain-text
  fallback. Migration 0032 added the column.
- Streaming: only complete, validated frames stream (`run.delta` with cumulative `rich_content`, or
  `run.rich_partial` when no text changed). Partial JSON is never shown. No skeleton / block-by-block build.
- Shared TS logic (`packages/core/src/visual-response.ts`) validates and evaluates documents (no eval);
  web (`apps/web/src/components/visual/RichResponse.tsx`) and mobile
  (`apps/mobile/components/native-rich-response.tsx`) render them.
- Only three actions exist: `follow_up` (sends a plain user message), `open_chart`, `open_artifact`.
  No `submit {intent,data}`, no `why`, no `go`, no Quiz/Timer/Celebrate/Markdown/Days/Segmented/Chips.
- Styling: the web renderer uses the LEGACY shadcn token names (`--foreground`, `--card`, `--border`,
  `--muted-foreground` ...) plus `@lonora/ui-tokens` `visual` metrics; it does NOT use the reference tokens
  (`--surface`, `--raised`, `--accent`, `--glass*`, `--r-md`, `.ux` card colours). On main, `reference.css`
  is not yet imported by `apps/web` (TOKENS.md, phase 1). Mobile uses `appearance` (legacy palette),
  dark-only on native.
- Lonora has already audited Open Intelligent UI (rev 16ef264) and OpenUI (rev 9d73d17 / 9bc3192): see
  `docs/chat-runtime-repair.md` lines 30-128. That audit deliberately EXCLUDED Timer/DatePicker/Flashcard/
  Celebration and all date/random functions. Owner decision Q27 (2026-11-09) now admits Quiz and Timer as
  light personal tasks, so that part of the earlier audit is superseded. Celebrate is not mentioned in Q27.

## 1. End-to-end flow

1. Prompt: `packages/agent-runtime/resources/prompts/native_visual_response.md` (38 lines, < 6,500 chars,
   enforced by `skills/visual_policy.py` MAX_VISUAL_GUIDANCE_CHARS) is inserted right after
   `</lonora_operating_policy>` in the system message (`visual_policy.refresh_visual_policy`, called from
   `skills/system_policy.py:160`). Old checkpoints get the current block in the request copy only.
   The marked block between `<!-- native-visual:generated -->` markers is generated from the live Python
   registry by `scripts/export_native_visual_reference.py` (`--check` fails the build on drift).
   Anthropic prompt caching covers only policy + vocabulary prefix.
2. Evidence catalog: `visual_response.visual_observation_catalog(messages)` appends a system message
   `<lonora_visual_observations>` listing successful current-request tool call ids + tool names (max 24)
   so the model can cite `{"fact":{"call_id","path"}}` (`model_runtime.py:74`).
3. Model reply: prose with zero or more ```lonora-ui``` (or ~~~) fences, each one JSON object
   `{version:1, mode: observed|example|estimate, state?, root:{id,type,...}}`. Max 12 frames compiled per
   reply (`project()` loop `range(12)`), extra frames dropped with `visual_parts_exceeded`.
   Fences inside an ordinary Markdown code block stay code (`visual_start`).
4. Compile: `packages/agent-runtime/src/lonora_agent/visual_response.py`
   - `read_frame` (443): json.loads; only recovers missing/transposed TERMINAL closers; never invents values.
   - `compile_document` (219): rejects drafts carrying `facts` or `{source}`; validates `VisualDocument`;
     resolves each `{fact:{call_id,path}}` via JSON Pointer into the current request's tool results
     (`_evidence` 72 = messages after the last owner conversation message), rejecting failed envelopes
     (`ok:false`, `error`, status in error/failed/denied/unavailable/rejected), private keys (password,
     secret, token, credential, api key, recovery code ...), non-scalars, non-finite numbers; `/length`
     counts returned arrays. Missing call/path -> unavailable cell (null) only if the document still has
     another resolved non-null fact; else whole frame rejected. Resolved facts become `facts{fN:{value,
     source(tool name), observed_at}}` and the tree references `{source:"fN"}`.
   - Display strings (`text,label,value,unit`, rows, points, state strings) pass `redact_private_reply`;
     composed `concat` expressions and the whole text projection pass `public_reply_violation`
     (`_guard_composed_display` 315). Unresolved `{{mustache}}` in display text rejects.
   - `mode=observed`: metric/progress/table/chart values must derive from facts (`_observed` 174).
   - `_resources` (188): image `artifact_id` and open_chart/open_artifact `resource_id` must be rows owned
     by the same owner AND agent AND thread, not `internal_tool_result`; images must be `image/*`.
   - On failure: frame replaced by a localized line ("تعذر عرض هذا الجزء التفاعلي." / "This interactive
     section could not be displayed."), diagnostics logged with structural paths only (no model input).
   - `text_projection` (407) builds the plain-text fallback for `content` (adds "[example]"/"[estimate]").
5. Streaming (`model_runtime.py` 94-178, `public_stream.py`, `progress.py` 43-95,
   `packages/db/src/lonora_db/streaming.py`):
   - `VisualReplyProjector.project(raw, partial=True)` on each provider chunk; a frame is admitted only
     after its closing fence line is complete. `PublicStream.offer` admits text at word boundaries, every
     >=8 chars / >=200 ms, and permanently stops incremental publication if the candidate contains an
     execution claim (`EFFECT_CLAIM` regex, English + Arabic) or a privacy violation.
   - Events: `run.reply_started` -> `run.delta {text, rich_content?}` (cumulative validated tree attached
     once its text is fully present) or `run.rich_partial {rich_content}` when only UI changed ->
     `run.reply_committed` (stream snapshot) -> `message.created` (canonical message with `rich_content`).
     Every write goes through `validated_rich_content` (`packages/db/src/lonora_db/rich_response.py`).
   - Incremental streaming is disabled when the request contains an unverified financial result or an
     unsettled wait (`incremental_allowed`).
6. Final: provider-supplied `rich_content` is discarded (`model_runtime.py:181`), the final text is
   re-projected (220), stored in run state (`tool_loop.py` 283-293, 558-581), and published by
   `complete_run` (`packages/db/src/lonora_db/runs.py:281`) as one `MessageRow(content, rich_content)`.
   Same payload on waits (`task_wait_settlement.py`), resumed runs, peer/subagent returns
   (`collaboration/outcome_return.py`), executor paths (`executor.py` 125-206).
7. Clients: `packages/core/src/reply-stream.ts` (reducer for run.delta/run.rich_partial/reply_committed,
   re-validates), `apps/web/src/lib/stream-timeline.ts`, `apps/mobile/lib/conversation-projection.ts`;
   `Message.rich_content` / `ReplyStreamSnapshot.rich_content` rendered by RichResponse / NativeRichResponse.

## 2. Contracts

Python `packages/contracts/src/lonora_contracts/visual_response.py` (433 lines) and
`visual_values.py` (EXTENDED_ARITY, legacy `{{x}}` -> concat adapter for text/badge only).
TypeScript `packages/contracts/src/visual-response.ts` (109 lines); `domain.ts:34` `Message.rich_content`;
`runs.ts:14` `ReplyStreamSnapshot.rich_content`.

- Node kinds (26): column, row, grid, card, container, divider, text, heading, badge, icon, metric, table,
  list, progress, timeline, diagram, chart, image, disclosure, tabs, button, select, checkbox, slider,
  input, form.
- Common props: id (`^[A-Za-z][A-Za-z0-9_-]{0,47}$`, unique, not __proto__/prototype/constructor), type,
  visible (expression), tone (neutral|info|success|warning|danger). Per-kind allowlist `ALLOWED` (124);
  any other property -> `visual_property_unsupported`.
- Values: scalar | {state} | {source} | {op,args} (draft also {fact}). Operators: add sub mul div min max
  round abs eq gt gte lt lte and or not if + floor ceil sqrt pow clamp percent change concat; arity table;
  expression depth <= 8.
- Limits: document 64,000 bytes, 120 nodes, depth 10, 40 children, 20 state keys, text 4000, label 300,
  table 12 fields x 100 rows, chart 100 points, diagram 20 vertices / 30 edges, 20 options, reply 24 parts,
  whole RichContent 128,000 bytes, text part 32,000 chars.
- Controls need `state_key` declared in `state` with a type-correct initial value inside bounds; tabs need
  one child per option; table `filter_key` must be a string state.
- `VisualAction` (78): `follow_up {text<=2000}` | `open_chart {resource_id uuid}` | `open_artifact
  {resource_id uuid}`. `follow_up.text` may contain `{{key}}` only for declared state keys.
- Chart kinds: line | bar | pie (points {label,value}). No series, period switch, table toggle.
- `VisualDocument`: version 1, mode, root, state, facts. No `why`, no `fallback`, no `title/sub/icon`
  envelope (the reference has `ui:{kind,title,sub,icon,why,...,fallback}`).
- `RichContent.compiled` rejects any remaining `{fact}` (unresolved) at the durable boundary.

## 3. Shared logic `packages/core/src/visual-response.ts` (817 lines)

`validateVisualDocument` (255) / `validateRichContent` (502) mirror the Python contract (own-property
checks, prototype keys, getters and cycles fail closed); `evaluateVisualValue` (538) pure bounded
evaluator, nulls for invalid math; `initialVisualState` (692) restores only declared scalar keys;
`updateVisualState` (712) only the declared control (or a table's own filter) can change state;
`expandVisualAction` (742) substitutes `{{key}}` from state into follow_up text; `filterVisualRows` (764);
`visualDocumentKey` (797, FNV-style cache id, not a signature); `visualStateStorageKey` (808)
`lonora:visual:v1:{owner}:{thread}:{message}:{docKey}`. Private-text guard in `visual-private-text.ts`.

## 4. Renderers

Web `apps/web/src/components/visual/` : RichResponse.tsx (617), VisualGraphics.tsx (chart/diagram SVG),
VisualNumberInput.tsx (Open Intelligent UI draft/commit pattern), VisualTable.tsx, visual.css (563).
- Invalid RichContent -> `<ChatMarkdown>{content}</ChatMarkdown>` fallback.
- Text parts and `text` nodes render through ChatMarkdown (so Markdown incl. code fences works inside).
- Chrome labels (ar/en): «مثال توضيحي», «تقدير», «المصادر», «بيانات مؤكدة», «إعادة ضبط المدخلات»,
  «جارٍ الإرسال…», «عرض المزيد/أقل», «تعذر عرض هذا الجزء.». Mode badge shown when mode != observed;
  provenance disclosure lists verified facts with observed_at; reset button when state exists.
- Local state persisted in `localStorage` under `visualStateStorageKey` (with preview->final migration via
  `previousMessageId`).
- Consumers: `apps/web/src/pages/shell/message-cards.tsx:137` (committed messages) and `:334` (streaming
  preview, messageId `preview:{run.id}`); action handler `apps/web/src/pages/shell/chat-context.tsx:291-302`.
- `dir="auto"` on the document section; RTL via logical CSS.

Mobile `apps/mobile/components/`: native-rich-response.tsx (872), native-rich-controls.tsx,
native-rich-graphics.tsx, native-rich-theme.ts; state in `apps/mobile/lib/visual-state.ts` (expo-file-system
JSON files, localStorage on web, cleared on session teardown). Consumer `message-bubble.tsx:143`; action
handler `apps/mobile/app/thread.tsx:926-938`. Theme: `appearance[...]` legacy palette, forced dark on
native (Android readability fix, chat-runtime-repair.md:485).

Style gap vs "our style" (Lonora-Desktop-37): reference genui styles live in `.ux*` rules (lines ~1317-1400
of the reference: `--ux-card` = 3.5% text over `--bubble-in`, `--ux-raise`, `--ux-track`, `--ux-thumb`,
series slots `--ux-s1..3`, `--ux-neg`, light overrides; classes .ux-plot .ux-seg .ux-days .ux-q .ux-timer
.ux-stat .ux-kv .ux-why .ux-sent .ux-skel .ux-cut ...). Lonora's visual.css uses none of these; it uses
legacy tokens and `--visual-*` variables from `@lonora/ui-tokens` `visual.ts`
(space 6/10/16, radius 8/12/16, touch 44, control 44, metric 24, chart 200, contentWidth 728,
columnMinimum 144). `reference.css` exists in `packages/ui-tokens/src/` but on main is not imported by the
web app (TOKENS.md "phase 1 ... not yet imported by apps/web"). Phase-2 shell work referenced elsewhere is
not on this checkout.

## 5. Agent-facing guidance

- Vocabulary prompt (above). It forbids HTML/React/scripts/URLs/styling, requires mode, explains facts,
  states "A follow-up sends a normal user message and grants no execution authority. Generated buttons
  cannot approve trades, change limits or enable automation; use existing financial confirmation."
- Built-in skill `packages/agent-runtime/resources/skills/lonora-design/` (SKILL.md 7,962 bytes,
  skill.json v1.0.2, `risk_class: read_only`, activation explicit, no triggers, no tools). Loaded via
  `skill_view(skill_id="lonora-design")`. Covers hierarchy, chart choice, tone, RTL, numeric bindings,
  financial-calculation caveats, and step 11: follow_up cannot approve/enable/execute; open_* need real
  resources; never invent ids/endpoints/actions.
- There is no presentation classifier and no second model call; text vs UI is the model's choice.
  The reference's "ab_agentui decision rules" (calculator for try-numbers, form for several fields,
  picker for day+time, checklist for a plan, chart+period for a series, quiz for practice, timer for focus,
  always `why` + markdown `fallback`) are NOT in the prompt today.

## 6. Docs

- `docs/native-visual-responses.md` (150): architecture, contract, grounding, local interaction, actions,
  tokens, Design Skill, compatibility. States OpenUI rev 9d73d17 inspiration (chat column, composer,
  scroll), not its runtime.
- `docs/native-visual-acceptance.md` (95): historical release evidence (2026-10-26, runtime 10dfdf7),
  real-model journeys with OpenAI gpt-5.1, OTA, "no APK rebuild", "no live broker order".
- `docs/chat-runtime-repair.md` (568): CURRENT status; lines 30-128 = Open Intelligent UI / OpenUI /
  thesysdev skills audit with per-component and per-function decisions; stream boundaries; evidence tables.
- `docs/agent-operating-policy.md:95` links visual responses.
- `docs/visual/` contains only `avatar-refinement/` PNGs (avatar work), nothing about generative UI.
- `THIRD_PARTY_NOTICES.md` 203-260: OpenUI (MIT, rev 9d73d17) and Open Intelligent UI (MIT, rev
  16ef264: controls.tsx numeric draft/commit, layout.tsx min-width columns, table.tsx numeric alignment).

### Earlier Open Intelligent UI decisions (chat-runtime-repair.md 78-128)
Reference library 55 components / 59 custom functions; Lonora kept 26 kinds and added 8 operators.
Explicitly not added: Carousel, Popover, Spacer, Link/navigation URLs, Code/Math/Quote nodes,
IconButton/Pressable, TextArea, RadioGroup, DatePicker, Timer, SearchImage, Map, YouTube, Svg primitives,
HtmlView, Flashcard, Celebration; list/collection mutation, Random/Shuffle, all Date functions (Now, Today,
AddDays ...), Format/Plural/Join, MixColor, aggregations. `@Set`-style mutation replaced by declared scalar
state. Autofix (second inference) rejected. Browser chat storage rejected (PostgreSQL is canonical).
Q27 now overrides the Timer exclusion (and admits Quiz) as light personal tasks.

## 7. Tests (not run in this survey)

Python: tests/test_visual_response.py (evidence, fallbacks, terminal recovery, private scrub, cross-thread
chart rejected, unverified financial receipt not bypassed, follow_up template keys), test_visual_persistence.py
(publication rejects trade_execute/grant/api/javascript actions and unknown kinds, fenced stream sequence,
rollback/stale worker, waits, peer return), test_incremental_visual_stream.py, test_visual_scalars.py,
test_native_visual_policy.py (vocabulary loading, cache boundary, generated drift, skill discovery),
test_visual_acceptance.py (cannot acquire financial services), test_visual_host_lifecycle.py.
TS unit: tests/web/visual-response.test.ts (14 cases), visual-scalars.test.ts, visual-streaming.test.ts.
Playwright: tests/web/visual-response.spec.mjs (ar/en x light/dark composition + reload; invalid/executable
fallback; numeric drafts on phone; dense content at 320px; live-model replay), tests/mobile/visual-response.spec.mjs
(Expo web, ar/en x light/dark, reopen), plus tests/web/chat-send-latency.spec.mjs, tests/mobile/chat-runtime.spec.mjs.
Drift check: `.venv/bin/python scripts/export_native_visual_reference.py --check`; real-model journeys:
`scripts/verify_agent_journeys.py`.

## 8. Capability map rows (docs/ui-reference/CAPABILITY_MAP.md)

- Line 9 summary: generative-UI vocabulary = WP-G.
- Line 123 `chat.messages.generated-ui`: reference message shape `{kind:'ui', text lead, ui:{kind,title,sub,
  icon,why,state,calc,root[],fallback,values,sent,view,whyOpen,asText,cut}}`; lead text streams then card
  builds block by block (230-350 ms per block, skeleton, newest block animates; stop mid-build keeps built
  blocks with «أوقفتَ الرد قبل اكتمال الواجهة»); components list; `when`; expressions ($state, @Round @Money
  @Pct..., calc); actions set/toggle/reset/copy/open(https)/go(whitelist)/send{intent,text,data,lock} -> a
  user message quoting the card; required fields block send; locked «أُرسل إلى … · تعديل»; «لماذا هذه
  الواجهة؟»; markdown fallback; menu «عرض كنص». Status build_backend. Mapping reference -> VisualNodeKind
  given in the row. Gaps listed: Markdown node, Days picker, Quiz, Timer, Celebrate, segmented, multi-select
  chips, `why`, calc/derived state, `send` with structured data + lock/edit, `go` whitelisted routes, chart
  period switch/table toggle. Money-safety note: generated controls never create grants, limits or trades.
- Line 124 supervisor-evidence (evidence-list part), 125 out-of-scope-reply (suggestion rows = follow_up
  buttons + new read-only `open_agent`/`open_journal`), 126 question-card (existing `wait_for_input` /
  `MessageCreate.input_answer` with `reply_to` quote), 127 task-card (`open_task`): all tagged WP-G.
- Line 195 dev genui gallery «معرض الواجهات»: dev_only, out of production.
- Line 206 settings.chat-prefs: «الواجهات التفاعلية» genui / genuiWhy toggles per device; genui off shows the
  markdown fallback.
- Line 252 WP-G: new node kinds + metadata (Markdown, Days, segmented, multi-chips, chart period/table
  toggle, `why`, derived state), action `send {intent,data,lock}` as quoted user message (non-financial),
  navigation actions go/open_agent/open_journal/open_task/open_operation/open_watch/open_message,
  evidence-list part, task-created card; Quiz/Timer/Celebrate after OQ26. Phase 3. Events: run.rich_partial
  unchanged.
- Line 337 OQ26 -> owner decision Q27.

## 9. Owner decisions that bind the work

- Q27: add `why` + non-financial `submit {intent, data}` rendered as a quoted user message; Quiz/Timer are
  light personal tasks (allowed). Celebrate: not named -> undecided.
- Q36: fenced code blocks allowed as explanation with «نسخ الكود»; code as a deliverable stays refused (D5).
  Today the contract has no code node; code can only appear inside Markdown text (text parts / text nodes).
- Q19: keep the reference's own vocabulary (labels such as «لماذا هذه الواجهة؟», «عرض كنص», «أُرسل إلى …»).
- Q23: `suggested_reply` (<=60 chars) for conversational answers only, never after cards.
- Q37: agent annotations on the live chart are read-only overlays; native `chart` is supplied-data only.
- D5 never deliver code; D6 light personal tasks only; corrections 1, 5, 21, 32 (single executor, grant,
  approval tap, domain scope).

## 10. Money-safety rules for anything a generated interface can trigger

What a generated control can do today:
1. Local only: change declared scalar state, filter a table, switch tabs, expand disclosures, reset.
   No network, no model call, no broker read (core + both renderers; tested "local changes do not send
   requests").
2. `follow_up`: web `thread.send(text)` / mobile `send(undefined, text)` -> `POST /api/threads/{id}/messages`
   with `MessageCreate{content}` (no input_answer, no reply_to, no marker). The owner's tap starts an ordinary
   Run; whatever the agent then does goes through the normal tools and gates.
3. `open_artifact`: web `GET /api/artifacts/{id}` then preview; mobile route `/artifact?artifactId=`.
4. `open_chart`: web `GET /api/charts/{id}` then the chart panel; mobile `chartSheet.open`.
   Both resource ids were already ownership-checked at compile time (owner, agent, thread).

What it can never reach (no action kind exists; schema rejects unknown kinds, URLs, HTML, scripts):
`POST /api/trading/approvals/{id}/decision`, `POST /api/owner-actions/{id}/challenge|decision` (grant,
limits, passkey), execution-policy routes, restriction lift (owner_only), broker/MetaApi endpoints,
arbitrary https, any tool directly.

Server gates that already protect money regardless of UI:
- Only `trade_execute`, `trade_close_positions`, `goal_step_execute` are FINANCIAL_CALLS
  (`context/financial_result.py:9`); they go to the single executor under the signed grant / approval card,
  account limits, pauses and restrictions. When a model turn proposes one, its reply text (and therefore
  any visual) is blanked (`model_runtime.py:202`). An unverified financial result replaces the reply with the
  verified summary and disables incremental streaming.
- `wait_for_input` refuses `purpose=execution_authorization` ("Financial consent must use trade_execute").
- Observed values only from successful current-request evidence; cannot claim fills/balances; mode labels
  never upgrade examples to evidence; `EFFECT_CLAIM` stops streaming of execution claims.
- Lonora Design Skill is `read_only`, grants no tools or authority.
- Restrictions: agents may only narrow; only the owner lifts (`tools/restrictions.py` "lift": "owner_only").

Risk to carry into the `submit` design (observed, not a decision):
- A `follow_up` message is model-authored text stored as `role="user"`, indistinguishable from typed owner
  words. Several sensitive checks read the latest user message as owner intent:
  `tools/restrictions.py:96 owner_message_id` (supervision, agent creation/control, owner profile and
  reach-me, model switches, narrowing other agents, lifting a supervision hold),
  `tools/owner_actions.py:132 owner_asked_full` (preselect Full delegation on the grant card),
  `tools/models.py:138` (model choice), and `tools/trade.py:152 owner_spoke_since` (after a rejected trade
  card, any later user message lets the agent raise a new approval card). Money still needs the passkey or
  the approval tap, but a model-authored button text can currently stand in for "the owner's words".
  A structured `submit {intent, data}` should carry provenance (e.g. a dedicated MessageCreate field
  referencing the source message + document) so these checks can tell a card submission from typed words,
  with an intent allowlist that excludes anything financial or authority-widening, and bounded scalar data.
- Existing precedent for "structured answer rendered as a quoted user message": `wait_for_input` choices ->
  `MessageCreate.input_answer {run_id, question_id, choice_id}`; `send_message` sets `reply_to` to the
  question message; web shows `.template-message-quote`. Reusing `reply_to` gives the quote for free.

## 11. Gap list (today vs reference + Q27), for planning

Contract/server: `why` on VisualDocument; `submit {intent, data(, lock)}` action + server-side validation +
provenance; Quiz, Timer (light personal tasks; need clock state rules: today no date/time operators),
Markdown node, Days picker, segmented control, multi-select chips, switch/checklist styling, KeyValue,
Note, Stat with delta; chart series/period switch/table toggle/crosshair; `when` already = `visible`;
derived `calc` (today inline expressions only); navigation actions (`go` whitelist, open_agent, open_journal,
open_task, open_operation, open_watch, open_message) each needing ownership checks; required fields;
locked "sent" state persisted (today only client localStorage for control state); `copy` action;
document-level fallback text (today `content` is the generated projection, not a model-written markdown
fallback). Celebrate needs an owner answer.
Prompt: decision rules (when to answer with UI), always `why`, Arabic-first examples.
Clients: reference look (`.ux` tokens, glass/raise, seg thumb, ring timer, quiz options, chart method:
2px line + 10% area + end dot; bars <=24px; polar colours), skeleton + block-by-block build animation,
stop mid-build keeps built blocks + «أوقفتَ الرد قبل اكتمال الواجهة», «لماذا هذه الواجهة؟» disclosure,
«عرض كنص» message-menu item, per-device genui / genuiWhy prefs, «أُرسل إلى … · تعديل» lock, quoted user
bubble for submissions. Mobile native currently dark-only.
Streaming: server streams whole validated frames; block-by-block is a client presentation of frames that
arrive (the prompt already asks for "small complete frames").
