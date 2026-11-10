# Open Intelligent UI (OIU): how it works

Read-only study notes. Source: `thesysdev/open-intelligent-ui`, MIT, clone HEAD
`9df2e64bc44282f6305a47eb6dbbbd8f28139138` (2026-11-06, "Size the chat to the body, not the viewport (#54)"),
shallow clone, no node_modules. Lonora's `THIRD_PARTY_NOTICES.md` cites an earlier OIU revision
`16ef26475999e3a021a50b1607a03717c0721255` (not present in this shallow clone).

Path conventions in these notes:
- `OIU/...` = `https://github.com/thesysdev/open-intelligent-ui (commit 9df2e64) /...`
- `PKG/...` = npm tarballs already extracted (by a sibling step) under
  `docs/ui-reference/genui-study/pkgs/`
  (`x-lang-core-1.0.0`, `x-react-lang-1.0.0`, `x-react-ui-0.18.1`, `x-react-headless-0.18.0`), versions pinned by
  `OIU/package-lock.json`. I recovered their TypeScript sources from the published source maps into
  `.../work/genui/src-lang-core/src`, `.../src-react-lang/src`, `.../src-react-headless/src`
  (react-ui ships `src/` itself). These are read as data only; nothing was executed.

OIU itself is a thin app: almost all language/runtime behaviour (parser, evaluator, store, actions,
message protocol, chat shell) lives in the `@openuidev/*` packages. OIU contributes: the component
library (`OIU/src/lib/library.ts`, `OIU/src/lib/components/*`), 59 functions (`OIU/src/lib/functions/*`),
one custom action (`OIU/src/lib/actions.ts`), prompt rules and worked examples
(`OIU/src/lib/prompt-options.ts`), the server route (`OIU/src/lib/chat-handler.ts`), image/route proxies
(`OIU/src/app/api/*`), localStorage persistence (`OIU/src/lib/chat-storage.tsx`) and the gallery/bench.

---------------------------------------------------------------------------------------------------

## 1. Top-level shape

- Next.js 16 app (`OIU/package.json`): deps `@openuidev/lang-core ^1.0.0`, `@openuidev/react-lang ^1.0.0`,
  `@openuidev/react-ui ^0.18.1`, `openai ^6.22`, `zod ^4`, `maplibre-gl ^6.13`, `katex`, `lucide-react`,
  `chess.js`, `posthog-js`. Node >= 24. `allowScripts: { "@openuidev/lang-core": false }` blocks lang-core's
  postinstall (which is opt-out PostHog install telemetry, see §13).
- Routes:
  - `/` chat (`OIU/src/app/page.tsx`) → POST `/api/chat` (`OIU/src/app/api/chat/route.ts`).
  - `/chess` (`OIU/src/app/chess/page.tsx`, `/api/chess`), `/clash` (`OIU/src/app/clash/page.tsx`, `/api/clash`):
    same handler with extended libraries (domain-extension pattern, §12).
  - `/gallery` dev-only (`OIU/src/app/gallery/page.tsx` → `notFound()` in production).
  - `/preview` dev-only, renders one program from `window.__OPENUI_PROGRAM__` (`OIU/src/app/preview/*`).
  - `/api/wiki`, `/api/image-search`, `/api/street-route` (server proxies with caches).
- `OIU/AGENTS.md` only points to an external skill (`thesysdev/skills/.../openui/SKILL.md`); not in the clone,
  not fetched. `OIU/docs/` holds only `openui-chatgpt-comparison.mp4/.jpg` (side-by-side video), no text docs.

## 2. Generation path (server)

`OIU/src/app/api/chat/route.ts`: `export const maxDuration = 300; export const POST = createChatHandler(spec, promptOptions)`
with `spec = OIU/src/generated/spec.json` (LibrarySpec) and `promptOptions` from `OIU/src/lib/prompt-options.ts`.
`/api/chess` and `/api/clash` are identical with `chess-spec.json`/`chessPromptOptions` and
`coach-spec.json`/`coachPromptOptions`.

`OIU/src/lib/chat-handler.ts` (`createChatHandler`):

1. Backend selection (module load, env):
   - `LLM_BASE_URL` set → **direct** "LLM": `apiKey=LLM_API_KEY`, `model=LLM_MODEL` (missing model → 500
     "LLM_MODEL is not set…").
   - else `MODEL_PROVIDER=ollama` or `OLLAMA_MODEL` → **direct** "Ollama": base `OLLAMA_BASE_URL` default
     `http://localhost:11434/v1`, key `"ollama"`, model default `qwen3.8:27b`.
   - else **cloud** "OpenUI Gateway": `THESYS_MODEL` default `openai/gpt-6.1-sol`, `THESYS_BASE_URL` default
     `https://api.thesys.dev/v1/embed`, `THESYS_API_KEY` required (missing → 500 with hint).
   - `OpenAI` client created lazily on first request (app builds without keys).
2. Instructions (built once per handler):
   - direct: `generateSystemPrompt({ library: spec, promptOptions })` → the full OpenUI 1.0 prompt text
     (~34 KB; README says ~8,000 tokens; Ollama users must raise context to 32k).
   - cloud: `generateSystemPrompt({ cloud: true, library: spec, promptOptions: { examples, additionalRules } })`.
     In `src-lang-core/src/parser/cloud-config.ts` this does **not** build a prompt: it emits
     `]]>openui:config\n{"chatLibrary": <spec minus "components">, "systemPromptOptions": {examples, additionalRules}}`.
     Gateway builds the prompt from the library schema server-side and **validates and corrects** the
     streamed OpenUI Lang (README "How it works"; chat-handler header comment). Only `examples`, `preamble`,
     `additionalRules` cross the wire (`CloudPromptOptions`); `bindings: true` is dropped (Cloud's assembler
     ignores flags). Library is validated by `validateChatLibrary` (throws on invalid).
   - Direct path has **no correction step**: output is rendered as written (README "Use any OpenAI-compatible API").
3. Request validation (per POST):
   - `hasAllowedOrigin(req)` (`OIU/src/lib/same-origin.ts`): Origin header required, must equal request origin,
     `x-forwarded-proto://x-forwarded-host|host`, or an entry of `ALLOWED_ORIGINS`; else 403 "Not allowed."
     (only chat routes check this; `/api/wiki`, `/api/image-search`, `/api/street-route` do not).
   - `content-type` must include `application/json` (415); body ≤ 1,000,000 bytes (413).
   - `toInput(messages)`: keep only `role` `user|assistant`; content string or array of parts joined by `.text`
     (images/files dropped); last 60 items (`MAX_ITEMS`); empty → 400 "messages must be a non-empty array".
     System/tool messages from the browser are discarded ("trusted instructions never come from the browser").
     Assistant/user **text is forwarded verbatim, including `]]>openui:content` / `]]>openui:context` marker
     lines** (that is how page state and button context reach the model, §6).
4. Model call:
   - cloud: `client.responses.create({ model, instructions, input, store: false, max_output_tokens: 16000,
     reasoning: { effort } (if set), stream: true }, { signal: req.signal })`.
   - direct: `client.chat.completions.create({ model, messages: [{role:"system", content: instructions}, ...],
     stream: true, reasoning_effort: effort, reasoning: { effort } })` (both keys: OpenAI-style and OpenRouter);
     no max tokens on this path. `asResponsesEvents` converts chunks to
     `response.output_item.added` → `response.output_text.delta`* → `response.output_text.done` →
     `response.completed`, so the browser stream is identical for both paths.
   - Upstream failure at create → JSON `{error:{message:"<backend name>: <msg>"}}` with `e.status ?? 502`.
5. Reasoning effort: `LLM_REASONING_EFFORT` default `"low"`; `"default"` or `""` sends none. Comment: low is
   "about five times sooner with the same quality of UI".
6. No tools are sent on either path (no search tool): `SearchImage` resolves photos client-side (§9).
7. Relay as SSE (`text/event-stream`, `no-cache, no-transform`): each event `data: <json>\n\n`; deletes
   `response.instructions` and `response.safety_identifier` from events carrying `response` (created /
   in_progress / completed repeat ~58 KB prompt). On `response.incomplete` (cap hit) appends
   `{type:"error", message:"The answer was cut off. Try a shorter request."}`; a thrown stream error becomes
   `{type:"error", message}`. Browser aborts propagate via `req.signal`.

### Browser side of the call
`OIU/src/app/page.tsx`: `fetchLLM({ url: withBase("/api/chat"), streamAdapter: openAIResponsesAdapter(),
messageFormat: openAIConversationMessageFormat })`. `PKG/.../src-react-headless/src/adapters/fetchLLM.ts` POSTs
`{ tools: [], context: [], threadId, runId, messages: messageFormat.toApi(messages) }`;
`openai-conversation-message-format.ts` maps user/assistant messages to Responses input items (assistant text as
`{role:"assistant", content, type:"message"}`). The adapter (`stream/adapters/openai-responses.ts`) handles
`response.output_text.delta/done`, `error`, `response.failed`.

`AgentInterface` (`PKG/x-react-ui-0.18.1/package/src/components/AgentInterface/Thread.tsx` ~L402): while a turn is
live, the last segment counts as the "answer" only once `hasLangSyntax` sees an unfenced `root =` line or an
```` ```openui-lang ```` fence (`src/utils/messages.ts`); before that, text is shown as a thinking/timeline row.

## 3. The system prompt

Generated by `generatePrompt` (`src-lang-core/src/parser/prompt.ts` L621-725). Order of sections:
preamble → syntax rules → component signatures (by group, with group notes) → built-in + library functions →
Action section → (Query/Mutation, filters, tool workflow only when tools) → "Hoisting & Streaming" →
`## Examples` → (edit/inline mode, unused) → Important Rules + Final Verification → `additionalRules` as `- ` bullets.
Reference copy: `OIU/src/generated/system-prompt.txt` (stale, see §14).

Key text (from `OIU/src/generated/system-prompt.txt`):
- Preamble: "You are an AI assistant that responds using openui-lang… Your ENTIRE response must be valid
  openui-lang code — no markdown, no explanations, just openui-lang."
- Syntax rules 1-16: one statement per line `identifier = Expression`; `root = Col(...)` entry; strings,
  numbers, booleans, null, arrays, objects, component calls; references for readability; every variable except
  root must be referenced (unreferenced are dropped); **positional args only** (no `name:` syntax); trailing
  optionals omitted; `$varName = default` state, components marked `$binding` read/write it, undeclared `$vars`
  auto-created as null; `+` concat; dot access (plucks over arrays); index access; `+ - * / %`;
  `== != > < >= <=`; `&& || !`; ternary; parentheses; double-quoted strings with backslash escapes.
- Signatures, e.g. `Slider(value: $binding<number>, min: number, max: number, step?: number, label?: string,
  unit?: string, marks?: {value: number, label: string}[]) — …`. Props typed `ActionExpression` take one
  `@step` or `Action([@steps…])`.
- Functions: "These are the ONLY functions available — do NOT invent new ones." + "Do NOT hardcode computed
  values." + composition examples + the **@Each rule** (loop var only inside the inline template; WRONG/CORRECT
  example).
- Actions: steps `@ToAssistant(message, context?)`, `@OpenUrl(url)`, `@Set($var, value)`, `@Reset($var…)`,
  `@CopyToClipboard(text)`; "Buttons without an action automatically send their label to the assistant".
- Hoisting & Streaming (CRITICAL): references may precede definitions; the output is re-parsed on every chunk;
  recommended order: `root` first → `$variable` declarations → component definitions → data values last.
- Final Verification: root first line; every referenced name defined and every defined name reachable;
  every `$binding` used.

### Prompt options (`OIU/src/lib/prompt-options.ts`)
`promptOptions = { bindings: true, additionalRules: rules (18), examples: [Example 1, 2, 3] }`.
`dashboardPromptOptions = { ...promptOptions, tools: demoToolSpecs, toolExamples: [Example 4 dashboard],
additionalRules: [...rules, Query/@Filter/@Between rule] }` (used only by bench/gallery, not by `/api/chat`).

The 18 rules (L52-71), paraphrased tightly:
1. Compose like a page: Title, short Text, then a mix of blocks; `SearchImage` for every place/dish/product
   with a look ("the app finds the photo, so never say you cannot show photos"); Row/Grid/Carousel side by side;
   Badge rows for facts; Card only to group; Popover for an aside.
2. Spacing system, three nesting tiers: inner (gap 1-2 = 4-8px), group (gap 3-4 = 12-16px), section (24px).
   Leave gap unset on root Col and card contents (the app applies tiers); set gap only on Row/Grid; never a
   gap larger than section.
3. Media row: `Row([Box([SearchImage(q, 1.33)]), Col([Title(…,"md"), Row([Badge…],1,null,null,true),
   Text(…,"sm")],2)], 4, "start")`; app sizes the photo to a third of the row (≤200px). Facts are Badges.
4. SearchImage query names the exact recognisable subject; if no photo would show it, no image.
5. Compact cards: Title "md" (never lg/xl in a Card), Text "sm", ≤1 short paragraph, facts as Badges or
   label/value rows (Caption, Spacer, Text); no bold-lead prose; cards in a Grid share block order and image
   ratio (worked `Card([...])` example).
6. **Working tool** whenever numbers, choices, lists, steps, a game or exploration: inputs/lists in `$vars`,
   everything shown computed with expressions and `@functions`, changed with `@Set`. Must work without another message.
7. `@ToAssistant` only for what the page cannot compute: a Form submit or a new request. Short, first person,
   like the user typing; form values travel with it, never repeat them in the message.
8. `$variable` defaults are literals, never expressions/`@calls`. Edit lists with `@Append/@Remove/@RemoveAt/@Update`;
   selections with `@Toggle/@Includes`.
9. `cond ? a : b` picks components; there is no `@If`; only listed functions.
10. Derive rows once with `@Each(list, "x", {...})`, reuse in `@Each`, Table, Chart, `@Sum(rows.field)`, `@Join`;
    `@Each(@Range(0, n), "i", …)` for series.
11. `@Random/@Pick/@Shuffle` only inside `@Set` (a click draws once; page stays still).
12. Medium per idea: Chart (numbers over time/categories), Svg (shapes, parts, movement), Map+MapMarker
    (places/routes), Table (comparisons), Flashcard/Celebration (learning, games), HtmlView only for a game/animation
    that needs a loop.
13. Draw with Svg whenever the user would otherwise picture it (assembly steps, knots, mechanisms, science diagrams,
    room/garden/board layouts, chords, clocks); ~240-wide viewBox, a dozen shapes in listed colors, SvgText labels,
    Line+Polygon arrows, `$vars` drive it.
14. `@Format` for money/percent/big numbers, `@Plural` for counts, `@FormatDate` for dates.
15. Relative dates from `@Today()`; `< > <= >=` compare numbers only, so order dates with `@DaysBetween(a,b) > 0`.
16. **To change a page from an earlier answer, keep its `$variable` names and start them from that answer's
    "context and form values"** (so typed/added/ticked state carries over; see §6).
17. Number inputs via `@Clamp(@Default($x, 1), 1, 50)` so 0/empty/negative cannot break the page.
18. Plain knowledge or safety question → Markdown text (+ SearchImage or Quote only where it helps).

Worked examples (exact programs in `prompt-options.ts`, also rendered and parse-tested in the gallery):
- Example 1 `exampleShoppingList`: `$guests` stepper (IconButton minus/plus with `@Clamp`), `lines = @Each(base, …)`
  rescaling quantities, Pressable checklist rows with `@Toggle($got, l.name)` and `@Includes`, copy button
  `@CopyToClipboard(@Join(@Each(lines, …), "\n"))`.
- Example 2 `exampleTrip`: Title, Text with `**bold**`, Carousel of SearchImages, Badge row, day rows via `@Each`
  (Box-wrapped SearchImage + Text with inline Icon), soft Card with `Form([RadioGroup($pace, …, "pills"),
  Button("Plan my trip", @ToAssistant("Tailor my Lisbon trip"))])`.
- Example 3 `exampleSteps`: four Svg drawings in a list, `drawings[$step]`, Back/Next with `@Clamp`, disabled at ends,
  `@Percent` progress, thumbnail Grid of Pressables `@Set($step, i)`.
- Example 4 `exampleDashboard` (dashboard prompt only): `orders = Query("get_orders", {days: 90}, {rows: []})`,
  SegmentedControl filter + `@Filter`, KPI Cards with `@Format(@Sum(rows.amount), "compact", 1, "USD")`,
  `@Bucket` line chart, `@GroupBy` donut, `@Top` Table.

## 4. Wire format: OpenUI Lang 1.0

Grammar/semantics (lexer/parser/materializer in `src-lang-core/src/parser/*`, evaluator in `src-lang-core/src/runtime/*`):
- **Statements**: `id = expr`, split at depth-0 newlines; newlines inside brackets are fine; a newline followed by
  `?` or `:` continues a ternary (`parser.ts` `scanNewCompleted`). Lines without `=` are silently skipped
  (`statements.ts` `split`), so stray prose lines are ignored.
- **Preprocess** (`parser.ts` L319-456): markdown fences are stripped (fence-aware of strings; unclosed fence while
  streaming takes the rest), `//` and `#` line comments removed outside strings.
- **Entry**: statement `root`; if missing, the first value statement whose call is the library root (`Col`) is used
  with a `no-root` warning (`pickEntry`). `root` may be a runtime expression (`root = $t ? A : B` →
  `rootExpression`).
- **References** are hoisted and **inlined** at parse time (`materialize.ts` `resolveRef`): a statement is a macro,
  not a memoised value; cycles → unresolved. Unknown refs → `null` and listed in `meta.unresolved`. Statements not
  reachable from root → not rendered, listed in `meta.orphaned` (state/Query/Mutation excluded).
- **Components are calls**: `Name(arg1, arg2, …)` positional → named props in the Zod object key order of
  `defineComponent` (`ParamDef[]`). Signatures printed from the schema (`signature.ts`); `tagSchemaId` names
  shared shapes (`Node`, `Color`, `Length`, `Radius`, `ActionExpression`).
- **State**: `$name = literal` declarations (`stateDeclarations`). Reading `$name` anywhere is a `StateRef`
  evaluated against the store each render.
- **Functions**: `@Name(args)`: 14 lang built-ins (`builtins.ts`: Count, First, Last, Sum, Avg, Min, Max, Sort,
  Filter, Round, Abs, Floor, Ceil, Each) plus library functions from `defineFunction` (OIU's 59, §8).
  `@Each(array, "x", template)` is **lazy**: the template is evaluated per item with `x` in scope (only inline).
  Library function args are validated against the Zod params; a bad literal is a parse error and the call is
  `null`; a bad runtime value (e.g. `$xs` holding a string) is a runtime error and `null`; a throw inside `fn` →
  `null`; an invalid optional arg is dropped so its default applies (tests:
  `OIU/src/lib/functions/__tests__/lists.test.ts` L141-153, `dates-data.test.ts` L158-175).
- **Actions**: steps `@Set($v, expr)`, `@Reset($a, $b…)`, `@ToAssistant(msg, ctx?)`, `@OpenUrl(url)`, `@Run(ref)`
  (Query/Mutation), custom `@CopyToClipboard(text)`; `Action([…])` sequences them. Evaluating an action prop yields
  an `ActionPlan {steps: […]}` (`types.ts` L213-231). `@Set` keeps the **value AST** and evaluates it at click time
  (so `@Random` inside `@Set` draws once per click, and references inside it are inlined then);
  custom-action params are evaluated when the prop is evaluated (each render), test
  `OIU/src/lib/functions/__tests__/patterns.test.ts` L49-52.
- **Query/Mutation** (only with tools in the prompt): `name = Query("tool", {args}, defaults, refreshSeconds)`;
  args may reference `$vars` (deps re-fetch); executed through the Renderer `toolProvider` (function map or MCP
  client). The main chat passes no `toolProvider` and no tools; only gallery/preview/bench use `demoTools`
  (`OIU/src/lib/demo-data.ts`: `get_orders`, `get_tickets`, `get_traffic`, deterministic per-day seeded data).

### Streaming and progressive rendering
- The Renderer receives the whole accumulated text on every chunk (`response` prop, `isStreaming`).
  `useOpenUIState` (`src-react-lang/src/hooks/useOpenUIState.ts`) calls
  `createStreamingParser(schema, root).set(program, !isStreaming)`.
- Stream parser (`parser.ts` L490-681): caches completed statements up to the last depth-0 newline (watermark);
  the trailing pending statement is **auto-closed** (`statements.ts` `autoClose`: closes an open string, then open
  `( [ {`) and parsed too. New statement ids render immediately; an id already completed is only replaced when the
  pending version no longer needs auto-closing. A `$name` at the very end that may still be growing (`$d` of
  `$dishes`) is skipped until complete. If the new text is not an append (regenerated), the parser resets.
- Every ElementNode carries `partial: true` while input was incomplete. Unresolved refs render as nothing, so the
  UI reveals top-down: root shell first (children null), then each child as its statement arrives, data last.
- Store defaults from a half-streamed `$x = …` are "pristine" and get replaced when the full declaration arrives;
  user-set and persisted values are never overwritten; keys are never deleted mid-stream (`runtime/store.ts`
  `initialize`).
- While streaming (`useIsStreaming()` = streaming || bundle incomplete): OIU's Button/IconButton/Pressable/Timer
  buttons are disabled; HtmlView shows "Preparing the interactive view…" and mounts its iframe only once complete;
  Map ignores `partial` markers and frames/draws the route only after the stream; Celebration ignores changes;
  SearchImage waits 500ms after the query stops changing.
- Errors: parser errors are not reported while streaming (`useOpenUIErrors` clears them); reported to `onError`
  after the stream ends. Render errors in a component are caught by `ElementErrorBoundary`
  (`src-react-lang/src/Renderer.tsx` L90-136) which keeps showing the **last good children** and recovers when new
  children arrive.

### Partial or invalid program (what the user sees)
From `src-lang-core/src/parser/materialize.ts` L330-424 and `validation.ts`:
- Unknown component → that node dropped (`null`), error `unknown-component` with the available list.
- Missing/null required prop → tries the schema default, else the **component is dropped**, error
  `missing-required`/`null-required` with the signature.
- Invalid value on an optional prop → prop removed (default applies), error `type-mismatch`.
- Extra positional args → ignored, `excess-args`.
- Unknown `@function` → `null`, `unknown-function`. `Query`/`Mutation` inline (not a statement) → `inline-reserved`.
- No usable entry → `no-root`; nothing renders. Unparseable text → `parse-failed`; nothing renders.
- In the chat nothing surfaces these errors to the user (`AgentInterface` passes no `onError`); the cloud path
  relies on Gateway correction; the gallery lists `onError` messages under each example
  (`OIU/src/app/gallery/gallery.tsx` L39-64); `/preview` exposes them on `window.__OPENUI_ERRORS__`.

## 5. State and interactivity

Store (`src-lang-core/src/runtime/store.ts`, `src-react-lang/src/hooks/useOpenUIState.ts`):
- One store per rendered message. `$vars` are top-level keys holding raw values. Inputs **not** bound to a `$var`
  store their value under `store[formName][fieldName] = {value, componentType}` (field name = label || statementId
  || React `useId`, `controls.tsx` `useFieldName`).
- Binding: input schemas wrap the value prop in `reactive(...)` (`controls.tsx`, `map.tsx`). When the arg is a
  `$var`, evaluation emits a `ReactiveAssign {target:"$var", expr:$value}`; `useStateField` →
  `resolveStateField` (`src-lang-core/src/runtime/state-field.ts`) reads `store.get($var)` and `setValue` writes it.
- Recompute: store changes trigger `useSyncExternalStore`, then `evaluateRoot` re-evaluates the **whole tree**
  (every expression reading the store recomputes). No dependency graph; statements are inlined expressions.
- `@Set` evaluates its value AST against current state; steps in `Action([...])` run in order and each sees earlier
  `@Set` results (patterns.test.ts L17-23). `@Reset` restores declared defaults (as pristine) for each target.
- Action dispatch (`useOpenUIState.triggerAction`, L326-447):
  - `run` (Query refresh / Mutation; halts plan if a mutation fails),
  - `continue_conversation` → `onAction({type:"continue_conversation", params:{context?}, humanFriendlyMessage:
    message, formState: getFormPayload(formName), formName})`,
  - `open_url` → `onAction({type:"open_url", params:{url}})`,
  - `custom_action` → `onAction({type:name, params})`,
  - `set`, `reset` → local store.
  - No action at all → `continue_conversation` with the label.
- OIU control semantics (`OIU/src/lib/components/controls.tsx`): `useRunAction` → with a plan, run it; with no
  plan, **Button sends its label** (sendLabel=true) while IconButton and Pressable do nothing (sendLabel=false).
  Pressable ignores clicks that land on an inner button/link/input. Form (`layout.tsx` L155-169) provides
  `FormNameContext = statementId ?? useId()` and prevents submit.
- `getFormPayload(formName)`: if the form has its own (unbound) field data → `{[formName]: data}`, else the **whole
  store snapshot** (all `$vars` + fields). OIU programs bind every input, so the whole page state travels.
- What `@ToAssistant` sends (`PKG/x-react-ui-0.18.1/package/src/components/OpenUIChat/utils/actionMessage.ts`):
  `runChatAction` → for `continue_conversation`, `processMessage({role:"user", content: buildActionUserMessage(e)})`:
  ```
  ]]>openui:content
  <message>
  ]]>openui:context
  ["User clicked: <message>", <formState or {}>, <context if given>]
  ```
  This new user turn goes to `/api/chat` as text (markers included), so the model sees the click, the full state
  snapshot and the hidden context. `open_url` → `window.open(url, "_blank")`; anything else → host `onAction`.
  OIU's `onAction` (`page.tsx` L56-58) runs `runLibraryAction` (only CopyToClipboard).
- User bubble (`GenUIUserMessage.tsx`): shows the message text plus a collapsible "Form data (N fields)" accordion
  listing entries that have a `{value}` wrapper (bound `$vars` are raw values and are not listed).
- `@OpenUrl` safety: `page.tsx` L24-30 overrides `window.open` so only `http(s)` opens, with
  `noopener,noreferrer`; `Link` and Markdown links render only `webUrl()` http(s) (`components/style.ts` L19-23).
- `@CopyToClipboard` (`OIU/src/lib/actions.ts`): `defineAction({name:"CopyToClipboard", params:{text}})`;
  handler `navigator.clipboard.writeText`, fallback hidden textarea + `document.execCommand("copy")`.

## 6. Persistence of what the user typed or ticked

- Message protocol (`src-lang-core/src/message.ts`): stored messages use marker lines
  `]]>openui:content[?attrs]`, `]]>openui:context` (JSON or text), `]]>openui:end`; last content wins; context
  after the winning content is parsed as JSON.
- On every user-driven store change, `onStateUpdate(snapshot)` fires (not during initialisation;
  `useOpenUIState` L268-278). `GenUIAssistantMessage.handleStateUpdate`
  (`PKG/x-react-ui-0.18.1/package/src/components/OpenUIChat/GenUIAssistantMessage.tsx` L46-58) rewrites the
  assistant message: `buildMessage({ content: program, attributes, context: [snapshot] })` → `updateMessage`.
- `SaveMessages` (`OIU/src/lib/chat-storage.tsx` L71-85) writes the open thread's messages to localStorage
  (`<prefix>:messages:<threadId>`) whenever messages change and no answer is streaming (no debounce).
  `localChatStorage(prefix)`: threads list at `<prefix>:threads` (newest first, max 50, overflow threads'
  messages deleted), title = first message collapsed to 60 chars. Prefixes: `oiu` (chat), `chess`, `coach`.
  Storage errors are swallowed.
- Reload: `readMessage(content)` → `context[0]` → `initialState` → `store.initialize(declaredDefaults, persisted)`;
  `$`-keys are bindings, other keys restore form state; persisted beats defaults.
- Next model turn: the assistant message (program + `]]>openui:context [snapshot]`) is sent back verbatim, which is
  what rule 16 calls "that answer's context and form values".

## 7. Component library (55 components)

`OIU/src/lib/library.ts`: `createLibrary({ root: "Col", components: baseComponents, functions, actions,
componentGroups })`; imports `theme.css`, `components.css`, `map/map.css`. Groups and notes (L46-67):
Layout (notes: gap/padding count 4px steps; Length px or CSS length; Radius sm/md/lg/xl/full/px; Color tokens
`ink muted faint surface info success warning danger purple pink chart1..chart6` or CSS color; status
backgrounds are soft tints), Text, Inputs (notes: first arg is the value; "Every input either changes something
shown on the page, or sits in a Form whose submit Button sends a short first-person @ToAssistant… No dead inputs."),
Media and data, Play, Drawing. Signatures below are from `OIU/src/generated/spec.json` (current).

Shared helpers (`OIU/src/lib/components/style.ts`): `UNSAFE_CSS` regex blocks `url( image( var( attr( env(
expression(` etc. and `\ ; { } < >` in model-written style values; `fg()` maps tokens to `var(--iui-*)`; `bg()`
maps status tokens to their `-soft` tints; `onColor()` picks #0d0d0d/#fff text on a raw hex/rgb background by
luminance (>0.36) and retunes `--iui-ink/muted/faint`; `space(n)=n*4px`; `size()` accepts px numbers or
`px % em rem vh vw fr auto`; `radius()` maps sm/md/lg/xl to tokens, full=999px. `glyph.tsx`: lucide icons via
`DynamicIcon`, names normalised (`MapPin`, `map_pin`, `map pin` → `map-pin`), unknown names render nothing.

Layout (`layout.tsx`, `extra.tsx`):
- `Col(children: Node[], gap?: number, align?)` — vertical; **without gap gets class `iui-flow`** (article spacing
  tiers, §10).
- `Row(children, gap?, align?, justify?, wrap?)` — horizontal, items centered, default gap 8px.
- `Box(children?, direction?: row|col, gap?, padding?, background?: Color, radius?, border?, width?: Length,
  height?: Length, flex?, align?, justify?, wrap?)` — flex container; radius clips; numeric width → `flex: 0 0 auto`;
  `flex` → `n 1 0%`.
- `Grid(children, columns? (1-12, default 2), minChildWidth?, gap? (default 12px))` — with minChildWidth uses
  `repeat(auto-fill, minmax(min(100%, max(minpx, (100% - gaps)/cols)), 1fr))` so columns drop on narrow screens.
- `Card(children, variant?: outline|soft, padding?, gap?)` — 20px padding, 1px border, radius xl; soft = surface fill.
- `Carousel(children, itemWidth? (80-640, default 240), gap?)` — scroll-snap track, items ≤85% width, prev/next
  frosted buttons when scrollable (hidden on touch).
- `Popover(trigger: string|Node[], content: string|Node[])` — button trigger; portal panel max 280px, flips up near
  the bottom, closes on outside pointerdown, Escape or scroll; copies ancestor `data-theme`.
- `Divider()`, `Spacer()`.
Text (`text.tsx`, `markdown.tsx`, `extra.tsx`):
- `Title(text, size? sm|md|lg|xl|2xl|3xl (default md), color?)` — `role=heading` with aria-level; inline markdown.
- `Text(text: string | Node[], size? xs|sm|md|lg, color?, weight? normal|medium|semibold, italic?, lineThrough?,
  tabularNums?, maxLines?)` — inline `**bold** *italic* ~~strike~~ \`code\` [link](https://…)`; a list mixes strings
  and inline components (Icon, Badge, Link, Math); `white-space: pre-line`.
- `Caption(text, color?)`, `Label(text)`, `Badge(text, color? neutral|info|success|warning|danger|purple|pink, icon?)`
  (pill, 26px min height, leading lucide icon), `Link(text, url)` (http(s) only, new tab, ↗ arrow; else plain text).
- `List(items: (string | ListItem)[], marker? bullet|number|none, timeline?)`, `ListItem(title, description?, marker?,
  children?)` — marker of 1-2 alphanumerics renders as an ink chip; longer markers (times) get a 76px text lane;
  timeline draws a connector line.
- `Markdown(text)` — own renderer, never injects HTML: paragraphs, `#`-`####` headings, `-`/`1.` lists, `>` quotes,
  fenced code, `---`, pipe tables.
- `Quote(text, cite?)`, `Code(code, language?)` (header with language or "code" and Copy/Copied button, no
  highlighting), `Math(tex, inline?)` (KaTeX `renderToString`, `trust:false`, `throwOnError:false`, inserted via
  `dangerouslySetInnerHTML`).
Inputs (`controls.tsx`; value args are `reactive` bindings):
- `Button(label, action?, variant? solid|outline|soft|ghost, color? primary|danger|success, size? sm|md|lg, icon?,
  disabled?, block?)` — pill; disabled while streaming; no action → sends label.
- `IconButton(icon, action?, label?, variant? outline|ghost|solid)` — 34px round; label is aria-label/title.
- `Pressable(children, action?, selected?, padding?, background?, radius?)` — `role=button`, Enter/Space, hover wash
  5%, press 8%, selected = hairline ring + check badge (rows with their own icon get no ring).
- `Input(value: $binding<string|number>, label?, type? text|number, placeholder?)` — number fields keep a text draft
  ("1." or "-") and commit parsed numbers; empty → null.
- `TextArea(value: $binding<string>, label?, placeholder?, rows? 2-20)`.
- `Select(value, options: (string | {value,label})[], label?, placeholder?)` — disabled "Choose…" option when value
  not in options.
- `SegmentedControl(value, options, block?)` — `role=radiogroup` pill buttons, for 2-4 choices.
- `Slider(value: $binding<number>, min, max, step?, label?, unit?, marks?)` — clamps value; readout prefix units
  `$€£¥₹`, else suffix; marks positioned by percentage; 24px track, 18px thumb.
- `Checkbox(checked: $binding<boolean>, label, lineThrough?)`.
- `RadioGroup(value, options: (string | {value,label,description?})[], label?, variant? list|pills|cards)`.
- `DatePicker(value: $binding<string>, label?, min?, max?)` — native date input, `YYYY-MM-DD` only.
- `Timer(seconds: $binding<number>, label?)` — countdown: Start/Pause/Resume and Reset; ticks every 1000ms writing
  the bound `$var` (so `$left == 0` reacts); Reset restores the value at first start; done = green time.
- `Form(children)` — groups fields; values go with any `@ToAssistant` inside.
Media and data (`media.tsx`, `table.tsx`, `chart.tsx`, `map/map.tsx`, `extra.tsx`):
- `SearchImage(query, aspectRatio?, radius?, fit? cover|contain)`, `Image(src, alt, aspectRatio?, radius?, fit?)` (§9).
- `Icon(name, size? sm|md|lg|xl = 14/18/24/32, color?)`.
- `Table(columns: string[], rows: any[][])` — cells may be components; a column whose non-empty cells are all numbers
  or amounts (`$1.2k`, `45%`, `n/a`/dash ignored) right-aligns with tabular nums; horizontal scroll wrapper.
- `Chart(type, data, x?, series?, format?, currency?, stacked?, height?)` (§11).
- `Map(markers: MapMarker[], route?, selected?: $binding<string>, height?)`, `MapMarker(label, lat, lng, category?,
  icon?)` (§9).
- `YouTube(video, title?)` — id or URL, `youtube-nocookie.com/embed/<id>` iframe with sandbox
  `allow-scripts allow-same-origin allow-presentation allow-popups`.
Play (`extra.tsx`):
- `Flashcard(front: string|Node[], back: string|Node[], hint?)` — button that flips (3D rotateY .45s); hint default
  "Tap to flip".
- `Celebration(when: boolean)` — on a false→true transition (not while streaming) bursts 70 confetti pieces in a
  body portal for 2.2s using chart colors; hidden under reduced motion.
Drawing (`svg.tsx`, `html-view.tsx`):
- `Svg(children, viewBox, width?, height?)` — viewBox validated (4 numbers, else `0 0 100 100`); without width it
  fills the column up to max(280px, 1.5×viewBox width).
- `G(children, transform?, opacity?)` — transform parsed per function with valid arg counts
  (translate 1-2, rotate 1|3, scale 1-2, skewX/Y 1, matrix 6), else dropped.
- `Circle`, `Ellipse`, `Rect(x,y,width,height,fill?,stroke?,strokeWidth?,opacity?,rx?)`, `Line`, `Path(d, …)` (d must
  match path-command charset), `Polyline(points, …)`, `Polygon(points, …)` (points charset-checked, <20000 chars),
  `SvgText(text, x, y, size?, fill?, anchor?, weight?)`. Filled shapes default to `currentColor`; stroke-only stays
  unfilled; colors via tokens.
- `HtmlView(html, height?, title?)` (§11).

## 8. The 59 functions (`OIU/src/lib/functions/*`)

`index.ts`: `functions = [...lists(19), ...numbers(9), ...text(12), ...colors(1), ...dates(8), ...data(10)]` = 59.
Pure except `@Random @Pick @Shuffle @Now` (and `@Today`). Bad args or a throw → `null` (runtime contract).
Helpers (`shared.ts`): `read(item, "a.b")` dot paths, `""` = item itself; `same()` deep equality where a number
equals its string; `finite()` throws on NaN/Infinity; `MAX_ITEMS = 10000` guards Range/Concat/Flatten/Split/Bucket.

Lists (`lists.ts`): `Append(list,item)`, `Prepend(list,item)`, `Concat(list,more)`, `Remove(list,field,value)`
(`""` compares items), `RemoveAt(list,index)` (negative from end), `Update(list,field,value,setField,setValue)`,
`Toggle(list,item)`, `Includes(list|text,item)`, `Find(list,field,value)`→item|null, `IndexOf(list,item)`,
`Take(list,n)` (negative = last n), `Slice(list|text,start,end?)`, `Unique(list)`, `Reverse(list)`,
`Range(start,end,step?)` (end excluded, fractional steps rounded to 12 digits), `Pick(list)`, `Shuffle(list)`,
`Flatten(list)` (one level), `Chunk(list,size)`.
Numbers (`numbers.ts`): `Pow`, `Sqrt` (null for negative), `Random(min,max,integer?)` (bounds swapped if reversed;
integer includes max), `Clamp(n,min,max)`, `Percent(part,total)` (0 when total 0), `Lerp(a,b,t)`,
`Allocate(total,weights,decimals?=2)` (largest-remainder so parts sum exactly), `Payment(principal,rate%,periods)`,
`Convert(value,from,to)` (length, mass, US volume, speed, area, c/f/k).
Text (`text.ts`, **locale hard-coded `en-US`**): `Format(value, kind? number|currency|percent|compact, decimals?,
currency?)` (unknown currency → USD; decimals cap, only currency pads), `Join(list,sep?=", ",field?)`,
`Plural(n,word,plural?)` (English "+s"), `Pad(value,length,char?="0")`, `Upper`, `Lower`, `Trim`, `Capitalize`,
`Split(text,sep?=",")` (trimmed, empties dropped), `Replace(text,find,replacement)` (all), `Duration(seconds,
style? short|clock)`, `Default(value?, fallback)` (null, "", NaN → fallback).
Colors (`colors.ts`): `MixColor(fromHex,toHex,t)`.
Dates (`dates.ts`): `Now()` ISO; `Today()` viewer zone `YYYY-MM-DD`; `FormatDate(date, style? date|short|long|
weekday|month|time|datetime|iso)` (en-US; date-only strings formatted in UTC so the day never shifts);
`AddDays`, `AddMonths` (clamped to month end), `DaysBetween`, `MonthsBetween` (whole months), `StartOf(date,
week|month|year)` (weeks start Monday).
Data (`data.ts`): `GroupBy(rows,key,field?,agg?)`→`{key,value}[]` (agg default sum with field, count without);
`Pivot(rows,rowKey,colKey,field?,agg?)`; `Top(rows,field,n,direction?)`; `Between(rows,field,min?,max?)` (numbers or
text such as ISO dates; null = open end); `Bucket(rows,dateField,day|week|month,field?,agg?)` (empty periods 0 for
sum/count; key `YYYY-MM-DD` or `YYYY-MM`); `Cumulative(rows,field)`; `MovingAvg(rows,field,window)`;
`Change(current,previous)` (null when previous 0); `Histogram(values,bins 1-500,min?,max?)`→`{key,value,start,end}[]`;
`Stats(values)`→`{count,min,max,mean,median,stdev}` (zeros for empty).
1.0 built-ins (from lang-core, listed in the prompt before these): Count, First, Last, Sum, Avg, Min, Max,
Sort(array, field, asc|desc), Filter(array, field, ==|!=|>|<|>=|<=|contains, value), Round(n, decimals?), Abs,
Floor, Ceil, Each.

## 9. Images and maps

Images (`OIU/src/lib/components/media.tsx`):
- `Photo` (behind SearchImage and Image): use `src` if http(s) and not failed; otherwise, if the query/alt is >2
  chars, search. Search waits 500ms after the query settles, then in parallel GET
  `/api/wiki?title=<query>` (uses `photos`) and `/api/image-search?q=<query>` (uses `images`), dedupes, tries URLs in
  order, moving to the next on `<img onError>`. Module cache of ≤200 queries; empty results are not cached (retry
  next time). Aspect ratio 0.2-5 else 1.5; radius default `lg`; `loading=lazy`, `referrerPolicy=no-referrer`;
  shimmer while loading, faint ImageIcon when nothing found. CSS media-row rule forces 4:3 and width
  `clamp(120px, 33%, 200px)` for a photo beside text (`components.css` last lines).
- `/api/wiki` (`OIU/src/app/api/wiki/route.ts`): `title` 1-200 chars; fetches en.wikipedia REST
  `page/summary/<t>` and `page/media-list/<t>` (8s timeout, UA header); 404 = cached empty; photos = lead thumbnail +
  up to 2 more media-list images skipping `svg|icon|logo|map|flag|seal`; returns `{lat, lng, photos}` (coords unused
  by the client); server cache 500; `Cache-Control: public, max-age=3600, s-maxage=86400`; failures 502 uncached.
- `/api/image-search` (`OIU/src/app/api/image-search/route.ts`): `q` 2-200 chars; en.wikipedia `generator=search`
  (6 results, `pageimages` thumbnails 960px) kept only when the article title shares a >3-letter word with the query;
  then Wikimedia Commons file search `<terms> filetype:bitmap` (full query, first 3 words, first 2 words) until ≥3;
  skip `svg|icon|logo|map|flag|seal|coat_of_arms|signature|diagram`; https only; max 4; cache 500; a 200-with-error
  body (rate limit) throws so "no photos" is not cached.

Maps (`OIU/src/lib/components/map/*`, `OIU/src/app/api/street-route/route.ts`):
- `MapMarker` renders nothing itself; `Map` reads marker elements from its `markers` prop (`placesOf`): skips
  non-elements, partial elements while streaming, empty labels and invalid coordinates (|lat|≤90, |lng|≤180);
  duplicate labels get `" (2)"` keys; `icon` must be a single emoji grapheme else the pin shows its 1-based number.
- MapLibre GL loaded lazily (`basemap.ts` `loadMapLibre`, worker URL set). Basemap: vector style on OpenFreeMap
  (`https://tiles.openfreemap.org/planet`, glyphs from the same host) with OIU's own LIGHT/DARK palettes; on a tile or
  style error falls back once to Esri ArcGIS raster (`World_Street_Map` / `Canvas/World_Dark_Gray_Base`); a second
  error shows "Map tiles are temporarily unavailable. The places are still shown."
- Options: `scrollZoom:false`, no rotation/pitch, `cooperativeGestures` on coarse pointers, attribution bottom-left,
  zoom buttons bottom-right (shown on hover/focus). Theme changes swap the style in place (`useColorScheme` reads the
  used `color-scheme`, watching `data-theme` attribute changes).
- Camera: first marker → `jumpTo(zoom 10.5)`; after streaming ends (or category filter change) `fitBounds` padding
  `{top:70,left:72,bottom:50,right:72}`, maxZoom 13, 920ms (instant under reduced motion; skipped if the user dragged).
- Pins: DOM elements (`map-utils.ts` `createPinElement`) focusable, Enter/Space/click → `selection.setValue(label)`
  where `selection = useStateField(statementId ?? "map-<id>", props.selected)` → writes the bound `$var`; selected
  pin gets an outline and z-index.
- Controls overlay: category `<select>` ("All places") when >1 category, recenter, info note, Expand/Collapse
  (fixed dialog inset 24px with focus trap, Escape, body scroll lock: `use-dialog.ts`). Height:
  `min(clamp(200, height ?? 400, 720)px, max(280px, 82vw))`.
- Route (`route: true`): `useStreetRoute` (`use-street-route.ts`) debounces 700ms, GET
  `/api/street-route?coords=lng,lat;lng,lat…` (10s abort, client cache 64); server validates 2-25 pairs, calls the
  public OSRM demo `router.project-osrm.org/route/v1/driving/<coords>?overview=full&geometries=geojson&steps=false`
  (10s, UA header), caches 200, returns `{points:[[lat,lng]…]}` with 1h/1d cache headers; error 502. The line is drawn
  once with a 760ms ease animation after framing; if routing fails the markers are joined straight with a
  "Route overview" tag and an info note ("driving profile; overview, not turn-by-turn").

## 10. Theming

- Tokens: `OIU/src/lib/components/theme.css`. `:root, [data-theme="light"]`: neutrals come from the react-ui theme
  (`--iui-font: var(--openui-font-body, "Inter")`, `--iui-canvas: var(--openui-foreground, #fff)`,
  `--iui-ink: var(--openui-text-neutral-primary, #0d0d0d)`, `--iui-muted/--iui-faint: var(--openui-text-neutral-secondary)`);
  greys are ink at alpha (`--iui-surface` 4%, hover 5%, pressed/selected 8%, border 8%, border-strong 10%,
  range-track 6%); `--iui-on-ink`; glass `--iui-glass` (canvas 70%) + rings; shadows; status `info` (= ink, neutral),
  `success #00805d`, `warning #8a5300`, `danger #c1322c`, `purple #7040c1`, `pink #b7377c`, each with `-soft`;
  separate calmer badge tones `--iui-badge-*`; charts `--iui-chart-1..6` `#0285ff #00a67d #8b5cf6 #f4a340 #e46d91
  #4b9ca6`; map water; spacing tiers `--iui-space-tight 4 / inner 8 / group 12 / group-lg 16 / section 24`,
  `--iui-control-gap 8`, `--iui-field-gap 24`, `--iui-action-gap 40`; radii sm 6, md 10, lg 12, xl 14, 2xl 20.
- Dark: `:root[data-openui-theme="dark"], [data-theme="dark"]` only retunes shadows, status, badge, glass, chart and
  map colors (neutrals flip through the react-ui `--openui-*` tokens).
- Chat theme wiring (`OIU/src/app/page.tsx` L60-70): `useThemeModePreference()` (follows system until the footer
  toggle is used), passes `theme={{mode}}` to `AgentInterface`, and mirrors the mode to
  `<html data-openui-theme=…>` so component dark tokens apply. Gallery/preview set `data-theme` on their wrapper.
- `components.css`: Inter weights 440/560/640 via `font-weight` (drops the body `wght` variation); title scale
  sm 15 / md 17 / lg 21 / xl 25 / 2xl 32 / 3xl 40; Text xs 12, sm 14, md 16, lg 18; inside a Card/grid
  cell/carousel item titles lg+ shrink to 18/24 and default Text to 15/22; a Card that opens with an sm/md Title reads
  it as 14/20 medium with a 13/18 muted subtitle; buttons are 999px pills (36/32/44px); inputs 42px, radius md,
  16px font; tables framed 14px radius with surface header; Markdown 16/1.65 rhythm.
- Spacing system (end of `components.css`): `.iui-flow > * + *` = section 24px; after a title = group 12px; nested
  flows and Card contents = group; title + its text/caption/badge row = inner 8px; caption above title = tight 4px.
- Mobile ≤640px: Card padding 16, smaller big titles, tighter table cells and list lanes.
- Reduced motion disables pressable transforms, image fade/shimmer, flashcard flip, confetti, pin animation.
- "response-theme": README lists `src/lib/response-theme.ts` and `src/app/shell.css`; **neither file exists at this
  HEAD**. The shell is plain `AgentInterface` + `@openuidev/react-ui/styles/index.css` + `OIU/src/app/globals.css`
  (reset, `.chat-shell` containment, 4-column starter grid, mascot size).
- RTL: the CSS is written LTR with physical properties, e.g. `text-align:left` in tables, `border-left` in Quote and
  Markdown blockquote, `padding-left` lists, `left/right` for carousel nav, map controls, slider marks, popover
  placement, timeline connector `left:11.5px`, select chevron `right 12px`, Link arrow `margin-left`. Number/date
  formatting is `en-US` throughout (functions, Chart, Slider, Table). Nothing in OIU sets `dir`.

## 11. Chart, HtmlView, Celebration, Flashcard, Timer, Code/Math

- Chart (`OIU/src/lib/components/chart.tsx`, no chart library, hand-drawn SVG): types `bar line area pie donut
  scatter`; `data` = array of records; `x` = given key if present, else first string key (first number key for
  scatter); `series` = given keys or every number key except x, max 8; colors `--iui-chart-1..6` cycling; `height`
  140-480 default 240; `format number|currency|percent` (+ ISO currency, default USD), axis ticks compact, tooltip
  2 decimals; nice ticks (1/2/2.5/5/10), zero baseline, dashed grid, category labels thinned to avoid overlap;
  hover band/guide line + tooltip; `stacked` for bar/area; area gradient fill; points shown when ≤16 rows;
  pie/donut 80-200px with legend percentages; scatter tooltip names a point by the first text key. Legend when ≥2
  series. Width from ResizeObserver.
- HtmlView (`html-view.tsx`): `<iframe sandbox="allow-scripts" srcDoc=…>` (opaque origin, no forms/popups/top
  navigation, no access to app cookies/storage); document = doctype + CSP meta first:
  `default-src 'none'; script-src 'unsafe-inline' cdn.jsdelivr.net unpkg.com cdnjs.cloudflare.com esm.sh;
  style-src 'unsafe-inline' <CDNs> fonts.googleapis.com; font-src fonts.gstatic.com data:; img-src data: blob:
  https:; media-src data: blob:; connect-src <CDNs>; frame-src 'none'; form-action 'none'; base-uri 'none'` + viewport
  + `color-scheme` from the host + a height reporter script (`postMessage({type:"iui-html-view-height"})`, parent can
  re-request with `"iui-html-view-measure"`). Height: fixed (80-2400) or measured, starting at 360. Rendered only after
  streaming ends. Used for the arcade game example and the gallery "catch the dot" game.
- Celebration, Flashcard, Timer: see §7. Quiz pattern (no dedicated component): RadioGroup `$answer` + ternary
  feedback text (`gdp`, `clt` in `tool-programs.ts`), or Buttons with `Action([@Set($picked,o), @Set($score, …),
  @Set($q, $q+1)])` and `Celebration($score == 4)` (`spanish` in `composition-programs.ts` L39-47).
- Code: copy-to-clipboard code block, language label; Math: KaTeX (CSS imported in `extra.tsx`).

## 12. Gallery, examples, preview, benchmark, extension libraries

- `/gallery` (`OIU/src/app/gallery/gallery.tsx`): dev-only, `?theme=light|dark`; renders each program with
  `<Renderer response={code} library={library} isStreaming={false} toolProvider={demoTools}>`, shows errors under
  each example, the source in `<details>`, and a toast for actions ("Sent to the assistant: “…” with {context}",
  "Copied to the clipboard"; `open_url` opens http(s) only). Sections: Composition (4: `web-analytics`,
  `compare-phones`, `flashcards` (Spanish flashcards + quiz + Celebration), `primitives`), Working tools
  (`toolPrograms` + 4 prompt examples), Components (19 programs in `programs.ts`: answer, text, lists, buttons,
  layout, gdp sliders, segmented, checklist, pressable, inputs+Form, svg, chart, table, images, map, html, timer,
  heatmap, icons).
- The 16 Intelligent UI examples (`OIU/src/app/gallery/tool-programs.ts`; id → prompt → technique):
  1. `recipe` "Plan a Sunday roast for friends, with a shopping list" — guest stepper rescales list (`@Each @Clamp
     @Format`), tick items/steps with `@Toggle`, copy list.
  2. `bill` "Make a bill splitter for dinner with friends" — add/remove people and items (`@Append @Remove`), who
     shared what (`@Update @Toggle`), tax/tip sliders, `@Allocate` to the cent, copy split.
  3. `monty` "Explain the Monty Hall problem with an interactive game" — `@Random` inside `@Set`, switch/stay,
     simulate 1,000 games (`@Range @Each @Filter`), result bar chart.
  4. `savings` "Help me explore how my retirement savings could grow" — 4 sliders, yearly rows with `@Pow`, area
     chart, $1M milestone via `@Filter/@First`, disclaimer "not advice".
  5. `gdp-explained` "How does GDP work? Let me explore an economy" — 4 sliders, flex bar from one parts list,
     negative net exports note, knowledge-check RadioGroup.
  6. `clt` "Help me understand the central limit theorem intuitively" — draw samples (`@Random` in `@Set`),
     `@Histogram @Stats`, σ/√n, quiz.
  7. `bicycle` "Break down the design of a 7-speed bike" — gear slider drives an Svg of sprockets, ratio and speed.
  8. `bike-repair` "Help me assemble a youth bicycle, step by step" — tap to tick steps (`@Toggle` on indexes),
     progress bar, brake type rewrites a step, inseam → saddle height.
  9. `route` "Plan a sightseeing route in San Francisco" — `Map(@Each(places, …), true, $stop, 340)`, pace
     SegmentedControl rescales times (`@Cumulative @Pad`), row/pin selects stop, Directions `@OpenUrl`,
     "Plan a second day" `@ToAssistant`.
  10. `roadtrip` "Plan a ten-day road trip through the Pacific Northwest" — 9-stop route, tap a day to select its
      stop, budget tier + traveler stepper recompute totals and a bar chart, `@ToAssistant` swap-a-day button.
  11. `room` "Help me choose a new paint color for my living room" — 3 answers score 6 colors (`@Includes @Sort
      @Take`), room Svg takes the picked color.
  12. `origami` "Show me how to fold an origami baby fox" — 6 Svg diagrams, Back/Next `@Clamp`, thumbnails.
  13. `garden` "Help me plan a small backyard vegetable garden" — size/sun sliders, crop chips `@Toggle`,
      square-foot Grid with `$w` columns, summary Table, checklist.
  14. `wardrobe` "Build me a versatile capsule wardrobe for a week away" — trip length/weather rebuild packing list
      (`@Concat @Take`) and outfits (modulo indexes), checklist.
  15. `drones` "Help me understand the drone photography market" — segments, market-size Chart, players Table, a
      4-slider business model (profit, margin, break-even), `@ToAssistant` follow-up.
  16. `game` "Make a retro arcade game I can play here" — HtmlView canvas space shooter (keyboard + on-screen buttons).
  Plus dashboards `dash-sales` (Query get_orders, `@Bucket @Cumulative @Change @GroupBy @Pivot @Top`) and
  `dash-support` (Query get_tickets, `@Between @Stats @Histogram @MovingAvg`).
  Header comment: "They work in the page with $variables and @Set; nothing goes back to the assistant."
- `/preview` (`OIU/src/app/preview/*`): dev-only, reads `window.__OPENUI_PROGRAM__`, `?library=clash|chess`,
  `?theme=dark`; writes `window.__OPENUI_ERRORS__` (`code: message`) and `__OPENUI_ACTIONS__`.
- Benchmark (`OIU/scripts/bench/run.mjs`, `prompts.json` = 16 tool + 8 dashboard prompts): calls any OpenAI-compatible
  `/chat/completions` with the **generated txt prompts** (`system-prompt.txt`, `dashboard-system-prompt.txt`), extracts
  the first fenced block or the whole text, parses with `createParser(spec.schema, spec.root)`, flags parse errors,
  unresolved, orphaned, unknown `@names` (probing the parser for built-ins) and unknown components, counts functions,
  `$vars`, `@Set/@Reset`, `@ToAssistant`, queries; screenshots via `/preview` light/dark at 390 and 1280px with
  Playwright; `--fake` uses `tool-programs.ts` as model output. Output `bench-out/<model>-<time>/report.{json,md}`.
- Domain extension pattern (`OIU/src/lib/chess/library.ts`, `OIU/src/lib/coach/library.ts`): `createLibrary({ root:"Col",
  components: [...baseComponents, …domain], functions: [...functions, …domain], actions, componentGroups:
  [...baseComponentGroups, {name, components, notes}] })`; prompt options = `{...promptOptions, additionalRules:
  [...base, ...domainRules], examples: [domain examples only] }` (`chess/prompt-options.ts` L51-58). Domain notes forbid
  the model from typing derived facts ("never type FENs, material or evaluations yourself; compute them" /
  "never type elixir costs"), push state into a `$var` list (`$moves`, `$deck`), and end answers with a soft Card of
  2-3 `@ToAssistant` follow-ups. Coach's `Arena` embeds `public/arena/index.html` in an `allow-scripts` sandboxed iframe.

## 13. Tests, security and telemetry

- `OIU/vitest.config.mts`: node env, `TZ=UTC`, `src/**/*.test.ts`.
- `OIU/src/lib/functions/__tests__/run.ts`: evaluates `root = Out(<expr>)` with the real 1.0 `createParser` +
  `evaluateElementProps`, a store and the library functions/actions; `click()` replays a plan's `@Set` steps.
  Table-driven cases per function (`lists.test.ts`, `numbers-text.test.ts`, `dates-data.test.ts`) including null
  results for bad args; `patterns.test.ts` covers `@Each` over `@Range` following state, `@Set` order, nested
  `@Each` + `@Update/@Toggle`, per-person shares, CopyToClipboard step shape, `@Random` once per click.
- `OIU/src/app/gallery/programs.test.ts`: spec lists exactly the library functions/actions; each function
  description matches `/^[^\n—]{8,240}$/`; every tool program, prompt example, component and composition program
  parses with no errors, no unresolved, no orphaned. Chess/coach tests cover rules, engine and sim.
- Safety measures in OIU: same-origin check on chat routes; CSS value sanitiser; http(s)-only links/URLs and
  `window.open` override; Markdown never injects HTML; SVG attribute validation; KaTeX `trust:false`; HtmlView
  sandbox + CSP; YouTube nocookie; `referrerPolicy=no-referrer` on photos; OpenUI devtools widget disabled unless
  `NEXT_PUBLIC_OPENUI_DEVTOOLS=1` (`OIU/src/lib/devtools.ts`); PostHog analytics only in production with
  `NEXT_PUBLIC_POSTHOG_KEY` (`OIU/src/app/analytics.tsx`, session recording at 0.3 sample rate).
- Telemetry inside `@openuidev/lang-core`: install telemetry in `postinstall.cjs` is **opt-out** (sent unless
  `OPENUI_TELEMETRY_DISABLED=1` or `DO_NOT_TRACK=1`; `src-lang-core-post/src/telemetry/install.ts`), which OIU blocks
  with `allowScripts`; runtime telemetry from `generateSystemPrompt` and `parser.parse` (`src-lang-core/src/telemetry/
  runtime.ts`) is opt-in (`OPENUI_RUNTIME_TELEMETRY_ENABLED=1`), server-side only, 10% sampled, hashes only.
- Not present: authentication, rate limiting, server-side message storage, i18n.

## 14. Discrepancies and stale artefacts found

- `OIU/src/generated/system-prompt.txt` and `dashboard-system-prompt.txt` are **stale** relative to
  `prompt-options.ts`/`spec.json`: they lack rules 2-5 (spacing tiers, media row, SearchImage query, compact cards),
  show `Badge(text, color?)` without `icon`, Title "lg for a card title" (spec says "md for a card title, lg for a
  section"), and Example 2 `days` gap 5 (source 4). `chess-` and `coach-system-prompt.txt` are current. The chat
  route builds its prompt at runtime from `spec.json` + `prompt-options.ts`, so it is current; the **bench** reads the
  stale txt files.
- README says "the chat is light only"; `page.tsx` follows the system theme with a toggle and `theme.css` has a
  `:root[data-openui-theme="dark"]` block, so the chat has dark mode.
- README lists `src/app/shell.css` and `src/lib/response-theme.ts`; both absent.
- README says Gateway "validates and corrects"; the client side only sends the config block, so correction behaviour
  cannot be verified from this repo.

## 15. Reproduction checklist (behaviour to match)

1. Server builds a library-specific system prompt (component signatures from schemas, functions, actions, rules,
   worked examples, "root first" streaming order) and streams model text; low reasoning effort; no tools.
2. Client re-parses the accumulated text on every chunk with a cached streaming parser: auto-close the trailing
   statement, resolve hoisted refs, drop unresolved/invalid nodes, render progressively; block interactions until
   the stream ends; keep last good render on component errors.
3. Page state lives in a per-message store: `$vars` from literal declarations, inputs two-way bound, everything
   recomputed from state on each change; `@Set/@Reset` mutate locally; `@Random` evaluated at click time.
4. `@ToAssistant(message, context)` becomes a user turn whose content is the message and whose hidden context is
   `["User clicked: …", stateSnapshot, context]`, shown as a user bubble (with collapsible form data).
5. Every state change is written into the assistant message (`context:[snapshot]`) and persisted; on reload and on
   the next model turn the state comes back (initialState; "context and form values").
6. Visual layer: token-driven CSS (`--iui-*`), spacing tiers by structure (no gaps on page/card), compact cards,
   light/dark sets, mobile breakpoints, reduced motion.

## 16. Flags for a Lonora port (from the binding documents; not OIU behaviour)

- Money: OIU's action set is `@Set @Reset @ToAssistant @OpenUrl @CopyToClipboard` plus `Query/Mutation/@Run` when
  tools are in the prompt. `Mutation`/`@Run` would let generated UI call tools directly; under VISION/MANDATE_CORRECTIONS
  (money moves only through the signed grant or an approval card at the single executor) no generated control may
  place, modify or approve a trade, so any tool-calling step must stay out or be limited to non-financial reads.
- Q27 maps naturally onto OIU's `@ToAssistant(message, context)`: the `why` and the non-financial `submit {intent,
  data}` would be the message/context of a user turn rendered as a quoted user message (OIU shows text + a
  "Form data" accordion). OIU has no `why` field.
- D5/Q36: OIU ships `Code` (copyable code blocks, allowed as explanation per Q36) and `HtmlView` whose purpose is
  running model-written games/apps (the arcade example is code as a deliverable, conflicting with D5). D6: most OIU
  examples (trips, recipes, games) are off-domain; quiz/timer count as light personal tasks (Q27).
- Arabic-first RTL and dark/light: OIU CSS uses physical left/right and `en-US` formatting everywhere (§10); its
  palette is Inter/neutral-ink; Lonora's own tokens (`packages/ui-tokens`) and `docs/ui-reference/Lonora-Desktop-37.html`
  would replace `theme.css`/`components.css` while keeping the behaviour.
- External services OIU depends on: OpenUI Gateway (cloud path), Wikipedia/Wikimedia (photos), OpenFreeMap + Esri
  (tiles), OSRM demo (routes), YouTube, script CDNs (HtmlView), Google Fonts; plus lang-core install telemetry.
