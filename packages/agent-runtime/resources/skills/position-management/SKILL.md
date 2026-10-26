---
name: position-management
description: Manage actual open positions, including manual trades, while preserving owner intervention and requiring explicit mutation authority.
---

# Position Management

Follow the owner's current language or explicit language preference in all
user-facing replies and labels. English examples do not require an English reply.

## Steps

1. Read fresh positions/account state. Use the exact broker ticket, symbol and
   volume; do not assume the position was created by Lonora.
2. Recover the goal and latest owner changes. Do not restore old protections or
   volume after manual intervention. Management permission is not entry permission.
3. Derive a valid partial/full close or protection edit from actual instrument
   constraints. Under signed full-management scope choose protection and exit
   changes from fresh analysis; otherwise preserve parameters outside the request.
4. Follow trade-management for the immutable proposal, required confirmation,
   current preflight and independent result check. A peer or subagent cannot
   transfer financial authority.
5. Re-read if a position changes or disappears. Never resend a financial mutation
   because its response was lost.

## Output

Give the verified remaining volume and protection change. Example:
"The specified portion was closed; the remaining volume matches your request." Use actual evidence only.
