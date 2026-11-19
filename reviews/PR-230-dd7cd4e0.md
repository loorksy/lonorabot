# PR #230 — re-review at dd7cd4e0

- New commit only: 9ed84fdf..dd7cd4e0 (`apps/mobile/lib/i18n.ts`, +12). No conflict with main.
- Reviewer: R-SEC
- Verdict: **FINDINGS** (0 high / 0 medium / 1 low). L4 is fixed.

## What I checked
- Mobile now labels `broker_rate_limited`, `broker_gateway_unavailable` and `broker_gateway_no_answer`, in Arabic and English, matching web.
- `broker_gateway_no_answer` tells the owner to check their trades before trying again; `broker_gateway_unavailable` says nothing reached the broker.

## Still standing
- **L3 (low):** `as_of` marks a quiet or closed-market quote stale, so "Market data unavailable" shows all weekend (display only).
