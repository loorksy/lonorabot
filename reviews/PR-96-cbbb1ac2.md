# PR #96 re-review at cbbb1ac2

- Reviewer: R-MONEY.
- Base: re-review of new commit cbbb1ac2, on 3c2615cd.
- Verdict: **CLEAN**. L1 from PR-96-3c2615cd.md is fixed.

## The fix
- "Unknown" / «غير معروفة» moved to `FIXED_CONTROL_LABELS`, which only the `control=True` branch reads (through `CONTROL_PLAIN`).
- **Probe at the head:**

  | Text | Refused as a heading | Refused as a button |
  | --- | --- | --- |
  | `Unknown` | no | yes |
  | `غير معروفة` | no | yes |
  | `Result: Unknown` | no | no |
  | `Trend · Unknown` | no | no |
  | `It executed` | yes | yes |

- **The new tests guard it:** with 3c2615cd's `genui_compile.py` restored, `test_genui_slots.py` fails 3 tests; at the head it passes.
- **10.2.2 is kept:** an agent's button can still not read like the Settle card's.

## Checks
`test_genui_slots`, `test_genui_contracts`, `test_genui_parity`, `test_card_lifetimes`: 68 passed, 4 skipped.
