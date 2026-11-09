import assert from "node:assert/strict";
import { test } from "node:test";
import { textDirection } from "../../apps/mobile/lib/text-direction";

test("the first strong letter decides, whatever the interface language", () => {
  assert.equal(textDirection("أُغلقت صفقة XAUUSD عند وقف الخسارة 2310.5", "ltr"), "rtl");
  assert.equal(textDirection("XAUUSD أُغلقت عند وقف الخسارة", "rtl"), "ltr");
  assert.equal(textDirection("Gold closed at the 2310.5 stop loss", "rtl"), "ltr");
  // Leading numbers and punctuation are not strong.
  assert.equal(textDirection("2310.5 — وقف الخسارة", "ltr"), "rtl");
  assert.equal(textDirection("٢٣١٠ - Gold", "rtl"), "ltr");
});

test("text without a letter follows the interface", () => {
  assert.equal(textDirection("2310.5", "rtl"), "rtl");
  assert.equal(textDirection("", "ltr"), "ltr");
});
