import assert from "node:assert/strict";
import test from "node:test";
import type { AgentModelSummary } from "../../packages/contracts/src/index";
import {
  agentModelLabels,
  agentModelLines,
  offersDefaultModel,
  usageLine,
} from "../../packages/core/src/agent-model";

const sonnet = { provider: "anthropic" as const, model: "claude-sonnet", name: "Claude Sonnet" };

const summary: AgentModelSummary = {
  record: {
    owner_id: "owner",
    agent_id: "agent",
    revision: 2,
    preference: { primary: { provider: "anthropic", model: "claude-sonnet" }, fallbacks: [] },
    chosen_by: "owner",
    chosen_by_agent_id: "lonora",
    previous: null,
    changed_at: null,
  },
  current: sonnet,
  available: [{ ...sonnet }],
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

test("both languages carry every model label", () => {
  assert.deepEqual(
    Object.keys(agentModelLabels.ar).sort(),
    Object.keys(agentModelLabels.en).sort(),
  );
  for (const value of Object.values(agentModelLabels.ar)) assert.match(value, /[؀-ۿ]/);
});

test("usage lines are plain owner text", () => {
  assert.equal(
    usageLine({ input_tokens: 0, output_tokens: 0, requests: 0 }, 30, "en"),
    "No model use in the last 30 days.",
  );
  assert.match(
    usageLine({ input_tokens: 12300, output_tokens: 4100, requests: 18 }, 30, "en"),
    /^Last 30 days: ⁨12\.3K⁩ in · ⁨4\.1K⁩ out · ⁨18⁩ requests$/,
  );
});

test("the card says who chose the model: the owner, or Lonora's model inherited", () => {
  const lines = agentModelLines(summary, "en");
  assert.equal(lines[0], "Answering now: ⁨Claude Sonnet⁩");
  assert.equal(lines[1], "Chosen by you");
  assert.match(lines[2] ?? "", /^Last 30 days: /);
  assert.ok(!lines.join(" ").includes("{"));
  const inherited = { ...summary, record: { ...summary.record, chosen_by: "inherited" as const } };
  assert.equal(agentModelLines(inherited, "en")[1], "Lonora's model when it was created");
  assert.equal(agentModelLines(inherited, "ar")[1], agentModelLabels.ar.inherited);
  // No mode, no allowed list: nothing else is shown.
  assert.equal(lines.length, 3);
});

test("a model someone set offers the way back to the default, on Web and Mobile alike", () => {
  assert.equal(offersDefaultModel(summary), true);
  const onDefault = {
    ...summary,
    record: { ...summary.record, preference: { primary: null, fallbacks: [] } },
  };
  assert.equal(offersDefaultModel(onDefault), false);
});
