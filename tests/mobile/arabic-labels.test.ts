// Arabic first (17): every owner-visible label of the mobile app is an [Arabic, English] pair,
// and the Arabic one is written in Arabic. A label added without its Arabic fails here.
import assert from "node:assert/strict";
import test from "node:test";
import { labels } from "../../apps/mobile/lib/i18n";
import incoming from "../../apps/mobile/lib/incoming-call-labels.json";

const arabic = /[؀-ۿ]/;

test("every mobile label has Arabic and English", () => {
  const missing = Object.entries(labels as Record<string, readonly string[]>).filter(
    ([, pair]) =>
      !Array.isArray(pair) ||
      pair.length !== 2 ||
      !pair[0]?.trim() ||
      !pair[1]?.trim() ||
      !arabic.test(pair[0]),
  );
  assert.deepEqual(
    missing.map(([key]) => key),
    [],
  );
});

test("the incoming-call labels have Arabic for every English entry", () => {
  const value = incoming as unknown as Record<string, Record<string, string>>;
  const ar = value.ar ?? {};
  const en = value.en ?? {};
  assert.ok(Object.keys(en).length > 0);
  assert.deepEqual(
    Object.keys(en).filter((key) => !ar[key]?.trim() || !arabic.test(ar[key])),
    [],
  );
});
