import assert from "node:assert/strict";
import { test } from "node:test";
import config from "../../apps/mobile/app.config";

test("the Android build blocks the Wi-Fi permission that expo-network declares", () => {
  // expo-network needs it only for getIpAddressAsync, which Lonora never calls; the live
  // feed reads the network state through ConnectivityManager (ACCESS_NETWORK_STATE).
  assert.ok(config.android?.blockedPermissions?.includes("android.permission.ACCESS_WIFI_STATE"));
});
