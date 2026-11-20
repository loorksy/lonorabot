import assert from "node:assert/strict";
import test from "node:test";
import {
  fittedLine,
  plainLine,
  SIGNED_NUMBER,
  textDirection,
  textWidth,
} from "../../packages/core/src/plain-line";

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

test("a line fitted to its width is cut between words, so a figure shows whole or not at all", () => {
  const said = "ربح الحساب (+$239) اليوم وتراجع −1.5% أمس";
  const whole = plainLine(said);
  const roomy = textWidth(whole, 14);
  // Room for all of it: the whole line, its numbers isolated.
  assert.equal(fittedLine(said, { width: roomy, fontSize: 14 }), whole);
  // Narrower: every width that cuts it gives words that fit beside «…», never part of a figure.
  for (let width = 40; width < roomy; width += 3) {
    const line = fittedLine(said, { width, fontSize: 14 });
    assert.equal(line.at(-1), "…", String(width));
    assert.ok(textWidth(line, 14) <= width, String(width));
    for (const part of line.replace(/[⁦⁩]/g, "").slice(0, -1).split(" "))
      assert.ok(said.split(" ").includes(part), `${width}: «${part}»`);
    assert.equal(line.split("⁦").length, line.split("⁩").length);
  }
  // Two lines wrap word by word; a single word longer than a line is cut where it stands.
  assert.equal(
    fittedLine("one two three four five six seven", { width: 100, fontSize: 14, lines: 2 }),
    "one two three four…",
  );
  assert.equal(fittedLine("x".repeat(40), { width: 100, fontSize: 14 }), `${"x".repeat(9)}…`);
});

test("the width bound is never narrower than the widest glyphs drawn in the test browser", () => {
  // Measured with canvas at 14 px in the apps' font stack (system-ui … Noto Sans Arabic).
  for (const [text, measured] of [
    ["WWWW", 4 * 0.985],
    ["mmmm", 4 * 0.876],
    ["MMMM", 4 * 0.903],
    ["سسسسس", 5 * 0.958],
    ["مفتاح الواجهة البرمجية لحساب التداول في منصة العملات الرقمية", 60 * 0.446],
    ["%%%%", 4 * 0.98],
  ] as const)
    assert.ok(textWidth(text, 14) >= measured * 14, text);
});
