---
name: position-management
description: Manage actual open positions, including manual trades, while preserving owner intervention and requiring explicit mutation authority.
---

# Position Management

## Steps

1. Read fresh positions/account state. Use the exact broker ticket, symbol and
   volume; do not assume the position was created by Lonora.
2. Recover the goal and latest owner changes. Do not restore old protections or
   volume after manual intervention. Management permission is not entry permission.
3. Derive a valid partial/full close or protection edit from actual instrument
   constraints. Preserve every field the owner did not ask to change.
4. Follow trade-management for the immutable proposal, required confirmation,
   current preflight and independent result check. A peer or subagent cannot
   transfer financial authority.
5. Re-read if a position changes or disappears. Never resend a financial mutation
   because its response was lost.

## Output

Give the verified remaining volume and protection change. Example:
"أُغلق الجزء المحدد؛ الحجم المتبقي مطابق لطلبك." Use actual evidence only.
