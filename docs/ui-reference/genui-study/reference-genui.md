Superseded by VISION.md

# Reference generative UI (Lonora-Desktop-37.html): full extraction

Source: `/home/user/lonorabot/docs/ui-reference/Lonora-Desktop-37.html` (9612 lines). All line numbers below are from this file
unless another file is named. Read-only extraction; nothing was executed.

Owner request (verbatim): «في الملف المرجعي وضعنا https://github.com/thesysdev/open-intelligent-ui تاكد من انه يعمل مثل
https://github.com/thesysdev/open-intelligent-ui لكن ب اسلوبنا نحن». The reference's own words: "Same idea as OpenUI /
'intelligent UI': a reply may carry a small declarative spec that the app renders with its own components" (6239-6242).

## 0. Map of the code

| Part | Lines |
|---|---|
| Header doc block (GENERATIVE UI section, same text as ref37.notes.txt 83-118) | 2354-2388 |
| Prefs in header (`genui`, `genuiWhy` in S.prefs) | 2336-2337 |
| CSS: generative UI block | 1311-1539 |
| CSS: `.ux-picks/.ux-pick` (v35 "no chip clouds": Chips render as a list) | 2230-2237 |
| Engine doc comment (spec, nodes, expr, actions) | 6239-6260 |
| Expressions: functions `UX_FN`, lexer, parser, evaluator, cache, templates | 6262-6358 |
| Helpers (clone, ymd, DayLabel, clock, ids, opts, Arabic-digit parser) | 6360-6373 |
| Hosts (chat message or gallery), values, env/calc, node lookup, save | 6375-6383 |
| Components `UX` + `uxNode/uxKids/uxBox/uxTone/uxLabel` | 6385-6449 |
| Timer state | 6450-6456 |
| Chart (`uxNice`, `uxChart`, crosshair/tooltip/keyboard) | 6458-6530 |
| Card markup, footer, message body, `uxSpec` normaliser | 6532-6555 |
| Partial refresh (`uxSwap`, `uxRefresh`, `uxSyncInput`, `uxSyncPicker`, `uxRepaint`) | 6557-6604 |
| Celebrate / confetti | 6606-6616 |
| Actions (`uxAction`, `uxRunAction`, required fields, `uxSend`, timer ops, timer tick) | 6618-6692 |
| Typing/change/Enter listeners | 6694-6707 |
| ab_agentui decision layer (doc comment, `UX_TEXT_ONLY`, `uxLit`, plan items, `UX_RECIPES`, `UX_MATCH`, `uxPlan`, `uxReply`, receipts) | 6708-6892 |
| Agent handling of submitted cards (`UX_EVENTS`, `UX_EVENT_STEPS`, `uxAnswer`, `uxSteps`, `uxCopyText`) | 6894-6953 |
| Gallery page `genuiPage()` and «جرّب في محادثة» `uxTry()` | 6955-6967 |
| Integration: message markup (`m.kind==="ui"` → `uxMsgBody`, bubble `wide ui-bubble`, class `k-ui`) | 3788, 3796-3800 |
| Integration: quote of a ui message (sparkle icon) | 3750-3753 |
| Integration: message menu «عرض كنص» / «عرض الواجهة» (`ux-text`) | 3883-3887 |
| Integration: reply pipeline (`startReplies`, steps, streaming start) | 3963-3995 |
| Integration: `agentAnswer` order of precedence (uiev → agentIntent → uxPlan → …) | 3997-4012 |
| Integration: streaming phases steps → text → ui, stop mid-build | 5804-5855 |
| Integration: «تجربة المحادثة» toggles + gallery row | 5748-5762 |
| Integration: dispatcher (`ux-try`, `ux-*`), copy (`uxCopyText`) | 9109-9123, 9148 |
| Integration: suggestion after a ui message «اشرح لي النتيجة» | 7589-7606 (7599) |
| Integration: route `genui` dev-gated, title, settings route set | 3671, 3016, 3111, 5660, 8623-8625 |
| Integration: `sendMessage(text, extra)` (extra spreads last into the user message) | 3939-3951 |
| Integration: order sentences never reach genui (`agentIntent` → `orderIntent/orderAnswer`) | 8532-8546, 8570-8587 |

## 1. Message and spec shape

Stored message (6245, 2356-2359):
```
{ kind:"ui", text: <lead, streamed first>, steps?, ui: {
    v:1, kind:<Arabic label of the interface type>, title, sub, icon, why,
    state:{…initial values}, calc:{name:expr,… in order}, root:[node…], fallback:"markdown",
    values?   (live state; lazily cloned from state on first read, 6378)
    sent?     {at, text}  (card locked after a send, 6671)
    view?     {<node path>: "table"|"chart"}  (chart/table toggle per chart, 6626)
    fx?       {<node path>: 1}  (Celebrate already fired, 6448, 6607-6611)
    whyOpen?  bool  (6623)
    asText?   bool  (menu «عرض كنص», 6625)
    cut?      number of root blocks built when the user stopped (0 = stopped before the card, 5849)
} }
```
`uxSpec(s)` normaliser (6555): `{v:1, kind:s.kind||"", title, sub, icon:s.icon||"sparkle", why, state:clone(s.state), calc:s.calc||{}, root:s.root||[], fallback}`.
Recipe objects additionally carry `lead` (used as message text) (6882).
Header note (2357-2359): "The spec is data the model emits (JSON tool output or a streamed DSL); the app renders it with its own
components and never accepts HTML. Validate each node with Zod (discriminated union on `type`)."

Node: `{type, when?:expr, …props}`; text props are templates `"{@Money($amount)} من {$total}"` (6246). Unknown `type` renders
nothing (6389). Node path = dotted index into root/children, e.g. "3.0" (6380, 6393); DOM carries `data-ux="<path>"`.

## 2. Components (every prop the code reads)

Classification sets (6386): containers `Col Row Grid Card`; inputs `Slider Number Input Select`; pickers
`Segmented Chips Choice Switch Checklist Days`. Any node: `when` (expr) → hidden placeholder `<div data-ux=… data-ux-off hidden>` (6390).

| type | props | render / behaviour | line |
|---|---|---|---|
| Col | children | `.ux-col` grid gap 12 | 6399 |
| Row | children | `.ux-row` flex wrap gap 8; buttons flex 1 1 auto | 6400 |
| Grid | cols (clamped 1..4, default 2), children | `.ux-grid` `--cols` | 6401 |
| Card | title, icon, children | `.ux-panel` (raised inner panel) + `.ux-panel-h` | 6402 |
| Divider | – | `<hr class="ux-hr">` | 6403 |
| Title | text | `.ux-title` 16/700 | 6404 |
| Text | text (inline md), tone, size:"sm" | `.ux-text` + `t-<tone>` | 6405 |
| Markdown | text | `.ux-md.md` via `md()` (escaped first) | 6406 |
| Badge | text, icon, tone | pill `.ux-badge` | 6407 |
| Note | text (inline md), tone (default info), icon (default alert/check/info by tone) | `.ux-note` role=status | 6408 |
| List | items[] (templates, inline md), icon (default check) | `.ux-list` | 6409 |
| KeyValue | rows: [[k,v],…] | `.ux-kv` label muted / value 600 end-aligned, hairline rows | 6410 |
| Stat | label, value, sub, trend (expr → "up"/"down"), tone | `.ux-stat` 19/700 value; trend icon trend/trendDown | 6411 |
| Progress | value (expr 0..100), label, tone | header label + `%`, `.ux-track` 8px accent; role=progressbar | 6412 |
| Slider | bind, label, min (0), max (100), step (1), show (template, default `{$bind}`) | range input, `<output>` live, `--p` fill, aria-valuetext | 6413-6414 |
| Number | bind, label, hint (template, live), prefix, suffix, required | text input inputmode=decimal dir=ltr; Arabic digits parsed | 6415-6416 |
| Input | bind, label, placeholder, max (maxlength, default 120), required | text input | 6417-6418 |
| Select | bind, label, options | native select with chevron | 6419-6420 |
| Segmented | bind, label, options | `.ux-seg` radiogroup, sliding thumb `--n/--i` | 6421-6422 |
| Chips | bind, label, options, multi | list rows `.ux-pick` with radio or check box; multi → array value | 6423-6424 |
| Choice | bind, label (aria), options:[{value,title,sub,badge,points[]}] | `.ux-opt` rich radio cards | 6425-6426 |
| Switch | bind, label, sub | row + `.switch` role=switch | 6427-6428 |
| Checklist | bind (object {id:true}), items:[{id,label,sub}] | `.ux-ci` role=checkbox rows, done = strike-through muted | 6429-6430 |
| Days | bind (YYYY-MM-DD), label, count (1..14, default 7) | horizontal day buttons «اليوم»/«غدًا»/weekday + date | 6431-6433 |
| Button | label, style:"primary" (else outline), icon, full, action, disabled (expr) | `.btn sm`; when card locked only go/open/copy stay enabled | 6434-6435 |
| Table | title, columns:[{label,num}], rows:[[…]] or each (expr) + as (default "item") + cells[] templates (locals: as, i), highlight (expr) | `.md-table`; ≤60 rows from each; highlighted row aria-current | 6436-6439 |
| Chart | kind line/bar, title, series:[{name,data}], labels, by (state key choosing data/labels by key), polar, fmt (template with local x, default `{@Fmt(x)}`), unit, zero, height (default 150), area (false disables wash) | see §6 | 6440, 6465-6510 |
| Quiz | bind (object {qIndex: optionIndex}), questions:[{q, options[], answer, explain}] | per question: options lock after answer, right/wrong marks, «صحيح.»/«ليس تمامًا.» + explain | 6441-6444 |
| Timer | bind (object {status idle/run/pause/done, total, left, end}), minutes (expr, default 25), label | 140px ring, clock mm:ss, ابدأ/متابعة · إيقاف مؤقت · من جديد | 6445-6447, 6450-6456 |
| Celebrate | on (expr) | invisible marker; confetti the first time `on` turns true | 6448, 6607-6616 |

Options (6371): array of primitives → `{value:x,label:String(x)}`; objects keep fields with `label` templated (default String(value)).
An option may carry `also:{key:value}` that is merged into state when picked (6633; used by the alert recipe to reset price per asset).

## 3. Expression language

Lexer (6287-6301): whitespace; number `\d+(\.\d+)?` (no sign, no exponent); string `'…'` or `"…"` (no escapes);
`$name` state; `@Name` function; identifier (true/false/null or a local); operators `&& || == != <= >= - + * / % < > ! ? : ( ) . , [ ]`.
Anything else throws.

Grammar (6302-6324), lowest to highest: `c ? a : b` (right-assoc) · `||` · `&&` · `== !=` · `< <= > >=` · `+ -` · `* / %` ·
unary `! -` · postfix `.prop` / `[expr]` · primary (number, string, `$var`, `@Fn(args)`, ident, `( )`, `[list]`).
AST nodes: c const, v state var, l local, a array, u unary, ? ternary, g get, f call, b binary.

Evaluator (6325-6348): state/locals read only own properties; `.length` allowed on strings/arrays; `__proto__`, `prototype`,
`constructor` blocked (6263); only whitelisted `UX_FN` callable; `&&`/`||` short-circuit; `+` concatenates if either side is a
string else numeric with `||0`; `/` and `%` by zero → 0; `==`/`!=` are loose JS equality.
`uxExpr(src, env, dflt)` (6350-6356): non-strings returned as-is; ASTs cached per source string (parse failures cached as null,
console.warn); runtime error, undefined or non-finite number → `dflt`.
Templates `uxTpl` (6358): `{expr}` (no nested braces) → `uxShow` (6357): numbers en-US grouping, integers 0 dp else ≤2 dp;
null → ""; arrays joined «، ». A failing template expression renders "" (dflt ""), not "—"; "—" comes from the number formatters
(`uxNum`) when given a non-finite value and from chart `fmt` for null points (6264, 6470).
Env (6379): `v` = copy of values, then each `calc` entry evaluated in order (later calcs see earlier ones); `l` = locals
(Table `as`/`i`, Chart `x`).
User text placed into a spec goes through `uxLit` (strips `{}`) so it never becomes an expression (6717, used in receipts 6889, 6915).

Functions `UX_FN` (6266-6286):
`Round(x,d=0)` · `Floor(x)` · `Ceil(x)` · `Abs(x)` · `Sqrt(x)` (≥0) · `Min(...)` / `Max(...)` (flatten arrays) · `Pow(a,b)` ·
`Clamp(x,a,b)` · `Fmt(x,d=0)` · `Money(x,d=0)` → "$1,234" / "-$…" (ASCII hyphen) · `Pct(x,d=0)` → "1.5%" · `Signed(x,d=0)`
→ "+3.1" / "−3.1" (U+2212) · `If(c,a,b)` (eager: both branches evaluated) · `Pick(k, k1,v1, k2,v2, …, default?)` ·
`Len(x)` · `Count(x, v=true)` (values equal to v in array/object) · `Sum(x)` · `Range(a,b,s=1)` (≤201 items) ·
`Includes(list,v)` (string compare) · `Join(x, sep="، ")` · `Plural(n, one, two, few, many, zero="")` (Arabic count via
`arCount`, 4968) · `Score(ans, keyArray)` (correct answers in a Quiz object) · `DayLabel("YYYY-MM-DD")` → «اليوم 9 نوفمبر» /
«غدًا …» / «الثلاثاء …» (ar with Latin digits, 6363-6368).
Note: the header/notes list omits Floor, Ceil, Abs, Sqrt, which the code has.

Number input (6373): Arabic-Indic ٠-٩ and Persian ۰-۹ digits, ٫ decimal, ٬ / , / spaces as grouping → number or null.

## 4. Actions

Button `action` (6648-6659, doc 6257-6260):
| do | fields | effect |
|---|---|---|
| set | key, value (expr) | `values[key]=expr` → refresh |
| toggle | key | boolean flip → refresh |
| reset | – | values ← clone(state), fx cleared, full repaint |
| copy | text (template) | clipboard, toast «نُسخ» |
| open | url (template) | only `https://` (regex), new tab noopener,noreferrer |
| go | route, args | only routes `tasks, schedules, usage, chat-prefs, genui, files, agents` |
| send | intent, text (template, default button label or «تم», ≤400 chars), data {k: expr}, lock (default true) | see below |

Button disabled when `disabled` expr is truthy, or when the card is sent/locked and the action is not go/open/copy (6434, 6650).

`send` (6666-6675):
1. Required check `uxMissing` (6661-6665): walks visible nodes; first `required` node whose bound value is null/blank → its input
   gets `aria-invalid="true"` + focus, toast «أكمل «<label>» أولًا» (warn). Typing clears aria-invalid (6699).
2. `data` = each expr evaluated and deep-cloned.
3. `lock!==false` → `ui.sent={at,text}`.
4. Gallery: repaint + toast «في المحادثة يصل هذا إلى الوكيل: «text»».
5. Chat: save, repaint, vibrate 8, `sendMessage(text, {uiev:{mid, intent, data}, to:[card's agent], reply:{id:mid, sender:"agent",
   agent, kind:"ui", text: ui.title || snippet}})` → a normal user bubble quoting the card (quote shows sparkle icon + title,
   3750-3753). `extra` spreads last into the user message (3951), so `to` routes the answer to the card's agent even in a group.
Locked footer: «أُرسل إلى <agent>» (gallery: «أُرسل») with checks icon + «تعديل» link (`ux-unlock`: removes `sent`, toast
«عدّل ثم أرسل من جديد») (6544, 6624). Locked body opacity .82 (1344). `lock:false` is used for repeatable questions
(perf.explain, quiz.review).

Internal UI actions (all `ux-` prefixed via `handle` → `uxAction`, 9123; 6619-6647): `ux-why` (toggle whyOpen), `ux-unlock`,
`ux-text` (menu, toggle asText), `ux-view` (chart/table), `ux-do` (button), `ux-timer` (start/pause/reset), `ux-pick`
(Segmented/Chips/Choice/Days; multi chips toggle membership; `also` merged), `ux-toggle` (Switch), `ux-check` (Checklist),
`ux-quiz` (answer once; focus moves to next unanswered question or the buttons after the quiz), `ux-try` (gallery, 9111).
Picks/toggles/checks are ignored once the card is sent (6630). Haptics: pick/toggle/check 6ms; quiz right 8 / wrong [10,40,10];
send 8; timer op 6; timer done [30,60,30]; celebrate [12,40,18].
Keyboard: Enter in a card text input clicks the card's first enabled `.btn.primary` (6707).

How the agent handles a submitted card (mock of "the agent acts with its tools", 6894-6947): `agentAnswer` checks `um.uiev` first
(4001) → `uxAnswer` → `UX_EVENTS[intent]({a, responder, um, d:data, card, push})`; unknown intent → «وصلني اختيارك وسأتصرف بناءً
عليه.». Steps for uiev turns come from `UX_EVENT_STEPS` (6937-6942), e.g. «أداة: إنشاء تنبيه سعر» + «تأكيد الإنشاء».
Answers are text or another interface; confirmations use a receipt interface (`uxReceipt`, 6886-6891: kind «إيصال», KeyValue rows
+ Row of buttons, default why «تأكيد مختصر بالتفاصيل مع زر للخطوة التالية؛ أوضح من فقرة وأسهل من البحث في القوائم.», fallback
`lead + "- **k:** v"` list).

## 5. Rendering, streaming, partial refresh

Card markup (`uxMarkup`, 6533-6540):
```
<div class="ux [is-sent] [is-building]" data-ux-mid role="group" aria-label=title [aria-busy]>
  <div class="ux-head"><span class="ux-ic">icon</span><span class="ux-ht"><b>title</b><small>sub</small></span></div>
  <div class="ux-body"> blocks… [newest block has data-ux-new] [skeleton .ux-skel two bars while building] </div>
  [ux-foot when not building]
</div>
```
Footer (`uxFoot`, 6541-6545) only when sent, cut or why: sent line + «تعديل» · cut line «أوقفتَ الرد قبل اكتمال الواجهة» (stop
icon) · «لماذا هذه الواجهة؟» button (sparkle, aria-expanded, end-aligned) → `<p class="ux-why">` under the footer when open.
Why button hidden when pref `genuiWhy` is off (6542).

Bubble (`uxMsgBody`, 6546-6554): steps markup → lead text (caret while streaming text) → if genui pref off or `asText`:
`<div class="md ux-alt">fallback</div>`; else the card (with `reveal` count while streaming). Card hidden during steps/text phases
and when `cut===0`.

Streaming (5804-5853) and reply timing (3963-3995):
- First reply starts 650ms after send (next responders 760ms); lab "slow" ×2.
- Steps: 620ms each (×2.2 slow); for a ui lead, steps are «فهم الطلب» (title) · «اختيار طريقة العرض» (kind) · «بناء الواجهة»
  (N عناصر) and «البحث في الويب · 4 نتائج» first when the chat's web option is on (`uxSteps`, 6948-6952). Then they fold to
  «N خطوات · Xث».
- Text: two tokens per 34-68ms with caret.
- UI phase (5824, 5820): 260ms after text ends, one root block every 230-350ms (`st.ui++`, repaint), newest animates `ux-in`
  (.38s, translateY 8px→0), skeleton below; 400ms after the last block the stream finishes.
- Without stream pref: the full message appears at once (3992).
- Stop (5845-5854): `ui.cut = blocks built` if stopped in ui phase, else 0; text keeps what streamed; `m.stopped` → «أوقفتَ الرد».
- Header note (2381-2382): "steps → lead text → the card builds block by block (skeleton, newest block animates); stop mid-build
  keeps what was built." Real build: "JSON tool output or a streamed DSL".

Partial refresh after any state change (`uxChanged` = debounced save 220ms + `uxRefresh`, 6604, 6382):
- `uxRefresh` (6564-6580) walks every `[data-ux]` element of the card:
  - visibility flip (`when`) → swap the whole node; hidden → skip;
  - Celebrate → `uxFx`; containers → skip (children have their own `data-ux`);
  - inputs → `uxSyncInput` (6581-6589): set value unless it is the element being typed in (and unless the typed text already parses
    to the same number), disabled state, slider `--p` + aria-valuetext, live `[data-ux-out]` (slider output / Number hint);
  - pickers → `uxSyncPicker` (6590-6598): `aria-checked` + disabled in place, Segmented `--i` so the thumb slides;
  - everything else → re-render and swap only if markup differs from the cached last markup (`uxLast`, 6387, 6391).
- `uxSwap` (6558-6563) keeps focus: re-focuses the same `data-args` control or the first enabled control in the new node.
- Full repaint (`uxRepaint`, 6599-6603): gallery swaps the whole card; chat calls `patchMessage` (whole message, 3864-3870).
  Used for why/unlock/asText/reset/send.
- Timer: a global 250ms interval updates clock text and ring offset in place; on 0 → status done, vibrate, refresh (6683-6692).
- Input events (6695-6705): `input` on `[data-ux-bind]` (num kind parsed with `uxNumIn`); `change` for selects; ignored when sent.

## 6. Chart rules (6458-6530; header 2383-2386)

- Data: `labels` and each `series[].data` may be arrays or objects keyed by the value of state `by` (period switch without asking
  the agent again). Null points allowed.
- Scale `uxNice(lo,hi,3)`: step from {1,2,2.5,5,10}×10^k, ~3 intervals; bars or `zero:true` include 0.
- SVG viewBox W=320, H=height||150; padding top 10, bottom 22, left 42, right 46 (line, room for end value) or 6 (bar).
- Grid: hairline `--line` lines with y tick labels (≤12), zero line `--line-strong` for bars. Ticks compact "12.5K" when |max|≥10,000;
  `unit` prefix; negative with "−".
- X labels: all when N≤7, else 5 evenly spaced; line end labels anchored start/end; bars centred.
- Line: 2px stroke (round joins, non-scaling), single series gets a 10% opacity area wash (unless `area:false`), end dot r=4 with a
  2px ring in the card colour, value label at the line end (`fmt`), omitted when two series ends are <13px apart.
- Bars: group width ≤ min(24·n + 2·(n−1), 66% of slot); each bar rounded 4px on the data end only (path with quadratic corners;
  negative bars round at the bottom); `polar:true` colours by sign `--ux-pos`/`--ux-neg`.
- Colours: single series `--ux-s0` (= accent ink); multi series slots `--ux-s1..s3`; legend only for 2+ series.
- Interaction: crosshair line + tooltip (glass pop, `title` + values; series swatches when multi) on pointerdown/move; touch hides
  1.6s after leaving; keyboard on the focused svg: → next, ← previous (or last), Home, End, Esc; focusout hides; bars not hovered
  fade to .4. SVG is `direction:ltr`, `touch-action:pan-y`.
- Accessibility: svg role=img tabindex=0, aria-label «title: firstLabel firstValue ← lastLabel lastValue. القيم في عرض الجدول.»
- «عرض كجدول» / «عرض كرسم» toggle (table/chart icon, aria-pressed) per chart path, stored in `ui.view`; table = labels × series
  with `fmt`.
- Empty data: «لا توجد بيانات.».

## 7. Decision rules (ab_agentui): when an interface, when text

System-prompt rule (6708-6714, header 2360-2365):
"answer in text by default — explanations, opinions, short facts, a requested table or code. Send an interface only when you will
act on the answer: numbers to try (calculator), several fields to fill (short form), a day and time to pick, options to compare and
choose, a plan to tick off, a series to explore (chart + period switch), or practice (quiz, timer). Every interface carries `why`
in plain words, a markdown `fallback`, and send-actions with an intent the agent handles with its own tools." Header adds:
«اكتب/اشرح/لخّص» → text; "Intent beats topic."

Mock implementation (keywords):
- `UX_TEXT_ONLY` (6716): جدول/كود/فقرة/اكتب/اشرح/شرح/لخص/ملخص/نص/مقال/قصيدة/بريد, `code`, `json` → text, whatever the topic.
- `uxPlan` (6874-6879): no interface for empty text, commands, non-text kinds (voice…), uiev messages, text-only words; «سؤال»
  without «اختب/امتحان» → no interface (keeps the built-in question card).
- Precedence `UX_MATCH = quiz, focus, alert, schedule, choose, plan, risk, perf` (6873): "what you ask to do outranks what it is
  about: «اختبرني في إدارة المخاطر» is a quiz, not a calculator" (6872).
- Global precedence in `agentAnswer` (3997-4003): paused agent text → group follow-ups → uiev answer → `agentIntent` (supervision,
  agent creation, ORDER sentences → approval card / grant path, out-of-scope one-liner) → `uxPlan` → other text. So buy/sell sentences
  never produce a generated UI (8543, 8570-8587).
- With genui off: the same plan answers with `fallback` text (6881-6884).

## 8. Gallery «معرض الواجهات» (route `genui`) and the eight kinds

Route: dev-only (`isDev()` = S.dev after 7 taps on the version; 3671, 8623-8625; also listed in the dev group of settings 5660 and
as a row under «الواجهات التفاعلية» in «تجربة المحادثة» with «8 أنواع» 5758). Title «معرض الواجهات» (3016). Page (6956-6962):
intro «يرسل الوكيل واجهة تفاعلية عندما تكون أوضح من النص، ويذكر السبب تحتها. هذه كل الأنواع؛ جرّبها هنا، أو اطلبها بكلماتك في
أي محادثة.»; when genui is off a note «العناصر التفاعلية متوقفة الآن، فيرد الوكيل بنص. فعّلها من «تجربة المحادثة».». Each recipe:
`<section class="ux-demo">` header (kind icon + Arabic kind) + chip «جرّب في محادثة» + the trigger sentence in «» + a live card
(state kept in `uxGallery`, never saved). «جرّب في محادثة» (`uxTry`, 6963-6967): puts the sample into the composer draft of the
first active agent, opens that chat, focuses the end of the text. Gallery sends do not message anyone (toast instead).

| id | kind (Arabic) | icon | trigger sentence (sample) | test regex (6744-6870) | content | send intent |
|---|---|---|---|---|---|---|
| risk | حاسبة تفاعلية | calc | «احسب حجم الصفقة المناسب لحسابي» | حجم الصفقة/لوت/عقد/مركز · إدارة المخاطر · حاسبة · احسب · كم لوت | Slider capital 500-50,000 · Segmented risk 0.5/1/2/3% · Slider stop $1-30 · Grid Stat lot / max loss · warn notes (risk≥3, lot<0.01) · Table "لو غيّرت نسبة المخاطرة" each [0.5,1,2,3] highlight current · «اعتمد هذا الحجم» / «إعادة الضبط» | risk.apply {lot, amount, risk, capital, stop} |
| alert | نموذج قصير | bell | «نبّهني إذا صعد الذهب فوق 2400» | تنبيه · نبهني · أبلغني · أعلمني | prefilled from the sentence (asset, direction, number); Segmented asset (also resets price) · Segmented above/below · Number price (required, hint «الآن …») · distance text / "already true" warn · Chips multi channel (داخل التطبيق / إشعار الهاتف / مكالمة الوكيل) · «إنشاء التنبيه» | alert.create → receipt «التنبيه فعّال» with «عرض التنبيهات» (go tasks) and «إيقاف التنبيه» (send alert.off) |
| schedule | منتقي موعد | calendar | «حدّد موعدًا لمراجعة الصفقات» | موعد · احجز · ذكرني · جدولة · اجتماع | Days 7 · Chips time 08-21 · Segmented once/daily/weekly · Input topic (required) · Note summary · «تأكيد الموعد» | schedule.create → receipt «الموعد مثبّت» |
| perf | رسم بياني تفاعلي | chart | «كيف كان أداء الحساب هذا الأسبوع؟» | أداء · إحصائيات · تقرير · رسم بياني · مخطط · أرباح · خسائر · نتائج | Segmented week/month/year · Grid 3 Stats · Chart line «الرصيد» by range · Chart bar polar «الربح والخسارة» · «اشرح أفضل وأسوأ {unit}» (lock:false) | perf.explain (text answer) |
| choose | بطاقات اختيار | cards | «ساعدني أختار أسلوب متابعة مناسب» | قارن · مقارنة · أيهما · ساعدني أختار · اختر لي · خيارات · أسلوب · باقة | Choice هادئ / متوازن (badge مُقترح) / نشط with points · «ابدأ بأسلوب «…»» | plan.choose → a new checklist interface |
| plan | قائمة قابلة للتأشير | check | «ضع لي خطة لهذا الأسبوع» | خطة · خطوات · قائمة · checklist · جهز · رتب | Progress «{n} من {total} مكتملة» · Checklist · Celebrate when all · good note · «حوّل المتبقي إلى مهام» + «مسح التأشير» | plan.tasks → tasks created + receipt «أُضيفت إلى المهام» |
| quiz | اختبار تفاعلي | target | «اختبرني في إدارة المخاطر» | اختبرني · اختبار · امتحان · تعلم · علمني · دربني | 3 questions with explain · Celebrate at 3/3 · score note · «اشرح أخطائي» (lock:false) / «أعد الاختبار» | quiz.review (text) |
| focus | مؤقت حيّ | timer | «ابدأ جلسة تركيز 25 دقيقة» | مؤقت · تركيز · ركز · بومودورو · pomodoro | Segmented 15/25/50/(asked) minutes while idle · Timer · Celebrate on done · «سجّل الجلسة» | focus.log (activity log entry) |

Each recipe has a `why` (shown under «لماذا هذه الواجهة؟») and a markdown `fallback`; quoted examples:
- risk why: «الحجم الصحيح يتغيّر مع رأس المال ونسبة المخاطرة ومسافة الوقف. حاسبة تحدّث النتيجة مع كل تغيير أوضح من جدول طويل بكل الاحتمالات.» (6748)
- alert why: «التنبيه يحتاج أصلًا واتجاهًا وسعرًا وطريقة إشعار. نموذج قصير يجمعها مرة واحدة ويمنع الأخطاء، بدل أربعة أسئلة متتالية.» (6772)
- schedule why (6790), perf why (6805), choose why (6826), plan why (6730), quiz why (6843), focus why (6863) follow the same
  pattern: what the request needs → why this interface is clearer than text.

## 9. Visual style (CSS 1311-1539, 2230-2237; tokens 12-50)

Message: `.msg.k-ui .msg-line` width min(440px,94%); ≥900px min(460px,78%) (1312-1313). Bubble `.bubble.ui-bubble` padding
8 8 6; lead text/steps get 4px inline margin (1314-1316). Bubble is `.wide` (flex:1, 372).

Card `.ux` (1317-1321): margin 8 0 2; radius 16px (= --r-md); background `--ux-card` = mix(text 3.5%, bubble-in) dark /
mix(text 2%, #fff) light; 1px `--line` border; text-align start; line-height 1.5; text selectable on hover devices.
Local tokens: `--ux-raise` (text 5% / 3.5% light) for inner panels/stats/notes/options; `--ux-track` (text 9% / #E6E2D8 light);
`--ux-thumb` (#3A3D46 / #fff); series `--ux-s0`=accent-ink, `--ux-s1` #3987e5 / #2a78d6, `--ux-s2` #d95926 / #eb6834,
`--ux-s3` #199e70 / #1baf7a; `--ux-pos`=accent-ink; `--ux-neg` #e66767 / #e34948.
Global tokens used: `--accent #22E3A8` (ink #22E3A8 dark, #087A57 light), `--on-accent #05271c`, `--primary/--on-primary`,
`--line #23252C`/`#E3DFD5`, `--line-strong #343741`/`#CFCAC0`, `--muted #8B919E`/`#5D6270`, `--faint #6A707C`/`#868B97`,
`--amber #F2C46B`/`#9a6a00`, `--red #ff8a91`/`#c0392b`, `--hover`, `--glass-pop`, `--glass-line`, `--blur`, `--float-shadow`,
`--hi`, `--ease cubic-bezier(.22,1,.36,1)`, `--spring cubic-bezier(.3,1.35,.5,1)`, `--fs-xs 12 / sm 14 / md 16`, `--r-*`.

Head (1323-1328): flex gap 10, padding 12 12 2; icon tile 34×34 radius 11 accent 14% tint, accent-ink icon 19px; title 15/700
lh 1.35; sub 12 muted. Body (1329): grid gap 14, padding 10 12 12. Footer (1335-1343): flex wrap gap 6×12, padding 7 12, top
hairline, 12px; sent line accent-ink 600; cut line muted; «تعديل» underlined link; why button muted, end-aligned (margin-inline-start
auto), sparkle accent-ink, text colour when expanded; why paragraph muted 13px lh 1.65, padding 0 12 12, fades in.
Inner surfaces radius 12 (panels, notes, stats, inputs, segmented, picks list, days), options 14, segmented thumb/buttons 9, chart
view button 9, tooltip 10, badges pill. Gaps: col 12, row/grid 8, field 6.
Text: `.ux-title` 16/700; `.ux-text` 14 lh 1.6 (sm 13); `.ux-badge` 11/700 pill raise (accent/good: accent 16% tint).
Notes (1363-1370): 13px, padding 10 12, icon 17 muted; warn = amber 13% tint + amber icon; good = accent 12% + accent-ink; bad = red 12%.
KeyValue: rows padding 8 0 with hairlines, label muted, value 600 end. Stat: padding 10 12 radius 12 raise, label 12 muted,
value 19/700 letter-spacing −.2, accent tone colours value; trend up accent-ink, down amber.
Progress: 13px header muted, value text tabular; track 8px pill accent 18% tint, fill accent, width transition .4s ease.
Fields (1393-1416): label row 13/500 muted with output 14/700 tabular (text colour); input box height 44, padding 0 12, radius 12,
bg `--bg` dark / #fff light, 1px line; focus border line-strong + 3px accent 22% ring; invalid border red; number input LTR
end-aligned tabular; affix muted 14.
Slider (1397-1407): 28px hit area, 6px track filled with accent from the start side (RTL gradient to left; LTR to right) by `--p`,
22px white gradient thumb with shadow, scale 1.12 while active, focus ring 3px bg + 5px text.
Segmented (1417-1421): track bg `--ux-track`, padding 3, radius 12; sliding thumb `--ux-thumb` radius 9 shadow, moves with
inset-inline-start .28s ease; buttons min-height 36, 13/600, muted → text when checked.
Choice (1422-1433): options padding 12 radius 14, 1.5px border, raise bg; checked = accent border + accent 8% tint; radio 18px
ring 2px line-strong → 5.5px accent; title 15/700; sub 13 muted indented 26px; points list with accent-ink check 14px.
Chips (2230-2237): bordered list radius 12 with hairline rows min-height 42, padding 8 12, 14px; checked 600 + accent radio/box.
Switch row (1434-1436) uses global `.switch` 48×28 pill, 22px knob springs, accent when on (141-144).
Checklist (1437-1447): rows padding 10 2 with hairlines; 22px box radius 7, 2px line-strong; checked accent fill + on-accent check;
done label muted line-through.
Days (1448-1454): horizontal scroll, no scrollbar; buttons min-width 54, padding 7 6, radius 12, raise + line; weekday 11 muted,
date 17/700 tabular; selected = `--primary` bg + `--on-primary` text (ivory dark / charcoal light), not accent.
Buttons inside cards: `.btn sm` min-height 40, pill radius (global `.btn` 118-130), primary = ivory gradient (dark) / charcoal
(light), outline transparent with line-strong border; `.ux-full` width 100%.
Table (1459-1463 + `.md-table` 1147-1151): caption 13/500 muted; numeric columns end/tabular; highlighted row accent 11% tint 700.
Chart (1464-1494): header min-height 30, title 13/600 muted; tick labels 10px faint tabular; end value 10.5/600 text; crosshair
muted .55; tooltip glass pop + blur + float shadow, 12px; legend 12 muted with 10px rounded swatches.
Quiz (1496-1515): question number 22px circle track bg (right = accent/on-accent, wrong = red 70%/white); options min-height 42
radius 12 1.5px border raise; right = accent border + 11% tint; wrong = red 65% border + 9% tint; disabled .5; explanation 13 muted.
Timer (1516-1525): 140px ring, 8px track `--ux-track`, accent arc round cap, dashoffset transition .5s linear; clock 30/700 tabular
LTR; status 12 muted; done arc greys.
Motion: block enter `ux-in` .38s ease (8px rise), why/quiz explanation .25s; skeleton shimmer 1.2s (`sk`); confetti 26 pieces
(7×11px, radius 2, s1-s3 colours) .9-1.5s cubic-bezier(.2,.7,.35,1), removed after 1.7s (1527-1529, 6614); glow ring 2px accent
1.2s under reduced motion (1322, 6612). `prefers-reduced-motion` turns off block/why/explain animations, thumb/progress/ring
transitions and skeleton shimmer (1539).
Gallery (1531-1538): section margin 4 0 26; header kind 700 with accent-ink icon 19; chip 34px 13px; sample 13 muted; demo card
uses `--surface` with `--hi` + 1px shadow.
RTL: text-align start / inset-inline everywhere; numbers, clock, chart and number inputs forced LTR; slider fill direction swaps
for `html[dir=ltr]`; Arabic number words via `arCount`; dates «ar-u-nu-latn» (Arabic words, Latin digits).

## 10. Preferences and surrounding UX

- «تجربة المحادثة» → section «الواجهات التفاعلية» (5758): «عناصر تفاعلية في الردود» — «حاسبات ونماذج ورسوم واختيارات يرسلها
  الوكيل عندما تكون أوضح من النص» (`genui`, default on); «سبب اختيار الواجهة» — «زر «لماذا هذه الواجهة؟» يشرح قرار الوكيل»
  (`genuiWhy`, default on, disabled look when genui off); dev row «معرض الواجهات · 8 أنواع». Defaults 5748.
- genui off: new replies arrive as the fallback text; existing ui messages render their fallback (6552, 6881-6884).
- Message menu: «عرض كنص» (news icon) / «عرض الواجهة» (grid icon) only when genui is on (3885).
- Copy text («نسخ النص»): lead + fallback (6953, 9148). List previews / heads-up use the lead text (`snippet`, 3732-3736).
- Suggested reply after a ui message: «اشرح لي النتيجة» (7599).
- Quote of a ui message in a reply: sparkle icon + card title (3752).

## 11. Cross-check with ref37.notes.txt (GENERATIVE UI, notes lines 83-118)

The notes text equals the file header (2354-2388). Differences found against the code:
1. Function list omits `@Floor @Ceil @Abs @Sqrt` (code 6268).
2. "errors render "—"": in the code a failing template expression renders "" (6358); "—" appears only from number formatters on
   non-finite input and chart nulls (6264, 6470).
3. "fallback … used in notifications/copy": copy uses lead + fallback (6953); heads-up/list previews use the lead text only (3734).
4. The notes do not mention: `also` merge on options (6633), `lock:false`, Enter-to-submit (6707), the `go` whitelist contents
   (6657), receipts (6886), `UX_EVENT_STEPS`, the `asText` menu labels, dev-only gating of the gallery (8623-8625), the precedence
   of order sentences over genui (4002-4003).
Everything else (spec shape, components, actions, partial refresh, streaming, chart method, gallery) matches the code.

## 12. Against the binding documents (to carry into Lonora's version)

Binding: OWNER_DECISIONS.md Q27 (line 48), Q36 (57), Q23 (suggested reply never after cards), Q4/Q10/Q53 (channels),
Q54 + CAPABILITY_MAP 87/195 (gallery dev-only); MANDATE_CORRECTIONS.md D5 (15), D6 (16), §1 walls (21), §32 domain scope (52);
VISION.md "money moves only through one checked door" (13-14) and the one rule (20-23).

Aligned in the reference:
- No action can place, modify or approve a trade: actions are set/toggle/reset/copy/open(https)/go(whitelist)/send; `send` is only
  a user message the agent reads. Buy/sell sentences are routed before genui to the approval card / signed-grant path (8543,
  8570-8587).
- `why` on every interface + «لماذا هذه الواجهة؟» (Q27). `send{intent,data}` rendered as a quoted user message (Q27).
- Quiz and Timer exist as light personal tasks (Q27, D6).
- Code/JSON requests answer as text (6716) — consistent with Q36 (code blocks as explanation) and D5 (no code deliverable is a
  separate agent policy).
- Model output is data; no HTML; escaped strings; sandboxed expressions; https-only open; route whitelist.

Points that need a Lonora decision or adaptation (do not copy blindly):
1. `risk.apply` («اعتمد هذا الحجم», 6762, 6896): the mock answer «سأقترح هذا الحجم تلقائيًا، وأنبّهك قبل أي صفقة تتجاوز X%».
   "Risk per trade" is an account money limit in VISION (brakes list). Under Q27 the submit must stay non-financial: at most an
   agent preference/memory note; any account limit or grant change must go through the existing owner action / passkey cards.
2. `choose` styles and their checklists (6831-6833, 6725-6727) mention «مخاطرة 0.5%/1%/2%», «كل الإشارات بموافقتك», «تحديد حد خسارة
   يومي»: choosing a style must not change the trading ladder, grant or limits; those steps become tasks the owner completes through
   the normal cards.
3. `perf` uses demo numbers (6807-6821, «حساب تجريبي»). Real figures must come from broker-verified journal data (VISION
   "verified outcomes decide reality"); Lonora's `VisualDocument` already has `mode observed/example/estimate` (CAPABILITY_MAP 123).
4. Alert channels «إشعار الهاتف» / «مكالمة الوكيل» (6781): Q10 hides phone-notification settings until a push channel exists; Q53
   Lonora is the only owner channel. Offer only in-app (and call only once Phase 6 calls exist).
5. Focus timer sub «لن أرسل تنبيهات أثناءها» (6861): Q4 says critical / action_required items always show; wording must not promise
   to suppress them.
6. Suggested reply «اشرح لي النتيجة» after a ui message (7599) vs Q23 "never after cards": open question whether a generated
   interface counts as a card.
7. Gallery is dev-only in the reference and "out of production per the owner" (CAPABILITY_MAP 87, 195; Q54 dev-only list).
8. Security: the text of a `send` is model-authored (a template in the spec) but arrives as the owner's own message. In Lonora,
   checks that rely on "the owner's own words" (Full-delegation preselect, model-choice override, supervision-by-sentence,
   agent-creation-by-sentence) must not accept submit messages; the submit must carry a structured origin (e.g. `uiev`) that those
   detectors exclude, and `intent`/`data` must be validated server-side against a non-financial allow-list.
9. `Money()` always prints "$" (6272); multi-currency accounts need the account currency.

## 13. Lonora counterparts already in the repo (orientation only, not read in depth)

From CAPABILITY_MAP.md line 123 and 252 (WP-G) and file checks:
- `packages/core/src/visual-response.ts` (exists, 29 KB): validate/evaluate/updateVisualState, no eval.
- `packages/contracts/src/lonora_contracts/visual_response.py`, `packages/agent-runtime/src/lonora_agent/visual_response.py` (exist).
- `apps/web/src/components/visual/RichResponse.tsx` (exists).
- `resources/prompts/native_visual_response.md` named in the map: NOT found at that path.
- Map of reference → `VisualNodeKind` and the listed gaps (Markdown node, Days, Quiz, Timer, Celebrate, segmented, multi chips,
  `why`, calc/derived state, `send` with data + lock/edit, `go` whitelist, chart period/table toggle) are in CAPABILITY_MAP line 123.
