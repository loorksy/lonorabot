import assert from "node:assert/strict";
import test from "node:test";
import { plainLine, SIGNED_NUMBER, textDirection } from "../../packages/core/src/plain-line";

const LRI = "\u2066";
const PDI = "\u2069";

test("a message is one plain line: no Markdown marks, a table reads with « · »", () => {
  assert.equal(
    plainLine("### الملخص\n**الذهب** ارتفع `XAUUSD`\n> رأي\n- نقطة\n[المصدر](https://example.com)"),
    "الملخص الذهب ارتفع XAUUSD رأي نقطة المصدر",
  );
  assert.equal(
    plainLine("| الزوج | التغير |\n|---|---|\n| XAUUSD | ذهب |"),
    "الزوج · التغير XAUUSD · ذهب",
  );
  assert.equal(plainLine("قبل\n```js\nlet a = 1\n```\nبعد"), "قبل بعد");
});

test("a signed number keeps its sign on its left inside Arabic", () => {
  assert.equal(plainLine("ربح (+$239) اليوم"), `ربح (${LRI}+$239${PDI}) اليوم`);
  assert.equal(plainLine("| XAUUSD | -1.5% |"), `XAUUSD · ${LRI}-1.5%${PDI}`);
  assert.equal(plainLine("التغير: −0.5"), `التغير: ${LRI}−0.5${PDI}`);
  // A range or a hyphenated word is not a signed number.
  assert.equal(plainLine("بين 10-20"), "بين 10-20");
  const found = [..."تغير +3.1% ثم -2".matchAll(SIGNED_NUMBER)].map((m) => m[2]);
  assert.deepEqual(found, ["+3.1%", "-2"]);
});

test("direction controls in the text cannot break the line's own isolates", () => {
  assert.equal(plainLine("abc\u202edef\u2069"), "abcdef");
});

test("one Arabic letter makes a text right-to-left; all-Latin text reads left-to-right", () => {
  assert.equal(textDirection("Hello, ready?"), "ltr");
  assert.equal(textDirection("XAUUSD ارتفع 1%"), "rtl");
  assert.equal(textDirection("2310.5 +3%"), undefined);
});

test("only letters set the direction: signs and Arabic punctuation take the surroundings", () => {
  assert.equal(textDirection("5 × 3 ÷ 2"), undefined);
  assert.equal(textDirection("٥ ÷ ٣"), undefined);
  assert.equal(textDirection("Hello، world؟"), "ltr");
  assert.equal(textDirection("؛ ٪ ٫ ۔"), undefined);
  assert.equal(textDirection("Ünïcödé ø"), "ltr");
});

test("a long line is cut before its numbers are isolated, so no isolate is left open", () => {
  // The cut would fall inside «+3.1%»: the figure goes whole, never «+3».
  const long = `${"ر".repeat(117)} +3.1% ثم`;
  const cut = plainLine(long, 120);
  assert.equal(cut, `${"ر".repeat(117)}…`);
  assert.equal([...cut].filter((c) => c === LRI).length, [...cut].filter((c) => c === PDI).length);
  // The «…» ends the line in the line's own direction, outside every isolate.
  assert.equal(cut.at(-1), "…");
  // A figure that ends before the cut stays whole.
  assert.equal(
    plainLine(`${"ر".repeat(113)} +3.1% ثم`, 120),
    `${"ر".repeat(113)} ${LRI}+3.1%${PDI}…`,
  );
  // A cut inside a word goes back to the word's start; one word longer than the line is cut.
  assert.equal(plainLine("الذهب ارتفع كثيرا", 14), "الذهب ارتفع…");
  assert.equal(plainLine("x".repeat(30), 20), `${"x".repeat(20)}…`);
  assert.equal(plainLine("قصير +1%", 120), `قصير ${LRI}+1%${PDI}`);
});
