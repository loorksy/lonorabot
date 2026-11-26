# Lonora website

- `Lonora_Website_v03.html`: the v03 prototype, kept unchanged.
- `cloud/site/public/index.html`: **v04**, served by the Cloudflare Pages project in `cloud/site/` (Phase W, PW-T1 to PW-T3).

v04 is v03 made true to the product, with normal registration that waits for staff approval. It keeps v03's tokens,
fonts, 3D world, layout and motion. It is still Arabic first, with English through `.ar` and `.en` spans.

## Truth changes from v03, and the clause behind each

| Change | Clause |
|---|---|
| Two trading modes only, «يستأذن» Ask and «وكّله» Full, switched by one tap on the mode card. Home chapter 03 "Your limits" is now "Your mode". The trading page's four mandate levels are now the two modes, with a mock of the mode card. The FAQ, company principle 03 and an updates post follow. | VISION 4.1, 4.2, 10.3 |
| No limits, caps, restrictions, goals or signed mandates. Removed: "Max daily loss" (home, memory panel, sign-up), the 4-level ladder, "Limits the server enforces", "within your mandate", "Mandates and limits" rows and the "+300$ monthly goal". The goal is now the memory item "Prefers the London session". | VISION P1, 4.4, 5.8.2 |
| No Stop. Removed "Stop everything now", "Emergency stop", "revoke the mandate" and the stop icon. "Stop it with a word" is now "Pause it with a word", because pausing an agent is kept. | Amendment 1; VISION 4.6, 4.7 |
| MetaTrader 5 only, on any symbol the owner's broker offers, with no crypto exchanges or other venues. | Amendment 2 |
| A flat team. Lonora leads, agents are created in a sentence, there is no cap on agents, and each agent trades under its own mode. "Risk Guard: guards your limits" is now the "Trade Manager". The per-agent "Can/Cannot execute" scope is now "Mode: Ask". "Ten desks" is gone. Each agent has its own memory, not its own workspace. | VISION 3.1 to 3.3, 4.3 |
| Lonora Cloud: one dedicated installation per customer, which we cannot sign in to or read. The broker connection needs only the account number, server and password, and the password passes once to MetaApi and is never stored by us. The customer brings their own model key. Plans limit hosting resources only. | Amendment 3 §1, §3, §4, §10; D6, D27, D41 |
| The native Android app is the product, and the site is for the account. "Web, desktop, iOS, Android" is now the Android app, with iOS later and Telegram optional. The desktop-app post is gone. | D36, D9, D40; VISION 11.4 |
| The plans page is «الباقات» / Plans, at route `#plans` (`#levels` still opens it). It shows Starter, Pro, Max and Enterprise with server size, workspace (memory, CPU, disk), storage, backups and snapshots, included MT5 connections (1, 2, 5; more later for a monthly fee), support and a custom domain on Max. Prices read "Announced at launch". The monthly/yearly toggle is removed. There are no rows for agents, watches, models, voice minutes or owners. "Most chosen" and "Lonora for teams" (a shared Lonora, roles) are replaced by an Enterprise section. The sizes are marked provisional. | D13 (sizes from PLAN §5.1), D14, D18, D28; Amendment 3 §4 |
| No promises. Removed "Ready in a minute", "wakes within a minute", "around the clock", "fills the order", "Thousands of private spaces" and "No copy keeps it". The product balance card now carries "Illustrative example, not real performance". The trading risk note and a footer line say there is no guarantee of profit, of execution or of uninterrupted service. | Owner brief for v04 |
| Security page: your own isolated Lonora; we can't sign in to it or read your keys or conversations; the broker password passes once to MetaApi; nothing new reaches your broker on Ask without your approval; every execution has a broker receipt; encrypted backups; export and delete; your own model key. | Amendment 3 §3, §10; VISION 10.3 |
| The legal pages are drafts pending counsel, with a banner and the draft version `draft-2026-11-25` (the same value as `TERMS_VERSION` in `wrangler.toml`). | D19 to D21 |

## Registration and the account (D46, D7)

- **Create your account** (`#start`, «إنشاء حساب») is one form. Required: name, email, password (10 to 128 characters), country (ISO-2, from a list of common countries) and language. Optional: the MT5 broker and what you want Lonora for (`watch`, `trade`, `analysis`, `news`, `brief`, `other`). Two required checkboxes link to the legal drafts. The form has a hidden honeypot field `website` and a Turnstile widget. It sends `POST /api/register` as JSON with same-origin credentials.
  - **202:** the exact "If this email is new…" text, with a sign-in button.
  - **400 with a field:** the error appears under that field, in both languages, with `aria-invalid` set.
  - **Other answers:** 429, 403, `challenge` and network errors each get their own message.
- **Sign in to your account** (`#login`) sends `POST /api/login`. The page says plainly that this signs in to the company account, not to your Lonora. On 200 it opens the account page. On 401 it shows «البريد أو كلمة المرور غير صحيحة».
- **Your account** (`#account`) reads `GET /api/me`:
  - `pending`, `approved` and `provisioning` show their status text. While `provisioning`, the page polls every 20 s, and it stops polling when the status changes or the visitor leaves the page.
  - `active` shows the instance address and two buttons, «افتح في التطبيق» and «رابط الإعداد الأول», with a note that the setup link works once. Only `https:` links are followed.
  - `rejected` and `suspended` show the reason.
  - 401 goes to the sign-in page.
  - "Sign out" sends `POST /api/logout`.
- **Nav:** "Sign in" and a primary "Create account". "My account" replaces both while a sign-in hint is stored; `/api/me` remains the source of truth.
- **Turnstile:** the script loads only when the start or sign-in page opens. The widget renders explicitly with `turnstile_site_key` from `GET /api/config`.
- **No server:** under `file://`, or when `/api` can't be reached, every portal page shows "Preview — the server is not connected", and nothing is reported as sent. The contact form is not wired to a server, so it says it sends nothing.

## Quality

- **Reduced motion:** with `prefers-reduced-motion`, the home page uses the existing flat world (no WebGL).
- **3D rendering:** WebGL `devicePixelRatio` is capped at 1.5 on phones (coarse pointer). The render loop pauses when the tab is hidden or the world is off-screen; v03 already did this, and it is kept.
- **Scripts:** all seven three.js 0.147.0 script tags have `integrity` (sha384) and `crossorigin="anonymous"`.
- **Metadata:** a bilingual meta description and Open Graph tags (no image yet). `lang` and `dir` switch with the language.
- **Forms:** every control has a label. Errors are linked with `aria-describedby`. Controls are at least 44 px high. In RTL, the password field leaves room for the show-password button.

## Open

- The Open Graph image, the country list (D21) and the contact endpoint are still to come.
- Prices are announced at launch (D14), and the plan sizes stay provisional while D13 is deferred.
