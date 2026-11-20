import assert from "node:assert/strict";
import test from "node:test";
import {
  isolateText,
  plainLine,
  SIGNED_NUMBER,
  textDirection,
} from "../../packages/core/src/plain-line";

const LRI = "\u2066";
const RLI = "\u2067";
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
  assert.equal(isolateText("Hello?"), `${LRI}Hello?${PDI}`);
  assert.equal(isolateText("XAUUSD ارتفع"), `${RLI}XAUUSD ارتفع${PDI}`);
  assert.equal(isolateText("2310"), "2310");
});
