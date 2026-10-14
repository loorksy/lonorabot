# Demo broker verification

Use a MetaApi **demo** account. These checks submit real broker orders: run them
only on demo, with the smallest valid volume. Keep autonomous goals disabled.
Never put account tokens, login credentials or account IDs in shared logs.

1. Keep two charts open on different broker symbols and timeframes. Restart the
   gateway; verify account, native tickets, quotes and candles recover. Repeat
   after a connection drop. Logs should identify the exception without secrets,
   avoid repeated synchronization on healthy RPC, and never show `.metaapi`
   permission errors. Close the browser and verify server chart state advances.
2. Ask the bot for account information, positions, orders and history. Compare
   broker name, login, balance, equity, margin, native symbol and tickets to MT5.
3. Request a market buy and sell. Before approval, verify MT5 has no new position.
   Reject one request: no journal send or trade. Approve another once; refresh
   and press again if possible: exactly one order, with a durable receipt showing
   the actual ticket/price or broker rejection. Test invalid volume, invalid stops,
   insufficient funds and closed market using demo conditions, never live funds.
4. Repeat for buy limit, sell limit, buy stop and sell stop. Verify entry price,
   volume and SL/TP in MT5. Modify pending entry/SL/TP, explicitly clear a stop,
   cancel one, and verify each ticket and result in chat.
5. Open a position manually in MT5. Ask the bot to list it, modify SL/TP, close a
   valid partial volume, then close its remaining volume. Verify native ticket
   matching works without a Lonora operation ID. Also test a position opened by
   Lonora. Check broker min/max/step volume and stop distance for each symbol.
6. With positions on several symbols, approve close-by-symbol and then close-all.
   Verify the approval contains the exact ticket set; a position opened after the
   proposal must not be silently included. Check every individual broker receipt.
7. Repeat market/pending/modify/close operations for broker forex, metals, index
   and crypto symbols including suffixes. Never substitute an alias for the exact
   native symbol. Verify unavailable symbols have a specific error.
8. Turn global trading OFF, then test Emergency Stop separately. Approving must
   not execute a new mutation. Reads remain available. Restore original controls.
9. Interrupt the connection **after** a demo send. Verify ambiguity is recorded,
   no automatic second send occurs, and reconciliation queries the broker before
   resolving the operation. Restart the worker while waiting for approval and
   after a send: durable decisions and journal results must survive recovery.
10. Confirm the resumed original run reports broker success/error in chat. A
    model failure must not hide the durable execution result card. Finish by
    closing demo test positions/orders and restoring original settings.

Automated counterparts: `tests/check_broker_recovery.py` exercises actual SDK
registry/wrappers with scripted transports; `tests/check_trade_approvals.py`
exercises PostgreSQL, approval HTTP admission and the simulation adapter.
These fixtures do not substitute for verification against an external demo broker.
