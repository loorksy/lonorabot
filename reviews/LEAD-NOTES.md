# R-MONEY notes for the lead (outside my authors' scope)

1. **Door ownership on netting (3.3.4).** `ticket_agent` (W-AUTH) and the picture that mirrors it take the newest matching journal entry. On a netting account, an add by agent B to agent A's position therefore gives B the position. 3.3.4 gives it to A, the agent that "opened it from flat". This was reproduced against the scripted journal (#108 review). Belongs to W-AUTH / R-DOOR.
2. **Pending-order fills.** Nothing posts an Execution Receipt when a pending order later fills at the broker; the receipt is posted at placement only. Decide whether a broker-side fill is "an operation the broker confirms" (10.3, 11.2). See #86.
3. **#80.** Skipped this pass: its head is still 3604c46b. It will be reviewed when the head moves.
4. **Rebases.** Every PR in my area except #80 stacks on d6b4a41. These conflict with `wauth/3b-provenance` 8704653: #86, #96, #99, #105, #106, #107, #109. #107's GitHub base is `main` (118 files) and should be retargeted to `ledger/2-label`.
