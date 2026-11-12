# genui/phase2-on-main at 5e5370f8 (W-GENUI phase 2; #69 is its older version)

- PR: no PR number yet for this branch. #69 is the older `genui/parity-mobile` head 19c8564e and is not reviewed here.
- Head: 5e5370f8
- Base: main 4d4348ae (merged in 5439988f). It merges cleanly with main e27c2357.
- Own commits: a52fca58..313a887d (13), f0556b17, the merge 5439988f, 5e5370f8.
- Verdict: **FINDINGS** (0 high, 1 medium, 2 low)

## Verified findings

### M1 (medium): this PR sends the mandate-removed approval-card rule to every install
- **Where:** `packages/agent-runtime/resources/prompts/genui_v2.md:5` ends with "Never put a card in the same reply as an approval card."
- **Mandate:** 10.2.4 and 5.8.4 remove that rule.
- **Why this PR matters:** on main the v2 prompt reached the model only with `LONORA_GENUI_V2=1` (main `skills/visual_policy.py`, `genui_v2_enabled()`, off by default). Main's default v1 prompt (`native_visual_response.md`) has no approval rule (grep: none). Commit 9e5e7e8e makes v2 the only prompt, so the removed rule now reaches every install. That extends a removed rule (0.4, "no change may extend it").
- No code enforces it (grep `visual_response.py`, `genui_compile.py`).
- **Fix:** delete that sentence from line 5 in this PR. W-SLOTS (#117) rewrites the line for 10.2 and 10.3.

### L1 (low): v2 becomes the default one commit after the parity check passes (10.1.3)
- 0e32e69c adds the parity journeys the mobile renderer passes, while `genui_v2_enabled` is still opt-in.
- b9125371 flips the default and keeps a `LONORA_GENUI_V2=0` opt-out.
- 9e5e7e8e deletes the flag.
- Main merges PRs with merge commits, so these intermediate states stay in history. 10.1.3 says "in the same change that makes the mobile v2 renderer pass the parity check".
- **Fix:** squash 0e32e69c, b9125371 and 9e5e7e8e (or squash-merge the PR). The end state is correct.

### L2 (low): comments cite sections that docs/genui.md does not have (0.4)
`GENUI_PLAN.md` was deleted, and its citations became "docs/genui.md" with the old labels kept. `docs/genui.md` has only sections 1-9 with plain headings (Wire format … Stored v1 messages).

Citations with labels docs/genui.md lacks:
- `packages/db/src/lonora_db/owner_words.py:47` ("rules V and N")
- `packages/db/src/lonora_db/messages.py:78` ("step 4")
- `packages/db/src/lonora_db/genui_taint.py:1` and `tests/test_genui_taint.py:1` ("#12, §8.5")
- `packages/core/src/genui/submit.ts:2` ("rules N and T, §9.3")
- `apps/api/src/lonora_api/routes/messages.py:62` ("rule N, Q21")
- `apps/mobile/app/thread.tsx:734` ("rule L, §9.7 M-a")

Code added in this PR that cites the deleted plan's § numbers:
- `apps/mobile/components/genui/card.tsx:136,164`
- `apps/web/src/components/genui/UiCard.tsx:747,782`
- `genui.css:25,737`

**Fix:** point each comment at a real `docs/genui.md` section (for example "§7 The send path") or drop the label.

## Observation (pre-existing, not counted against this PR): a final card can claim an execution or imitate an approval card
- `genui_compile.py:765-769` runs the `EFFECT_CLAIM` check only while streaming (`if not final`). The same guard is on main (`genui_compile.py:739-743` at 4d4348ae).
- Probe through `VisualReplyProjector.project(..., partial=False)`: all of the following compile with no diagnostic:
  - a `receipt` card with "Order executed successfully";
  - a card with «تم تنفيذ الصفقة بنجاح»;
  - a card titled «موافقة على صفقة» with buttons «موافقة» and «رفض».
- Harmless through the system: the buttons only `ask` with their label, the run is tainted, and no approval, settle or mode endpoint is reachable.
- It is a visual imitation of a fixed card (10.2.2, 10.3: "the agent can never draw confirmed itself"). Phase 2 makes it the default path.
- **Suggested:** drop the `if not final:` guard for cards. Refuse Approve/Reject-labelled buttons (موافقة/رفض) on the default `ask` action. Sent to W-GENUI and W-SLOTS.

## Rejected candidates
- **"Third-party URLs from tool results can be `open` targets (6.10)":** literal `https://` only, at most 400 characters, re-checked on both clients, opened with `noopener,noreferrer` or `Linking.openURL`. Informational.
- **"The `baseline.jsonl` recording names the removed lonora-design skill":** a stored recording, never shown to the model.

## What I checked
- **10.1.3 end state:**
  - `LONORA_GENUI_V2` has no occurrence outside VISION.md.
  - The live-evaluation gate, `genui_eval` and the prompt variant switch are deleted.
  - v1 generation is deleted. v1 remains only to validate and render stored messages.
- **10.1.4:** `RESTING_LIMIT = 560` is unchanged, and no budget constant changed.
- **10.1.5 parity:**
  - `NODES`/`ACTIONS` generate `genui-catalog.ts`; `export_genui_catalog.py --check` passes.
  - The vocabulary covers every node.
  - Web and mobile node maps are typed `Record<UiRenderedNodeType,…>`.
  - Mobile renders natively, with no text fallback for a built card.
- **5.8.6:** `export_agent_tool_reference.py --check` passes. The manifest does not hash genui prompts.
- **14.3.12:** the lonora-design skill paths are removed from both pyproject files, and the skill count is fixed (5e5370f8).
- **P5:** card routes stay main's five (market, tasks, usage, files, agents), pointing at screens main has. `chat-prefs` and `schedules` are dropped.
- **Stop:** untouched.
- **Merge 5439988f:**
  - No goal, `TradingControl`, `require_trading` or `resume_trading` line is added.
  - The goal files main deleted stay deleted.
- **6.10:**
  - A card send carries only `ui_submit {source_message_id, part, path, values}`; the only other card call is `ui-state/{part}/unlock`.
  - Probe: `trade.open` and `owner_action.resolve` sends make the card fall back; a `go` outside the five routes is refused; `javascript:` opens are dropped; a copy carrying a UUID falls back as private.
  - The intent registry, `genui_submit.py`, taint and `owner_words` are unchanged except comments.
- **14.3.9:** no stored contract changed. `RichUiPart.document` is still `VisualDocument | UiDocument`, and `test_visual_persistence` passes.
- **Security:** no `innerHTML` or `dangerouslySetInnerHTML` in either client. Markdown renders as text, and the unverified-financial-result guard still replaces the whole reply.
- **Arabic:** web i18n has **0 missing ar** (1967 of 1968). All 17 new mobile labels have Arabic.
- **Tests at 5e5370f8:**
  - Core 14.1.2, all pass: `check_trading`, `check_execution_recovery`, `check_broker_recovery`, `check_account_recovery`, `check_broker_orders`; the six core pytest files, 101 passed.
  - GenUI and related pytest: 512 passed. A second set: 507 passed, 6 skipped.
  - `check_owner_actions.py` and `check_trade_approvals.py` pass.
  - tsx genui-parity, genui-engine, chat-rows, visual-response: 43/43.
  - Playwright web genui and visual-response: 16/16. Playwright mobile genui and visual-response: 7/7.
