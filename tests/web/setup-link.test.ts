import assert from "node:assert/strict";
import { test } from "node:test";
import { setupTokenFromHash } from "../../apps/web/src/lib/setup-link.ts";

test("a setup link's fragment yields its token", () => {
  assert.equal(
    setupTokenFromHash("#token=abcdefghijklmnopqrstuvwxyz_-0123"),
    "abcdefghijklmnopqrstuvwxyz_-0123",
  );
  assert.equal(
    setupTokenFromHash("token=abcdefghijklmnopqrstuvwxyz"),
    "abcdefghijklmnopqrstuvwxyz",
  );
  assert.equal(
    setupTokenFromHash("#a=1&token=abcdefghijklmnopqrstuvwxyz"),
    "abcdefghijklmnopqrstuvwxyz",
  );
});

test("anything that is not a plausible token is ignored", () => {
  assert.equal(setupTokenFromHash(""), null);
  assert.equal(setupTokenFromHash("#/app/chats"), null);
  assert.equal(setupTokenFromHash("#token=short"), null);
  assert.equal(setupTokenFromHash("#token=<script>alert(1)</script>xxxxxxxxxxxx"), null);
  assert.equal(setupTokenFromHash(`#token=${"a".repeat(129)}`), null);
});
