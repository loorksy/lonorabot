import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { translate } from "../../apps/mobile/lib/i18n";
import type { OwnerAction } from "../../packages/contracts/src/index";
import { ownerActionCard } from "../../packages/core/src/owner-actions";

const isolated = (value: string) => `⁨${value}⁩`;

test("a pause card names the supervisor, the agent and the item, with one-tap Resume", () => {
  const held = {
    supervisor_name: "Lonora",
    supervised_names: ["Gold agent"],
    active: true,
    target: "routine" as const,
    target_label: "Review XAUUSD before London",
    from_owner_message: false,
    owner_holds: false,
  };
  const pause: OwnerAction = {
    id: "pause",
    kind: "supervision_paused",
    status: "pending",
    status_reason: null,
    source: "system",
    agent_id: "gold",
    thread_id: "thread",
    run_id: "run",
    timeline_seq: 4,
    facts: { several_accounts: false, supervision: held },
    requires_passkey: false,
    result: {},
    expires_at: "2026-11-09T10:00:00Z",
    decided_at: null,
    decided_via: null,
    created_at: "2026-11-08T10:00:00Z",
    updated_at: "2026-11-08T10:00:00Z",
  };
  for (const locale of ["en", "ar"] as const) {
    const spec = ownerActionCard(pause, locale);
    assert.equal(spec.lines.length, 3);
    assert.ok(spec.lines[0]?.includes(isolated("Lonora")), spec.lines[0]);
    assert.ok(spec.lines[1]?.includes(isolated("Gold agent")), spec.lines[1]);
    assert.ok(spec.lines[2]?.includes(isolated("Review XAUUSD before London")), spec.lines[2]);
    for (const line of spec.lines) assert.ok(!line.startsWith("⁨"), line);
    assert.deepEqual(
      spec.buttons.map((button) => [button.decision, button.primary]),
      [
        ["confirm", true],
        ["cancel", false],
      ],
    );
  }
  const english = ownerActionCard(pause, "en");
  assert.equal(english.title, "Paused by a supervisor");
  assert.equal(english.lines[2], `What: Routine · ${isolated("Review XAUUSD before London")}`);
  assert.equal(ownerActionCard(pause, "ar").lines[2]?.startsWith("ما أُوقف: مهمة مجدولة"), true);
  const ownerHolds = ownerActionCard(
    {
      ...pause,
      facts: {
        ...pause.facts,
        supervision: { ...held, owner_holds: true, from_owner_message: true },
      },
    },
    "en",
  );
  // Asked for in chat: the owner lifts it, or an agent acting on the owner's message in
  // chat does (4.7.2).
  assert.equal(
    ownerHolds.hint,
    "You asked for this pause: it stays until you resume it, or an agent resumes it acting on your message in chat.",
  );
  assert.equal(
    ownerActionCard(
      {
        ...pause,
        facts: {
          ...pause.facts,
          supervision: { ...held, owner_holds: true, from_owner_message: true },
        },
      },
      "ar",
    ).hint,
    "طلبت هذا الإيقاف: يبقى حتى تستأنفه أنت، أو يستأنفه وكيل بناءً على رسالتك في المحادثة.",
  );
  assert.ok(ownerHolds.lines[0]?.endsWith("from your message"), ownerHolds.lines[0]);
  // The owner's own control made it control-only: only the owner resumes it.
  const controlOnly = ownerActionCard(
    {
      ...pause,
      facts: {
        ...pause.facts,
        supervision: { ...held, owner_holds: true, from_owner_message: false },
      },
    },
    "ar",
  );
  assert.equal(controlOnly.hint, "هذا الإيقاف لك: لا يستأنفه غيرك.");
  assert.ok(!controlOnly.lines[0]?.endsWith("من رسالتك"), controlOnly.lines[0]);
  const ended = ownerActionCard(
    {
      ...pause,
      facts: { ...pause.facts, supervision: { ...held, active: false } },
    },
    "ar",
  );
  assert.deepEqual(
    ended.buttons.map((button) => button.decision),
    ["cancel"],
  );
  assert.equal(ownerActionCard({ ...pause, status: "confirmed" }, "en").outcome, "Resumed.");
  assert.equal(ownerActionCard({ ...pause, status: "cancelled" }, "ar").outcome, "بقي موقوفًا.");
  assert.equal(
    ownerActionCard({ ...pause, status: "expired", status_reason: "supervision_pause_ended" }, "en")
      .outcome,
    "This pause already ended. Nothing changed.",
  );
});

test("the paused-agent refusal asks for a resume and a retry, and promises no answer", () => {
  // Only refused input shows it (a tapped choice, a card's send, an invitation), and that
  // input is not kept: a typed message to a paused agent is kept and answered on resume.
  const ar = "هذا الوكيل متوقف مؤقتًا: استأنفه ثم أعد المحاولة.";
  const en = "This agent is paused: resume it, then try again.";
  assert.equal(translate("ar", "agent_paused"), ar);
  assert.equal(translate("en", "agent_paused"), en);
  assert.ok(readFileSync("apps/web/src/lib/user_error.ts", "utf8").includes(`t\`${en}\``));
  const catalog = readFileSync("apps/web/src/i18n/locales/ar/messages.po", "utf8");
  assert.ok(catalog.includes(`msgid "${en}"\nmsgstr "${ar}"`));
});
