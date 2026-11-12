import assert from "node:assert/strict";
import test from "node:test";
import type {
  CapabilityServer,
  CapabilitySkill,
  OwnerAction,
  TrustedSource,
} from "../../packages/contracts/src/index";
import {
  builtInLine,
  capabilityLabels,
  serverLine,
  skillLine,
  sourceLine,
} from "../../packages/core/src/capabilities";
import {
  ownerActionCard,
  ownerActionError,
  ownerActionLabels,
} from "../../packages/core/src/owner-actions";

const isolated = (value: string) => `⁨${value}⁩`;
const base: OwnerAction = {
  id: "card",
  kind: "secret",
  status: "pending",
  status_reason: null,
  source: "agent",
  agent_id: "news",
  thread_id: "thread",
  run_id: "run",
  timeline_seq: 3,
  facts: { several_accounts: false },
  requires_passkey: false,
  result: {},
  expires_at: "2026-11-15T10:00:00Z",
  decided_at: null,
  decided_via: null,
  created_at: "2026-11-08T10:00:00Z",
  updated_at: "2026-11-08T10:00:00Z",
};

test("a connecting Secret card shows the agent's details and asks for the address and secret", () => {
  const card: OwnerAction = {
    ...base,
    kind: "secret",
    facts: {
      several_accounts: false,
      secret: {
        label: null,
        connect: "mcp_server",
        service: "x",
        details: { name: "X" },
        fields: [
          { key: "URL", label: null, secret: false, role: "server_url", required: true },
          { key: "TOKEN", label: null, secret: true, role: "token", required: false },
        ],
        destination: "workspace",
        agent_name: "News",
        saves_as: ["MCP_X_URL", "MCP_X_TOKEN"],
      },
    },
  };
  for (const locale of ["en", "ar"] as const) {
    const spec = ownerActionCard(card, locale);
    const text = ownerActionLabels[locale];
    assert.equal(spec.title, text.connectX);
    assert.ok(spec.hint?.includes(text.connectXHint));
    // The address may carry a key: the owner types it into the card, never into chat.
    assert.ok(!spec.lines.some((line) => line.includes("https://")));
    assert.ok(
      spec.lines.some((line) => line.includes("MCP_X_URL") && line.includes("MCP_X_TOKEN")),
    );
    assert.deepEqual(spec.secret, {
      fields: [
        { key: "URL", label: text.fieldServerUrl, type: "url", required: true },
        { key: "TOKEN", label: text.fieldToken, type: "password", required: false },
      ],
      submit: text.connect,
    });
    // Connect is the form's own submit; the only button sends nothing but a cancel.
    assert.deepEqual(
      spec.buttons.map((button) => button.decision),
      ["cancel"],
    );
  }
  // A credential card converted by migration 0071 still reads as what it connected; a
  // trading account is now connected with broker_connect's own card.
  const converted = ownerActionCard(
    {
      ...card,
      status: "confirmed",
      result: { target: "broker", configured: true },
      facts: {
        several_accounts: false,
        secret: {
          label: null,
          connect: "broker",
          service: null,
          details: {},
          fields: [{ key: "METAAPI_TOKEN", label: null, secret: true, role: null }],
          destination: "broker",
          agent_name: null,
        },
      },
    },
    "en",
  );
  assert.equal(converted.title, ownerActionLabels.en.connectBroker);
  assert.equal(converted.outcome, ownerActionLabels.en.connected);
  assert.equal(converted.secret, null);
  const feed = ownerActionCard(
    {
      ...card,
      facts: {
        several_accounts: false,
        secret: {
          label: null,
          connect: "news_feed",
          service: null,
          details: { name: "Desk" },
          fields: [{ key: "URL", label: null, secret: false, role: "feed_url", required: true }],
          destination: "workspace",
          agent_name: null,
        },
      },
    },
    "ar",
  );
  // A feed's address may carry a key: it is stored encrypted, but shown while typed.
  assert.deepEqual(
    feed.secret?.fields.map((field) => [field.type, field.label]),
    [["url", ownerActionLabels.ar.fieldFeedUrl]],
  );
  const settled = ownerActionCard({ ...card, status: "confirmed" }, "en");
  assert.equal(settled.secret, null);
  assert.equal(settled.outcome, ownerActionLabels.en.connected);
});

test("capability lines name source, tier and state in both languages", () => {
  const github: TrustedSource = {
    id: "s",
    kind: "github",
    identifier: "github.com",
    label: "github.com",
    effect_tier: "read",
    tools: [],
    write_tools: [],
    blocked_tools: [],
    needs_review: false,
    added_via: "default",
    added_by_agent_name: null,
    active: true,
    created_at: "2026-11-08T10:00:00Z",
    updated_at: "2026-11-08T10:00:00Z",
    last_used_at: null,
    revoked_at: null,
  };
  const server: CapabilityServer = {
    connection_id: "c",
    name: "X posts",
    enabled: true,
    credentials_configured: true,
    trusted_tier: "read",
    trusted_tools: ["post_reply", "search_posts"],
    write_tools: ["post_reply"],
    blocked_tools: ["place_order"],
    operator_declared: 0,
    trust_source_id: "t",
    last_used_at: null,
  };
  const skill: CapabilitySkill = {
    resource_id: "r",
    agent_id: "a",
    agent_name: "News",
    skill_id: "briefing",
    version: "1.0.0",
    provenance: "external",
    repository: "example/briefings",
    commit: "a".repeat(40),
    enabled: true,
    undone: false,
    can_undo: true,
    installed_at: "2026-11-08T10:00:00Z",
    updated_at: "2026-11-08T10:00:00Z",
  };
  for (const locale of ["en", "ar"] as const) {
    const text = capabilityLabels[locale];
    assert.ok(sourceLine(github, locale).startsWith(text.github));
    assert.ok(sourceLine({ ...github, active: false }, locale).endsWith(text.removedState));
    // A source an agent added because the owner's own message named it says so.
    const named: TrustedSource = {
      ...github,
      kind: "feed_domain",
      identifier: "analyst.example",
      label: "analyst.example",
      added_via: "owner_message",
    };
    assert.ok(sourceLine(named, locale).includes(text.owner_message), sourceLine(named, locale));
    const line = serverLine(server, locale);
    assert.ok(line.startsWith(isolated("X posts")) && line.includes(text.read), line);
    // Trusted for reading: the tool that may change something is counted as waiting.
    assert.ok(line.includes(`${isolated("1")} ${text.needWrites}`), line);
    assert.ok(
      !serverLine({ ...server, trusted_tier: "write_nonfinancial" }, locale).includes(
        text.needWrites,
      ),
    );
    // An operator entry whose declaration is gone says it waits for a review.
    const operator: TrustedSource = {
      ...github,
      kind: "mcp_server",
      identifier: "c",
      label: "Declared",
      tools: ["search_posts"],
      added_via: "operator",
      needs_review: true,
    };
    const declared = sourceLine(operator, locale);
    assert.ok(declared.includes(text.needsReview) && !declared.includes(text.read), declared);
    assert.ok(skillLine(skill, locale).includes(isolated("example/briefings")));
    assert.ok(skillLine({ ...skill, undone: true, can_undo: false }, locale).endsWith(text.undone));
    assert.equal(
      builtInLine({ capability: "web_browse", state: "not_set_up", via: null }, locale),
      `${text.web_browse}: ${text.not_set_up}`,
    );
  }
  assert.equal(ownerActionError("owner_action_tier_required", "ar"), null);
  assert.ok(ownerActionError("trusted_source_write_blocked", "ar"));
  assert.ok(ownerActionError("mcp_tools_changed", "en"));
});
