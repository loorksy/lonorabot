# Lonora mandate team (26 worker sessions) — owner of every area

The lead (session_0111sgouu67WYk3Zo9wPCpEY) keeps this file current. Read it before touching an area that is not yours; read the owner's open PRs (branch prefixes below) and build on their branches when you depend on them. Migration ids are per worker; the lead re-chains at merge.

| Worker | Area (mandate clauses) | Branch prefix | Migration ids |
|---|---|---|---|
| W-UI | land the web conversation UI (#76) | ui/* | none |
| W-MOBILE | mobile parity of the conversation surface and the P5 mobile shell (13.1, P5) | mobile/* | 0185-0189 |
| W-GENUI | phase 2: GenUI v2 default, mobile v2 renderer, parity (10.1) | genui/* | 0080-0084 |
| W-SLOTS | trusted slots (10.2) with W-GENUI's renderers | slots/* | 0160-0164 |
| W-AUTH | phase 3 core: mode, Mandate card, door, Trade Approval validity, operation key, provenance (#71 #73 #74 #75); approvals without a waiting run (3c); one merged stale-target check (6.6, 14.3.1-14.3.2); the 14.3.18 data migration; deletion of grants, ladder, delegation, activation reviews; frame replacement | wauth/* | 0060-0066 |
| W-PAUSE | owner pauses move (14.3.6), 4.6, 4.7, money_standing (14.3.7), run integrity (6.9, 14.3.4) | pause/* | 0155-0159 |
| W-RECEIPT | Execution Receipt and Settle cards (10.3, 11.2) | receipt/* | 0100-0104 |
| W-TASK | continuous account-management task (4.5, 14.3.3) | task/* | 0105-0109 |
| W-REMOVE | removals: goals (#68), entry-thesis gate (#72), restrictions, money limits and caps (with deal_pnl -> lonora_trading/realized.py) | remove/* | 0067-0069, 0085-0089 |
| W-NOSTOP | Amendment 1: remove Stop entirely (TradingControl, require_trading, "not started", resume_trading, Stop UI and text) | nostop/* | 0150-0154 |
| W-ENV | secret store by scope, redaction (7.2.6), the Secret card and connect_credential mapping (7.2, 10.3) | w-env/* | 0070-0079 |
| W-CLI | the CLI endpoint, per-agent tokens, the `lonora` client, read commands, notify, wake, orders (7.3) | cli/* | 0165-0169 |
| W-WS | the persistent workspace, its tools, injection, "What is running", deletion of the old workspace (7.1, 7.2.5) | ws/* | 0135-0139 |
| W-LEDGER | closed-trade ledger, judgment labels, statistics (5.5.1, 5.5.3, 5.5.4) | ledger/* | 0110-0114 |
| W-PICTURE | the full picture on every wake, close wake and self-review, checkpoint freeze (5.4, 5.5.2) | picture/* | 0115-0119 |
| W-METHOD | method and skill versions, owner methods from files, dormant resources; later the prompt rewrite (5.8) and trading code (5.7) | method/* | 0120-0124 |
| W-TEAM | Lonora's lead powers, flat uncapped team, delete with transfer, supervision and binding removal (3.1.2, 3.2, 3.3, 14.2.6, 14.3.15) | team/* | 0125-0129 |
| W-OWNER | owner model and "What I know about you" (8), peers as data (3.2.3), model and trust from the typed message (12.3, 14.3.8), memory privacy (3.2.4) | owner/* | 0130-0134 |
| W-PRO | routine output (11.6), silence (11.5), wake sources (11.8), app opens and time zone, section 13 sweep of phase 7, calls | wpro/* | 0090-0099 |
| W-ATTN | attention items for the five events, broker-health rule, Lonora's system alerts (3.1.5, 9.4 wake), the attention view (11.7) | attn/* | 0170-0174 |
| W-BRIEF | morning brief (11.1) and weekly report (11.3, 5.5.6) | brief/* | 0175-0179 |
| W-PUSH | device push and the push sender (11.4), Telegram | push/* | 0140-0144 |
| W-BROKER | MetaApi provisioning, connect and manage from chat, broker health, other venues (9) | broker/* | 0145-0149 |
| W-MODELS | model providers: API keys only, adapters, guard test, provider keys from chat (12.1, 12.2) | models/* | 0195-0199 |
| W-ACCEPT | the section 16 acceptance scenario harness (fake terminal, fake provisioning, induced drop and drift, compressed time) and the live demo script | accept/* | none |
| W-SWEEP | section 13 survey of switched-off features in no other worker's area, and the section 17 audit (no raw ids or JSON, Arabic first) outside W-UI's branch | sweep/* | 0190-0194 |
