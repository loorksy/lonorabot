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
  kind: "trust_source",
  status: "pending",
  status_reason: null,
  source: "agent",
  agent_id: "news",
  thread_id: "thread",
  run_id: "run",
  timeline_seq: 3,
  facts: {
    several_accounts: false,
    source: {
      kind: "mcp_server",
      label: "X posts",
      subscribe: false,
      tools: ["search_posts", "user_timeline"],
      blocked: ["place_order"],
      review: false,
      tier: null,
    },
  },
  requires_passkey: false,
  result: {},
  expires_at: "2026-11-15T10:00:00Z",
  decided_at: null,
  decided_via: null,
  created_at: "2026-11-08T10:00:00Z",
  updated_at: "2026-11-08T10:00:00Z",
};

test("an MCP trust card lists the reviewed tools, the blocked ones and two tiers", () => {
  for (const locale of ["en", "ar"] as const) {
    const spec = ownerActionCard(base, locale);
    const text = ownerActionLabels[locale];
    assert.equal(spec.title, text.trustTitle);
    assert.ok(spec.lines[0]?.includes(isolated("X posts")), spec.lines[0]);
    assert.ok(spec.lines[1]?.includes(isolated("user_timeline")), spec.lines[1]);
    assert.ok(spec.lines[2]?.startsWith(text.trustBlocked), spec.lines[2]);
    // Every line starts in the owner's language, never with a Latin name.
    for (const line of spec.lines) assert.ok(!line.startsWith("⁨"), line);
    assert.deepEqual(
      spec.buttons.map((button) => [button.decision, button.tier ?? null]),
      [
        ["confirm", "read"],
        ["confirm", "write_nonfinancial"],
        ["cancel", null],
      ],
    );
    assert.equal(spec.passkey, false);
    assert.equal(spec.credential, null);
  }
  const review = ownerActionCard(
    {
      ...base,
      facts: {
        ...base.facts,
        source: { kind: "mcp_server", label: "X posts", subscribe: false, review: true },
      },
    },
    "en",
  );
  assert.equal(review.title, ownerActionLabels.en.trustReviewTitle);
  const done = ownerActionCard(
    { ...base, status: "confirmed", result: { tier: "write_nonfinancial" } },
    "ar",
  );
  assert.equal(done.outcome, ownerActionLabels.ar.trustedWrite);
  assert.deepEqual(done.buttons, []);
});

test("a repository or feed card is one tap, and a settled one says why", () => {
  const repo: OwnerAction = {
    ...base,
    facts: {
      several_accounts: false,
      source: { kind: "github_repo", label: "example/briefings", subscribe: false },
    },
  };
  const spec = ownerActionCard(repo, "en");
  assert.deepEqual(
    spec.buttons.map((button) => button.decision),
    ["confirm", "cancel"],
  );
  assert.ok(spec.lines[0]?.includes(isolated("example/briefings")));
  const feed = ownerActionCard(
    {
      ...repo,
      facts: {
        several_accounts: false,
        source: { kind: "feed_domain", label: "analyst.example", subscribe: true },
      },
    },
    "ar",
  );
  assert.ok(feed.lines.includes(ownerActionLabels.ar.trustSubscribe));
  const stale = ownerActionCard(
    { ...repo, status: "expired", status_reason: "source_already_trusted" },
    "ar",
  );
  assert.equal(stale.outcome, ownerActionLabels.ar.alreadyTrusted);
});

test("a credential card offers a secure form whose secret is a password field", () => {
  const card: OwnerAction = {
    ...base,
    kind: "connect_credential",
    facts: { several_accounts: false, credential: { target: "mcp_server", service: "x" } },
  };
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
    blocked_tools: [],
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
    trusted_tools: ["search_posts"],
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
    installed_at: "2026-11-08T10:00:00Z",
    updated_at: "2026-11-08T10:00:00Z",
  };
  for (const locale of ["en", "ar"] as const) {
    const text = capabilityLabels[locale];
    assert.ok(sourceLine(github, locale).startsWith(text.github));
    assert.ok(sourceLine({ ...github, active: false }, locale).endsWith(text.removedState));
    const line = serverLine(server, locale);
    assert.ok(line.startsWith(isolated("X posts")) && line.includes(text.read), line);
    assert.ok(skillLine(skill, locale).includes(isolated("example/briefings")));
    assert.equal(
      builtInLine({ capability: "web_browse", state: "not_set_up", via: null }, locale),
      `${text.web_browse}: ${text.not_set_up}`,
    );
  }
  assert.ok(ownerActionError("owner_action_tier_required", "ar"));
  assert.ok(ownerActionError("mcp_tools_changed", "en"));
});
