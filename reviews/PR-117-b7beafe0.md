# PR #117 at b7beafe0 (re-review of the new commit only)

- PR: #117, `slots/1-trusted-slots`
- Head: b7beafe0. Previous review: d7289da8 (`PR-117-d7289da8.md`).
- Reviewed: d7289da8..b7beafe0.
- **Rebase request (unchanged):** restack onto `genui/phase2-on-main` (now d1d438fd) or main. The branch conflicts with main.
- Verdict: **CLEAN**

## What changed
`imitates_fixed_card(text, control=False)` now treats headings and controls differently:
- **A heading** is refused only when it, or a segment between separators (`· • : | / – — -`), is a fixed card's words.
- **A Button label** (`control=True`) is still refused when it starts with them.

This answers #127's L1.

**Probe at the head** (heading / control):

| Input | Heading | Control |
|---|---|---|
| «يستأذن قبل كل صفقة» | False | False |
| «التفويض الكامل للخطة» | False | False |
| "Trading mode comparison" | False | False |
| «طلب موافقة · XAUUSD» | True | True |
| «موافقة» | True | True |
| `'موا‌فقة'` | True | True |
| "Approve trade" | False | True |

The frame mark is still refused everywhere.

## What I checked
- `tests/test_genui_slots.py`: 20 passed (fresh DB).
