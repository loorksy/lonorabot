import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { agentShowingMandate, otherTradingMode } from "../../apps/mobile/lib/mandate-mode";

test("a successful Ask to Full response is the mode the parent shows", () => {
  const shown = agentShowingMandate(
    { id: "gold", name: "Gold desk", trading_mode: "ask" as const, trading_account_id: "acct" },
    { trading_mode: "full", withdrawn: 2 },
  );
  assert.equal(shown.trading_mode, "full");
  assert.equal(shown.name, "Gold desk");
  assert.equal(shown.id, "gold");
  assert.equal(shown.trading_account_id, "acct");
  // Reopening offers the other mode from that same field.
  assert.equal(otherTradingMode(shown.trading_mode), "ask");
});

test("a successful Full to Ask response offers Full again", () => {
  const shown = agentShowingMandate({ trading_mode: "full" as const }, { trading_mode: "ask" });
  assert.equal(shown.trading_mode, "ask");
  assert.equal(otherTradingMode(shown.trading_mode), "full");
});

test("a response that is not Full is shown as Ask", () => {
  assert.equal(agentShowingMandate({ trading_mode: "full" as const }, {}).trading_mode, "ask");
  assert.equal(
    agentShowingMandate({ trading_mode: "ask" as const }, { trading_mode: null }).trading_mode,
    "ask",
  );
});

test("mobile settings and the conversation keep that response on the agent the control reads", () => {
  const control = readFileSync("apps/mobile/components/agent-permissions.tsx", "utf8");
  const settings = readFileSync("apps/mobile/app/bot-settings.tsx", "utf8");
  const thread = readFileSync("apps/mobile/app/thread.tsx", "utf8");
  const apply = control.slice(control.indexOf("const apply"), control.indexOf("const line"));
  assert.match(apply, /agentShowingMandate\(agent, updated\.result\)/);
  assert.match(apply, /onMode\?\.\(shown\.trading_mode\)/);
  assert.match(settings, /agentShowingMandate\(current, \{ trading_mode \}\)/);
  assert.match(thread, /agentShowingMandate\(row, \{ trading_mode \}\)/);
  // Q9: no connected account still shows no mode control.
  assert.match(control, /if \(!props\.agent\.trading_account_id\) return null/);
  assert.doesNotMatch(control, /useState<TradingMode/);
});
