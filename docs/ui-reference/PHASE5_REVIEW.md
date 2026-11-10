# UI phase 5 — eye-review sheet

Settings, onboarding and usage against `Lonora-Desktop-37.html`, run with
`tests/ui-reference/side-by-side.mjs --only=<the states below> --themes=dark --no-bindings`
(a fresh `*_ci` database seeded by `seed_reference.py`). Pixel mismatch is a report, not a gate:
the reference's demo data (spend, accounts, facts, providers) is not in the app's database, and
the rows the owner decisions removed are absent on purpose. The gate is the computed-style probe
of the reference's own class names (`.prefs-row`, `.lang-select`, `.theme-switch`, `.reach-opt`,
`.switch`, `.u-*`, `.store-*`, `.pf-log .row`, `.lk-*`) and the browser tests in
`tests/web/settings.spec.mjs`.

| State | 390×844 | 1280×800 | What differs, and why |
| --- | --- | --- | --- |
| settings-root | 3.7% | 1.6% | No «خلفية المحادثة» (phase 3), «تجربة المحادثة» (phase 3 reads it), «المساعدة والدعم» (Q49) or «حول Lonora» (Q54); the Lonora version is the last line. |
| settings-owner | 12.9% | 7.5% | The reference seeds facts and a change log; a fresh owner has none. Zones are IANA names, not the demo city list. |
| settings-notify | 5.9% | 1.9% | No browser-notification row (Q10). «الجهاز» lists the devices registered for the passkey (the server rings one device), not «this · computer · all». «العاجل يصل دائمًا» is a fixed fact (critical items always show), not a switch. |
| settings-integrations | 6.3% | 3.0% | Demo accounts, GitHub repos and skills of the reference are not seeded. Telegram reads as an inbound channel to an agent (Q53). |
| settings-privacy | 1.8% | 1.0% | No «البيانات» group (Q48) and no prototype footnote. The biometric row appears only where a platform authenticator exists (Q51). |
| settings-storage | 4.9% | 2.1% | Parts are what this browser really keeps (drafts and unsent messages, settings, cache); no media group or chat export (Q48: no data export actions). |
| settings-a11y | 5.7% | 2.8% | Same layout; bubble preview uses the app's bubble classes. |
| usage | 7.7% | 5.3% | No budget meter or «تعديل الحد» (D4, Q22): the card shows month to date, the day of the month and the projection. Real figures from WP-I (zero on a fresh database). |
| broker-form | 12.5% | 7.7% | The server's fields (Q52): MetaApi preselected (account number, token, region), «حساب تجريبي» (simulation) second; no password or server field. The account type shows only for the demo account (the server has no real/demo fact for MetaApi). A demo account imports its market snapshot on its account page. |
| lock | 1.6% | 0.5% | Same keypad and dots. The code is a PBKDF2 salted digest, wrong tries and the cool-down survive a reload, and while locked the page behind is inert (no keys, no focus, no shortcuts). |

Not built in this phase (recorded deviations): `settings.chat-prefs` and the wallpaper row (they
belong to the conversation of phase 3, which must read them first; a switch that changes nothing
would be faked), the per-agent MCP allow list (Q55), stdio MCP (Q56), phone/OTP, sign-up and
forgot-password (Q46), support sheets (Q49), legal pages (Q50), «حول» (Q54), the provider form's
model select (the server stores a key per provider, not a default model; models are chosen per
agent) and deleting a provider key (no server route).

Auth: the intro slides show on a device's first visit and again after the owner signs out, as
the reference's `signOut` does; a session the server ended shows «انتهت جلستك» instead.
