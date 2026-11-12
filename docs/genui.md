# Generated interfaces (lonora-ui v2)

The reference for Lonora's generated interfaces as they are built. Lonora has one format,
lonora-ui v2 (mandate 10.1.3). Each turn the agent decides whether its answer is text, one
lead line and one card, or a card alone; there is no presentation classifier and no second
model call. Agents compose from the component catalog and never write CSS, colours or fonts:
the clients draw every node with the design-system tokens (mandate 10.1.1). A card is input
to the agent's own judgment: it can never approve a Trade Approval, settle an operation or
switch a mode (mandate 6.10).

## 1. Wire format

A card is one fenced `lonora-ui` block (backticks or tildes) outside Markdown code, one JSON
object per line, in this order:

1. **Head:** `{"v":2, "kind", "title", "sub"?, "icon"?, "mode"?, "currency"?}`. `kind` is one
   of `lonora_contracts.genui.KINDS`; `mode` is `observed`, `example` or `estimate`.
2. **Data (optional):** `{"facts"?, "state"?, "calc"?}`. A fact names
   `{"call": "<call id>", "path": "/json/pointer"}` into one of this request's tool results;
   state holds the card's initial values; a calc is an expression or a literal.
3. **Blocks:** one line per top-level node, `{"type": …, "when"?: "<expr>", …props}`.
4. **Close:** `{"why", "fallback"}`: one sentence on why a card is clearer than text, and
   Markdown that says the same as the card.

Expressions (`lonora_contracts.genui_expr`, mirrored by `packages/core/src/genui/expr.ts`) use
`$state` and calc names, numbers, `'strings'`, arithmetic, comparisons, `&&` `||` `!`, `?:`
and `@Function(…)` (`genui_functions.FUNCTIONS`, mirrored by `functions.ts`); a text prop is a
template `"…{expr}…"`. `@Fact('key')` reads a data-line fact. Shared vectors
(`tests/fixtures/genui/expr-vectors.json`) keep both evaluators equal.

## 2. One component set

The server contract `lonora_contracts.genui` is the single source of the set (mandate 10.1.5):

- **Nodes (`NODES`):** Segmented, Select, Number, Slider, Title, Text, Markdown, Note, Badge,
  KeyValue, Stat, Button, Divider, Row, Col, Grid, Card, More. Every node takes `when`.
- **Server rows (`SERVER_NODES`):** Delivery, the read-only delivery row the compiler adds
  above an alert's send. The model never writes it.
- **Actions (`ACTIONS`):** `send {intent, data, lock?}`, `go {route}`, `set {key, value}`,
  `toggle {key}`, `reset`, `copy {text}`, `open {url}`.
- **Icons:** `genui_icons.ICON_NAMES`, the keys of `packages/ui-tokens/src/icons.ts`, which
  both clients draw.

`scripts/export_genui_catalog.py` generates `packages/contracts/src/genui-catalog.ts` (node
types, props, server rows, actions, routes, tones; `--check` in `scripts/build.sh`). Each part
accepts exactly that set and has a check:

| Part | Where | Check |
|---|---|---|
| Server contract and compiler | `lonora_contracts/genui.py`, `lonora_agent/genui_compile.py` | `tests/test_genui_parity.py` compiles parity cards that use every node, prop and action |
| Vocabulary taught to the model | `lonora_agent/genui_vocabulary.py`, generated from the contract | `tests/test_genui_parity.py` |
| Client validator | `packages/core/src/genui/spec.ts` | `tests/web/genui-parity.test.ts` |
| Web renderer | `apps/web/src/components/genui/UiCard.tsx` | node, prop and action maps typed against the catalog (`pnpm check`); `tests/web/genui.spec.mjs` "Parity" draws every node |
| Mobile renderer (native) | `apps/mobile/components/genui/` | the same typed maps; `tests/mobile/genui.spec.mjs` draws every node in dark and light |

## 3. What the model is taught

`native_visual_policy()` (`lonora_agent/skills/visual_policy.py`) builds the block that follows
the mandatory operating policy in the cached prompt prefix: `resources/prompts/genui_v2.md`
with the answer-shape teaching (`genui_v2_teaching.md`) and the generated vocabulary, bounded
by `MAX_GENUI_GUIDANCE_CHARS`. Old checkpoints receive the current block in their request copy.
Each request also carries:

- `<lonora_ui_capabilities>` (`genui_capabilities.py`): the intents whose tool path exists, the
  delivery channels, the client routes, the owner's time zone and language;
- `<lonora_visual_observations>` (`visual_response.visual_observation_catalog`): this request's
  successful tool call ids, which a fact may name.

## 4. Compiling a reply

`lonora_agent/visual_response.py` (`VisualReplyProjector`) finds the fences; every fence is a
v2 card. `genui.parse_lines` repairs structurally: an invalid optional prop is dropped, a block
with an unknown type or a missing required prop is dropped, an unknown icon is omitted; a head
or data line that fails makes the whole card fall back. `genui_compile.compile_card` then:

- resolves facts to this request's results only; a failed or private value is never shown,
  nor anything inside an operation the broker has not confirmed (an agent never draws
  "confirmed": the server posts its own Execution Receipt),
  and a card whose facts all fail falls back; source metadata is privacy-filtered;
- binds the card to one account (the first account-bearing fact) and, for a fixed-market agent,
  to its own pair;
- checks sends against the intent registry (`genui_intents.REGISTRY`, closed and non-financial;
  denied families are refused) and the capabilities, `go` against the routes, `set`/`toggle`
  against the state, and `open` against the literal https URLs of the owner's message and the
  tool results; an asset option must be a symbol read this turn and labelled with one of its
  known names;
- refuses a market or account number typed into the card instead of read through `@Fact`, any
  private value in any string a client can show, and an unfilled `{{name}}` placeholder;
- folds to the budget (section 5) and adds the delivery row to an alert;
- stores the result as `UiDocument` (re-validated on every write).

A card that cannot be built shows its model-written fallback. One card per reply: a second is
dropped and its fallback kept as text. Diagnostics carry structural codes only, never model text.

## 5. Budgets

- At rest a card shows at most 6 top-level blocks and at most 560 px (`RESTING_LIMIT`, estimated
  per node by `estimate_height`); the rest folds into one More, never the send, required inputs,
  inputs the send reads or the delivery row. Above 720 px (`HARD_LIMIT`) the card falls back.
- Text caps (`TEXT_CAPS` and the per-node checks): title 32, sub 48, label 24, option 16,
  button 24, Text 180, Note 140, Markdown 600, why 220, fallback 1,500 characters.
- Limits in `genui.py`: 12 block lines, 8 children, depth 4, 24 state keys, 24 calcs, 24 facts,
  6,000 bytes per line; options 1-20; KeyValue rows 1-8.

## 6. Streaming and storage

While the model writes, the card streams line by line: a skeleton until the head line is
complete, then each complete block (`building: true`); a partial line is never read. If the
owner stops the reply mid-card, the built blocks are stored with `cut`; stopped before any
block, the fallback stands in. `content` holds the lead and the fallback (search, previews,
notifications); `rich_content` holds the ordered text and card parts.

## 7. The send path

A Button's send posts only `MessageCreate.ui_submit {source_message_id, part, path, values}`
(`lonora_db/genui_submit.py`). The server reads the intent from the stored card, computes the
data from the stored card and the validated values, re-evaluates `disabled`, and writes the
owner's bubble itself: the button label for `ask`, or the intent's template filled with the
server's own names (with several enabled accounts, the card's account is named). The
submission (`origin = 'ui_submit'`) always gets its own queued Run carrying
`ui_submit_origin`; it never steers an active Run. Its Run is claimed only after the agent's
earlier Runs in the thread end (rule Q), reads the thread up to its claim (rule W), stays
invisible to every other Run until it ends and for good if it never started (rules V and N),
takes its ticks from its own Run (rule T), and is cancelled if it has not started 30 minutes
after the send (rule L). Both clients post a card send at once, never through the
auto-flushed outbox or offline queue; a retry after a failure is the owner's tap. A Run
started by a card send, its retry, and work it creates are tainted
(`lonora_db/genui_taint.py`). A card's `message.updated` events carry the message as a history
page shows it (`genui_submit.client_row`). In the model's context, card words are labelled as
card words, never as the owner's own (`lonora_db/owner_words.py`), and the submission's
validated data is marked as data (`<ui_submit>`).

A locking send locks its card part (`ui_lock`); «تعديل» posts
`/threads/{thread}/messages/{message}/ui-state/{part}/unlock`, which cancels a send whose Run
has not started. A send whose Run never started is marked «مُعدّلة» or «لم يُنفَّذ» and never
locks. `ui_state` keeps a card's values per part. The client rules (lock, marks, whether a send
may go now) are shared by web and mobile in `packages/core/src/genui/submit.ts`.

## 8. Clients

Both clients validate fail closed (`spec.ts`), render the same nodes with the same evaluator,
keep the card's values, disable every control while the card builds or is uncommitted, keep
only go/open/copy while it is locked, and show the why panel with when its facts were read.
A card text that starts with «الآن» or "now" reads «آخر تحديث HH:MM» once its oldest fact is
older than 120 s.
Web: `UiCard.tsx` and `genui.css` (the reference look). Mobile: `apps/mobile/components/genui/`,
native React Native views (no web view), right to left, the reference tokens in dark and light
(`theme.ts`). Card Markdown is one parser (`packages/core/src/genui/markdown.ts`): paragraphs,
lists and bold, never HTML, links shown as text.

## 9. Stored v1 messages

Messages written before v2 was the only format may hold v1 documents (`version: 1`). They are
only rendered: `lonora_contracts.visual_response` still validates them, and
`apps/web/src/components/visual/RichResponse.tsx` and
`apps/mobile/components/native-rich-response.tsx` draw them. No reply becomes a v1 document.
