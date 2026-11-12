import assert from "node:assert/strict";
import test from "node:test";
import type { OwnerAction } from "../../packages/contracts/src/index";
import {
  ownerActionCard,
  ownerActionLabels,
  submitSecret,
} from "../../packages/core/src/owner-actions";

const isolated = (value: string) => `⁨${value}⁩`;
const secret = {
  label: "مفاتيح بينانس",
  fields: [
    { key: "BINANCE_API_KEY", label: "مفتاح API", secret: true },
    { key: "BINANCE_USER", label: "اسم المستخدم", secret: false },
  ],
  destination: "workspace" as const,
  agent_name: "Gold",
};
const card: OwnerAction = {
  id: "card/1",
  kind: "secret",
  status: "pending",
  status_reason: null,
  source: "agent",
  agent_id: "gold",
  thread_id: "thread",
  run_id: "run",
  timeline_seq: 4,
  facts: {
    several_accounts: false,
    secret,
  },
  requires_passkey: false,
  result: {},
  expires_at: "2026-11-19T10:00:00Z",
  decided_at: null,
  decided_via: null,
  created_at: "2026-11-12T10:00:00Z",
  updated_at: "2026-11-12T10:00:00Z",
};

test("a Secret card shows the agent's label and fields and our own words", () => {
  for (const locale of ["ar", "en"] as const) {
    const text = ownerActionLabels[locale];
    const spec = ownerActionCard(card, locale);
    assert.equal(spec.title, text.secretTitle);
    // The agent's label and name are isolated inside the owner's language.
    assert.deepEqual(spec.lines, [
      isolated("مفاتيح بينانس"),
      text.secretAskedBy.replace("{agent}", isolated("Gold")),
    ]);
    assert.equal(spec.hint, text.secretWorkspace);
    assert.deepEqual(spec.secret, {
      fields: [
        { key: "BINANCE_API_KEY", label: "مفتاح API", type: "password" },
        { key: "BINANCE_USER", label: "اسم المستخدم", type: "text" },
      ],
      submit: text.secretSave,
    });
    // Save is the form's own submit; the only button is Not now.
    assert.deepEqual(
      spec.buttons.map((button) => [button.key, button.decision]),
      [["cancel", "cancel"]],
    );
    assert.equal(spec.credential, null);
    assert.equal(spec.outcome, null);
  }
  const broker = ownerActionCard(
    { ...card, facts: { ...card.facts, secret: { ...secret, destination: "broker" } } },
    "ar",
  );
  assert.equal(broker.hint, ownerActionLabels.ar.secretBroker);
});

test("a saved Secret card says so and shows no form", () => {
  const saved = ownerActionCard(
    {
      ...card,
      status: "confirmed",
      result: { saved: ["BINANCE_API_KEY", "BINANCE_USER"], destination: "workspace" },
    },
    "ar",
  );
  assert.equal(saved.secret, null);
  assert.deepEqual(saved.buttons, []);
  assert.equal(saved.outcome, ownerActionLabels.ar.secretSaved);
});

test("the values go only to the card's own route", async () => {
  const posted: Array<[string, unknown]> = [];
  const answer = await submitSecret(
    async (path, body) => {
      posted.push([path, body]);
      return { id: "card/1", status: "confirmed" };
    },
    "card/1",
    { BINANCE_API_KEY: "k", BINANCE_USER: "u" },
  );
  assert.deepEqual(posted, [
    ["/owner-actions/card%2F1/secret", { values: { BINANCE_API_KEY: "k", BINANCE_USER: "u" } }],
  ]);
  assert.deepEqual(answer, { id: "card/1", status: "confirmed" });
});

test("a broker connect card shows the account as server facts and only our own words", () => {
  const broker: OwnerAction = {
    ...card,
    id: "card/broker",
    facts: {
      several_accounts: false,
      secret: {
        label: "70000001 @ Exness-MT5Trial16",
        fields: [
          { key: "PASSWORD", label: "Trading password", secret: true },
          { key: "METAAPI_TOKEN", label: "MetaApi API token", secret: true },
        ],
        destination: "broker",
        agent_name: "Lonora",
        account: { login: "70000001", server: "Exness-MT5Trial16", platform: "mt5" },
      },
    },
  };
  for (const locale of ["ar", "en"] as const) {
    const text = ownerActionLabels[locale];
    const spec = ownerActionCard(broker, locale);
    assert.equal(spec.title, text.brokerConnectTitle);
    assert.equal(
      spec.lines[0],
      text.brokerAccount
        .replace("{login}", isolated("70000001"))
        .replace("{server}", isolated("Exness-MT5Trial16"))
        .replace("{platform}", "MT5"),
    );
    // Field labels are ours by key, never the stored English label; both are masked.
    assert.deepEqual(spec.secret?.fields, [
      { key: "PASSWORD", label: text.brokerPassword, type: "password" },
      { key: "METAAPI_TOKEN", label: text.brokerToken, type: "password" },
    ]);
    assert.equal(spec.hint, text.secretBroker);
    const saved = ownerActionCard({ ...broker, status: "confirmed", result: {} }, locale);
    assert.equal(saved.outcome, text.brokerSaved);
  }
});

test("a broker card for a new password or token is titled for what it changes", () => {
  for (const locale of ["ar", "en"] as const) {
    const text = ownerActionLabels[locale];
    for (const [purpose, title] of [
      ["rotate_password", text.brokerRotateTitle],
      ["replace_token", text.brokerTokenTitle],
    ] as const) {
      const spec = ownerActionCard(
        {
          ...card,
          facts: {
            several_accounts: false,
            secret: {
              label: "70000001 @ Exness-MT5Trial16",
              fields: [{ key: "PASSWORD", label: "Trading password", secret: true }],
              destination: "broker",
              agent_name: "Lonora",
              account: { login: "70000001", server: "Exness-MT5Trial16", platform: "mt5" },
              purpose,
            },
          },
        },
        locale,
      );
      assert.equal(spec.title, title);
    }
  }
});
