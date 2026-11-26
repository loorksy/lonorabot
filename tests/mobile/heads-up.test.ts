// The heads-up banner's rules on mobile, as on Web's HeadsUp: an agent's answer in another chat
// shows; the open chat, muted or archived chats, the owner's quiet hours, an agent whose in-app
// rule is off and anything from before the app opened do not; an urgent attention item always
// shows on its agent's row.
import assert from "node:assert/strict";
import test from "node:test";
import { attentionTitle } from "../../apps/mobile/lib/attention-labels";
import { attentionBanner, messageBanner } from "../../apps/mobile/lib/heads-up";
import { translate } from "../../apps/mobile/lib/i18n";
import type { Event } from "../../packages/contracts/src";

const row = (id: string, fields: Record<string, unknown> = {}) =>
  ({
    key: `agent:${id}`,
    kind: "agent",
    id,
    threadId: `t-${id}`,
    name: `Agent ${id}`,
    subtitle: "",
    paused: false,
    lastActivityAt: "",
    entry: { thread_id: `t-${id}`, muted: false, archived: false },
    ...fields,
  }) as never;
const opened = Date.parse("2026-11-12T08:00:00Z");
const event = (thread: string, payload: Record<string, unknown> = {}): Event => ({
  cursor: 1,
  kind: "message.created",
  thread_id: thread,
  agent_id: "a",
  run_id: null,
  created_at: "2026-11-12T08:01:00Z",
  payload: {
    role: "assistant",
    agent_id: "a",
    content: "Gold broke 2,425; I added 0.05.",
    created_at: "2026-11-12T08:01:00Z",
    ...payload,
  },
});
const base = {
  rows: [row("a"), row("b", { entry: { thread_id: "t-b", muted: true, archived: false } })],
  agents: [],
  current: undefined as string | undefined,
  quiet: null,
  off: new Set<string>(),
  openedAt: opened,
  now: new Date("2026-11-12T08:01:00Z"),
  newMessage: "New message",
};

test("an answer in another chat shows with its text", () => {
  const banner = messageBanner(event("t-a"), base);
  assert.equal(banner?.row.id, "a");
  assert.equal(banner?.text, "Gold broke 2,425; I added 0.05.");
});

test("the banner reads one plain line: no Markdown marks, a signed number kept whole", () => {
  const banner = messageBanner(
    event("t-a", { content: "**الذهب** ارتفع\n| XAUUSD | +1.5% |" }),
    base,
  );
  assert.equal(banner?.text, "الذهب ارتفع XAUUSD · \u2066+1.5%\u2069");
});

test("a cut answer never leaves a number's isolate open", () => {
  const banner = messageBanner(event("t-a", { content: `${"x".repeat(118)} +3.1% more` }), base);
  const text = banner?.text ?? "";
  assert.equal(text.at(-1), "…");
  assert.equal(text.split("\u2066").length, text.split("\u2069").length);
});

test("the open chat, a muted chat, the owner's own messages and old news do not show", () => {
  assert.equal(messageBanner(event("t-a"), { ...base, current: "t-a" }), null);
  assert.equal(messageBanner(event("t-b"), base), null);
  assert.equal(messageBanner(event("t-a", { role: "user" }), base), null);
  assert.equal(messageBanner({ ...event("t-a"), kind: "run.delta" }, base), null);
  assert.equal(messageBanner(event("t-a", { created_at: "2026-11-12T07:50:00Z" }), base), null);
  assert.equal(messageBanner(event("t-zz"), base), null);
});

test("quiet hours and an agent's in-app rule off silence it", () => {
  const quiet = { quiet_start_hour: 7, quiet_end_hour: 9, timezone: "UTC" };
  assert.equal(messageBanner(event("t-a"), { ...base, quiet }), null);
  assert.equal(messageBanner(event("t-a"), { ...base, off: new Set(["a"]) }), null);
});

test("a long answer is cut; an empty one says «New message»; a group names the speaker apart", () => {
  const long = messageBanner(event("t-a", { content: "x".repeat(300) }), base);
  assert.equal(long?.text.length, 121);
  assert.equal(messageBanner(event("t-a", { content: "  " }), base)?.text, "New message");
  const group = row("g", {
    kind: "group",
    key: "group:g",
    threadId: "t-g",
    entry: { thread_id: "t-g" },
  });
  const said = messageBanner(event("t-g"), {
    ...base,
    rows: [group],
    agents: [{ id: "a", name: "Gold" }] as never,
  });
  // The speaker stays apart from the words, so each keeps its own direction (as Web).
  assert.equal(said?.who, "Gold:");
  assert.equal(said?.text, "Gold broke 2,425; I added 0.05.");
  assert.equal(messageBanner(event("t-a"), base)?.who, undefined);
});

test("an urgent attention item always shows on its agent's row; an informational one does not", () => {
  const lonora = row("l", { agent: { role: "personal" } });
  const item = (fields: Record<string, unknown>) =>
    ({
      id: "n1",
      code: "approval_required",
      importance: "action_required",
      agent_id: "a",
      parameters: { summary: "Approve buy 0.10 XAUUSD" },
      created_at: "2026-11-12T08:01:00Z",
      ...fields,
    }) as never;
  const labels = {} as Record<string, string>;
  const shown = attentionBanner(item({}), { rows: [row("a"), lonora], openedAt: opened, labels });
  assert.equal(shown?.row.id, "a");
  assert.equal(shown?.text, "Approve buy 0.10 XAUUSD");
  // A long summary is cut between words before its numbers are isolated: «+3.1%» goes whole,
  // never «+3…».
  const long = attentionBanner(item({ parameters: { summary: `${"x".repeat(117)} +3.1% more` } }), {
    rows: [row("a")],
    openedAt: opened,
    labels,
  });
  assert.equal(long?.text, `${"x".repeat(117)}…`);
  assert.equal(
    attentionBanner(item({ importance: "info" }), { rows: [row("a")], openedAt: opened, labels }),
    null,
  );
});

test("urgent items: old ones stay quiet, a group's shows on its row, a broker outage on Lonora's", () => {
  const lonora = row("l", { agent: { role: "personal" } });
  const group = row("g", { kind: "group", key: "group:g" });
  const item = (fields: Record<string, unknown>) =>
    ({
      id: "n",
      code: "approval_required",
      importance: "action_required",
      agent_id: "a",
      parameters: {},
      created_at: "2026-11-12T08:01:00Z",
      ...fields,
    }) as never;
  const context = {
    rows: [row("a"), group, lonora],
    openedAt: opened,
    labels: { approval_required: "Waiting for approval", broker_connection_lost: "Broker lost" },
  };
  // The label stands in for a missing summary.
  assert.equal(attentionBanner(item({}), context)?.text, "Waiting for approval");
  assert.equal(attentionBanner(item({ created_at: "2026-11-12T07:00:00Z" }), context), null);
  assert.equal(
    attentionBanner(item({ agent_id: "zz", parameters: { group_id: "g" } }), context)?.row.id,
    "g",
  );
  const outage = attentionBanner(
    item({ code: "broker_connection_lost", agent_id: "zz", importance: "action_required" }),
    context,
  );
  assert.equal(outage?.row.id, "l");
  assert.equal(outage?.text, "Broker lost");
  // Any other urgent item with no row of its own shows nowhere.
  assert.equal(attentionBanner(item({ agent_id: "zz" }), context), null);
});

test("a refused model names its provider and the failure family, in both languages", () => {
  const en = (label: Parameters<typeof translate>[1]) => translate("en", label);
  const ar = (label: Parameters<typeof translate>[1]) => translate("ar", label);
  const named = { reason: "auth" as const, provider_name: "OpenAI" };
  assert.equal(attentionTitle(en, "model_access_failed", named), "Model key rejected by OpenAI");
  assert.equal(attentionTitle(ar, "model_access_failed", named), "رفض OpenAI مفتاح النموذج");
  assert.equal(
    attentionTitle(en, "model_access_failed", { reason: "billing", provider_name: null }),
    "Credit spent or plan ended at your OpenAI-compatible endpoint",
  );
  // Without a family it says what it always said; other items keep their own line.
  assert.equal(
    attentionTitle(en, "model_access_failed", {}),
    "A model provider refused background work",
  );
  assert.equal(
    attentionTitle(en, "gateway_stopped", named),
    "Lonora's background service has stopped",
  );
});
