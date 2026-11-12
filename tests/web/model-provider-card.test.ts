import assert from "node:assert/strict";
import test from "node:test";
import type { OwnerAction } from "../../packages/contracts/src/index";
import { ownerActionCard, ownerActionLabels } from "../../packages/core/src/owner-actions";

const isolated = (value: string) => `⁨${value}⁩`;

const card: OwnerAction = {
  id: "card/model",
  kind: "secret",
  status: "pending",
  status_reason: null,
  source: "agent",
  agent_id: "lonora",
  thread_id: "thread",
  run_id: "run",
  timeline_seq: 4,
  facts: {
    several_accounts: false,
    secret: {
      label: null,
      connect: "model_provider",
      service: null,
      details: {
        name: "llm.example.test",
        provider: "openai_compatible",
        url: "https://llm.example.test/v1",
      },
      fields: [{ key: "API_KEY", label: null, secret: true, role: "api_key", required: true }],
      destination: "workspace",
      agent_name: "Lonora",
      saves_as: ["OPENAI_COMPATIBLE_API_KEY"],
      replaces: ["OPENAI_COMPATIBLE_API_KEY"],
    },
  },
  requires_passkey: false,
  result: {},
  expires_at: "2026-11-19T10:00:00Z",
  decided_at: null,
  decided_via: null,
  created_at: "2026-11-12T10:00:00Z",
  updated_at: "2026-11-12T10:00:00Z",
};

test("a model provider card is ours: its title, the endpoint, the saved name, a masked key", () => {
  assert.equal(ownerActionLabels.ar.connectModel, "ربط مزوّد نماذج");
  for (const locale of ["ar", "en"] as const) {
    const text = ownerActionLabels[locale];
    const spec = ownerActionCard(card, locale);
    assert.equal(spec.title, text.connectModel);
    assert.ok(spec.lines.includes(`${text.fieldName}: ${isolated("llm.example.test")}`));
    assert.ok(
      spec.lines.includes(`${text.fieldServerUrl}: ${isolated("https://llm.example.test/v1")}`),
    );
    // Replacing a saved key is said, never silent; no provider id is shown raw.
    assert.ok(spec.lines.some((line) => line.includes("OPENAI_COMPATIBLE_API_KEY")));
    assert.ok(!spec.lines.some((line) => line.includes("openai_compatible")));
    assert.equal(spec.hint, text.connectHint);
    assert.deepEqual(spec.secret?.fields, [
      { key: "API_KEY", label: text.fieldApiKey, type: "password", required: true },
    ]);
    assert.equal(spec.secret?.submit, text.connect);
  }
});
