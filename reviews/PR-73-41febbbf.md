# PR #73 at 41febbbf (restack onto main 0a4d9560 + L-brief)

- Head: 41febbbf. Base: wauth/1-trading-mode. Note: origin/wauth/1-trading-mode is
  still 648e52c8. The 3a364264 commit W-AUTH names for #71, a clean merge of batch 12
  with an empty remerge-diff, is reachable only through this branch. Push it to #71.
- Verdict: **CLEAN**

## Verified
- L-brief (my low on 7cc8a095) is fixed. brief_facts.new_mandate_cards lists, once, each
  agent with a pending Mandate card (kind trading_mode, source "agent") created since the
  last brief. The onboarding card (source "system") is not listed. The cards never count
  toward pending_owner_cards and never hold nothing_else_needs_you. WAKE_TEXT and
  plain_brief name them (ar "بطاقة تفويض جديدة", joined with "، "). test_morning_brief
  asserts the first, second and third brief: [], [name], then [] again.
  docs/morning-brief.md matches.
- Merge e796c291 (remerge-diff, 14 conflicted files, checked by a reviewer subagent and
  spot-checked): trade.py keeps the authority_lock order, reviewed_approval, the
  fingerprint check, trade_approval_mismatch and expire_if_due. Only the restriction
  brake goes. trading_mode survives in the contracts, the core TS, both card components
  and the web spec. Docs are true at the commit. The manifest hash matches lonora.md.
- Runs at the stack top 4ec40367 (fresh *_test DBs): check_trading_mode,
  check_account_authority, check_grant_card and check_simple_lonora pass. pytest: 227
  passed, covering the six core files plus morning_brief, genui_taint, card_lifetimes,
  mandate_card, trade_approval_validity, genui_submit, conversation_status,
  trading_mode(+tools), approval_brakes, system_policy and acceptance_scenario.
  The web ar catalog has 1733 live entries, 0 empty, and no conflict markers.

## Relay for the lead (my send to the lead is refused)
- Batch 13 (#71 + #192): #71's Full guidance in permission_guidance
  (lonora_agent/context/permissions.py) says "The account's monetary limits still bind
  you." #192 removes money limits, so drop the clause in the batch merge and regenerate
  the manifest (5.8.6).
