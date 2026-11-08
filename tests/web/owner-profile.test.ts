import assert from "node:assert/strict";
import test from "node:test";
import {
  ownerProfileError,
  ownerProfileLabel,
  ownerProfileLabelKeys,
  preferenceFieldLabel,
  preferenceValueText,
  reachMeChannels,
  reachMeHint,
  reachMeLabel,
  replyLanguageLabel,
  replyLanguages,
} from "../../packages/core/src/owner-profile";

const arabic = /[؀-ۿ]/;

test("every profile, reach-me and language label exists in Arabic and English", () => {
  for (const key of ownerProfileLabelKeys) {
    const en = ownerProfileLabel(key, "en");
    const ar = ownerProfileLabel(key, "ar");
    assert.ok(en && !arabic.test(en), key);
    assert.ok(arabic.test(ar), key);
  }
  for (const channel of reachMeChannels) {
    assert.ok(arabic.test(reachMeLabel(channel, "ar")) && reachMeLabel(channel, "en"));
    assert.ok(arabic.test(reachMeHint(channel, "ar")) && reachMeHint(channel, "en"));
  }
  for (const language of replyLanguages)
    assert.ok(arabic.test(replyLanguageLabel(language, "ar-SA")));
  assert.deepEqual([...reachMeChannels], ["activity", "notify", "message", "call"]);
  // Delivery is in-app until off-app delivery exists; the label says so.
  assert.match(ownerProfileLabel("inAppOnly", "en"), /inside Lonora/);
});

test("recorded preference changes read as plain words and never as raw values", () => {
  assert.equal(preferenceFieldLabel("reach_me", "en"), "How to reach you");
  assert.equal(preferenceValueText("reach_me", "message", "ar"), "راسلني");
  assert.equal(preferenceValueText("reply_language", "ar", "en"), "Arabic");
  assert.equal(preferenceValueText("reply_language", null, "en"), "Not set");
  assert.equal(preferenceValueText("opportunity_calls", true, "ar"), "مفعّل");
  assert.equal(preferenceFieldLabel("device_id", "en"), null);
});

test("profile and memory errors explain what to do in the owner's language", () => {
  assert.match(ownerProfileError("memory_user_section_moved", "en") ?? "", /profile/);
  assert.ok(arabic.test(ownerProfileError("owner_profile_too_large", "ar") ?? ""));
  assert.equal(ownerProfileError("trading_disabled", "en"), null);
});
