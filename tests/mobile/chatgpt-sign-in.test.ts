// The Android Secret card for the ChatGPT plan (VISION Amendment 4) renders the shared spec:
// Continue with ChatGPT, then the pasted address, in the owner's language, and its run
// banner names the plan's own limit with Manage usage. The logic is packages/core's.
import assert from "node:assert/strict";
import test from "node:test";
import type { OwnerAction, Run } from "../../packages/contracts/src";
import { chatgptLabels, planLimitReached } from "../../packages/core/src/chatgpt-plan";
import { ownerActionCard } from "../../packages/core/src/owner-actions";

const pending = {
  id: "card-1",
  kind: "secret",
  status: "pending",
  status_reason: null,
  source: "agent",
  agent_id: "lonora",
  thread_id: "t",
  run_id: "r",
  timeline_seq: 1,
  facts: {
    several_accounts: false,
    secret: {
      label: null,
      connect: "model_provider",
      details: { provider: "openai_chatgpt", name: "ChatGPT" },
      fields: [],
      destination: "workspace",
      agent_name: null,
      saves_as: [],
      replaces: [],
    },
  },
  requires_passkey: false,
  result: {},
  expires_at: "2026-12-01T00:00:00Z",
  decided_at: null,
  decided_via: null,
  created_at: "2026-11-26T00:00:00Z",
  updated_at: "2026-11-26T00:00:00Z",
} as unknown as OwnerAction;

test("the Android card offers the sign-in, not a key field, until it settles", () => {
  for (const locale of ["ar", "en"] as const) {
    const spec = ownerActionCard(pending, locale);
    assert.equal(spec.secret, null);
    assert.equal(spec.signIn?.continue, chatgptLabels[locale].continue);
    assert.equal(spec.signIn?.address, chatgptLabels[locale].address);
    // Only Not now remains as a button: the sign-in is the form's own.
    assert.deepEqual(
      spec.buttons.map((button) => button.key),
      ["cancel"],
    );
  }
  const cancelled = ownerActionCard({ ...pending, status: "cancelled" }, "ar");
  assert.equal(cancelled.signIn, null);
});

test("the run banner names the ChatGPT plan's limit only for the plan's quota failure", () => {
  const failed = (failure: Run["failure"]) => ({ status: "failed", failure }) as Run;
  assert.ok(
    planLimitReached(
      failed({ family: "quota", retry_after_seconds: null, provider: "openai_chatgpt" }).failure,
    ),
  );
  assert.ok(!planLimitReached(failed({ family: "quota", retry_after_seconds: null }).failure));
  assert.ok(!planLimitReached(failed(null).failure));
});
