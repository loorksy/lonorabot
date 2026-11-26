import assert from "node:assert/strict";
import { test } from "node:test";
import {
  holdSetupToken,
  parseConnectLink,
  takeSetupToken,
} from "../../apps/mobile/lib/connect-link.ts";

const TOKEN = "abcdefghijklmnopqrstuvwxyz012345";

test("an https server and its setup token are accepted", () => {
  assert.deepEqual(parseConnectLink("https://sara.lonora.app/", TOKEN), {
    server: "https://sara.lonora.app",
    host: "sara.lonora.app",
    token: TOKEN,
  });
  assert.equal(parseConnectLink("https://sara.lonora.app", undefined)?.token, null);
  assert.equal(parseConnectLink("https://sara.lonora.app", "short")?.token, null);
});

test("plain http is accepted only for local addresses", () => {
  assert.equal(parseConnectLink("http://sara.lonora.app", TOKEN), null);
  for (const local of [
    "http://localhost:8080",
    "http://192.168.1.20",
    "http://10.0.0.5",
    "http://172.20.1.1",
    "http://lonora.local",
  ]) {
    assert.ok(parseConnectLink(local, TOKEN), local);
  }
  assert.equal(parseConnectLink("http://172.40.1.1", TOKEN), null);
});

test("credentials, queries, fragments and other schemes are refused", () => {
  for (const bad of [
    "https://u:p@sara.lonora.app",
    "https://sara.lonora.app/?x=1",
    "https://sara.lonora.app/#a",
    "javascript:alert(1)",
    "ftp://x",
    "",
    42,
  ]) {
    assert.equal(parseConnectLink(bad, TOKEN), null, String(bad));
  }
});

test("the held token is taken once", () => {
  holdSetupToken(TOKEN);
  assert.equal(takeSetupToken(), TOKEN);
  assert.equal(takeSetupToken(), null);
});
