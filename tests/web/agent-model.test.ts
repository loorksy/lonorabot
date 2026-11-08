import assert from "node:assert/strict";
import test from "node:test";
import type { AgentModelSummary, OwnerAction } from "../../packages/contracts/src/index";
import {
  agentModelLabels,
  agentModelLines,
  modelCard,
  modelChoiceLine,
  usageLine,
} from "../../packages/core/src/agent-model";
import { ownerActionCard } from "../../packages/core/src/owner-actions";

const sonnet = { provider: "anthropic" as const, model: "claude-sonnet", name: "Claude Sonnet" };
const opus = { provider: "anthropic" as const, model: "claude-opus", name: "Claude Opus" };
const fallback = { provider: "openai" as const, model: "gpt-default", name: null };
const none = { provider: null, model: null, name: null };

const request: OwnerAction = {
  id: "card",
  kind: "agent_model",
  status: "pending",
  status_reason: null,
  source: "agent",
  agent_id: "agent",
  thread_id: "thread",
  run_id: "run",
  timeline_seq: 4,
  facts: {
    several_accounts: false,
    model: {
      agent_name: "Gold agent",
      default_model: fallback,
      current: { mode: "automatic", model: none },
      requested: { mode: "automatic", model: opus },
      allow: true,
    },
  },
  requires_passkey: false,
  result: {},
  expires_at: "2026-11-09T10:00:00Z",
  decided_at: null,
  decided_via: null,
  created_at: "2026-11-08T09:30:00Z",
  updated_at: "2026-11-08T09:30:00Z",
};
const undo: OwnerAction = {
  ...request,
  id: "undo",
  kind: "agent_model_changed",
  source: "system",
  facts: {
    several_accounts: false,
    model: {
      agent_name: "Gold agent",
      default_model: fallback,
      previous: { mode: "automatic", model: none },
      current: { mode: "automatic", model: sonnet },
    },
  },
};

test("both languages carry every model label", () => {
  assert.deepEqual(
    Object.keys(agentModelLabels.ar).sort(),
    Object.keys(agentModelLabels.en).sort(),
  );
  for (const value of Object.values(agentModelLabels.ar)) assert.match(value, /[؀-ۿ]/);
});

test("a model request card shows server facts, one tap and no passkey", () => {
  const spec = ownerActionCard(request, "en");
  assert.equal(spec.title, "Change the model of ⁨Gold agent⁩?");
  assert.equal(spec.passkey, false);
  assert.deepEqual(
    spec.buttons.map((button) => [button.label, button.decision]),
    [
      ["Use it", "confirm"],
      ["Not now", "cancel"],
    ],
  );
  assert.ok(spec.lines.some((line) => line.includes("your default model (⁨gpt-default⁩)")));
  assert.ok(spec.lines.some((line) => line.includes("⁨Claude Opus⁩ joins the models")));
  assert.match(spec.hint ?? "", /nothing is repeated/);
  const done = ownerActionCard({ ...request, status: "confirmed" }, "ar");
  assert.equal(done.buttons.length, 0);
  assert.match(done.outcome ?? "", /⁨Claude Opus⁩/);
});

test("the Undo card reads along the reading direction and says what happened", () => {
  const en = modelCard(undo, "en");
  assert.equal(en.title, "⁨Gold agent⁩ switched its model");
  assert.ok(en.lines[0]?.includes("→"));
  assert.deepEqual(
    en.buttons.map((button) => button.label),
    ["Undo", "Keep"],
  );
  const ar = modelCard(undo, "ar");
  assert.ok(ar.lines[0]?.includes("←"));
  assert.equal(modelCard({ ...undo, status: "cancelled" }, "en").outcome, "Kept.");
  assert.equal(
    modelCard({ ...undo, status: "superseded", status_reason: "model_changed_again" }, "en")
      .outcome,
    "Its model changed again since. Nothing changed.",
  );
  assert.equal(
    modelCard({ ...request, status: "superseded", status_reason: "owner_changed_model" }, "ar")
      .outcome,
    agentModelLabels.ar.ownerChanged,
  );
});

test("choice and usage lines are plain owner text", () => {
  assert.equal(
    modelChoiceLine({ mode: "fixed", model: opus }, fallback, "en"),
    "Fixed · ⁨Claude Opus⁩",
  );
  assert.equal(
    modelChoiceLine({ mode: "automatic", model: null }, fallback, "ar"),
    "تلقائي · نموذجك الافتراضي (⁨gpt-default⁩)",
  );
  assert.equal(
    usageLine({ input_tokens: 0, output_tokens: 0, requests: 0 }, 30, "en"),
    "No model use in the last 30 days.",
  );
  assert.match(
    usageLine({ input_tokens: 12300, output_tokens: 4100, requests: 18 }, 30, "en"),
    /^Last 30 days: ⁨12\.3K⁩ in · ⁨4\.1K⁩ out · ⁨18⁩ requests$/,
  );
  const summary: AgentModelSummary = {
    record: {
      owner_id: "owner",
      agent_id: "agent",
      revision: 2,
      mode: "automatic",
      preference: { primary: { provider: "anthropic", model: "claude-sonnet" }, fallbacks: [] },
      chosen_by: "agent",
      chosen_by_agent_id: "agent",
      previous: null,
      changed_at: null,
    },
    current: sonnet,
    allowed: [fallback, sonnet],
    available: [],
    connected_providers: ["anthropic", "openai"],
    usage: {
      days: 30,
      requests: 18,
      input_tokens: 12300,
      output_tokens: 4100,
      cached_tokens: 0,
      models: [],
    },
  };
  const lines = agentModelLines(summary, "en");
  assert.equal(lines[0], "Answering now: ⁨Claude Sonnet⁩");
  assert.equal(lines[1], "Set by the agent");
  assert.match(lines[2] ?? "", /^Models it may choose on its own: /);
  assert.ok(!lines.join(" ").includes("{"));
});
