import assert from "node:assert/strict";
import test from "node:test";
import type { SuperBotRequest } from "@lonora/contracts";
import { mergeSuperBotRequest } from "../../packages/core/src/super-bot";

const row = {
  id: "request",
  status: "rejected",
  timeline_seq: 2,
  created_at: "2026-10-20T00:00:00Z",
  updated_at: "2026-10-20T00:02:00Z",
} as SuperBotRequest;
test("old pending GET cannot reopen a resolved authorization card", () => {
  const incoming = {
    ...row,
    status: "pending",
    updated_at: "2026-10-20T00:01:00Z",
  } as SuperBotRequest;
  assert.equal(mergeSuperBotRequest(row, incoming).status, "rejected");
});
test("a newer server transition wins and partial responses retain causal anchors", () => {
  const incoming = {
    id: "request",
    status: "activated",
    updated_at: "2026-10-20T00:03:00Z",
  } as SuperBotRequest;
  const value = mergeSuperBotRequest(row, incoming);
  assert.equal(value.status, "activated");
  assert.equal(value.timeline_seq, 2);
  assert.equal(value.created_at, row.created_at);
});
