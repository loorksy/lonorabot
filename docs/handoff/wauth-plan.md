# W-AUTH completion plan: order of work under VISION 14.1

All file:line references are to origin/main **de1e2827** (fetched 2026-11-19) unless a branch or commit is named. Nothing was edited.

## 0. Starting state and assumptions

- **Alembic.** The single head on main is `0155_owner_message_pauses_are_owners` (I computed it from every `revision`/`down_revision` on main). Production runs 1658eb45, whose head is 0088, so the next deploy also runs 0089 through 0155.
- **Team stack.** The team stack (#232: team/5b-flat-roles 26bf8503, wteam/3-creation 47a4ce9a) is assumed to merge **before** this plan's data step. It changes things this plan relies on:
  - it deletes `TEMPLATE_LEVEL` (contracts agent_creation.py:16-23);
  - it writes `trading_mode` at creation and calls `initial_permission(..., "supervised")`;
  - it deletes PermissionMenu.tsx:85-130 (PORT_MAP row 20), bot-panel.tsx and mobile new.tsx (rows 46-48);
  - it adds 0125 (hanging off 0061), 0126 (merging 0125 and 0155) and 0127 (drops `ln_supervision_grants`).

  It does **not** change `default_level` (agent_permissions.py:34-45). It does not flatten stored roles.
- **The ladder still overrides the mode.**
  - The door refuses `agent_analysis_only` before it reads the mode (agent_permission.py:72-74).
  - That refusal also blocks **risk-reducing** requests, which goes against 4.1 and 4.7.
  - trade.py:69-79 hides the trade tools for "analysis" agents, and trade.py:425-427 refuses them.
  - The fallback level for an agent with no stored record is `"analysis"` unless the agent is personal or a root specialist (agent_permissions.py:43-45).
- **Fixtures that need the ladder.** The core-test fixture `check_streaming.py:104-112` raises agents through `PUT /agents/{id}/permissions`. `check_trading.py:17,23,475-480` calls `change_permission`.
- **Production.**
  - 3 agents, all in Ask.
  - Grants: 0 active and 3 revoked.
  - 3 confirmed `grant_authority` cards. Their settled line «وُقّع. يتداول بنفسه ضمن هذا التفويض.» is already untrue.
  - 0 positions.
- **PORT_MAP.** PORT_MAP-38 exists only on origin/ui/v38-port (4de44ec8), mapped against 1658eb45. Its line numbers have drifted, so this plan uses main's lines. PORT_MAP rows are cited as `UI_CHANGES:n` (PORT_MAP-38.md line).

### The gate every slice must pass ("Gate G")

- `bash scripts/build.sh` (ruff, ruff format, pyright, check_policy_distribution, pnpm lint/check/build)
- `bash scripts/migrate.sh`
- `python tests/run_foundation_checks.py --isolated-databases`
- the 11 core tests of 14.1.2
- `pnpm exec tsx --test …` (ci.yml:829)
- `python tests/check_clients.py`
- `python tests/check_streaming.py`
- `pnpm test:web` and `pnpm test:mobile`
- Lingui extract with no orphaned msgids
- `resources/system/manifest.json` regenerated whenever `lonora.md`, a frame or a tool description changes (5.8.6)
- **True (0.4):** every doc, prompt and UI string the slice makes untrue changes in the same slice.

---

## 1. Decisions needed before coding (VISION 0.1: "how" questions go to the owner)

| # | Question | Recommendation |
|---|---|---|
| Q1 | 14.3.18.1: should the data step force every agent to Ask? | **No write.** 0060 already did it (`0060_agent_trading_mode.py:22`, server_default 'ask'). A forced write now would silently revert the owner's Mandate taps: by='system' is outside `ModeChanger` (trading_mode.py:21), no line goes to the owner, and the raw UPDATE skips `end_management_task`. |
| Q2 | Passkey **device enrolment**: does it survive? | **Keep it.** Incoming calls require an enrolled device (owner_profile.py:185-198; voice/incoming.py:139/178/288). 4.4 and 14.2.1 remove passkey signing *for trading* only, and 13.1 says nothing built stays off. Move enrolment into the call settings first (slice A5). |
| Q3 | `agents_on_their_own` feeds `run_retry` (run_retry.py:163-207). Should it switch to `trading_mode == 'full'`? | **Yes, and not paused.** Full agents then skip the automatic retry of a late instruction, which matches the docstring's intent. Say so explicitly in the slice. |
| Q4 | 14.3.2 survivors. After grants go, `lonora_opened`, `authority_snapshot` and `provisional_voice` have no trading caller. | Move them, because 14.3.2 binds. Make `lonora_opened`/`ticket_agent` the single ownership entry the door calls (3.3.4). Put `provisional_voice` next to `ui_submit_provenance` in `lonora_db/owner_words.py`. Whether orphans are then deleted is the owner's call (13.2). |
| Q5 | 14.3.3 `stop_management_task` | Satisfied by the per-agent `management_task.end_management_task` (management_task.py:194-199). **Drop** step-10 C2's move of the grant-keyed function. |
| Q6 | 14.3.18.6 supervisor-made holds | Release each with `released_by='stale'`, unpause, re-enable routines and resume watches. Leave Tasks as they are for the owner or agent to resume. No generated wake. This replaces #180's 8-shape resume machinery (1688d8e3 0063:811-1056). |
| Q7 | How a client reaches an agent's live Mandate card outside a thread (needed by rows 21, 22, 43) | Add an agent-scoped read of the live `trading_mode` card. Raising one when none is live goes through the existing propose path (tools/owner_actions.py:212-213). The menu renders the **real fixed card**, never an imitation (6.10). |
| Q8 | Error code after merging the stale-target checks (6.6) | One code (`broker_state_changed`), with client copy updated in the same slice. |
| Q9 | Q3 of PORT_MAP ("agents that cannot trade show no mode") once the ladder is gone | "Cannot trade" means no connected broker account. |
| Q10 | 14.3.18.4 role flattening: in W-AUTH's data step, or in the team stack? | In the data step, because 14.3.18 says "one step". Guard the `ln_supervision_grants` UPDATE so it does not run on the table that 0127 drops. |

---

## 2. What happens to the open PRs and the branch (d)

**#180 (wauth/9-data-migration, 387d46a4): close without merging.**
- 387d46a4 is the unverified WIP commit.
- Its 0063 forks the chain: `down_revision` is 0061, but 0061 already has the child 0071 on main.
- Items 1, 5, 6-restrictions/goals, 6-owner_message, 7 and 8 are already done on main or void.
- Keep **1688d8e3** as the source to reuse in slice D:
  - `lock` (248), `shown_grants` (347), `mandate_cards` (383), `revoke_grants` (458), `stop_management_task` (522), `keep_task_watches` (588), `team_agents` (679), `edit_method` (760);
  - its 3 client files (contracts owner-actions.ts `previous_grants`; core owner-actions.ts `mandatePreviousGrant`, `mandatePreviousFull`, `mandatePreviousAllPairs`; owner-actions.test.ts);
  - its owner_actions.py `payload_hash` and `card_facts previous_grants` hunks.

**#162 (wtask/2-no-grant-task, 831de5ab): close without merging.**
- Its dependency #80 is on main.
- It conflicts in 42 hunks across 12 files, all in grant code that this plan deletes.
- Its intent lands through deletion instead:
  - `finish_activation` goes in S1a (routes) and S2d (module);
  - grant-task precedence and hand-over go in S2b-3 (management_task.py:97-127, 163-164, 235; account_authority.py:191-206; obligations.py:138-152; routes/threads.py:118-126; device_authority.py:98-103; agent_permissions.py:231-235).
- Port these into slices:
  - d7e35848, `tests/check_simple_lonora.py` J1/J5 tapping the Mandate card (main still signs grants at :630-714, :897-932): **S1a**;
  - 59d84779, `scripts/agent_eval/bank.py` switching through `set_trading_mode`: **S1a**;
  - the `check_full_account_management.py` adjustments: **S2a**;
  - the docs/agent-eval.md and agents-from-chat.md text: with the slice whose behaviour it describes.
- Drop its activation-review test edits; S3 deletes that check.

**origin/wauth/10-remove-grants (1a8a0769): do not rebase.** It has 175 conflict hunks with main. Re-apply by hand:
- C1 (1a0b3f08) becomes **A1**, without the check_trading_restrictions part.
- C2 (a64a4ccc) is split:
  - the `AuthorityAction` move and `tradeActionLabels` go to **A2**;
  - `trading_mode` on agent_data and the TS Agent go to **A4**;
  - enrolment in call settings goes to **A5**;
  - the `stop_management_task` move is dropped (Q5).
- C3 (b269f243) becomes **S3**. Its imagined "0064" Run cancellation goes into **D**.
- C4 onward was never written. It is S1a through S2d below, written fresh on main.

---

## 3. Slice order and deploy grouping

| Slice | Kind (14.1) | Content | Release |
|---|---|---|---|
| A1 | add (tests) | Port the safety-core assertions held only by grant and ladder tests | R1 |
| A2 | move | `AuthorityAction`, trade-action labels, the 14.3.2 survivors, the 14.3.13 doc | R1 |
| A3 | move (6.6) | One stale-target door check | R1 |
| A4 | add | The mode on every read; the agent's Mandate card reachable; withdrawn count; readiness and avatar marker read the mode | R1 |
| A5 | add | Call-device enrolment outside the grant flows | R1 |
| A6 | add | Client readouts show the mode (v38 display rows) | R1 |
| **D** | data | Successor to 0063 (14.3.18), plus `default_level` set to "supervised" | **R2** |
| **S1a** | delete | No new grants: the Mandate is the only way to Full; ladder API and grant screens gone | **R2** |
| **S1b** | delete | The `grant_authority` card kind goes | **R2** |
| S3 | delete | Activation reviews (C3) | R3 |
| S2a | delete | The door and the tools read only the mode (6.7) | R3 |
| S2b-1/2/3 | rewrite | Readers off the ladder and grants: frame (agent), status and projections (owner), lifecycle | R3 |
| S2c | delete | Ladder storage, plus deleting the `agent-permission:%` rows | R3 |
| S2d | delete | Grant storage, signing and delegation modules; drop `ln_account_authorities` and the `account_activate` challenges | R3 |

- **Main stays true and green at every merge.**
  - After A6, the screens tell the truth about the mode.
  - After D alone, grants still work and stay offered; only the existing ones are revoked.
  - After S1a, nothing can create a grant.
  - Each R3 slice deletes code that nothing reaches any more.
- **R2 deploys D, S1a and S1b together.** Otherwise an owner could sign a new grant after D revoked the old ones, and that grant would never get its one Mandate card (14.3.18.2). Before deploying R2, re-run the §4 production queries.

---

## 4. Production queries (read-only, before writing D and again before R2)

1. `ln_agents`: role, template, `parent_id IS NOT NULL`, trading_mode, `trading_account_id IS NOT NULL`, `trading_symbol IS NOT NULL`. This decides whether item 4 acts.
2. `ln_account_authorities`: count by status, and `expires_at` for active rows. Expected: 0 active, 3 revoked, and confirm 0 pending.
3. `ln_settings WHERE key LIKE 'agent-permission:%'`: count by `payload->>'fallback_level'`.
4. `ln_owner_actions WHERE kind IN ('grant_authority','trading_mode')`: count by status. Expected: 3 confirmed grant cards.
5. `ln_supervision_holds WHERE released_at IS NULL`: source and the holder's role. This decides whether item 6 acts.
6. Live Runs with `trigger='activation'`, or with `account_management_id` not equal to the agent id; live grant-keyed management Tasks.
7. `ln_device_credentials` not revoked (the call path depends on them); `ln_device_challenges WHERE kind='account_activate'`.

---

## 5. Slices

### A1 — Port the safety-core assertions (tests only)
- **Why:** 14.1.3. No assertion about 6.1-6.9 is removed or weakened.
- **Files**
  - Re-apply 1a0b3f08:
    - `tests/check_trade_approvals.py`: one card per exact request, reused while it waits, after approval and right after a refusal; the owner's ticket is `ticket_not_owned` with no card.
    - `tests/check_trading_mode.py`: 6.6 under Full; 6.2 send attribution on a broker rejection; 6.3/6.4 a lost acknowledgement is ambiguous and a replay never resends.
    - `tests/test_mandate_card.py`, `tests/test_card_journeys.py`.
    - `tests/run_foundation_checks.py`, `.github/workflows/ci.yml`.
  - Audit for any other 6.x assertion held only by grant or ladder tests, and port it to the mode: `check_account_authority.py`, `check_grant_coverage.py`, `check_full_delegation.py`, `check_full_account_management.py`, `check_unified_permissions.py`, `check_device_authority.py`, `check_delegated_scope.py`, `test_agent_permissions_enforcement.py` (keep the run-integrity case at :55).
  - Drop C1's `check_trading_restrictions.py` part; the file is gone from main.
- **Acceptance**
  - The ports pass on main.
  - Mutation spot checks make each one fail: drop `require_exact_approval` (agent_permission.py:105); skip the stale-target check (execution.py:391-403); resend an ambiguous operation.
  - Gate G.
- **Risks**
  - A port that asserts grant behaviour rather than mode behaviour.
  - The foundation runner gets slower.

### A2 — Move the survivors (no behaviour change)
- **Files**
  - `AuthorityAction`: move from contracts/account_authority.py:12 to `packages/contracts/src/lonora_contracts/trading.py:18-29`, and type `TradeRequest.action` with it (the inline Literal has the same ten members).
  - The 14.3.2 survivors leave `packages/trading/src/lonora_trading/account_authority.py` for a surviving module (for example `lonora_trading/ownership.py`):
    - `ticket_agent` (106-168), `lonora_opened` (99-103), `entry_holder`, `management_target` (222-229), `authority_snapshot` (171-181);
    - `provisional_voice` (42-53) goes to `lonora_db/owner_words.py` (Q4).
  - Repoint the callers:
    - execution.py:29 (and 173, 187, 303, 345);
    - agent_permission.py:29, 82, 88;
    - tools/trade.py:43, 428;
    - picture.py:34;
    - context/permissions.py:12, 168;
    - tests check_account_picture.py:31, test_trading_mode.py:19.
  - New `packages/core/src/trade-action-labels.ts` takes the action words from `account-authority-labels.ts` (en 49-58, plus ar). Repoint order-line.ts:13, 172 and owner-actions.ts:22, 77, 528.
  - 14.3.13: move the exact-request match and the reuse of `reviewed_approval` (docs/account-authority.md:61, 79-80) into `docs/trading-safety.md`.
- **Acceptance**
  - The diff is moves only.
  - A golden test shows the `trade_fingerprint` and operation id of a fixed `TradeRequest` are byte-identical before and after (14.3.9).
  - Order lines and the Settle card keep their words (tests/web/order-state, owner-actions tests).
  - Gate G.
- **Risks**
  - Import cycles between lonora_trading and lonora_db.
  - JSON-schema snapshot drift from re-typing a Literal.

### A3 — One stale-target check (6.6, 14.3.1); this edits the safety core
- **Files**
  - `execution.py:384-414`: the non-grant `broker_state_changed` check (391-403) is skipped today when `account_authority_id` is set. It now runs for every agent-originated close or modify, in both modes.
  - Fold `require_approved_target_current` (`trade_approvals.py:328-352`) into it, comparing against the target captured at approval.
  - The grant-path check (`lonora_trading/account_authority.py:312-315`) still runs; it is now redundant and S2a deletes it.
  - `material_state` (manual_activity.py) and the expected-target capture in tools/trade.py are kept.
  - Error-code copy in core agent-permission-errors.ts and web user_error.ts (Q8).
- **Acceptance**
  - Under Full, a blind modify and an owner-changed target are refused with nothing sent.
  - In Ask, an approved card whose target changed is refused with no send.
  - Grant-path requests are now checked too.
  - The owner's own Trading-page orders are unaffected.
  - A paused agent's risk-reducing close still goes through when the target is unchanged (4.7).
  - Core 11, check_trade_approvals, check_trading_mode.
- **Risks**
  - A wrong merge lets a stale close through, or refuses a legitimate exit.
  - The code rename breaks client copy.

### A4 — The mode on every read (server and contracts)
- **Files**
  - `trading_mode` on `agent_data` (packages/db/src/lonora_db/agents.py:13-25), the py domain contract, and `packages/contracts/src/domain.ts:14`. Source: C2 a64a4ccc, plus its `authority_changed` activity line.
  - The agent's live Mandate card readable per agent (Q7).
  - `routes/owner_actions.py:149-168` returns the count of cards withdrawn by `withdraw_pending` (trading_mode.py:55-58). This is row 25.
  - `trading_readiness.py`:
    - carry `trading_mode`;
    - the headline (189-219) says `on_its_own` when the mode is Full or, until S2d, an active grant exists; `ask_me` otherwise; `no_trading` only while the ladder says "analysis";
    - contracts `trading.ts:193-231`.
  - `agent_on_its_own.py:11-42`: the mode is Full and the agent is not paused, **or** an active grant exists (the union stays true while grants live). Callers: routes/agents.py:55, 129, 159; run_retry.py:20, 203-207 (Q3).
- **Acceptance**
  - GET /agents and GET /agents/{id} carry `trading_mode`.
  - A Mandate tap emits `agent.trading_mode.updated`.
  - A Full agent with no grant reads `on_its_own` and shows the avatar marker (today it reads `ask_me`, trading_readiness.py:207-208).
  - test_trading_readiness.py and tests/web/trading-readiness.test.ts are updated; py/TS parity holds (check_clients).
  - Gate G.
- **Risks**
  - `extra="forbid"` consumers of agent_data.
  - The retry behaviour change (Q3).
  - The Mandate-card read must not create cards as a side effect of a GET.

### A5 — Call-device enrolment outside the grant flows (13.1, 14.1.1)
- **Files**
  - Web: `apps/web/src/shell/settings/NotifyPages.tsx:253-283` gets an enrol button and drops "· registered for the passkey" at :280 (row 63, ar.po 300).
  - Mobile: `apps/mobile/components/incoming-call-settings.tsx:99, 113-122`.
  - Core: `owner-profile.ts:61-64, 128-131` (noDevice text).
  - Kept as they are: core `device-proof.ts`, `apps/mobile/lib/device-proof.native.ts`, `react-native-passkeys` (mobile package.json:39), routes device_authority.py:21-57, auth devices.py:172-250.
  - Specs from a64a4ccc: `tests/web/device-enrollment.spec.mjs`, `tests/mobile/device-enrollment.spec.mjs`.
- **Acceptance**
  - A fresh owner registers a device and chooses Calls without opening any grant screen, in Arabic and English.
  - A second registration says the device is already registered.
  - A wrong password is refused.
- **Risks**
  - WebAuthn rpId and origin on mobile.
  - Wording must not mention trading.

### A6 — Client readouts show the mode (v38 display rows)
- **Web**
  - Composer.tsx:154-172, 249-257: the chip reads `agent.trading_mode` instead of GET /permissions. `showsTradingControl` becomes agent-based (Q9).
  - PermissionMenu.tsx:21-39, 131-173: the chip shows the two mode words (row 19). Light-theme chip in conversation.css:644-649 (row 94). Usage line 480-482 (row 24).
  - ToolsSheet.tsx:172-194 and PermissionMenu.tsx:61-74 (rows 26, 27).
  - AgentPage.tsx: modeLine 63-87, hero badge 238-243 (extra defect), h3 307-309 (row 40), note 431-435 (row 41). shared.tsx:43-58.
  - AgentSheet.tsx: line 204-216, titles 404-409 (row 43), raw op.action 340-344. ChatMenu.tsx:187.
  - Conversation.tsx:924: a tapped Mandate card keeps the `oa` width (row 73).
- **Core:** `trading-readiness.ts` gains `mandateLine` and `tradingSubLine` (row 88).
- **Mobile**
  - Extract the composer control (agent-permissions.tsx:61-66, 724-760) into a small surviving component that shows the mode word.
  - `safety-pill.tsx:23-92` returns null unless `unresolved_count > 0` (row 87). Drop the level and grant lines at 139-156.
- **Acceptance**
  - After a «وكّله» tap, the chip, the agent-page line, the sheet line, the avatar and the pill all say Full from that one event.
  - An agent with no account shows no mode.
  - Specs: agent-pages.spec.mjs:48, 97; one-vocabulary.spec.mjs:15; trading-readiness.test.ts:43-121, 147; mobile safety-pill.spec.mjs:15-77 rewritten for the uncertain-only capsule.
  - Gate G.
- **Risks**
  - .po churn.
  - Conflicts with the team stack's PermissionMenu and AgentPage hunks (#193 rewrites 233 lines of AgentPage).
  - The Mandate slot budget.

### D — The data step: successor to 0063 (14.3.18, 14.3.9)
- **Files**
  - A new revision whose `down_revision` is the head at merge time: 0155 today, or 0127 after the team stack.
  - It reuses 1688d8e3's functions (§2).
  - Contracts and core: #180's `previous_grants`, `mandatePreviousGrant`, `mandatePreviousFull`, `mandatePreviousAllPairs`.
  - db/owner_actions.py: `payload_hash` override and `card_facts previous_grants`.
  - `agent_permissions.py:43-45`: `default_level` returns `"supervised"` for every agent (one line; nothing is ever "No trading" by default).
  - `tests/check_authority_migration.py`: a much smaller test than #180's 2240 lines.
- **Content, item by item**
  - **Item 1:** no mode write (Q1). Ladder half: every agent whose stored or default level is "analysis" gets an explicit "supervised" record (`ask_me_levels`, 1688d8e3:300).
  - **Items 2 and 3:** for every grant still active or pending at deploy:
    - revoke it;
    - stop its Task and keep its watches;
    - cancel waiting grant-management and `trigger='activation'` Runs (the missing "0064");
    - raise that agent's Mandate card once, with the previous-grant line in the owner's language.
  - **14.3.9:** delete every `grant_authority` owner-action row (the 3 confirmed in production included), following `0087_end_money_limits.py:91`, and emit card events so open clients drop them.
  - **Item 4:** delegated, child and supervisor agents become specialists with no parent. Their bound account and symbol go into their method **in the owner's language** (1688d8e3 wrote English at :741). Skip any `ln_supervision_grants` write if 0127 already dropped the table.
  - **Item 6:** supervisor holds are released with 'stale' (Q6). Owner holds stay.
  - **Items 5, 7 and 8:** nothing. 5 is done by 0061; 7 is computed at read time (`ticket_agent`); 8 is void under Amendment 1 (0150).
  - **Not in D:** the `agent-permission:%` rows (S2c), `ln_account_authorities` and the `account_activate` challenges (S2d). Live code still reads them.
  - **Downgrade:** a no-op that never widens authority.
- **Acceptance**
  - `alembic heads` returns one head.
  - Seeded with production's shape (3 Ask agents, 3 revoked grants, 3 confirmed grant cards, 0 positions), the upgrade:
    - leaves 0 `grant_authority` rows;
    - leaves 3 Ask agents;
    - raises no Mandate card;
    - cancels no Run.
  - Seeded with one active grant: the grant is revoked, its Task stopped, its watches kept, and exactly one Mandate card is raised (ar and en). A second upgrade raises no second card.
  - An agent in Full stays in Full with its Task.
  - An "analysis" agent becomes "supervised".
  - A delegated agent becomes a specialist and gets the method line.
  - A supervisor hold becomes 'stale'; an owner hold is unchanged.
  - A journal row left `ambiguous` before the migration reconciles afterwards with no resend (14.3.9).
  - These seed-then-`upgrade head` checks still pass: check_notice_card_migration, check_approval_validity_migration, check_pause_source_migration, check_money_limits_migration, check_shadow_removal_migration, check_workspace_migrations. Pin the ones that seed grant rows to their own revision, as #180 did.
  - Gate G.
- **Risks**
  - Chain position against the team stack's 0125/0126/0127.
  - 1688d8e3's code predates the batch-19 pause stack (tasks.py:399, pauses.py:86, supervision.py:463), so re-read the schema at head.
  - The longer previous-grant line against `SLOT_HEIGHTS mandate=405`: re-measure with `tests/check_genui_browser.py:467`.
  - Merging D without S1a reopens the grant window, so deploy D, S1a and S1b together.

### S1a — No new grants; the Mandate is the only way to Full (server, web, mobile in one change, 14.1.4)
- **Server**
  - `tools/owner_actions.py`: remove `grant_authority` from the tool (214, 255-261, 272) and the grant draft and preselect code (40-110, 159-239).
  - Delete `lonora_core/delegation_words.py` (only caller tools/owner_actions.py:16).
  - Delete `routes/agent_permissions.py` (13-38) and `app.py:28`, with `change_permission` and `save_customization` (agent_permissions.py ~205-272) and the `PermissionChange` and customization contracts.
  - Delete `routes/account_authority.py`: draft 69-110, `begin_activation` and `finish_activation` 121/132, revoke 144, verify.
- **Prompt and text**
  - lonora.md:161 and 432.
  - context/permissions.py: the grant-proposal closing text (142-147) and the grant paragraph (107-118).
  - constitution/tool-policy.md and skills/trade-management/SKILL.md.
  - The manifest.
- **Web**
  - PermissionMenu.tsx:176-385 becomes the Mandate menu:
    - it renders the agent's live fixed card (needs A4) (row 21);
    - «وكّله» posts `trading_mode:'full'` (row 22) and «يستأذن» posts Ask with no confirmation (4.2.2);
    - the toast reads «‹agent›: ‹mode›» plus the withdrawn count (row 25);
    - delete the down page 192-196 and 313-372 (row 23), «تفاصيل التفويض» 288-303 (row 31), and the badge 76-84;
    - the back aria-label at 426.
  - Delete MandateSheet.tsx (1-334), AgentPermissions.tsx (1-976), PermissionEditor.tsx, permission-labels.ts, agent-permissions.css, and components/trading/AccountAuthoritySettings.tsx with bot-settings.tsx:11, 95 and ChatMenu.tsx:10, 74-88.
  - Grant wording on surviving screens:
    - AuthFlow.tsx:73-77 (row 59), Welcome.tsx:61-63 (row 67), IdentityPage.tsx:21-24 and 289-297 (row 49);
    - ConnectionPages.tsx:264-269 (row 50) and 410-415;
    - GroupPage.tsx:137-141, AgentMarketPicker.tsx:41-48;
    - core capabilities.ts:25, 80, 91, 146.
  - **Keep** apps/web/src/shell/PermissionSheet.tsx. It is the microphone and camera sheet; UI_CHANGES:74 misattributes it.
- **Mobile**
  - Delete agent-permissions.tsx (1-1411), keeping the A6 control, which now raises and taps the Mandate card.
  - Delete account-authority-settings.tsx and permission-labels.ts.
  - bot-settings.tsx:8, 175 gets the «التداول» group with one «التفويض: …» row (row 40 mobile; Q9 guard).
  - i18n.ts:41-44 (defaultMarketHint) and 280-291 (unused keys); agent-market-picker.tsx:26; integrations.tsx:124, 162.
- **Core**
  - agent-permission.ts: the proposal builders (11-146).
  - account-authority.ts (1-164).
  - agent-permission-errors.ts: drop the authorization, scope and limits categories.
- **Tests:** see §6, S1a rows. This is the first core-test change: check_trading.py:17, 23, 475-480 and the check_streaming.py:91-112 fixture (and its callers check_execution_recovery.py:686, check_account_recovery.py:165) lose the ladder **setup** only. The default is now "supervised" (D), and no assertion changes.
- **Acceptance**
  - `git grep` finds no route, tool or screen that creates an AccountAuthority or writes a ladder level.
  - Full can be set only by a tap on the fixed Mandate card (chip menu, agent sheet, mobile settings).
  - The call-device check still passes (A5).
  - check_simple_lonora J1/J5 tap the Mandate card.
  - Gate G.
- **Risks**
  - This is the largest slice; review it as five commits: server, web, mobile, core, texts.
  - It needs A4 and A5 merged first.
  - Conflicts with the team stack in PermissionMenu and NewChatSheet.

### S1b — The grant card kind goes (10.3.2)
- **Server**
  - Contracts owner_actions.py: 21-35, 237-270, 313 (`DeviceProof` in the decision), 317-355.
  - db/owner_actions.py: 57, 138-154, 212-376, 295-300 (`full_delegation_available`), 572-660, 1410-1460, 1543-1599, 1756-1765.
  - routes/owner_actions.py: 43, 104-121, 171-217, 288-292, 352-430.
  - agent_state.py:66.
  - A migration repeating `DELETE … kind='grant_authority'` (idempotent; 14.3.9 before the contract changes).
- **Clients**
  - OwnerActionCard.tsx: 65-66, 132-202, 230-231, 269-302, 378-381, 404-405.
  - Mobile owner-action-card.tsx: 18, 25-26, 41-158, 182-235.
  - Core owner-actions.ts: 72-123, 236, 289-338, 448, 593-597, 646-647, 765-905, 1093-1101, 1322.
  - Contracts owner-actions.ts: 8, 24.
  - The enrolment UI that A5 replaced.
- **Acceptance**
  - `OwnerActionKind` has no `grant_authority`.
  - Proposing it is a validation error.
  - The Mandate, Trade Approval, Secret and Settle tests are unchanged and pass.
  - The GenUI rule that generated UI cannot stand in for a fixed card still holds.
  - Gate G.
- **Risks:** a blank card if any row of the kind survives; the migration must run before the new code serves.

### S3 — Activation reviews (C3 b269f243, re-applied)
- **Files**
  - activation_review.py (27-127) and activation_acknowledgment.py (22-49).
  - gateway/service.py:13, 59, 450 and gateway/scheduler.py:4, 20.
  - outcome_return.py:338-409 and context/routine.py:29.
  - agent_state.py:452-472 `review_status` and contracts agent-state.ts:63.
  - The mobile live-status review line and i18n.ts:122, 272.
  - apps/web/src/components/ai/AgentLiveStatus.tsx: no importer, so delete the whole file (ar.po 8003, 9051).
  - The `'activation'` entry in `WORK_TRIGGERS` (D cancelled those Runs).
- **Acceptance**
  - No dispatch, trigger or text of a review remains.
  - test_gateway_reliability passes.
  - Gate G.
- **Risks:** a live activation Run at deploy. D cancels them; the §4 query confirms it.

### S2a — The door and the tools read only the mode (6.7); this edits the safety core
- **Files**
  - `agent_permission.py`: docstring 14-16, `account_authority_id` parameter (62), ladder and grant branch 72-85. Only 86-105 remain.
  - `execution.py`: 141, 199-210, 257-261 (the journal detail), 391-403 (skip), 406, 428-431.
  - Delete `lonora_trading/account_authority.py`. A2 already moved its survivors.
  - `tools/trade.py`: 69-79, 413-449, 677, 719-748, 781, 1105-1110, 1117, 1132, and 1073-1084 (`active_signed_grants`).
  - lonora.md:86, 289, 310; docs/trading-safety.md; the analysis wording in core agent-permission-errors.ts.
- **Acceptance**
  - `git grep` finds no `account_authority_id`, `effective_permission` or `agent_analysis_only` in packages/trading or packages/tools.
  - A decision-table test covers {Ask, Full} × {reducing, increasing} × {own ticket, another's, Lonora on an Ask agent's ticket} × {paused, not paused}, and gives exactly the outcomes of 4.1, 4.7 and 3.3.4.
  - The exact-approval match (`operation_id` plus `trade_fingerprint`) is unchanged.
  - The `authority_lock` race test (mode switch during a send) is unchanged.
  - Journal rows written before the change reconcile.
  - Core 11, test_run_integrity.py:330-342 and 365, test_capability_exposure (every agent now gets `trade_execute`, per 3.2.1).
- **Risks**
  - Safety core.
  - Old journal rows that carry `account_authority_id` in `result.details`.

### S2b — Readers off the ladder and grants (three thin slices, each with its own clients)
- **S2b-1, the agent frame (14.2.8, 5.8.7):**
  - context/permissions.py:16-176 becomes the mode frame (the mode every turn; no Stop);
  - team.py:14, 110; environment.py:80, 136, 174-175;
  - tools/supervision.py:154 and 169 `trading_level`;
  - lonora.md and the manifest.
- **S2b-2, the owner status line (14.3.17):**
  - `trading_readiness.py` loses 16, 52-88 and the ladder and grant parts of 168-219; contracts trading.py and trading.ts;
  - core trading-readiness.ts:29-70, 95-147, 150-163;
  - agent_state.py:405-497, 534, 585-586, 636-637 and contracts agent-state.ts:57-65;
  - mobile agent-live-status.tsx:37, 133-138, core agent-status.ts:185-191, i18n.ts:119-121;
  - Mandate facts `active_grant` (owner_actions.py:535-546) and `mandateGrantStays` (core owner-actions.ts:42-43, 260, 1075-1076), with their tests (owner-actions.test.ts:622-643, genui.spec.mjs:567);
  - creation facts `level` (owner_actions.py:669-720);
  - `agent_on_its_own.py` reads the mode only.
- **S2b-3, lifecycle (the #162 intent, 14.3.16):**
  - management_task.py:97-127, 163-164, 235;
  - obligations.py:97-152 loses its grant steps; the refusal at 113-116 stays;
  - agent_creation.py:335-339 (undo_plan);
  - tools/market_binding.py:79-100 (default_account);
  - routes/threads.py:118-126;
  - device_authority.py:70-103 (grant revocation inside DELETE).
- **Acceptance**
  - No reader of `AccountAuthorityRow` or `permission_state` remains outside the modules S2c and S2d delete.
  - The status line is right in each case: Full, Ask, paused, and paused with positions.
  - Deleting an agent with an unconfirmed operation is still refused.
  - check_management_task:300 and 480 pass.
  - Gate G.
- **Risks**
  - The status line must still survive (section 17).
  - `prepare_delete` regressions.

### S2c — Ladder storage
- **Files**
  - agent_permissions.py (30-272) and contracts agent_permissions.py (1-61).
  - agents.py:128-131 (`pin_level`).
  - agent_creation.py's `initial_permission` call (after the team stack).
  - TS contracts agent-permissions.ts; the rest of core agent-permission.ts; core index.ts:13-14.
  - A migration deleting `ln_settings` rows with key `'agent-permission:%'` (14.3.9).
- **Acceptance**
  - No `agent-permission:` key exists outside migrations, and no such row exists after the upgrade.
  - Gate G.
- **Risks:** low; pyright catches leftover imports.

### S2d — Grant storage, signing and delegation
- **Files**
  - db/account_authority.py (22-228) and auth/account_authority.py (41-181).
  - auth devices.py: the trading-only assertion and `allow_used` paths (63-170).
  - Contracts account_authority.py (12-124).
  - lonora_trading/delegation.py.
  - agent_binding.py:108-130 (`require_financial_agent`), plus the grant text in `BINDING_POLICY` (:21, 155-157, 171-172).
  - schema.py:148-182.
  - A migration: refuse if any grant is still active, then drop `ln_account_authorities`, then delete `ln_device_challenges` rows with kind `'account_activate'` (0087 precedent).
  - TS account-authority.ts; core account-authority-labels.ts (its words moved in A2).
  - docs/account-authority.md (14.3.13 moved in A2) and the other docs that still name grants.
  - **Keep** `DeviceCredentialRow`, enrolment and device-proof.ts.
- **Acceptance**
  - `git grep -E 'AccountAuthority|account_authorit|grant_authority|require_financial_agent|full_delegation'`, outside migrations and VISION, finds nothing.
  - The downgrade recreates the table empty.
  - The incoming-call device check and the enrolment specs pass.
  - Gate G.
- **Risks:** a missed reader in the gateway or agent-runtime; CHECK constraints on challenge kinds.

---

## 6. Tests (e)

### Must pass after every slice (14.1.2) and must never be weakened (6.x)

- **The 11 core tests:**
  - check_trading, check_execution_recovery, check_broker_recovery, check_account_recovery, check_broker_orders;
  - test_broker_effect_verification, test_execution_records, test_preflight_identity, test_metaapi_reconciliation_history, test_tool_execution_core, test_financial_admission.

  Only S1a touches them: ladder setup in check_trading.py:17, 23, 475-480 and check_streaming.py:91-112 (used by check_execution_recovery.py:686 and check_account_recovery.py:165).
- **6.x holders that stay:**
  - check_trade_approvals, check_trading_mode (with the A1 ports), test_trading_mode, test_trading_mode_tools, test_mandate_card, test_card_journeys;
  - test_trade_approval_validity, test_run_integrity;
  - check_management_task (per-agent parts), check_account_picture, check_execution_receipts (S1a drops its `change_permission` setup);
  - test_genui_submit and test_genui_taint (6.10; drop their grant references in S2a);
  - check_genui_browser (Mandate slot);
  - check_simple_lonora (rewritten in S1a).

### Deleted or rewritten with each feature (14.1.3)

| Slice | Delete | Rewrite (setup or wording only) |
|---|---|---|
| S1a | tests/web/agent-permissions.spec.mjs, tests/mobile/agent-permissions.spec.mjs, tests/web/account-authority.spec.mjs, tests/mobile/account-authority.spec.mjs, tests/web/account-authority.test.ts, the proposal parts of tests/web/agent-permission.test.ts, check_full_delegation.py (run_foundation_checks.py:92), openui-chat-ux.spec S7 (452) and S10 (514), agent-status.test.ts:344-351, simple-lonora web :47 and mobile :30, the PermissionChange parts of test_agent_permission_contracts.py, the PUT parts of check_unified_permissions.py (:60); ci.yml:829 list | check_trading, the check_streaming fixture, check_execution_receipts, test_capability_exposure, check_execution_quality, check_market_analysis, check_personal_agent, check_flexible_agents, test_supervision (PUT /permissions setup); check_simple_lonora J1/J5 (#162 d7e35848); safety-truth.spec:324-330; owner-actions.spec effective_level checks (mobile 165-166, 346-347, 465-466); question-card (web 91-94, mobile 72-75) and visual-response:295-298 change from "no grant created" to "no mode change and no journal row"; one-vocabulary.spec.mjs:15; agent-pages.spec.mjs:48, 97 (A6) |
| S1b | check_grant_card.py (:90), test_grant_card.py, owner-actions.test.ts:239-607, owner-actions.spec.mjs grant blocks (:171, :280, :410), mobile owner-actions.spec.mjs (:269, :375), genui-parity.test.ts:62 | test_owner_actions, test_card_lifetimes, check_conversational_setup (grant_authority fixtures) |
| S3 | check_activation_review.py (:80) | the review assertions in check_device_authority; the 'activation' example trigger in two tests |
| S2a | the door parts of check_account_authority.py (:57), check_grant_coverage.py (:91), the grant parts of check_full_account_management (:58) and test_full_account_management | test_agent_permissions_enforcement (keep :55), test_agent_environment (agent_analysis_only), test_capability_exposure |
| S2b | — | test_trading_readiness, tests/web/trading-readiness.test.ts:43-121, mobile safety-pill.spec, owner-actions.test.ts:622-643, genui.spec.mjs:536-568, test_conversation_status, test_model_default (agents_on_their_own), test_gateway_reliability, test_watch_lifecycle, check_durable_records |
| S2c | test_agent_permission_contracts.py, tests/web/agent-permission.test.ts, one-vocabulary.test.ts:192-200 and 214-217 | — |
| S2d | check_delegated_scope.py (:67), the grant parts of check_device_authority.py (:79; move the enrolment checks into a device-enrollment check), check_flexible_agents.py:348 part, tests/device_fixture.py if only grants use it | pin to their own revision every migration check that seeds grant rows: check_workspace_migrations, check_money_limits_migration, check_shadow_removal_migration, check_agent_create, check_genui_browser fixtures |

---

## 7. v38 port rows (c): PORT_MAP-38 row, then the slice

| Rows | Slice |
|---|---|
| 19 chip words (line 60), 24 usage line (65), 26 and 27 ToolsSheet (67-68), 40 web h3 (81), 41 note (82), 43 titles (84), 73 card width (114), 87 pill (128), 88 mandateLine (129), 94 light chip (135), the AgentPage badge defect | **A6** |
| 63 device row (104) | **A5** |
| The withdrawn count for 25 (66) server side; the avatar-marker defect; trading_mode on the read (lines 162-163 note) | **A4** |
| 104 seedV38 (145) | **D** |
| 21 (62), 22 (63), 23 (64), 25 client (66), 31 (72), 40 mobile settings row (81), 43 Mandate card section (84), 49 (90), 50 (91), 59 (100), 67 (108); grant wording not in PORT_MAP (GroupPage, AgentMarketPicker, capabilities, back label) | **S1a** |
| 74 old kinds (115); PermissionSheet.tsx is kept | **S1b** |
| Mobile grant live-status lines (161, 199) | **S3** (review) and **S2b-2** (pending authorization) |
| 85 door remnants (126) | **S2a** |
| The mandateGrantStays note (114); the agent-permission-errors critic item (229) | **S2b-2**, **S2a**, **S2c** |
| 20 (61), 46-48 (87-89) | the team stack (#138) |

PORT_MAP's statement that #127 is open is stale: it was merged as 5f6ed7b0.
