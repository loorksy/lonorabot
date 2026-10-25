import assert from "node:assert/strict";
import test from "node:test";
import type {
  VisualDocument,
  VisualNode,
  VisualValue,
} from "../../packages/contracts/src/visual-response";
import {
  evaluateVisualValue,
  expandVisualAction,
  filterVisualRows,
  initialVisualState,
  updateVisualState,
  validateRichContent,
  validateVisualDocument,
  visualDocumentKey,
  visualStateStorageKey,
} from "../../packages/core/src/visual-response";

const resource = "11111111-2222-4333-8444-555555555555";
function example(): VisualDocument {
  return {
    version: 1,
    mode: "example",
    state: { risk: 100, stop: 10, enabled: true, timeframe: "15m", query: "" },
    facts: { tick: { value: 1, source: "instrument", observed_at: "2026-10-25T10:00:00Z" } },
    root: {
      id: "root",
      type: "column",
      children: [
        {
          id: "risk",
          type: "slider",
          label: "Risk",
          state_key: "risk",
          minimum: 0,
          maximum: 500,
          step: 10,
        },
        {
          id: "stop",
          type: "input",
          label: "Stop distance",
          state_key: "stop",
          input_kind: "number",
          minimum: 1,
          maximum: 100,
          step: 1,
        },
        { id: "enabled", type: "checkbox", label: "Show detail", state_key: "enabled" },
        {
          id: "timeframe",
          type: "select",
          label: "Timeframe",
          state_key: "timeframe",
          options: [
            { value: "15m", label: "15 minutes" },
            { value: "1h", label: "1 hour" },
          ],
        },
        {
          id: "size",
          type: "metric",
          label: "Illustrative size",
          value: {
            op: "div",
            args: [{ state: "risk" }, { op: "mul", args: [{ state: "stop" }, { source: "tick" }] }],
          },
        },
        { id: "filter", type: "input", label: "Filter", state_key: "query" },
        {
          id: "positions",
          type: "table",
          fields: [
            { key: "symbol", label: "Symbol" },
            { key: "value", label: "Value" },
          ],
          filter_key: "query",
          rows: [
            { symbol: "GOLD.demo", value: 4 },
            { symbol: "EUR.demo", value: 2 },
          ],
        },
        {
          id: "followup",
          type: "button",
          label: "Review",
          action: {
            kind: "follow_up",
            text: "Review {{timeframe}} with illustrative risk {{risk}}",
          },
        },
      ],
    },
  };
}
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

test("a mixed response keeps text and native UI order and survives JSON reopening", () => {
  const content = {
    version: 1,
    parts: [
      { type: "text", text: "An explanation." },
      { type: "ui", document: example() },
      { type: "text", text: "A conclusion." },
    ],
  };
  assert.deepEqual(validateRichContent(clone(content)), content);
  assert.equal(validateVisualDocument(content.parts[1].document), content.parts[1].document);
});

test("shared Web/native calculations update locally with bounded controls and no effects", () => {
  const document = example();
  const initial = initialVisualState(document);
  const metric = document.root.children?.find((node) => node.id === "size");
  assert.equal(evaluateVisualValue(metric?.value, document, initial), 10);
  const slider = document.root.children?.[0] as VisualNode;
  const state = updateVisualState(document, initial, slider, 247);
  assert.equal(state.risk, 250);
  assert.equal(evaluateVisualValue(metric?.value, document, state), 25);
  assert.equal(initial.risk, 100);
  assert.equal(updateVisualState(document, state, slider, 1000000).risk, 500);
  assert.equal(updateVisualState(document, state, { ...slider, id: "forged" }, 10).risk, 250);
  assert.equal(
    expandVisualAction(
      { kind: "follow_up", text: "Review {{timeframe}} at {{risk}}" },
      document,
      state,
    )?.kind,
    "follow_up",
  );
  assert.deepEqual(
    expandVisualAction(
      { kind: "follow_up", text: "Review {{timeframe}} at {{risk}}" },
      document,
      state,
    ),
    { kind: "follow_up", text: "Review 15m at 250" },
  );
});

test("invalid math is explicitly unavailable, with lazy conditions and finite results", () => {
  const document = example();
  const evaluate = (value: VisualValue) =>
    evaluateVisualValue(value, document, initialVisualState(document));
  assert.equal(evaluate({ op: "div", args: [10, 0] }), null);
  assert.equal(evaluate({ op: "mul", args: [1e308, 1e308] }), null);
  assert.equal(evaluate({ op: "round", args: [1.567, 2] }), 1.57);
  assert.equal(evaluate({ op: "round", args: [1.567, 100] }), null);
  assert.equal(evaluate({ op: "if", args: [false, { op: "div", args: [1, 0] }, 7] }), 7);
  assert.equal(evaluate({ op: "add", args: ["100", 1] }), null);
  assert.equal(evaluate({ op: "gte", args: [100, 20] }), true);
});

test("unknown components/properties/executable code and privileged actions cannot render", () => {
  for (const node of [
    { id: "x", type: "script", text: "alert(1)" },
    { id: "x", type: "text", text: "safe", onClick: "trade_execute()" },
    { id: "x", type: "text", html: "<script>alert(1)</script>" },
    { id: "x", type: "button", label: "Buy", action: { kind: "trade_execute", volume: 1 } },
    {
      id: "x",
      type: "button",
      label: "Approve",
      action: { kind: "approve", resource_id: resource },
    },
    {
      id: "x",
      type: "button",
      label: "Open",
      action: { kind: "open_chart", resource_id: "javascript:alert(1)" },
    },
    { id: "x", type: "image", artifact_id: "https://untrusted.example/image.png" },
  ])
    assert.equal(validateVisualDocument({ version: 1, mode: "example", root: node }), null);
});

test("only server-resolved sources and declared state may participate in calculations", () => {
  for (const value of [
    { fact: { call_id: "unverified", path: "/balance" } },
    { source: "absent" },
    { state: "undeclared" },
    { op: "eval", args: ["globalThis.fetch('/trade')"] },
    { op: "div", args: [1] },
    { op: "add", args: [1], javascript: "run()" },
  ])
    assert.equal(
      validateVisualDocument({
        version: 1,
        mode: "observed",
        root: { id: "metric", type: "metric", value },
      }),
      null,
    );
  const document = example();
  assert.ok(validateVisualDocument(document));
  assert.equal(evaluateVisualValue({ source: "tick" }, document, {}), 1);
  assert.equal(
    validateVisualDocument({
      ...document,
      facts: { tick: { value: Number.NaN, source: "instrument" } },
    }),
    null,
  );
});

test("graph identity, nesting, expressions and document bytes are bounded", () => {
  const document = example();
  const duplicate = clone(document);
  duplicate.root.children?.push({ id: "risk", type: "text", text: "Duplicate" });
  assert.equal(validateVisualDocument(duplicate), null);
  let deep: VisualNode = { id: "leaf", type: "text", text: "Leaf" };
  for (let index = 0; index < 12; index++)
    deep = { id: `depth${index}`, type: "column", children: [deep] };
  assert.equal(validateVisualDocument({ version: 1, mode: "example", root: deep }), null);
  const wide: VisualNode = {
    id: "wide",
    type: "column",
    children: Array.from({ length: 41 }, (_, index) => ({
      id: `child${index}`,
      type: "text",
      text: "x",
    })),
  };
  assert.equal(validateVisualDocument({ version: 1, mode: "example", root: wide }), null);
  assert.equal(validateVisualDocument({ ...document, state: { query: "ع".repeat(40000) } }), null);
  let expression: VisualValue = 1;
  for (let index = 0; index < 10; index++) expression = { op: "abs", args: [expression] };
  assert.equal(
    validateVisualDocument({
      version: 1,
      mode: "example",
      root: { id: "x", type: "metric", value: expression },
    }),
    null,
  );
});

test("persisted state is message/document/owner scoped and cannot inject permissions", () => {
  const document = example();
  const restored = initialVisualState(document, {
    risk: 800,
    stop: "12",
    timeframe: "forged",
    enabled: "yes",
    authority: "unrestricted",
    query: "gold",
  });
  assert.deepEqual(restored, {
    risk: 500,
    stop: 12,
    enabled: true,
    timeframe: "15m",
    query: "gold",
  });
  assert.equal(Object.hasOwn(restored, "authority"), false);
  const key = visualStateStorageKey("owner", "thread", "message", document);
  assert.notEqual(key, visualStateStorageKey("other", "thread", "message", document));
  assert.notEqual(key, visualStateStorageKey("owner", "other", "message", document));
  assert.notEqual(key, visualStateStorageKey("owner", "thread", "other", document));
  const changed = clone(document);
  changed.state = { ...document.state, risk: 200 };
  assert.notEqual(key, visualStateStorageKey("owner", "thread", "message", changed));
  assert.equal(visualDocumentKey(clone(document)), visualDocumentKey(document));
  const reordered = {
    root: document.root,
    facts: document.facts,
    state: document.state,
    mode: document.mode,
    version: 1,
  } as VisualDocument;
  assert.equal(visualDocumentKey(reordered), visualDocumentKey(document));
});

test("tables filter evaluated values locally and selectors cannot forge options", () => {
  const document = example();
  const table = document.root.children?.find((node) => node.type === "table") as VisualNode;
  const filtered = updateVisualState(document, initialVisualState(document), table, "GOLD");
  assert.equal(filtered.query, "GOLD");
  assert.equal(filterVisualRows(table, document, filtered).length, 1);
  assert.equal(updateVisualState(document, filtered, table, 123).query, "GOLD");
  assert.equal(
    updateVisualState(document, filtered, { ...table, id: "forged-table" }, "EUR").query,
    "GOLD",
  );
  assert.equal(
    filterVisualRows(table, document, { ...initialVisualState(document), query: "GOLD" }).length,
    1,
  );
  const selector = document.root.children?.find((node) => node.type === "select") as VisualNode;
  assert.equal(
    updateVisualState(document, initialVisualState(document), selector, "1h").timeframe,
    "1h",
  );
  assert.equal(
    updateVisualState(document, initialVisualState(document), selector, "javascript").timeframe,
    "15m",
  );
});

test("action interpolation uses declared scalar data without executing it", () => {
  const document = example();
  assert.deepEqual(
    expandVisualAction({ kind: "open_chart", resource_id: resource }, document, {}),
    { kind: "open_chart", resource_id: resource },
  );
  assert.equal(expandVisualAction({ kind: "follow_up", text: "{{missing}}" }, document, {}), null);
  assert.equal(
    expandVisualAction({ kind: "follow_up", text: "{{risk.constructor}}" }, document, {}),
    null,
  );
  assert.equal(
    validateVisualDocument({
      ...document,
      root: {
        id: "bad",
        type: "button",
        label: "Broken",
        action: { kind: "follow_up", text: "{{missing}}" },
      },
    }),
    null,
  );
  assert.equal(
    expandVisualAction({ kind: "follow_up", text: "{{query}}" }, document, {
      ...initialVisualState(document),
      // biome-ignore lint/suspicious/noTemplateCurlyInString: Deliberately inert interpolation attack fixture.
      query: "${globalThis.fetch('x')}",
    })?.kind,
    "follow_up",
  );
});

test("malformed graphs, prototype keys, getters and cyclic data fail closed", () => {
  const document = example();
  const state = JSON.parse('{"__proto__":"unsafe"}') as unknown;
  assert.equal(validateVisualDocument({ ...document, state }), null);
  const malicious = {
    version: 1,
    mode: "example",
    get root() {
      throw new Error("Must not evaluate");
    },
  };
  assert.equal(validateVisualDocument(malicious), null);
  const root: Record<string, unknown> = { id: "cyclic", type: "column" };
  root.children = [root];
  assert.equal(validateVisualDocument({ version: 1, mode: "example", root }), null);
  assert.equal(
    validateVisualDocument({
      version: 1,
      mode: "example",
      root: {
        id: "diagram",
        type: "diagram",
        vertices: [{ id: "a", label: "A" }],
        edges: [{ source: "a", target: "missing" }],
      },
    }),
    null,
  );
});

test("wire enum values are exact strings and cannot be coerced into component actions", () => {
  assert.equal(validateVisualDocument({ ...example(), mode: ["example"] }), null);
  for (const root of [
    { id: "x", type: "text", text: "Safe", tone: ["success"] },
    { id: "x", type: "column", gap: ["small"] },
    { id: "x", type: "chart", chart_kind: ["line"], points: [] },
    { id: "x", type: "input", input_kind: ["text"], state_key: "query" },
    {
      id: "x",
      type: "button",
      label: "Open",
      action: { kind: ["open_chart"], resource_id: resource },
    },
  ])
    assert.equal(validateVisualDocument({ ...example(), root }), null);
});

test("array properties and sparse operands cannot execute or silently supply missing arguments", () => {
  let touched = false;
  const children: unknown[] = [];
  Object.defineProperty(children, "0", {
    enumerable: true,
    get() {
      touched = true;
      return { id: "x", type: "text", text: "Untrusted" };
    },
  });
  assert.equal(
    validateVisualDocument({
      version: 1,
      mode: "example",
      root: { id: "root", type: "column", children },
    }),
    null,
  );
  assert.equal(touched, false);
  const args = new Array(2);
  assert.equal(
    validateVisualDocument({
      version: 1,
      mode: "example",
      root: { id: "metric", type: "metric", value: { op: "div", args } },
    }),
    null,
  );
});

test("mixed reply limits match the server contract without discarding valid long text", () => {
  const parts = Array.from({ length: 24 }, () => ({ type: "text", text: "A" }));
  assert.ok(validateRichContent({ version: 1, parts }));
  assert.equal(
    validateRichContent({ version: 1, parts: [...parts, { type: "text", text: "B" }] }),
    null,
  );
  assert.ok(
    validateRichContent({ version: 1, parts: [{ type: "text", text: "A".repeat(32000) }] }),
  );
  assert.equal(
    validateRichContent({ version: 1, parts: [{ type: "text", text: "A".repeat(32001) }] }),
    null,
  );
  assert.equal(
    validateRichContent({
      version: 1,
      parts: Array.from({ length: 3 }, () => ({ type: "text", text: "ع".repeat(30000) })),
    }),
    null,
  );
});

test("initial control and filter state must match the declared native control", () => {
  for (const [type, state, props] of [
    ["checkbox", "yes", {}],
    ["slider", 101, { minimum: 0, maximum: 100 }],
    ["slider", false, {}],
    ["input", null, { input_kind: "number" }],
    ["input", 1, { input_kind: "text" }],
    ["select", "absent", { options: [{ value: "first", label: "First" }] }],
  ] as const)
    assert.equal(
      validateVisualDocument({
        version: 1,
        mode: "example",
        state: { field: state },
        root: { id: "control", type, state_key: "field", ...props },
      }),
      null,
    );
  assert.equal(
    validateVisualDocument({
      version: 1,
      mode: "example",
      state: { filter: 1 },
      root: {
        id: "table",
        type: "table",
        fields: [{ key: "value", label: "Value" }],
        rows: [],
        filter_key: "filter",
      },
    }),
    null,
  );
});
