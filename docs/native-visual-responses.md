# Generated interfaces (lonora-ui v2)

Lonora has one generated-interface format, lonora-ui v2 (mandate 10.1.3). The agent decides
each turn whether its answer is text, text and one card, or a card alone; there is no
presentation classifier and no second model call. Agents compose from the component catalog
and never write CSS, colours or fonts: the clients draw every node with the design-system
tokens (mandate 10.1.1).

## One component set

The server contract `lonora_contracts.genui` (`NODES`, `SERVER_NODES`, `ACTIONS`) is the single
source of the component set (mandate 10.1.5):

- **Nodes:** Segmented, Select, Number, Slider, Title, Text, Markdown, Note, Badge, KeyValue,
  Stat, Button, Row, Col, Grid, Card, More, Divider, plus the read-only delivery row
  (`Delivery`) that only the compiler writes.
- **Actions:** send (an intent from the per-request capabilities), go (a client route), set,
  toggle, reset, copy, open (a literal https URL from the owner's message or a tool result).

`scripts/export_genui_catalog.py` generates `packages/contracts/src/genui-catalog.ts` from it
(`--check` in `scripts/build.sh`). Four parts accept exactly that set, and each has a check:

| Part | Where | Check |
|---|---|---|
| Server contract and compiler | `lonora_contracts/genui.py`, `lonora_agent/genui_compile.py` | `tests/test_genui_parity.py` compiles parity cards that use every node and action |
| Vocabulary taught to the model | `lonora_agent/genui_vocabulary.py` in `resources/prompts/genui_v2.md` | `tests/test_genui_parity.py` |
| Web renderer | `apps/web/src/components/genui/UiCard.tsx` | node, prop and action maps typed against the catalog (`pnpm check`); `tests/web/genui.spec.mjs` "Parity" draws every node |
| Mobile renderer (native) | `apps/mobile/components/genui/` | the same typed maps; `tests/mobile/genui.spec.mjs` draws every node in dark and light |

The client validator (`packages/core/src/genui/spec.ts`) accepts the same catalog and is
checked by `tests/web/genui-parity.test.ts`.

## The prompt

`native_visual_policy()` (`lonora_agent/skills/visual_policy.py`) builds the block that follows
the mandatory operating policy: `genui_v2.md` with the answer-shape teaching
(`genui_v2_teaching.md`) and the generated vocabulary. It is part of the cached prompt prefix;
old checkpoints receive the current block in their request copy. Each request also carries a
`<lonora_ui_capabilities>` block with the intents, delivery channels and routes that exist, and
`<lonora_visual_observations>` with the current request's tool call ids a card fact may name.

## Compiling a reply

`lonora_agent/visual_response.py` finds `lonora-ui` fences outside Markdown code and compiles
each as a v2 card (`genui_compile.compile_card`): facts resolve to this request's tool results,
options and sends are checked against real evidence and capabilities, private values and
unfilled `{{…}}` placeholders never reach a card, and the card is folded to six visible blocks
and 560 px at rest (`RESTING_LIMIT`). A card that cannot be built shows its model-written
fallback text. One card per reply; a second is dropped and its fallback kept as text. A
building card streams line by line; partial lines are never shown.

`content` keeps the text representation (lead, blank line, fallback) for search, previews and
notifications; `rich_content` holds the ordered text and card parts.

## Stored v1 messages

Messages written before v2 became the only format may hold v1 documents (`version: 1`). They
are only rendered: `lonora_contracts.visual_response` still validates them, and the web
(`components/visual/RichResponse.tsx`) and mobile (`components/native-rich-response.tsx`)
renderers draw them. No reply is compiled into a v1 document.
