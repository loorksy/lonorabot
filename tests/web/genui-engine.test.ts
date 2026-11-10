import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { AgentWatchSummary, Message, Run } from "@lonora/contracts";
import { watchCondition } from "../../packages/core/src/agent-status";
import { isPlainOutgoing } from "../../packages/core/src/chat-rows";
import { environment, evaluate, renderTemplate } from "../../packages/core/src/genui/expr";
import { ARITY } from "../../packages/core/src/genui/functions";
import { parseCardNumber } from "../../packages/core/src/genui/input";
import { validateUiDocument } from "../../packages/core/src/genui/spec";
import { cardLock, sendBlocked, submitMark } from "../../packages/core/src/genui/submit";

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

// The shared client helpers (§8.1, §8.2 rules N and T, §8.6, §9.3).
const sendMessage = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "s1",
    thread_id: "t",
    seq: 5,
    role: "user",
    content: "أنشئ تنبيهًا",
    origin: "ui_submit",
    reply_to: "card",
    ui_submit: {
      source_message_id: "card",
      part: 1,
      intent: "alert.create",
      lock: true,
      run_id: "r1",
    },
    ...overrides,
  }) as unknown as Message;
const cardMessage = { id: "card", thread_id: "t", seq: 4, role: "assistant" } as unknown as Message;
const run = (status: string, overrides: Record<string, unknown> = {}) =>
  ({ id: "r1", thread_id: "t", agent_id: "a", status, ...overrides }) as unknown as Run;

test("a card's send is never flushed by the outbox", () => {
  assert.equal(isPlainOutgoing({ content: "hi" }), true);
  assert.equal(isPlainOutgoing({ content: "", ui_submit: { part: 1 } }), false);
  assert.equal(isPlainOutgoing({ content: "x", input_answer: { run_id: "r" } }), false);
});

test("the never-run mark is the server's fact only (review U1)", () => {
  // A Run that finished without the client hearing of its start is not «لم يُنفَّذ».
  assert.equal(submitMark(sendMessage()), null);
  assert.equal(submitMark(sendMessage({ ui_mark: "not_run" })), "not_run");
  const superseded = sendMessage();
  (superseded.ui_submit as Record<string, unknown>).mark = "superseded";
  assert.equal(submitMark(superseded), "superseded");
  const started = sendMessage({ ui_mark: "not_run" });
  (started.ui_submit as Record<string, unknown>).started_at = "2026-11-10T00:00:00Z";
  assert.equal(submitMark(started), null);
  assert.equal(submitMark({ ...sendMessage(), origin: "owner" } as Message), null);
});

test("a card is locked by its latest locking send unless never run or unlocked", () => {
  assert.deepEqual(cardLock(cardMessage, 1, [cardMessage, sendMessage()]), { id: "s1", seq: 5 });
  assert.equal(cardLock(cardMessage, 0, [cardMessage, sendMessage()]), null);
  assert.equal(cardLock(cardMessage, 1, [cardMessage, sendMessage({ ui_mark: "not_run" })]), null);
  const unlocked = {
    ...cardMessage,
    ui_state: { parts: { "1": { unlocked_seq: 5 } } },
  } as unknown as Message;
  assert.equal(cardLock(unlocked, 1, [unlocked, sendMessage()]), null);
  const repeatable = sendMessage();
  (repeatable.ui_submit as Record<string, unknown>).lock = false;
  assert.equal(cardLock(cardMessage, 1, [cardMessage, repeatable]), null);
});

test("a send waits while the agent is paused, waits for the owner, or has one queued", () => {
  assert.equal(sendBlocked("a", "t", [], [], true), "paused");
  assert.equal(sendBlocked("a", "t", [], [run("waiting_input")], false), "waiting");
  assert.equal(sendBlocked("a", "t", [sendMessage()], [run("queued")], false), "queued");
  assert.equal(sendBlocked("a", "t", [sendMessage()], [run("completed")], false), null);
  assert.equal(
    sendBlocked("a", "t", [sendMessage()], [run("queued", { agent_id: "b" })], false),
    null,
  );
});

test("the client's card validator fails closed on anything malformed", () => {
  const valid = {
    v: 2,
    kind: "form",
    title: "t",
    facts: {},
    state: {},
    calc: {},
    blocks: [{ type: "Text", text: "x" }],
    fallback: "f",
  };
  assert.ok(validateUiDocument(valid));
  for (const broken of [
    { ...valid, v: 1 },
    { ...valid, kind: "unknown" },
    { ...valid, blocks: [{ type: "Script", text: "x" }] },
    { ...valid, blocks: [{ type: "Button", label: "x", action: { do: "trade" } }] },
    { ...valid, blocks: [{ type: "Button", label: "x", action: { do: "open", url: "http://x" } }] },
    { ...valid, calc: { x: "@Nope(" } },
    { ...valid, fallback: "x".repeat(1501) },
    JSON.parse('{"v":2,"__proto__":{"x":1}}'),
  ])
    assert.equal(validateUiDocument(broken), null, JSON.stringify(broken));
  const getter = { ...valid };
  Object.defineProperty(getter, "title", { get: () => "t", enumerable: true });
  assert.equal(validateUiDocument(getter), null);
});

test("a calc chain of nested lists stays within one budget (review round 4)", () => {
  const calc = {
    a: "@Join(@Range(0,200),'xxxxxxx')",
    b: `[${Array(120).fill("$a").join(",")}]`,
    c: `[${Array(120).fill("$b").join(",")}]`,
  };
  const started = Date.now();
  const env = environment({}, calc, {});
  assert.equal(String(env.values.a).length, 1893);
  assert.equal(env.values.b, null);
  assert.deepEqual(env.values.c, Array(120).fill(null));
  assert.equal(renderTemplate("{$b}", env), "");
  assert.equal(renderTemplate("{$c}", env), "، ".repeat(119));
  assert.ok(Date.now() - started < 2000);
});
