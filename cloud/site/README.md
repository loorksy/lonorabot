# Lonora Cloud website: registration, approval and activation

The company website, the customer's portal account and the staff admin panel (docs/cloud/DECISIONS.md D46). Since D48 everything runs on **one server**: the website, the admin panel, the build of each release and every customer's own installation.

- `cloud/site/`: the pages (`public/`), the handlers (`functions/`), the database tables (`schema.sql`) and the tests.
- `cloud/host/`: what runs them on the server. `server.mjs` (the website), `compose.yml` (shared: Caddy with automatic TLS, PostgreSQL, SearXNG), `customer.yml` (one customer's Lonora), `customer.sh` (create, update, remove, release), `Caddyfile`, `lonora-site.service`.

It lives here only until `loorksy/lonora-cloud` exists (D2). Nothing under `cloud/` goes into the Lonora image (VISION Amendment 3 §7).

## بالعربية

**ما يفعله:** الزائر ينشئ حساباً (الاسم، البريد، كلمة المرور، الدولة، اللغة، والموافقة على الشروط وإفصاح المخاطر) فيبقى «بانتظار الموافقة». من لوحة الإدارة توافق أو ترفض بسبب يراه العميل. زر **«تفعيل بضغطة واحدة»** ينشئ نسخة Lonora الخاصة بالعميل على الخادم نفسه في أقل من دقيقة: قاعدة بيانات ودور خاصان به، ومفتاح تشفير خاص به، وخادم Lonora وعامله، وعنوانه `اسمه.lonora.app` بشهادة TLS تلقائية. ويصبح حساب الموقع مالك نسخته بكلمة المرور التي سجّل بها (D7)، فيرى العميل «افتح في التطبيق» ويدخل بنفس البريد وكلمة المرور، دون تسجيل ثانٍ. كل قرار يُسجَّل باسم الموظف. الشركة لا تدخل إلى نسخة العميل، ومفاتيح النماذج يضعها العميل بنفسه داخلها (BYOK).

### مرة واحدة: تجهيز الخادم (Hostinger KVM 4، Ubuntu 24.04)

1. **النطاق:** عند مزوّد النطاق سجلّا A إلى عنوان الخادم: `lonora.app` و`*.lonora.app`.
2. **الأدوات:**
   ```
   curl -fsSL https://get.docker.com | sudo sh
   curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash - && sudo apt-get install -y nodejs git
   sudo git clone https://github.com/loorksy/lonorabot /srv/lonora/src
   ```
3. **إعدادات الخادم** في `/srv/lonora/host.env`: `BASE_DOMAIN=lonora.app` و`SITE_DOMAIN=lonora.app` و`ACME_EMAIL=بريدك`.
4. **دخول الموظفين:** لكل موظف سطر «البريد ثم البصمة» في `/srv/lonora/caddy/staff`. البصمة من:
   ```
   sudo docker run --rm -it caddy:2.10-alpine caddy hash-password
   ```
5. **إعدادات الموقع** في `/srv/lonora/site.env` (لا يقرؤها غير الجذر): `SITE_ORIGIN=https://lonora.app`، `BASE_DOMAIN=lonora.app`، `ADMIN_EMAILS=` (البريد نفسه، وبينها فاصلة)، و`TERMS_VERSION` و`RISK_VERSION` و`PRIVACY_VERSION`.
6. **التشغيل:**
   ```
   sudo /srv/lonora/src/cloud/host/customer.sh init
   sudo /srv/lonora/src/cloud/host/customer.sh release <رقم الالتزام الكامل>
   ```
   الأول يشغّل الخدمات المشتركة والموقع. الثاني يبني صورة Lonora مرة واحدة.

### كل يوم

- **مراجعة الحسابات:** `https://lonora.app/admin`. موافقة، أو رفض بسبب، ثم **تفعيل بضغطة واحدة**. إن فشل التفعيل يُحذف ما أُنشئ، ويظهر السبب وزر **إعادة المحاولة**. التفعيل اليدوي بعنوان ورابط ما زال متاحاً.
- **إصدار جديد لكل العملاء:** `sudo /srv/lonora/src/cloud/host/customer.sh release <رقم الالتزام>`: بناء واحد، ثم ينتقل كل عميل في ثوانٍ.
- **مساحة العمل والمتصفح** تعمل عند الطلب، بحد 1 GB لكل منهما: `customer.sh workspace <الاسم> start` أو `stop`.
- **إيقاف مؤقت:** يخص حساب الموقع فقط، ولا يمس صفقاته ولا وكلاءه (التعديل 3، البند 9).
- **حذف شخص بطلبه:** «حذف بطلبه» يحذف الحساب، ونسخته بكل بياناتها إن وُجدت. يبقى في السجل أثر مشفّر فقط.
- **تصدير CSV:** تُعطَّل الخلايا التي قد تعمل كمعادلة.
- **نسخة من قائمة الحسابات:** `sudo sqlite3 /srv/lonora/site/site.db ".backup /root/lonora-site.db"`.

الاتساع: نحو ستة عملاء براحة وثمانية على الأكثر، ثم يُرفع الخادم إلى KVM 8. يُقاس استهلاك الذاكرة الحقيقي على الخادم قبل أول عميل.

## English

**What it does:** a visitor registers and waits as `pending`. Staff approve or reject in the admin panel. **"Activate in one click"** runs `customer.sh create <handle>`, which in under a minute creates the customer's own database and role in the shared PostgreSQL, an env file (mode 600) with the customer's own encryption key and database password, the customer's Lonora server and worker from the current release image, the website account as its owner (with the password the customer signed up with, D7), and the route `https://<handle>.<BASE_DOMAIN>` in Caddy. It waits until `/ready` answers there. The account then turns active and the customer sees "Open in the app" and signs in with the same email and password: there is no second sign-up. If any step fails, `customer.sh remove` undoes it, the account returns to `approved` with the script's message, and "Retry" appears.

### One-time host setup

The Arabic steps above, in short: A records for `lonora.app` and `*.lonora.app`; Docker, Node 22 and git; the repository in `/srv/lonora/src`; `host.env` (`BASE_DOMAIN`, `SITE_DOMAIN`, `ACME_EMAIL`, optional `WORKSPACE_DISK`, default `10g`); one `email bcrypt-hash` line per staff member in `/srv/lonora/caddy/staff`; `site.env` (`SITE_ORIGIN`, `BASE_DOMAIN`, `ADMIN_EMAILS`, Turnstile keys, document versions); then `customer.sh init` and `customer.sh release <full commit id>`.

`init` widens Docker's network pools once (`/etc/docker/daemon.json`: 256 networks of /24 in `10.201.0.0/16`, since the default of about 30 would stop new customers after nine or ten), starts the shared services, creates the `lonora-site` user, installs `lonora-site.service` and the nightly `lonora-backup.timer`, and allows that user exactly two root commands: `customer.sh create *` and `customer.sh remove *` (`/etc/sudoers.d/lonora-site`). The website listens only on a unix socket that Caddy reaches.

### Daily use

- **Activate:** the admin panel. If the panel cannot, `sudo customer.sh create <handle>` (nothing on stdin) prints a one-time setup link for a manual activation.
- **Ship a release:** `sudo customer.sh release <git ref>` builds the image once (`infra/compose/build-from-source.sh`, capped at 2 CPUs and 3 GB) and switches every customer with `update`. Each Lonora runs its migrations as it starts.
- **Workspace and browser:** on demand, 1 GB each: `customer.sh workspace <handle> start|stop`.
- **Delete on request:** removes the account and, with confirmation, the customer's installation and data (`customer.sh remove`).
- **Backups:** every night at 02:17 UTC, `customer.sh backup` writes `/srv/lonora/backups/<date>/` (mode 700): `postgres.sql.gz` (every customer's database and role), `site.db` (accounts and decisions) and `keys.tar.gz` (each customer's `.env` with its encryption key, `host.env`, `site.env`, `release.env`, `caddy/`). Without the keys the database copy cannot be read, so both are kept together. The last 7 nights stay on this disk; turn on the provider's server backup (Hostinger: weekly, in hPanel) for a copy off this disk. Workspaces are not included (D10). Run it by hand any time: `sudo customer.sh backup`.
- **Restore:** stop the site and the customers, then `gunzip -c postgres.sql.gz | docker exec -i lonora-postgres psql -U postgres`, `tar -xzf keys.tar.gz -C /srv/lonora`, copy `site.db` to `/srv/lonora/site/` (owner `lonora-site`), and start everything again (`customer.sh update <handle>` for each customer).
- **New staff member:** add the line to `caddy/staff`, the email to `ADMIN_EMAILS`, then `docker exec lonora-caddy caddy reload --config /etc/caddy/Caddyfile` and `systemctl restart lonora-site`. The staff file must never be empty, or Caddy refuses its configuration.

### Security notes

- Staff sign in at Caddy (`basic_auth` on `/admin` and `/api/admin`). Caddy passes the name in `X-Staff-Email` and removes that header from every other request; the site also checks it against `ADMIN_EMAILS`.
- Customers are separated by database role (`REVOKE ALL … FROM PUBLIC`), by their own keys, and by container names on the shared networks. The database network has no route out. Each workspace runs behind its own network guard on its own fixed-size disk and cannot reach this host's addresses.
- Registration, sign-in, sessions, headers and logs work as before: same-origin POSTs, honeypot, rate limits, no account enumeration, hashed `__Host-` session tokens, and no body, email, password or token in any log. Cloudflare Turnstile is off by default (D48: no Cloudflare); setting `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET` turns it back on. Signups still wait for staff approval (D46).

### Tests

`npm test` runs 47 tests with Node's built-in runner: the site through `server.mjs` with an in-memory SQLite, and activation with the real `customer.sh` in dry-run mode (`--dry-run` prints every Docker and system command instead of running it; files go to `LONORA_HOST_HOME`). Turnstile is stubbed. The legal texts are drafts until counsel reviews them (D20).
