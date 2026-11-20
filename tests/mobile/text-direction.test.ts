import assert from "node:assert/strict";
import { test } from "node:test";
import { textDirection } from "../../apps/mobile/lib/text-direction";

test("one Arabic letter makes a text right-to-left; all-Latin text reads left-to-right", () => {
  assert.equal(textDirection("أُغلقت صفقة XAUUSD عند وقف الخسارة 2310.5", "ltr"), "rtl");
  // A Latin ticker first no longer turns an Arabic sentence left-to-right (v38).
  assert.equal(textDirection("XAUUSD أُغلقت عند وقف الخسارة", "rtl"), "rtl");
  assert.equal(textDirection("Gold closed at the 2310.5 stop loss", "rtl"), "ltr");
  // Numbers and punctuation are not letters.
  assert.equal(textDirection("2310.5 — وقف الخسارة", "ltr"), "rtl");
  assert.equal(textDirection("٢٣١٠ - Gold", "rtl"), "ltr");
});

test("text without a letter follows the interface", () => {
  assert.equal(textDirection("2310.5", "rtl"), "rtl");
  assert.equal(textDirection("", "ltr"), "ltr");
});
