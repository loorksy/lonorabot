import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { AgentWatchSummary } from "@lonora/contracts";
import { watchCondition } from "../../packages/core/src/agent-status";
import { environment, evaluate, renderTemplate } from "../../packages/core/src/genui/expr";
import { ARITY } from "../../packages/core/src/genui/functions";
import { parseCardNumber } from "../../packages/core/src/genui/input";

type Vectors = {
  values: Record<string, unknown>;
  facts: Record<string, unknown>;
  cases: { src: string; expected: unknown }[];
};
const vectors = JSON.parse(
  readFileSync(new URL("../fixtures/genui/expr-vectors.json", import.meta.url), "utf8"),
) as Vectors;

test("the shared expression vectors evaluate as in Python", () => {
  for (const item of vectors.cases) {
    const env = { values: vectors.values, facts: vectors.facts, names: {} };
    assert.deepEqual(evaluate(item.src, env), item.expected, item.src);
  }
});

test("the canonical alert card computes the screenshot's hint and distance", () => {
  const env = environment(
    { symbol: "XAUUSD", dir: "above", price: 2400 },
    {
      cur: "@Pick($symbol,'XAUUSD',@Fact('xau'),'XAGUSD',@Fact('xag'),@Fact('eur'))",
      dp: "@Pick($symbol,'EURUSD',4,2)",
      gap: "($price-$cur)/$cur*100",
      hit: "($dir=='above'&&$price<=$cur)||($dir=='below'&&$price>=$cur)",
    },
    { xau: 2368.4, xag: 28.92, eur: 1.0842 },
  );
  assert.equal(renderTemplate("الآن {@Fmt($cur,$dp)}", env), "الآن 2,368.40");
  assert.equal(
    renderTemplate("يبعد **{@Pct(@Abs($gap),2)}** عن السعر الحالي", env),
    "يبعد **1.33%** عن السعر الحالي",
  );
  assert.equal(evaluate("$price&&!$hit", env), true);
});

test("formatters print the placeholder dash for bad input and U+2212 for negatives", () => {
  const env = { values: {}, facts: {}, names: {}, context: { currency: "EUR" } };
  assert.equal(evaluate("@Fmt('x',2)", env), "—");
  assert.equal(evaluate("@Signed(-3.1,1)", env), "−3.1");
  assert.equal(evaluate("@Money(-1234.5)", env), "-€1,235");
  assert.equal(evaluate("@Money(1234.5,2)", { ...env, context: {} }), "1,234.50");
  assert.equal(evaluate("@Random(1,2)", env), null);
});

test("the server's watch names equal watchCondition's words (shared vectors)", () => {
  const { cases } = JSON.parse(
    readFileSync(new URL("../fixtures/genui/watch-name-vectors.json", import.meta.url), "utf8"),
  ) as { cases: { watch: Partial<AgentWatchSummary>; locale: string; expected: string }[] };
  for (const item of cases) {
    const watch = {
      id: "w",
      account_id: null,
      expires_at: null,
      lifecycle: "pending",
      ...item.watch,
    };
    assert.equal(
      watchCondition(watch as AgentWatchSummary, item.locale),
      item.expected,
      JSON.stringify(item.watch),
    );
  }
});

test("a card's number field reads grouped and Arabic numbers, never a prefix (M7)", () => {
  const cases: [string, number | null | undefined][] = [
    ["2400", 2400],
    ["2,400", 2400],
    ["2،400", 2400],
    ["2 400", 2400],
    ["2 400", 2400],
    ["2,400.50", 2400.5],
    ["٢٤٠٠", 2400],
    ["٢٬٤٠٠٫٥", 2400.5],
    ["۲۴۰۰", 2400],
    ["1,234,567", 1234567],
    ["-12.5", -12.5],
    ["", null],
    ["  ", null],
    // Partial or malformed input is never a number: the card's send stays disabled.
    ["2,", undefined],
    ["2,4", undefined],
    ["2,4000", undefined],
    [",400", undefined],
    ["2..4", undefined],
    ["abc", undefined],
    ["1e999", undefined],
  ];
  for (const [text, expected] of cases) assert.equal(parseCardNumber(text), expected, text);
});

test("every function's arity equals Python's (shared fixture)", () => {
  const expected = JSON.parse(
    readFileSync(new URL("../fixtures/genui/arity.json", import.meta.url), "utf8"),
  ) as Record<string, [number, number | null]>;
  const { Random: _random, ...shared } = ARITY;
  assert.deepEqual(
    Object.fromEntries(Object.entries(shared).map(([name, range]) => [name, [...range]])),
    expected,
  );
});
