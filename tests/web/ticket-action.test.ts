import assert from "node:assert/strict";
import test from "node:test";
import { modifyTicket, ticketOf } from "../../apps/web/src/components/trading/useTicketAction";

test("each distinct modify body is its own ticket; the same body is the same ticket", () => {
  const a = modifyTicket({ position_id: "p1", stop_loss: "205" });
  const b = modifyTicket({ position_id: "p1", stop_loss: "206" });
  const clear = modifyTicket({ position_id: "p1", clear_stop_loss: true });
  assert.notEqual(a, b);
  assert.notEqual(a, clear);
  assert.equal(a, modifyTicket({ position_id: "p1", stop_loss: "205" }));
});

test("a journal row settles the ticket its button held", () => {
  // The executor's journal keeps the full TradeRequest, false flags and nulls included.
  const journalled = {
    action: "modify_position",
    position_id: "p1",
    stop_loss: "205",
    take_profit: null,
    clear_stop_loss: false,
    clear_take_profit: false,
  };
  assert.equal(
    ticketOf("modify_position", journalled),
    modifyTicket({ position_id: "p1", stop_loss: "205" }),
  );
  assert.equal(ticketOf("close_position", { position_id: "p1" }), "p1");
  assert.equal(ticketOf("cancel_order", { order_id: "o1" }), "o1");
});
