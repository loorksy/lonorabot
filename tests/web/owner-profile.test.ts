import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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

test("quiet hours in the change log read as the settings page names them, and off reads as off", () => {
  assert.equal(preferenceFieldLabel("quiet_hours", "ar"), "ساعات الهدوء");
  assert.equal(preferenceValueText("quiet_hours", "22:00-08:00", "ar"), "22:00 – 08:00");
  assert.equal(preferenceValueText("quiet_hours", null, "ar"), "متوقف");
  assert.equal(preferenceValueText("quiet_hours", null, "en"), "Off");
});

test("profile and memory errors explain what to do in the owner's language", () => {
  assert.match(ownerProfileError("memory_user_section_moved", "en") ?? "", /profile/);
  assert.ok(arabic.test(ownerProfileError("owner_profile_too_large", "ar") ?? ""));
  assert.equal(ownerProfileError("broker_disabled", "en"), null);
});

test("the notify choice promises only what happens until agents can raise alerts", () => {
  assert.doesNotMatch(reachMeHint("notify", "en"), /add an alert/);
  assert.match(reachMeHint("notify", "en"), /write to you/);
  assert.doesNotMatch(reachMeHint("notify", "ar"), /يضيف الوكلاء تنبيهًا/);
});

test("undo names what it does and why it may be refused, in both languages", () => {
  assert.equal(ownerProfileLabel("restore", "en"), "Undo this change");
  assert.match(ownerProfileLabel("restored", "en"), /Later changes were kept/);
  for (const code of [
    "memory_revert_conflict",
    "invalid_timezone",
    "incoming_call_device_required",
    "incoming_call_quiet_hours_incomplete",
    "incoming_call_quiet_hours_empty",
    "incoming_call_channel_conflict",
  ]) {
    assert.ok(ownerProfileError(code, "en"), code);
    assert.ok(arabic.test(ownerProfileError(code, "ar") ?? ""), code);
  }
});

test("Web and Mobile read profile errors from the same shared table", () => {
  for (const file of ["apps/web/src/lib/user_error.ts", "apps/mobile/lib/session.tsx"]) {
    assert.match(
      readFileSync(new URL(`../../${file}`, import.meta.url), "utf8"),
      /ownerProfileError\(/,
      file,
    );
  }
});
