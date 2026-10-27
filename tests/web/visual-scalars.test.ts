import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { VisualDocument, VisualValue } from "@lonora/contracts";
import {
  evaluateVisualValue,
  initialVisualState,
  parseVisualNumberDraft,
  updateVisualState,
  validateVisualDocument,
} from "../../packages/core/src/visual-response";

const cases = JSON.parse(
  readFileSync(new URL("../fixtures/visual-scalars.json", import.meta.url), "utf8"),
) as { op: string; args: unknown[]; expected: unknown }[];
const document: VisualDocument = {
  version: 1,
  mode: "example",
  root: { id: "metric", type: "metric", value: 1 },
};
for (const item of cases)
  test(`scalar parity: ${item.op}(${JSON.stringify(item.args)})`, () => {
    assert.equal(
      evaluateVisualValue({ op: item.op, args: item.args } as VisualValue, document, {}),
      item.expected,
    );
  });

test("scalar output size counts Unicode code points and keeps missing data unavailable", () => {
  assert.equal(evaluateVisualValue({ op: "concat", args: ["x".repeat(4001)] }, document, {}), null);
  assert.equal(
    evaluateVisualValue({ op: "concat", args: ["😀".repeat(4000)] }, document, {}),
    "😀".repeat(4000),
  );
});

test("composed display values cannot reveal credentials, private locations or unresolved bindings", () => {
  for (const args of [
    ["password", "=", "sensitive-example"],
    ["pass", "word", "=", "sensitive-example"],
    ["pass\u200bword", "=", "sensitive-example"],
    ["Bearer ", "sensitive-example"],
    ["/opt/", "lonora/private.env"],
    ["{", "{symbol}}"],
  ]) {
    const expression: VisualValue = { op: "concat", args };
    assert.equal(evaluateVisualValue(expression, document, {}), null);
    assert.equal(
      evaluateVisualValue({ op: "if", args: [true, expression, "Safe"] }, document, {}),
      null,
    );
    assert.equal(
      evaluateVisualValue({ op: "if", args: [false, expression, "Safe"] }, document, {}),
      "Safe",
    );
  }
  const dynamic: VisualDocument = { ...document, state: { left: "Safe", right: " value" } };
  assert.equal(
    evaluateVisualValue({ op: "concat", args: [{ state: "left" }, { state: "right" }] }, dynamic, {
      left: "password=",
      right: "sensitive-example",
    }),
    null,
  );
  for (const text of [
    "password requirements",
    "Use the market_read tool",
    "API request failed",
    "Token usage: 120",
    "0.5 lots",
    "11111111-2222-4333-8444-555555555555",
  ]) {
    assert.equal(evaluateVisualValue(text, document, {}), text);
  }
});

test("legacy previews become reactive declared-state expressions without mutating stored input", () => {
  const raw = {
    version: 1,
    mode: "example",
    state: { symbol: "GOLD.example", entry: 12.5 },
    root: { id: "preview", type: "text", text: "Example {{symbol}} at {{entry}}" },
  };
  const original = JSON.stringify(raw);
  const normalized = validateVisualDocument(raw);
  assert.ok(normalized);
  assert.equal(JSON.stringify(raw), original);
  assert.equal(normalized.root.text, undefined);
  assert.equal(
    evaluateVisualValue(normalized.root.value, normalized, { symbol: "GOLD.example", entry: 14 }),
    "Example GOLD.example at 14",
  );
  assert.equal(
    validateVisualDocument({ ...raw, root: { ...raw.root, text: "Example {{missing}}" } }),
    null,
  );
  assert.equal(
    validateVisualDocument({ ...raw, root: { ...raw.root, text: "Example {{symbol" } }),
    null,
  );
  assert.equal(
    validateVisualDocument({
      ...raw,
      root: { id: "metric", type: "metric", label: "{{symbol}}", value: 1 },
    }),
    null,
  );
});

test("numeric drafts preserve incomplete input, decimals, Arabic digits and distinct slider tick behavior", () => {
  for (const draft of ["-", ".", "1e", "1e-", "invalid", "1e9999"])
    assert.equal(parseVisualNumberDraft(draft), undefined);
  assert.equal(parseVisualNumberDraft(""), null);
  assert.equal(parseVisualNumberDraft("-1.25"), -1.25);
  assert.equal(parseVisualNumberDraft("١٢٫٥"), 12.5);
  assert.equal(parseVisualNumberDraft("۱۲٫۵"), 12.5);
  assert.equal(parseVisualNumberDraft("1."), 1);
  const input = {
    id: "value",
    type: "input" as const,
    input_kind: "number" as const,
    state_key: "value",
    minimum: -100,
    maximum: 100,
    step: 1,
  };
  const doc: VisualDocument = { ...document, state: { value: 10 }, root: input };
  assert.equal(updateVisualState(doc, initialVisualState(doc), input, -1.25).value, -1.25);
  const slider = { ...input, type: "slider" as const };
  assert.equal(updateVisualState({ ...doc, root: slider }, { value: 10 }, slider, -1.25).value, -1);
});
