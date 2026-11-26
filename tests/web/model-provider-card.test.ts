import assert from "node:assert/strict";
import test from "node:test";
import type { AgentModelSummary, OwnerAction } from "../../packages/contracts/src/index";
import { agentModelLines, usesChatGptPlan } from "../../packages/core/src/agent-model";
import {
  chatgptLabels,
  chatgptRow,
  continuingAsLine,
  finishChatGptSignIn,
  isChatGptCard,
  MANAGE_USAGE_URL,
  planLimitReached,
  signOutChatGpt,
  signOutLine,
  startChatGptSignIn,
} from "../../packages/core/src/chatgpt-plan";
import {
  ownerActionCard,
  ownerActionError,
  ownerActionLabels,
} from "../../packages/core/src/owner-actions";

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

test("an endpoint card is ours: its title, the saved key by its label, its address and key typed", () => {
  assert.equal(ownerActionLabels.ar.connectModel, "ربط مزوّد نماذج");
  // The key is a workspace secret: commands in the workspace that name it receive it.
  assert.match(ownerActionLabels.ar.modelHint, /مساحة العمل/);
  assert.match(ownerActionLabels.en.modelHint, /workspace/);
  for (const locale of ["ar", "en"] as const) {
    const text = ownerActionLabels[locale];
    const spec = ownerActionCard(card, locale);
    assert.equal(spec.title, text.connectModel);
    // Replacing a saved key is said, never silent, by its field's label: no provider id or
    // workspace name is shown raw (17). The address is not saved under a name.
    assert.ok(
      spec.lines.includes(text.secretReplaces.replace("{fields}", isolated(text.fieldApiKey))),
    );
    assert.ok(
      spec.lines.includes(text.secretSavesAs.replace("{fields}", isolated(text.fieldApiKey))),
    );
    assert.ok(!spec.lines.some((line) => /openai_compatible|OPENAI_COMPATIBLE/.test(line)));
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

const chatgpt: OwnerAction = {
  ...card,
  id: "card/chatgpt",
  facts: {
    ...card.facts,
    secret: {
      label: null,
      connect: "model_provider",
      service: null,
      details: { provider: "openai_chatgpt", name: "ChatGPT" },
      fields: [],
      destination: "workspace",
      agent_name: "Lonora",
      saves_as: [],
      replaces: [],
    },
  },
};

test("the ChatGPT plan card signs in instead of asking for a key, and says the paste step first", () => {
  assert.ok(isChatGptCard(chatgpt) && !isChatGptCard(card));
  for (const locale of ["ar", "en"] as const) {
    const plan = chatgptLabels[locale];
    const spec = ownerActionCard(chatgpt, locale);
    assert.equal(spec.title, plan.title);
    assert.equal(spec.secret, null);
    assert.deepEqual(spec.signIn, {
      continue: plan.continue,
      address: plan.address,
      submit: plan.connect,
      otherAccount: plan.otherAccount,
    });
    // The second step is said before it happens: the page does not open on a server.
    assert.deepEqual(spec.lines.slice(0, 3), [plan.plan, plan.stepSignIn, plan.stepPaste]);
    assert.equal(spec.hint, plan.hint);
  }
  assert.equal(chatgptLabels.en.continue, "Continue with ChatGPT");
  assert.match(chatgptLabels.ar.stepPaste, /انسخ عنوانها كاملاً من شريط العنوان والصقه هنا/);
  assert.equal(chatgptLabels.ar.title, "استخدم اشتراك ChatGPT");
});

test("the settled ChatGPT card names the account, and no form is left", () => {
  const done: OwnerAction = {
    ...chatgpt,
    status: "confirmed",
    result: { target: "model_provider", configured: true, saved: [], account: "o@example.test" },
  };
  for (const locale of ["ar", "en"] as const) {
    const spec = ownerActionCard(done, locale);
    assert.equal(spec.signIn, null);
    assert.equal(
      spec.outcome,
      chatgptLabels[locale].connected.replace("{account}", isolated("o@example.test")),
    );
  }
  const unnamed = ownerActionCard({ ...done, result: { ...done.result, account: null } }, "en");
  assert.equal(unnamed.outcome, chatgptLabels.en.connectedNoAccount);
});

test("the sign-in posts only to the card's own routes, the address trimmed", async () => {
  const posts: [string, unknown][] = [];
  const post = async (path: string, body: unknown) => {
    posts.push([path, body]);
    return { authorization_url: "https://example.test/authorize", expires_at: "x" };
  };
  await startChatGptSignIn(post, "card/chatgpt");
  await startChatGptSignIn(post, "card/chatgpt", true);
  await finishChatGptSignIn(post, "card/chatgpt", "  http://127.0.0.1:1455/auth/callback?code=c  ");
  await signOutChatGpt(async (path, body) => {
    posts.push([path, body]);
    return { signed_out: true, revoked: false };
  });
  assert.deepEqual(posts, [
    ["/owner-actions/card%2Fchatgpt/chatgpt/start", {}],
    ["/owner-actions/card%2Fchatgpt/chatgpt/start", { new_account: true }],
    [
      "/owner-actions/card%2Fchatgpt/chatgpt/finish",
      { address: "http://127.0.0.1:1455/auth/callback?code=c" },
    ],
    ["/providers/openai_chatgpt/sign-out", {}],
  ]);
  assert.equal(signOutLine({ signed_out: true, revoked: true }, "en"), chatgptLabels.en.signedOut);
  assert.equal(
    signOutLine({ signed_out: true, revoked: false }, "ar"),
    chatgptLabels.ar.revocationUnconfirmed,
  );
});

test("each sign-in refusal has its own text in both languages, never the provider's", () => {
  for (const code of [
    "chatgpt_sign_in_unavailable",
    "chatgpt_sign_in_expired",
    "chatgpt_address_invalid",
    "chatgpt_state_mismatch",
    "chatgpt_sign_in_declined",
    "chatgpt_sign_in_failed",
    "chatgpt_sign_in_code_expired",
    "chatgpt_client_mismatch",
    "chatgpt_identity_invalid",
    "chatgpt_other_account",
    "chatgpt_plan_use_declined",
    "chatgpt_unreachable",
    "chatgpt_sign_in_required",
  ]) {
    const en = ownerActionError(code, "en");
    const ar = ownerActionError(code, "ar");
    assert.ok(en && ar && en !== ar, code);
  }
  assert.match(ownerActionError("chatgpt_sign_in_unavailable", "en") ?? "", /OpenAI API key/);
  // An exchange that did not complete is started again; the issued registration is kept.
  assert.match(ownerActionError("chatgpt_unreachable", "en") ?? "", /start again/);
  assert.doesNotMatch(ownerActionError("chatgpt_unreachable", "en") ?? "", /Nothing changed/);
  assert.match(
    ownerActionError("chatgpt_other_account", "en") ?? "",
    /Use a different ChatGPT account/,
  );
});

test("an attempt names the account it continues and offers another one", () => {
  assert.equal(continuingAsLine(null, "en"), null);
  assert.equal(
    continuingAsLine("o@example.test", "en"),
    chatgptLabels.en.continuingAs.replace("{account}", isolated("o@example.test")),
  );
  assert.equal(
    continuingAsLine("o@example.test", "ar"),
    chatgptLabels.ar.continuingAs.replace("{account}", isolated("o@example.test")),
  );
  assert.equal(chatgptLabels.en.otherAccount, "Use a different ChatGPT account");
});

test("the providers list keeps Sign out while a sign-in holds tokens, plan use or not", () => {
  const status = { email: "o@example.test", plan: false, sign_in_again: false, signed_in: false };
  // Never signed in, or signed out: no row.
  assert.equal(chatgptRow(undefined, "en"), null);
  assert.equal(chatgptRow(status, "en"), null);
  for (const locale of ["ar", "en"] as const) {
    const text = chatgptLabels[locale];
    assert.deepEqual(chatgptRow({ ...status, plan: true, signed_in: true }, locale), {
      line: text.usingPlan,
      signOut: true,
    });
    // Plan use declined at sign-in, or the sign-in turned off: still signed in.
    assert.deepEqual(chatgptRow({ ...status, signed_in: true }, locale), {
      line: text.planNotUsed,
      signOut: true,
    });
    // A refused renewal cleared the tokens: sign in again, nothing to sign out.
    assert.deepEqual(chatgptRow({ ...status, sign_in_again: true }, locale), {
      line: text.signInAgain,
      signOut: false,
    });
  }
});

test("the plan's model line and its limit link to ChatGPT's usage settings", () => {
  assert.equal(MANAGE_USAGE_URL, "https://chatgpt.com/settings/usage");
  assert.ok(planLimitReached({ family: "quota", provider: "openai_chatgpt" }));
  assert.ok(!planLimitReached({ family: "quota", provider: "openai" }));
  assert.ok(!planLimitReached({ family: "rate", provider: "openai_chatgpt" }));
  const summary = {
    current: { provider: "openai_chatgpt", model: "gpt-6.1-sol", name: "GPT-6.1 Sol" },
    record: { preference: { primary: null, fallbacks: [] }, chosen_by: null },
    usage: { input_tokens: 0, output_tokens: 0, requests: 0, days: 7 },
  } as unknown as AgentModelSummary;
  assert.ok(usesChatGptPlan(summary));
  assert.ok(agentModelLines(summary, "en").includes("Using ChatGPT plan"));
  assert.ok(agentModelLines(summary, "ar").includes(chatgptLabels.ar.usingPlan));
});
