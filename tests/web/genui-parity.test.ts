// One v2 component set (mandate 10.1.5): the client validator accepts exactly the catalog
// generated from the server contract, and every document the server compiled for the
// parity check (tests/test_genui_parity.py) passes it. Both renderers type their node map
// against the same catalog (`pnpm check`) and draw every type in genui.spec.mjs.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  UI_ACTIONS,
  UI_NODE_TYPES,
  UI_SERVER_NODE_TYPES,
  type UiBlock,
  type UiDocument,
} from "@lonora/contracts";
import { UI_NODES, validateUiDocument } from "../../packages/core/src/genui/spec";

const { documents } = JSON.parse(
  readFileSync(new URL("../fixtures/genui/parity-compiled.json", import.meta.url), "utf8"),
) as { documents: UiDocument[] };

function nodes(blocks: UiBlock[]): UiBlock[] {
  return blocks.flatMap((block) => [block, ...nodes((block.children as UiBlock[]) ?? [])]);
}

test("the client validator accepts exactly the catalog's node types", () => {
  assert.deepEqual([...UI_NODES].sort(), [...UI_NODE_TYPES, ...UI_SERVER_NODE_TYPES].sort());
});

test("every compiled parity document passes the client validator", () => {
  for (const document of documents) assert.ok(validateUiDocument(document), document.title);
});

test("the parity documents cover every node type and action of the catalog", () => {
  const all = documents.flatMap((document) => nodes(document.blocks));
  assert.deepEqual(
    [...new Set(all.map((node) => node.type))].sort(),
    [...UI_NODE_TYPES, ...UI_SERVER_NODE_TYPES].sort(),
  );
  const actions = all.flatMap((node) =>
    node.action ? [String((node.action as { do: string }).do)] : [],
  );
  assert.deepEqual([...new Set(actions)].sort(), [...UI_ACTIONS].sort());
});

test("a node or action outside the catalog is refused", () => {
  const [card] = documents;
  assert.ok(card);
  const unknown = { ...card, blocks: [{ type: "Chart", series: [] }] };
  assert.equal(validateUiDocument(unknown), null);
  const action = { ...card, blocks: [{ type: "Button", label: "x", action: { do: "eval" } }] };
  assert.equal(validateUiDocument(action), null);
});

test("a trusted slot is its card and record at the top level, nothing else", () => {
  const [card] = documents;
  assert.ok(card);
  const slot = { type: "Slot", card: "trade_approval", record: "approval-1" };
  assert.ok(validateUiDocument({ ...card, blocks: [slot] }));
  for (const forged of [
    { ...slot, when: "false" },
    { ...slot, label: "Approve" },
    { ...slot, card: "grant_authority" },
    { ...slot, record: "../x" },
  ])
    assert.equal(validateUiDocument({ ...card, blocks: [forged] }), null, JSON.stringify(forged));
  const nested = { type: "More", children: [slot] };
  assert.equal(validateUiDocument({ ...card, blocks: [nested] }), null);
});
