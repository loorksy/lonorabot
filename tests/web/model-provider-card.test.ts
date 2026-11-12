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
      details: { provider: "openai_compatible" },
      fields: [
        { key: "URL", label: null, secret: false, role: "server_url", required: true },
        { key: "API_KEY", label: null, secret: true, role: "api_key", required: true },
      ],
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

test("an endpoint card is ours: its title, the saved name, its address and key typed", () => {
  assert.equal(ownerActionLabels.ar.connectModel, "ربط مزوّد نماذج");
  for (const locale of ["ar", "en"] as const) {
    const text = ownerActionLabels[locale];
    const spec = ownerActionCard(card, locale);
    assert.equal(spec.title, text.connectModel);
    // Replacing a saved key is said, never silent; no provider id is shown raw.
    assert.ok(spec.lines.some((line) => line.includes("OPENAI_COMPATIBLE_API_KEY")));
    assert.ok(!spec.lines.some((line) => line.includes("openai_compatible")));
    assert.equal(spec.hint, `${text.modelHint} ${text.modelEndpointHint}`);
    assert.deepEqual(spec.secret?.fields, [
      { key: "URL", label: text.fieldServerUrl, type: "url", required: true },
      { key: "API_KEY", label: text.fieldApiKey, type: "password", required: true },
    ]);
    assert.equal(spec.secret?.submit, text.connect);
  }
});

test("a fixed provider's card names it and asks only for the key", () => {
  const secret = card.facts.secret;
  assert.ok(secret);
  const fixed: OwnerAction = {
    ...card,
    facts: {
      ...card.facts,
      secret: {
        ...secret,
        details: { provider: "anthropic", name: "Anthropic" },
        fields: [{ key: "API_KEY", label: null, secret: true, role: "api_key", required: true }],
        saves_as: ["ANTHROPIC_API_KEY"],
        replaces: [],
      },
    },
  };
  for (const locale of ["ar", "en"] as const) {
    const text = ownerActionLabels[locale];
    const spec = ownerActionCard(fixed, locale);
    assert.ok(spec.lines.includes(`${text.fieldName}: ${isolated("Anthropic")}`));
    assert.equal(spec.hint, text.modelHint);
    assert.deepEqual(spec.secret?.fields, [
      { key: "API_KEY", label: text.fieldApiKey, type: "password", required: true },
    ]);
  }
});
