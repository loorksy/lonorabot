# PR #215 at 1eda7e1b

- PR: #215 "W-SLOTS 4: the Secret card as a trusted slot (10.2, 10.3), stacked on #157" (W-SLOTS, slots/4-secret)
- Head: 1eda7e1ba7da91d7d2f384413ec419cd30629d67
- Base: stacked on w-env/secret-targets (#157) at eae13b0b. Reviewed only its own commits, 240c8018 (the slot) and 1eda7e1b (catalog re-extract).
- Verdict: FINDINGS 0/2/3
- Rebase request: the head conflicts with main dcf86b43 (git merge-tree). Restack after #157.

## Findings

### M1 (medium, 10.1.4): the Secret slot counts a fixed 400 px, but the card grows with its fields
- Where:
  - `packages/agent-runtime/src/lonora_agent/genui_compile.py:91`: `SLOT_HEIGHTS = {..., "secret": 400}`, used as is at :617.
  - `docs/genui.md`: "secret 400 px".
  - `tests/web/genui.spec.mjs` (new assertion): `≤ 400` for a one-field card only.
- Evidence:
  - Trade Approval and Settle have fixed content. The Secret card's content is chosen by the agent: `OwnerActionProposal.secret_fields` allows 1–8 fields (`lonora_contracts/owner_actions.py:114`, `max_length=8`), and broker and connect cards add lines.
  - I reran the web Slots journey with the PR's record holding three fields instead of one: Key, Secret key, Passphrase. Only the field list and the height line were changed, temporarily, then restored. `SECRET3 588.375`, 1 passed. So a three-field slot alone is 588 px, over its own 400 px budget and over the 560 px card budget.
  - The reviewer's eight-field run measured the slot at 1000 px and its card at 1176 px.
  - Because the compiler counts 400 px, such a card passes the 560 px budget, and it never reaches the "over 720 falls back" rule.
- Fix:
  - Have `genui_slots.slot_records` return the Secret record's height inputs: the number of fields, and whether it has connect or broker lines.
  - Count the slot as a measured base plus a per-field step, both measured by the web Slots journey with one field and with eight.
  - Add a web assertion for a multi-field card, and a compile test where an eight-field secret slot falls back and its row returns.
  - Update docs/genui.md to match.

### M2 (medium, 10.2.2): the Secret card's English title is not refused
- Where: `genui_compile.py:112` adds only «بيانات سرّية» to `FIXED_LABELS`.
- Evidence:
  - The other cards are listed in both languages. The ASCII entries include "Approval request", "Approve", "Reject", "It executed" and more.
  - The English client title is `secretTitle: "Secret"` (`packages/core/src/owner-actions.ts:241`).
  - A probe of `imitates_fixed_card` at the head: «بيانات سرّية» True; "Secret" False; "Secret · Binance" False.
  - So in English an agent's card can head itself as the Secret card. The commit message says the title "joins the refused labels".
- Fix:
  - Add "Secret" to `FIXED_LABELS`. It is already a client string, so the clients'-own-strings test holds.
  - Add an English case to the imitation parametrize list in `tests/test_genui_slots.py`.

### L1 (low, 10.2.2): the broker titles a Secret card shows are not refused in either language
- Evidence: `imitates_fixed_card` returns False for "Connect trading account", «ربط حساب التداول» and "New trading password". The same holds for `brokerTokenTitle` ("New MetaApi API token" / «رمز MetaApi API جديد»). These are titles of `kind == "secret"` cards (`owner-actions.ts:251-254, 494-497`). The trust frame and the frame-mark refusal still apply.
- Fix: add `brokerConnectTitle`, `brokerRotateTitle` and `brokerTokenTitle` in both languages, or say in docs/genui.md why they are left out.

### L2 (low): an unrelated change in packages/core/src/trading-avatar-motion.js
- Evidence: the commit changes three `Math.pow(...)` to `**`, which has nothing to do with slots. Main keeps `Math.pow`.
- Fix: drop those hunks.

### L3 (low): wording
- `docs/genui.md`: the reflow left "secret 400\n  px, its" across two lines. Reflow the line.
- `tests/fixtures/genui/parity-compiled.json`: the new secret entry copies the approval entry's `why` («الطلب في مكانه من الشرح…») and `fallback` («طلب موافقة بانتظار قرارك.»). Reword both for a Secret card.

## Rejected candidates
- The agent's element can read, prefill or echo the secret: no.
  - The slot renders the same `OwnerActionCard`. Values stay in the card's local state and are posted only to `POST /owner-actions/{id}/secret` (owner session).
  - The agent's card is not a form. The agent's Enter handler presses only `.btn.primary[data-ux-type="Button"]`.
  - The catalog has no free-text input.
  - The PR adds no logging.
- Wrong-kind record lookup: `slot_records` scopes to owner, thread and `kind == "secret"`, and tests cover a wrong kind in both directions.
- Fallback row (10.2.3): only a `secret` slot hides the secret row. tsx covers it.
- Ordinary words refused: no. "Key", "Token", "API key", «المفتاح» and "Save"/«حفظ» compile.

## Checked
- pytest on a fresh database (worktree PYTHONPATH): genui_slots, genui_parity, genui_contracts, genui_projector, genui_submit, genui_taint, owner_actions*, secret*: 248 passed. system_policy, capability_exposure, skill_runtime: 68 passed.
- tsx `tests/mobile/conversation-timeline.test.ts`: 5 of 5.
- Playwright web genui.spec.mjs: 9 passed. Expo genui.spec.mjs: 6 passed.
- Height probe: three fields measured 588 px (M1).
- Web i18n: ar 0 missing. 1eda7e1b changes source references only.
- merge-tree against main dcf86b43: conflicts (rebase request).
