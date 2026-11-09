import assert from "node:assert/strict";
import { test } from "node:test";
import { type IncomingPolicy, reachMePayload } from "../../apps/mobile/lib/incoming-call";

const policy: IncomingPolicy = {
  channel: "message",
  enabled: false,
  device_id: null,
  opportunities: false,
  action_required: false,
  critical: true,
  timezone: "UTC",
  quiet_start_hour: null,
  quiet_end_hour: null,
  ttl_seconds: 45,
  minimum_interval_seconds: 300,
};
const devices = [{ id: "newest" }, { id: "older" }];

test("the channel decides; the derived enabled flag is never sent", () => {
  const saved = reachMePayload(policy, devices, { start: "", end: "" }, "Asia/Riyadh");
  assert.equal("enabled" in saved, false);
  assert.equal(saved.channel, "message");
  assert.equal(saved.device_id, null);
  assert.equal(saved.timezone, "Asia/Riyadh");
});

test("calling uses the chosen enrolled device, otherwise the newest one", () => {
  const call = { ...policy, channel: "call" as const };
  assert.equal(reachMePayload(call, devices, { start: "", end: "" }, "UTC").device_id, "newest");
  assert.equal(
    reachMePayload({ ...call, device_id: "older" }, devices, { start: "", end: "" }, "UTC")
      .device_id,
    "older",
  );
  assert.equal(
    reachMePayload({ ...call, device_id: "revoked" }, devices, { start: "", end: "" }, "UTC")
      .device_id,
    "newest",
  );
});

test("quiet hours are whole hours or cleared together", () => {
  const quiet = reachMePayload(policy, devices, { start: "22", end: "7" }, "");
  assert.deepEqual([quiet.quiet_start_hour, quiet.quiet_end_hour, quiet.timezone], [22, 7, "UTC"]);
  const invalid = reachMePayload(policy, devices, { start: "25", end: "x" }, "UTC");
  assert.deepEqual([invalid.quiet_start_hour, invalid.quiet_end_hour], [null, null]);
});
