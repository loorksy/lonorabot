# PR #156 at ff76eb6a: CLEAN

- PR: #156 (W-ATTN). New since 2ec8f341: ff76eb6a, "The watchdog's unread items stay in the view; the read-all route goes".
- Reviewer: R-AGENT, 2026-11-12T08:53Z
- Verdict: CLEAN. Both findings of the 2ec8f341 review are fixed.

## What was checked

- The medium is fixed. `attention_view` (`db/attention.py`, `SYSTEM_VIEW_CODES`) lists unread `operation_unresolved` and `run_quarantined` items that are still current (`mandatory_current`) as `system_alert`.
  - The contracts are updated (Python and TypeScript `AttentionViewKind`).
  - Both clients read the alert on open and label each code apart: mobile `codeLabels` with Arabic «صفقة ما زالت بلا نتيجة مؤكدة من الوسيط» and «توقف عمل بعد انقطاعات متكررة».
  - A new check case covers it.
- The low is fixed: `POST /attention/seen-all` and `acknowledge_all` are removed with their test assertions. A grep finds no remaining caller.
- Tests on fresh databases: `check_attention_items` exits 0 (all PASS); `test_domain_pages` and `test_attention`: 52 passed.
- Design note, not a finding: like an agent alert, a system alert leaves the view once the owner opens it, even while the operation stays unresolved. The watchdog item and its Lonora path (#124 for uncertain operations) remain.
