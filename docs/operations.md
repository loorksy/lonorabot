# Running Lonora in production

## ملخص بالعربية

- **التثبيت:** خادم جديد يحتاج Docker وgpg فقط، دون Python أو Node أو نسخة من الكود. الأمر `sudo bash install.sh --domain نطاقك` ينزّل الصورة، يثبّت بصمتها (digest)، ينشئ الأسرار ومفتاح النسخ الاحتياطي بصلاحيات 600 دون طباعتها، ويشغّل Lonora ثم ينتظر حتى تنجح `/ready`.
- **التحديث:** `sudo lonora update <الإصدار>` يثبّت بصمة الصورة الجديدة، يوقف API وGateway، يأخذ نسخة احتياطية مشفرة ويتحقق منها أولاً، يشغّل الترحيلات خطوةً مستقلة، يشغّل API أولًا ثم Gateway، ثم ينتظر `/ready`. إذا فشلت أي خطوة يعود تلقائيًا إلى الإصدار السابق ويستعيد قاعدة البيانات من النسخة التي أُخذت قبل التحديث.
- **إذا فشل التحديث:** تظهر رسالة «Rolled back to …» ويعمل الإصدار السابق؛ لا تفعل شيئًا آخر. **إذا ظهرت «ROLLBACK HELD»** فمعناها أن الإصدار الجديد ربما أرسل أوامر إلى الوسيط، فلم تُستعد قاعدة البيانات حتى لا تُمحى سجلاتها، وAPI وGateway متوقفان. افحص المراكز والأوامر في منصة الوسيط نفسها، ثم اختر: `sudo lonora rollback --force` (استعادة نسخة ما قبل التحديث؛ تضيع السجلات المكتوبة بعدها) أو `sudo lonora update <إصدار مُصلَح> --keep-data`.
- **إذا انقطع التحديث** (انقطاع SSH أو إعادة تشغيل): `sudo lonora status` يعرض «UPDATE NOT FINISHED»، والأمر `sudo lonora update <الإصدار>` يتراجع عن التحديث المنقطع أولًا ثم يكمل.
- **النسخ الاحتياطي:** نسخة يومية مشفرة (AES-256 عبر gpg) تشمل قاعدة البيانات والمرفقات وملف الإعدادات والإصدار المثبّت وملفات تحديثات التطبيق. يُحتفظ بآخر 14 نسخة.
- **المفتاح:** الملف `/opt/lonora/backup.key` (صلاحية 600، لا يُطبع ولا يُسجَّل أبدًا). **إذا ضاع هذا المفتاح تصبح كل النسخ الاحتياطية غير قابلة للقراءة نهائيًا، ولا توجد أي طريقة لاسترجاعها.** احفظ نسخة منه خارج الخادم، مثلًا في مدير كلمات المرور، وفي مكان منفصل عن النسخ الاحتياطية نفسها.
- **اختبار الاستعادة:** `sudo lonora restore-test` يستعيد أحدث نسخة في بيئة مؤقتة معزولة عن الإنترنت (بلا مفاتيح مزودين أو وسيط، فلا تداول ولا اتصال خارجي)، ويتأكد أن التطبيق يعمل عليها، ثم يحذفها. شغّله مرة شهريًا على الأقل.
- **الاستعادة الفعلية:** `sudo lonora restore <ملف> --replace` تأخذ نسخة احتياطية من الوضع الحالي أولًا، ثم تستبدل البيانات بالنسخة وتشغّل الترحيلات.
- **بعد كارثة (خادم جديد):** ثبّت خادمًا جديدًا بالمثبّت، انسخ إليه ملف النسخة الاحتياطية ومفتاحك `backup.key` (صلاحية 600)، ثم: `sudo lonora restore <ملف> --replace --with-config`. هذا يعيد الأسرار والنطاق من النسخة، ويحتفظ بكلمة مرور قاعدة البيانات الجديدة وبملفات النشر من الصورة.
- **الخادم الحالي (VPS):** لم يُلمس. المسار الموصى به بداية جديدة بقاعدة بيانات فارغة: تُحفظ نسخة كاملة من التثبيت القديم وتُنحّى جانبًا، ثم يُثبَّت النظام الجديد. الخطوات في قسم «Your current server: start fresh» أدناه. نقل التثبيت القديم كما هو خيار إضافي فقط.

## The pieces

| Piece | Where | What it does |
|---|---|---|
| Deployment definition | `infra/compose/docker-compose.prod.yml` | The one canonical production stack: PostgreSQL, API, Gateway, Caddy (HTTPS), plus a `migrate` service that runs only when asked. |
| Optional overlays | `infra/research/compose.research.yml`, `infra/analysis/compose.workspace.yml`, or your own file | Listed in `LONORA_COMPOSE_OVERLAYS` in `.env` (space separated). `lonora` always adds them, so every command sees the same stack. |
| `lonora` command | `infra/compose/lonora` (linked as `/usr/local/bin/lonora`) | Status, start, update, backup, restore, restore test. |
| Installer | `infra/compose/install.sh` | Sets up a new server. |
| Release manifest | `/app/release.json` inside every server image | Version, commit, migration head, minimum client version. |

All of these files ship **inside the server image** under `/app/deploy`. The installer and
`lonora update` copy them from the image to the server, so the server never needs a source
checkout, Git, Python or Node. The files on the server always match the image that runs.

Layout on a server (default `/opt/lonora`):

```
/opt/lonora/.env              configuration and secrets (mode 600)
/opt/lonora/backup.key        backup encryption key (mode 600) — copy it off the server
/opt/lonora/state/image.env   the pinned image, e.g. ghcr.io/loorksy/lonorabot@sha256:…
/opt/lonora/state/history.log one line per update, rollback and the backup taken
/opt/lonora/backups/          encrypted backups, lonora-YYYYMMDDTHHMMSSZ.tar.gpg
/opt/lonora/infra/…           the deployment files from the image
/opt/lonora/.runtime/releases mobile APK and OTA updates (served read-only by the API)
```

## Install a new server

Requirements: Linux with Docker Engine and the Compose plugin, ports 80 and 443 open, and a
domain name pointing at the server. `gpg` is installed automatically on Debian/Ubuntu if missing.

```sh
docker run --rm --entrypoint cat ghcr.io/loorksy/lonorabot:main \
  /app/deploy/infra/compose/install.sh >install.sh
sudo bash install.sh --domain lonora.example.com --version main
```

`--version` takes a tag (`main`, `v0.3.0`) or an exact `repo@sha256:…` reference. The installer:

1. pulls the image and pins its digest in `state/image.env`;
2. copies the deployment files out of the image;
3. creates `.env` with a fresh database password, encryption key, bootstrap token and
   webhook secret, and `backup.key` — all mode 600, never printed;
4. enables the daily backup timer (`lonora-backup.timer`, 03:00);
5. runs `lonora start`: database, migrations, services, and waits for `/ready`.

It is for new installations only: it refuses a directory that already has one (use `lonora update`
there) and refuses to start when a Docker volume `lonora_database` already exists, because the new
install would silently reuse that old data.

Then:

- copy `/opt/lonora/backup.key` somewhere safe that is not this server (a password manager is fine);
- open `https://your-domain` and create the owner account with the bootstrap token from
  `sudo grep LONORA_BOOTSTRAP_TOKEN /opt/lonora/.env`;
- for host hardening (firewall, unattended security updates) run `sudo bash /opt/lonora/infra/compose/harden-host.sh --apply`.

## Update

```sh
sudo lonora update v0.3.0     # or: main, or ghcr.io/loorksy/lonorabot@sha256:…
```

What happens, in order:

1. The tag is resolved to its exact digest. Only that digest is ever run. An installation with no
   pinned image is refused (a rollback would have nothing to return to).
2. The image's release manifest is read. An image without one is refused. If the database is at
   a migration the new image does not know (a downgrade), the update is refused: restore a
   backup made on that version instead.
3. An in-progress marker (`state/update-in-progress`) is written, then API and Gateway are stopped,
   so nothing writes during the next steps.
4. An encrypted backup is taken **and verified** (decrypted, authenticated, every checksum and the
   whole dump read back). If that fails, nothing changes, the marker is removed and the old version
   starts again.
5. The new deployment files are copied in (each file renamed into place) and the new digest is pinned.
6. Migrations run as their own step (`migrate` service).
7. The API starts first, **with the Gateway still stopped**, and must pass `/health`. Only then does
   the Gateway (agent and trading loops) start, and the update waits for `/ready` (default 240 s,
   `LONORA_READY_TIMEOUT`).
8. **If step 5, 6, 7 or a health gate fails**, `lonora` rolls back by itself: the old deployment
   files and pin come back, and the database is **restored from the backup of step 4** — dropped
   and recreated from that dump, not migrated down. An Alembic downgrade after the new version has
   written rows can lose or corrupt data; restoring the pre-update backup cannot. Because API and
   Gateway were stopped before that backup, nothing the owner did is lost, and nothing the failed
   version wrote (including a half-applied migration) survives. Services start, `/ready` is checked
   again, and it says clearly that the update was not applied.

**The money exception — a held rollback.** While the new Gateway runs during the `/ready` wait, it
could send an order to the broker. Before restoring, `lonora` compares a digest of the trading
journal and trade approvals with the one taken at the backup. If they differ, it does **not** drop
the database (that would erase the record of orders that may be live at the broker). It stops API
and Gateway, keeps the failed version pinned, prints `ROLLBACK HELD` and exits with status 2. Then:

1. check positions and orders in the broker's own terminal since the time it shows;
2. choose `sudo lonora rollback --force` to restore the pre-update backup anyway (journal rows
   written since then are lost, so note them first), or
   `sudo lonora update <fixed version> --keep-data` to keep the current data and update forward.

**An interrupted update** (SSH dropped, reboot) leaves the marker behind. `lonora status` shows
`UPDATE NOT FINISHED`, `lonora start` and `lonora restore` refuse to run, and the next
`sudo lonora update <version>` first rolls the unfinished one back (same rules, including the hold),
then performs the requested update. `sudo lonora rollback` only rolls back.

Only one of update, restore, rollback, start and backup runs at a time (a lock in `state/`); the
daily backup waits for a running update. `state/history.log` records every update and rollback
with the backup that was taken.

Expect a short outage (stop → backup → migrate → start), usually under a minute plus backup time.

## Backups

```sh
sudo lonora backup
```

One file per backup, `backups/lonora-<time>.tar.gpg`, mode 600. It is a single gpg file
(AES-256, key stretched with SHA-512) containing:

- `database.dump` — the full PostgreSQL database (`pg_dump -Fc`);
- `artifacts.tar.gz` — all files agents and charts produced;
- `config.tar.gz` — `.env` (which holds the key that decrypts saved provider and broker
  credentials), the pinned image (for information) and the mobile APK/OTA releases. Deployment
  files are not in backups: they always come from the image;
- `manifest.json` — time, image, migration revision and the financial-journal digest;
  `SHA256SUMS` for every member.

Every backup is verified before it is kept: decrypted, authenticated, every checksum checked and
the whole dump read with `pg_restore`. A backup that fails any step is deleted, never kept as good.
Work files (the clear dump while it is being built and checked) live in a mode-700 directory on
the backups disk, not in `/tmp`, and are removed on every exit path.

**If the key is lost, every backup is unreadable for good** — there is no recovery, by design.
Keep a copy off the server (a password manager is fine), separate from where backups are stored.

The key comes from `LONORA_BACKUP_KEY` in the environment if set, otherwise from
`backup.key` (or `LONORA_BACKUP_KEY_FILE`). It is handed to gpg on a file descriptor; it never
appears in a command line, a log or the output. The newest 14 backups are kept
(`LONORA_BACKUP_KEEP`). Not included: Caddy's TLS certificates (re-issued automatically).

Backups stay on the same server. For real protection copy `backups/` off the server
regularly (they are encrypted, so any storage is fine) — and keep `backup.key` in a
different place from the backups.

### Prove a backup restores

```sh
sudo lonora restore-test                       # newest backup
sudo lonora restore-test backups/lonora-….tar.gpg
```

This decrypts the backup, checks every checksum and refuses anything unexpected inside, then
builds a **separate, throwaway** stack: a fresh PostgreSQL, the backup restored into it, the
migrations run, and the API and Gateway started on it. It passes only if `/ready` passes. The
stack runs on a Docker network with **no internet access**, and only the encryption key and the
bootstrap token from the backup are passed in — no provider keys — so it cannot call a model
provider or a broker, and cannot trade. Nothing is shared with the live installation; everything
(containers and their volumes) is deleted afterwards. A wrong key, a damaged file or a forged
one fails with "Decryption failed": only a file gpg really decrypts and authenticates with this key
is accepted — a plain, unencrypted OpenPGP file is refused.

Run it monthly, and after any change to how you back up.

### Restore

```sh
sudo lonora restore backups/lonora-….tar.gpg --replace
```

It refuses a backup whose migration is newer than the installed image knows (update to that
image first). Otherwise it **takes a safety backup of the current state first**, stops API, Gateway
and Caddy, replaces the database with a fresh copy from the backup, replaces the artifact files,
runs the migrations (so an older backup is brought up to the installed version), starts everything
and waits for `/ready`. `--replace` is required.

**Disaster recovery on a new server**, exactly:

```sh
sudo bash install.sh --domain <your domain> --version <the backup's version or newer>
sudo install -m 600 /path/to/your/backup.key /opt/lonora/backup.key
sudo lonora restore /path/lonora-….tar.gpg --replace --with-config
```

`--with-config` also restores the secrets and settings in `.env` (domain, encryption key for saved
credentials, bootstrap token, provider keys) and the APK/OTA release files. It never restores the
database password (the new server's database was created with its own), the overlay list, the
pinned image or any deployment file. Without `--with-config` the current `.env` is kept.

## Release manifest and client versions

Every image carries `/app/release.json`, e.g.:

```json
{"schema": 1, "version": "v0.3.0", "package_version": "0.2.0", "git_sha": "…",
 "built_at": "2026-11-10T00:00:00Z", "migration_head": "0045_chat_lists",
 "min_client_version": "0.2.8"}
```

It is generated at image build time by `scripts/release_manifest.py`, which reads the single
Alembic head from the migration files (a build with two heads fails) and the minimum client
version from `infra/release/compatibility.json`. **Raise `min_client_version` there** in the
same change that makes the server stop working with older mobile/web clients. The CI publish
workflow stamps the tag or branch, the commit and the build time. `lonora status` prints the
manifest of the running image.

## Your current server: start fresh (recommended)

The owner decided the new system starts from an empty database: no agents or data are carried
over. Nothing in this change touched the live VPS. Do this at a quiet time, as root, on the server.
The new stack uses the same Compose project name (`lonora`) and volume names as the old one, so
the old volumes must be archived and then removed — otherwise the new install would reuse them.

1. Stop the old install (use the Compose file it actually runs with):
   `cd /opt/lonora && docker compose --env-file .env -f <its compose file> stop`
2. Archive everything the old install has, in one private directory:

   ```sh
   install -d -m 700 /opt/lonora-old-archive
   for v in database artifacts; do
     docker run --rm --entrypoint tar -v lonora_$v:/data:ro -v /opt/lonora-old-archive:/out \
       postgres:16-alpine -C /data -czf /out/volume-$v.tar.gz .
   done
   ls -l /opt/lonora-old-archive    # both files must exist and not be empty
   ```

   (`docker volume ls | grep lonora_` shows the exact volume names if they differ.)
3. Set the old install aside: `docker compose --env-file .env -f <its compose file> down` (no `-v`),
   then `mv /opt/lonora /opt/lonora-old`. Its `.env` (with the old encryption key) stays in
   `/opt/lonora-old`; keep that directory and the archive private, they hold secrets.
4. Only after step 2 succeeded, remove the old volumes so the new database starts empty:
   `docker volume rm lonora_database lonora_artifacts`
5. Install the new system as in «Install a new server» above, with your domain. Copy the new
   `backup.key` off the server.
6. Optional: to keep the existing Android download and OTA updates working, copy them over
   before clients update: `cp -a /opt/lonora-old/.runtime/releases/. /opt/lonora/.runtime/releases/`
7. Check: `sudo lonora status` shows `/ready: ok`; open the site and create the owner account;
   then `sudo lonora backup` and `sudo lonora restore-test`.

Once the new system has run well for a while, `/opt/lonora-old` and `/opt/lonora-old-archive`
can be deleted. Until then they are the only way back to the old system.

## Optional: adopting the existing install instead

Not the recommended path (see above) and **not supported** for the owner's server; kept for a
future server whose data must be kept. Known limits on this path: an image built on the server has
no registry digest, so its local tag is a mutable pin; old backup timers that call
`infra/compose/backup-prod.sh` keep working only once `backup.key` exists; ports the old Compose file
published must be re-declared in an overlay; `deploy-main.sh` on a checkout and re-running
`install.sh` there are not supported; and the lifecycle test's adoption check starts from an empty
database, so it proves the mechanics, not that real data carries over.
Nothing in this change touched the live VPS. The VPS today runs its own customised
Compose file (see `docs/lonora-specs/DEPLOYMENT_2026_10_19.md`) from the checkout in `/opt/lonora`.
To adopt it, at a quiet time:

1. Compare: `cd /opt/lonora && git pull` (or copy the new `infra/` files in), then
   `infra/compose/lonora config` prints the canonical stack (variables not expanded, so no secrets).
   Put every real difference of the VPS file — published ports, extra mounts, extra services — into
   one overlay file, e.g. `infra/compose/site.yml`, and list it in `LONORA_COMPOSE_OVERLAYS`.
   Keep the Compose project name `lonora` and the volume names (`database`, `artifacts`) so the
   existing data is used as is.
2. Create the backup key: `sudo sh -c 'umask 077; head -c 48 /dev/urandom | base64 >/opt/lonora/backup.key'`
   and copy it off the server.
3. Pin what runs today: `mkdir -m 700 -p state && echo "LONORA_IMAGE=<current image>" >state/image.env`.
   `docker image inspect --format '{{index .RepoDigests 0}}' "$(docker inspect lonora-api-1 --format '{{.Image}}')"`
   prints its `repo@sha256:…` reference; for an image built on the server (no registry digest), use its
   local tag instead and keep that image on the server until the first update succeeded — it is what a
   rollback returns to.
4. `sudo infra/compose/lonora backup`, then `sudo infra/compose/lonora restore-test`.
5. The first update, exactly: `cd /opt/lonora && sudo infra/compose/lonora update <version>`. It
   resolves the version to a digest, reads its release manifest, stops API and Gateway, takes the
   encrypted backup, copies the new deployment files from the image into `infra/` (this replaces the
   checked-out ones; your differences live in the overlay from step 1), pins the digest in
   `state/image.env`, runs `migrate` as its own container, starts everything and waits for `/ready`,
   rolling back on failure. From then on **the API no longer migrates when it starts**
   (`LONORA_MIGRATE_ON_START=false` in the canonical Compose file): migrations run only through
   `lonora update`, `lonora start` or `deploy-main.sh`. The lifecycle test below includes exactly this
   adoption path (an installation running an image from before this tooling).
6. Install the backup timer: `sudo install -m 644 infra/systemd/lonora-backup.* /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now lonora-backup.timer`.

`infra/compose/deploy-main.sh` (build from source on the server) still uses the same Compose
file, backs up with `lonora backup` (so it needs `backup.key`) and runs migrations as a separate
step. It does not pin digests or roll back; use `lonora update` instead.

The `docker-compose.postgres-host.yml` overlay (PostgreSQL on the host instead of the `db` service)
points API, Gateway and `migrate` at the host database. `lonora backup`, `restore` and the rollback
work only with the bundled `db` service.

## Testing

`tests/ops/lifecycle_test.sh REPO` runs the whole lifecycle against real Docker on a disposable
machine. It uses the project name `lonora`, its volume names and ports 80/443, so it refuses to run
where a Lonora installation exists. It checks, in order:

1. install (digest pinned, secrets mode 600 and never printed, bundle modes, no second install);
2. no secret in the image's bundle or `release.json`;
3. seed an owner account and an artifact;
4. backup: verified; the decrypted copy holds the dump and `.env`, the file holds neither in clear;
5. restore test, leaving no container or volume behind;
6. damaged file, wrong key and a forged plaintext backup refused, nothing changed;
7. a failing and a truncating `pg_dump`: the update aborts before pinning, the live database untouched;
8. refusals: a concurrent operation (lock), no pinned image, an image without a release manifest;
9. update, API gated before the Gateway, the script replaced atomically;
10. a broken update rolled back from the pre-update backup, earlier rows kept;
11. a journal row written during the `/ready` wait: rollback held, then `rollback --force`;
12. an update killed mid-way: marker kept, `start` refused, the next update rolls back and completes;
13. `restore --replace`: safety backup first, an older backup migrated to the image head;
14. disaster recovery: a newer backup refused on an older image; `--with-config` restores the
    secrets and keeps the new database password;
15. adoption of an installation on an image from before this tooling (optional path).

`REPO` must hold the tags `old`, `v1`, `v2`, `v3-broken` and `v4-good` described at the top of the
script; any local registry (`docker run -d -p 127.0.0.1:5000:5000 registry:2`) works.

### What was verified, and what still needs a real host

Verified in a development container with Docker 29.9 and Compose 5.6, real images, a real local
registry (real digests), PostgreSQL 16: all 15 lifecycle checks passed.

The fresh-start steps 2, 4 and 5 were also run here against volumes named like the old ones
(`lonora_database` with a PostgreSQL cluster, `lonora_artifacts` with a file): both archives were
complete, and the new install came up with `/ready` passing, no old table, no owner and no artifacts.

Still to be checked on a real server:

- The test images were built from the real `Dockerfile` with only the Chromium and font `apt-get`
  line removed (the development container cannot reach the Debian package mirror). That line stays
  in the production `Dockerfile` unchanged: Chromium drives the server chart renderer (TradingView
  image capture, `LONORA_CHART_BROWSER_EXECUTABLE=/usr/bin/chromium`) and the fonts render chart text.
  `/ready` does not depend on them, which is why the lifecycle passed without them; chart capture was
  not exercised here. The full production image build itself was not run here.
- Caddy obtaining a real certificate for a public domain (the test used `localhost`).
- The systemd backup timer (installed with `--no-systemd` in the test).
- Pulling from `ghcr.io` (the test used a local registry), and the CI publish workflow, which
  cannot run while GitHub Actions is unavailable.
- The fresh-start procedure on the actual VPS (its customised Compose file is not in the repository).
