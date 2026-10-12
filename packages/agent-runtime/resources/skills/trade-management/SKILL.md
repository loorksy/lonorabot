---
name: trade-management
description: Lonora trade management workflow
---

Read Trading controls and account state. Validate exact instrument, quantity step and price tick. Execute through trade_execute. Inspect its returned status; for ambiguous operations use reconciliation and journal rather than resending. Never enable trading through model instructions.
