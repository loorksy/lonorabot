Superseded by VISION.md

# OpenUI packages: what Lonora can reuse as a dependency

Read-only study, 2026-11-09. Nothing was installed into any repo and no package script was run.
Tarballs were fetched with curl from registry.npmjs.org into `work/genui/pkgs/` and each
sha512 was checked against the reference lockfile or the registry packument (all match).
Bundle sizes were measured with the esbuild binary already in Lonora's pnpm store
(bundling only, no execution).

## Versions

| Package | Locked by open-intelligent-ui | Latest on npm (published) | Licence |
|---|---|---|---|
| @openuidev/lang-core | 1.0.0 | 1.1.0 (2026-11-04); 1.0.2 (2026-10-27) | MIT, (c) Thesys Inc. |
| @openuidev/react-lang | 1.0.0 | 1.1.0 (2026-11-04); 1.0.2 (2026-10-27) | MIT |
| @openuidev/react-ui | 0.18.1 | 0.18.5 (2026-11-06) | MIT |
| @openuidev/cli | 0.4.1 (dev) | 0.6.3 (2026-11-06) | MIT |
| @openuidev/devtools (dep of react-lang) | 0.3.0 | 0.3.1 | MIT |
| @openuidev/observability (dep of react-lang) | 0.0.4 | 0.0.4 | MIT |
| @openuidev/react-headless (peer of react-ui) | 0.18.0 | n/a | MIT |

MIT is compatible with Lonora's Apache-2.0. Every package's repository field points to
github.com/thesysdev/openui (`packages/<name>`).

Resolved tarball URLs (lockfile):
- https://registry.npmjs.org/@openuidev/lang-core/-/lang-core-1.0.0.tgz
- https://registry.npmjs.org/@openuidev/react-lang/-/react-lang-1.0.0.tgz
- https://registry.npmjs.org/@openuidev/react-ui/-/react-ui-0.18.1.tgz
- https://registry.npmjs.org/@openuidev/cli/-/cli-0.4.1.tgz

## @openuidev/lang-core (framework-agnostic; no React)

Dependencies: `ci-info`. Peers: `zod ^3.25 || ^4` (it imports `zod/v4` and `zod/v4/core`,
so zod 3.25.x works through its v4 subpath) and optional `@modelcontextprotocol/sdk`.
Exports `.` and `./cloud`.

What it provides (from `dist/index.d.mts`):
- **Lexer and parser.** `tokenize`, `split`, a Pratt `parseExpression`, `parse`, `createParser(schema, rootName)`.
- **Streaming and incremental parsing.** `createStreamingParser(schema, rootName)` has `push(chunk, complete?)`,
  `set(fullText, complete?)` (diffs against its buffer and resets when the text is replaced, not appended)
  and `getResult()`. `autoClose` closes unclosed strings and brackets so partial text parses.
  `ParseResult.meta` holds `incomplete`, `unresolved` (forward refs, dropped as null),
  `orphaned`, `statementCount` and `errors`. `ElementNode.partial` marks nodes still streaming.
- **Validator.** It checks props against the library JSON Schema. Error codes: `missing-required`, `null-required`,
  `unknown-component`, `inline-reserved`, `excess-args`, `type-mismatch`, `unknown-function`
  and `no-root` (a `fallback` warning when the root statement is missing but a root-component
  call exists). Invalid components are dropped from the tree and recorded, not thrown.
  Messages are humanised and include signatures and the available components. There are also form
  validators (`parseRules`, `parseStructuredRules`, `validate`, `builtInValidators`).
- **Evaluator.** `evaluate(ast, ctx)`, `evaluateElementProps`, `evaluateRoot` (supports
  `root = cond ? A : B`) and `stripReactiveAssign`. The AST covers literals, refs, `$state`, BinOp,
  UnaryOp, Ternary, Member, Index and Assign. There is no JS eval: it walks the AST.
- **State store.** `createStore()`: get, set (with `pristine`), subscribe, snapshot, initialize, dispose.
- **Functions.** `defineFunction({name, description, params: z.object, returns?, fn})`, called as
  `@Name(...)` in programs; a bad argument, bad result or a throw evaluates to null. There are also built-ins
  (@Count, @Sum, @Each and others). Lazy built-ins: @Each, Action, @Run, @Set, @Reset.
- **Actions.** Built-in steps: `ACTION_STEPS` = Run, ToAssistant (`continue_conversation`),
  OpenUrl, Set, Reset. `defineAction({name, description, params})` defines a custom step that is delivered
  to the host as `{type: name, params}`. `action()` and `steps.*.ref` restrict which actions a slot accepts.
- **Query and Mutation.** `createQueryManager(toolProvider)`. A program can declare
  `x = Query("tool", args, defaults, refreshSec)` and `m = Mutation("tool", args)`, run via `@Run`.
  `ToolProvider` is `{callTool(name,args)}` or an MCP-client-like object (`extractToolResult`).
  Prompt flags: `toolCalls` defaults to true only when `tools` are passed, and `bindings` defaults to true if toolCalls.
- **Prompt generation.** `generateSystemPrompt({library: LibrarySpec, promptOptions})` (also
  `library.prompt(opts)`). Options: `preamble`, `additionalRules`, `examples`,
  `toolExamples`, `tools` (ToolSpec with input/output schema and readOnly/destructive hints), `toolCalls`,
  `bindings`, `builtinFunctions`, `editMode`, `inlineMode`. In inline mode the model writes prose
  plus a ```openui-lang fenced block, and the parser pulls the code from the fences.
- **Library definition API (zod).** `defineComponent({name, props: z.object, description, component})`,
  where `component` is opaque to lang-core (the framework adapter supplies it). `createLibrary({components,
  componentGroups, functions, actions, root, id})` returns `prompt()`, `toSpec()`,
  `toJSONSchema()` and `extend({components:{add,override,remove}, functions, actions})`.
  Positional arguments map to props in zod key order. `ref` is used for child slots, `tagSchemaId` for prompt type names.
- **Editing.** `mergeStatements(existing, patch)` patches by statement name and garbage-collects
  unreachable statements. `jsonToOpenUI(tree, library)` serialises a tree back to source.
- **Stored message format.** `parseMessage` and `buildMessage` handle `]]>openui:content|context|end`
  marker lines. The renderer uses them to persist form state and context inside the message text.
- **`./cloud`.** Only `artifactTool()`, which builds an OpenUI Cloud Responses `tools[]` entry. Nothing imports it
  unless the host does. `generateSystemPrompt({cloud:true})` emits a `]]>openui:config` block meant for
  Gateway, and Lonora would never use it.

**Telemetry (important).**
- `postinstall: node ./postinstall.cjs` sends install telemetry to PostHog through a CloudFront proxy
  (`dgoeivjus9jfp.cloudfront.net`). It runs `git config --get remote.origin.url` (hashed
  with a salt) and writes `~/.config/openui/telemetry.json`. It is on by default; opt out with
  `OPENUI_TELEMETRY_DISABLED=1` or `DO_NOT_TRACK=1`. It is still present in 1.1.0.
  Lonora uses pnpm 11 with `allowBuilds: { esbuild: true }` only, so dependency lifecycle scripts are
  blocked and the postinstall would not run. Keep lang-core out of `allowBuilds`. The reference repo
  does the same with `allowScripts: {"@openuidev/lang-core": false}`.
- Runtime telemetry (sampled `generateSystemPrompt` and `createParser().parse`) is opt-in through
  `OPENUI_RUNTIME_TELEMETRY_ENABLED=1`, and is never sent from a browser, a worker or React Native
  (`navigator.product === "ReactNative"`). Default: off.

## @openuidev/react-lang (React runtime)

Dependencies: `@openuidev/lang-core`, `@openuidev/observability` (an in-memory event bus on
`globalThis[Symbol.for("openui.observability")]`, with no network) and `@openuidev/devtools`.
Peers: `react *`, `react-dom *` (optional), `zod ^3.25 || ^4`, optional MCP SDK.
1.0.2 and later add an optional `react-native *` peer. The README says react >=19. The code uses
useSyncExternalStore, useInsertionEffect and useId. It re-exports most of lang-core.

What it provides:
- **Renderer.** `<Renderer response library isStreaming onAction onStateUpdate initialState
  onParseResult toolProvider queryLoader onError publishObservability/>`. It also has composable slots:
  `Renderer.Root` (one runtime; renders only its children), `.Content`, `.QueryLoading`,
  `.QueryError` and `.Retry`, plus `WithPreviewRenderer` (a collapsed preview or panel).
- **State store and forms.** The `$variables` and form state live in a lang-core Store per Renderer.
  `onStateUpdate` delivers the snapshot and `initialState` rehydrates it.
- **Hooks.** `useRenderNode`, `useTriggerAction`, `useIsStreaming`, `useIsQueryLoading`,
  `useGetFieldValue`, `useSetFieldValue`, `useSetDefaultValue`, `useFormName`, `useStateField`
  (with `reactive(schema)` for `$binding` props), `useFormValidation`, `useCreateFormValidation`,
  `useRendererQuery` and `useRendererPreview`.
- **Action dispatch** (`triggerAction`, read in `dist/exports-*.mjs`):
  - `Set` and `Reset` change local state only.
  - `ToAssistant`, `OpenUrl`, custom `defineAction` steps and legacy `{type,...}` objects all go to the host's `onAction`
    as `{type, params, humanFriendlyMessage, formState, formName}`. **react-lang never opens URLs
    or sends messages by itself.**
  - `Run` on a **Mutation calls `toolProvider.callTool` directly from the client**, and `Run` on a Query refetches.
    With no toolProvider, query and mutation calls fail with "[openui] toolProvider is null".
  - Interactions are blocked while `isStreaming` is true.
- **Errors and partial programs.**
  - Each component renders inside an error boundary that keeps its last valid children and reports a
    `render-error`.
  - A parser crash is caught and reported as `parse-exception`. Non-empty text with no statements is reported as `parse-failed`.
  - Validation errors are enriched with hints.
  - Runtime errors come from functions returning null. Query and tool errors (`tool-not-found`,
    `tool-error`, `mcp-error`) can be retried with a retry function.
  - `onError(OpenUIError[])` is suppressed while streaming and fires with `[]` once everything is resolved.
    `OpenUIError` is designed for a correction loop: `statementId`, `component`, `path` and `hint` tell the model
    which statement to patch.
  - Missing or forward refs render as null until they resolve, so partial streams render progressively.
- **Devtools auto-mount (a risk in development only).** The web entry (`dist/index.mjs`) has a top-level
  side effect. When `process.env.NODE_ENV === "development"` and a `document` exists, it dynamically imports
  `@openuidev/devtools`. Devtools in turn `import()`s
  `https://cdn.jsdelivr.net/npm/@openuidev/devtools@0/dist/devtools.browser.js?t=...`, which is
  **remote code from a floating major tag, executed in the dev browser**.
  - Production builds drop it: verified, since the minified production bundle has no jsdelivr string and the dev bundle has one.
  - The native entry never imports it.
  - Opt-out: set `globalThis[Symbol.for("openui.devtools.autoMount")] = true` in a module evaluated
    before react-lang. The flag is checked synchronously when the module evaluates. The reference app does this in
    `src/lib/devtools.ts`, gated by `NEXT_PUBLIC_OPENUI_DEVTOOLS`.
  - For Lonora (Vite web, and Expo web, which also takes the web entry): set the flag, and optionally
    alias `@openuidev/devtools` to a stub exporting `OpenUIDevtools = () => null`.
  - The auto-mount is still present in 1.1.0.
- **React Native path.**
  - **1.0.0 (the version the reference locks): no usable native presentation.** The package has a
    `react-native` export condition (`index.native.*`) that drops the devtools bootstrap, but it shares
    the web chunk. `Renderer` and `Renderer.Content` render `<div>`, `Retry` renders `<button>` and Preview
    renders `<section>`, so they would fail on native. The evaluated root is not exposed through context,
    so a host cannot render it another way.
  - **1.0.2 and 1.1.0: a real native entry.** `index.native.mjs` imports `View`, `Text`, `Pressable` and
    `ActivityIndicator` from `react-native`. The slots are `View`-based, Button is a `Pressable` and the
    spinner is an `ActivityIndicator`. Metro's `react-native` export condition selects it. So use **>= 1.0.2**
    for apps/mobile (Expo 57, RN 0.86.3, React 19.2.3). The default spinner uses physical `right: 8`;
    pass `queryLoader` for RTL.
  - The library components themselves are the host's own, so mobile needs RN implementations
    (View, Text and so on) of the same component names. The same zod schemas and prompt can be shared.
- **Public API change from 1.0.0 to 1.1.0:** only `isElementNode` was added to lang-core. The 1.1.0 README
  documents renderers as `component: ({ props, renderNode, statementId })` and
  `import { z } from "zod/v4"`.

## Bundle size (minified, gzip -9; react, react-dom and react-native external; NODE_ENV=production)

| Bundle | min | gzip |
|---|---|---|
| react-lang 1.0.0 + lang-core 1.0.0 (Renderer, createLibrary, defineComponent and the main hooks), zod external | 95.2 KB | 32.8 KB |
| lang-core 1.0.0 only (parser, prompt, library, evaluator, store), zod external | 80.6 KB | 27.8 KB |
| lang-core streaming parser only | 31.3 KB | 10.4 KB |
| react-lang 1.1.0 web, zod external | 98.7 KB | 34.2 KB |
| react-lang 1.1.0 native entry, zod external | 98.4 KB | 34.1 KB |
| react-lang 1.1.0 web + zod/v4 (from zod 3.25.76) | 341.4 KB | 80.8 KB |

Zod adds about 46 KB gzip and is required: component props are zod schemas, and lang-core imports the full `zod/v4`
`z`, not zod/mini. Lonora has zod 3.25.76 only transitively through `@expo/cli` (a dev tool), so zod
would become a new runtime dependency of web, mobile and the library package. Unpacked sizes: lang-core
1.0.0 is 1.42 MB and react-lang 1.0.0 is 0.37 MB (1.1.0: 0.70 MB). Both are mostly source maps and type declarations.

## React versions

apps/web uses react and react-dom 19.2.3. apps/mobile uses react 19.2.3, react-native 0.86.3 and Expo 57.
react-lang's peers (`react *`, `react-dom *` optional, `react-native *` optional from 1.0.2) and its
documented `react >= 19` are satisfied. react-ui needs `react ^18.3.1 || ^19` and `zustand ^4.5.5`;
Lonora has no zustand.

## A fully custom component library is supported

The language and runtime do not depend on react-ui. `defineComponent` takes any React component, and
the reference app itself uses only react-lang `defineComponent`, `createLibrary`, `defineFunction`,
`defineAction`, `reactive` and `useStateField` for its whole generative library
(`src/lib/library.ts`, `src/lib/components/`, its own `theme.css` tokens). It imports
`@openuidev/react-ui` only for the chat shell (`AgentInterface`, `fetchLLM`,
`openAIResponsesAdapter`, `useThread`, `useThreadList`, theme). Lonora can therefore keep its own
components, tokens (packages/ui-tokens), Arabic RTL and dark/light, and depend on lang-core and react-lang only.
`library.extend({components:{override}})` also allows swapping individual components.

## Offline, without OpenUI Cloud or Gateway

Yes. Nothing in lang-core, react-lang or observability contacts thesys.dev.
- The only network code is lang-core telemetry (install-time and blockable; runtime is opt-in and server-only)
  and devtools (dev-only and suppressible).
- The `api.thesys.dev` endpoints live in the reference app's env (`THESYS_BASE_URL`) and in the
  CLI (`api.app.thesys.dev`, OIDC login, `deploy`, `generate-api-key`). Neither is needed.
- The reference README documents a direct path (`LLM_BASE_URL` or Ollama). There, `/api/chat` builds the full prompt
  with `generateSystemPrompt` from the library spec and streams any OpenAI-compatible model.
- **What is lost without Gateway:** "Output is rendered as written: Cloud's correction step is not
  there." Gateway validates and corrects generated OpenUI Lang. Locally, Lonora would have to build its
  own correction loop from `onError`/`meta.errors` (OpenUIError carries statementId and hint) plus
  `mergeStatements` and edit mode.
- **For Lonora:** prompt text is provider-agnostic, so `model_runtime.model_turn` can carry it.
  The agent runtime is Python (`packages/agent-runtime/src/lonora_agent/model_runtime.py`), and
  `generateSystemPrompt` and the parser are TypeScript only. The prompt and spec would need to be generated at
  build time by a small tsx script (`library.prompt(opts)`, `toSpec()`, `toJSONSchema()`; this
  is all `openui generate` does) and shipped as a resource the Python runtime loads. Server-side validation
  of streamed output (today Lonora validates `VisualDocument` frames in Python,
  `lonora_contracts/visual_response.py`, before `run.rich_partial`) has no Python OpenUI parser.
  The options are a Node sidecar, validation only on the client, or a port.

## OpenUI Lang 1.0 spec

There is no specification document in any package tarball.
- The lang-core README links "Language specification" to `openui.com/docs/openui-lang/specification-v05` (a v0.5
  spec, on the website, not packaged).
- "OpenUI Lang 1.0" appears only in react-ui's README and the reference README.
- The 1.0 language is effectively defined by the lang-core 1.x code and types (AST, `ACTION_STEPS`,
  built-ins, validation codes) and by the generated system prompt.
- The 1.1.0 README notes vue-lang, svelte-lang and angular-lang "stay on lang-core 0.4 for now".
- I did not fetch the website docs.

## Other packages, not recommended as Lonora dependencies

- **@openuidev/react-ui 0.18.1.**
  - Contents: 29 MB unpacked, DOM-only (Radix, floating-ui, d3, react-markdown, KaTeX,
    react-syntax-highlighter, date-fns, lodash-es and more), the Thesys chat shell (`AgentInterface`, `OpenUIChat`,
    `ModelSwitcher`) and a default genui library (Card, Charts, Table, Form and others).
  - Peers: zustand ^4.5.5 and react-headless (`@ag-ui/core`, optional `ai`).
  - Its styling is its own and mostly physical CSS (`padding-left` x209 vs `padding-inline-start` x7), so it is not RTL-ready.
  - Conflicts with "our own style" and with Lonora's chat-ui. Use it only as a visual reference.
- **@openuidev/cli.** `generate` bundles a library file with esbuild 0.25, executes it, and writes
  `toSpec()`, `toJSONSchema()` or `prompt(options)`. The other commands are `create`, `deploy` and
  `generate-api-key` (Thesys OIDC). It bundles posthog-node telemetry (on by default; opt out with DO_NOT_TRACK or
  `--no-telemetry`), plus openid-client, inquirer and open. A 20-line tsx script replaces it.
- **@openuidev/devtools.** Installed anyway as a react-lang dependency. Development only; it loads remote code from
  jsdelivr. Suppress it as described above.
- **@openuidev/react-headless.** The chat-state layer for react-ui. Not needed.

## Lonora-specific constraints to enforce if adopted

1. **Money (VISION, MANDATE).** Pass `toolProvider={null}` or only read-only data tools, never a
   tool that can place, modify or approve a trade.
   - Generate the prompt without `tools` (or with read-only tools only), so `Query`, `Mutation` and `@Run` are not taught.
   - A Mutation runs client-side through the provider, so the provider is the enforcement point.
     The prompt is not.
   - `defineAction` steps and `ToAssistant` reach `onAction`. Map them to Q27's non-financial
     `submit {intent, data}`, sent as a quoted user message through the normal agent turn. Money still moves only
     through the signed grant or an approval card at the single executor.
2. **OpenUrl.** react-lang only reports it, so Lonora's handler decides (https only, or its existing `go` whitelist).
3. **D5 and Q36 (code).** OpenUI Lang is UI markup rendered by Lonora's components, not delivered code.
   Do not port the reference app's `HtmlView` (a sandboxed iframe running model HTML) or `Code` as a deliverable.
4. **D6 (light personal tasks).** Quiz and Timer are allowed per Q27. Keep the library vocabulary small. Programs
   can compute through `@functions`, so keep functions to pure, light helpers.
5. **Q27 `why`.** Not built into OpenUI. Add it as a component prop or as a message `context` (`buildMessage`
   context) and render it in Lonora's own card chrome.
6. **Supply chain.**
   - Pin exact versions and verify integrity.
   - Keep lang-core's postinstall blocked (pnpm `allowBuilds`).
   - Set the devtools auto-mount flag in development.
   - The packages publish often (1.0.0 to 1.1.0 within about 3 weeks), and the workspace already uses pnpm
     `minimumReleaseAge` exclusions. 1.1.0 is 5 days old and 1.0.2 is 13 days old.

## Verdict

Reusable as dependencies: **@openuidev/lang-core + @openuidev/react-lang** (pin >= 1.0.2 so mobile has
the native entry; 1.0.2 or 1.1.0 depending on the release-age policy) plus **zod** (v4 API). These give the language, the streaming
parser, validation, evaluation, state, actions, prompt generation and the React/React Native renderer, with a fully
custom Lonora component library and no OpenUI Cloud.

Not reusable: react-ui, react-headless and cli. The Gateway's output correction must be rebuilt
locally if wanted.

Open architectural point for the parent: Lonora already ships its own generative UI
(`VisualDocument v1` / `RichContent`, validated in `packages/core/src/visual-response.ts` and the
Python mirror, streamed as validated `run.rich_partial` frames). Adopting OpenUI Lang means
replacing that wire format, or translating between the two, and deciding where validation runs.
