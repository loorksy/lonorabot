import assert from "node:assert/strict";
import { test } from "node:test";
import {
  acceptedIncoming,
  type IncomingCall,
  visibleIncoming,
} from "../../apps/mobile/lib/incoming-call";

const call: IncomingCall = {
  id: "call",
  agent_id: "agent",
  thread_id: "thread",
  status: "ringing",
  reason: "A verified account safety change",
  expires_at: new Date(10000).toISOString(),
  version: 1,
  execution_authorized: false,
};

test("only current authoritative ringing state is displayed", () => {
  assert.equal(visibleIncoming([call], 9999), call);
  assert.equal(visibleIncoming([call], 10000), null);
  for (const status of ["accepted", "rejected", "missed", "cancelled"] as const)
    assert.equal(visibleIncoming([{ ...call, status }], 9000), null);
  assert.equal(visibleIncoming([{ ...call, expires_at: "invalid" }], 0), null);
});

test("push or stale acceptance is not sufficient to join", () => {
  assert.equal(acceptedIncoming(call, 9000), false);
  assert.equal(acceptedIncoming({ ...call, status: "accepted" }, 9000), true);
  assert.equal(acceptedIncoming({ ...call, status: "accepted" }, 10000), false);
  assert.equal(acceptedIncoming({ ...call, status: "rejected" }, 0), false);
});
