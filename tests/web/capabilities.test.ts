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
  submitCredential,
} from "../../packages/core/src/owner-actions";

const isolated = (value: string) => `⁨${value}⁩`;
const base: OwnerAction = {
  id: "card",
  kind: "connect_credential",
  status: "pending",
  status_reason: null,
  source: "agent",
  agent_id: "news",
  thread_id: "thread",
  run_id: "run",
  timeline_seq: 3,
  facts: { several_accounts: false, credential: { target: "mcp_server", service: "x" } },
  requires_passkey: false,
  result: {},
  expires_at: "2026-11-15T10:00:00Z",
  decided_at: null,
  decided_via: null,
  created_at: "2026-11-08T10:00:00Z",
  updated_at: "2026-11-08T10:00:00Z",
};

test("a credential card offers a secure form whose secret is a password field", () => {
  const card = base;
  for (const locale of ["en", "ar"] as const) {
    const spec = ownerActionCard(card, locale);
    const text = ownerActionLabels[locale];
    assert.equal(spec.title, text.connectX);
    assert.ok(spec.hint?.includes(text.connectXHint));
    assert.deepEqual(
      spec.credential?.fields.map((field) => [field.key, field.type, field.required]),
      [
        ["name", "text", true],
        ["url", "url", true],
        ["secret", "password", false],
      ],
    );
    assert.equal(spec.credential?.fields[0]?.initial, "X");
    // Connect is the form's own submit; the only button sends nothing but a cancel.
    assert.deepEqual(
      spec.buttons.map((button) => button.decision),
      ["cancel"],
    );
  }
  const broker = ownerActionCard(
    {
      ...card,
      facts: { several_accounts: false, credential: { target: "broker", service: null } },
    },
    "en",
  );
  assert.deepEqual(
    broker.credential?.fields.map((field) => field.key),
    ["account", "secret"],
  );
  const settled = ownerActionCard({ ...card, status: "confirmed" }, "en");
  assert.equal(settled.credential, null);
  assert.equal(settled.outcome, ownerActionLabels.en.connected);
});

test("the form posts the value only to the owner API and names what it created", async () => {
  const calls: Array<[string, unknown]> = [];
  const post = async (path: string, body: unknown) => {
    calls.push([path, body]);
    return { id: path === "/integrations/secrets" ? "secret-id" : "resource-id" };
  };
  const connected = await submitCredential(post, "mcp_server", {
    name: "X",
    url: " https://mcp.example.test/rpc ",
    secret: "token-value",
  });
  assert.deepEqual(connected, { resource: "mcp", id: "resource-id" });
  assert.deepEqual(
    calls.map(([path]) => path),
    ["/integrations/secrets", "/mcp"],
  );
  const server = calls[1]?.[1] as { payload: Record<string, unknown> };
  assert.equal(server.payload.secret_id, "secret-id");
  assert.equal(server.payload.url, "https://mcp.example.test/rpc");
  assert.ok(!JSON.stringify(server).includes("token-value"));
  calls.length = 0;
  assert.deepEqual(
    await submitCredential(post, "news_feed", { name: "Desk", url: "https://a.b/rss" }),
    {
      resource: "integration",
      id: "resource-id",
    },
  );
  assert.deepEqual(
    calls.map(([path]) => path),
    ["/integrations"],
  );
  calls.length = 0;
  await submitCredential(post, "broker", { account: "acct", secret: "metaapi" });
  assert.deepEqual(
    calls.map(([path]) => path),
    ["/trading/connections"],
  );
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
      builtInLine({ capability: "web_browse", state: "ready", via: null }, locale),
      `${text.web_browse}: ${text.ready}`,
    );
  }
  assert.equal(ownerActionError("owner_action_tier_required", "ar"), null);
  assert.ok(ownerActionError("trusted_source_write_blocked", "ar"));
  assert.ok(ownerActionError("mcp_tools_changed", "en"));
});
