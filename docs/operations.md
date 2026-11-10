# Running Lonora in production

## ملخص بالعربية

- **التثبيت:** خادم جديد يحتاج Docker وgpg فقط، دون Python أو Node أو نسخة من الكود. الأمر `sudo bash install.sh --domain نطاقك` ينزّل الصورة، يثبّت بصمتها (digest)، ينشئ الأسرار ومفتاح النسخ الاحتياطي بصلاحيات 600 دون طباعتها، ويشغّل Lonora ثم ينتظر حتى تنجح `/ready`.
- **التحديث:** `sudo lonora update <الإصدار>` يثبّت بصمة الصورة الجديدة، يوقف API وGateway، يأخذ نسخة احتياطية مشفرة أولاً، يشغّل الترحيلات خطوةً مستقلة، ثم ينتظر `/ready`. إذا فشلت أي خطوة يعود تلقائيًا إلى الإصدار السابق ويستعيد قاعدة البيانات من النسخة التي أُخذت قبل التحديث.
- **النسخ الاحتياطي:** نسخة يومية مشفرة (AES-256 عبر gpg) تشمل قاعدة البيانات والمرفقات وملف الإعدادات والإصدار المثبّت وملفات تحديثات التطبيق. يُحتفظ بآخر 14 نسخة.
- **المفتاح:** الملف `/opt/lonora/backup.key` (صلاحية 600، لا يُطبع ولا يُسجَّل أبدًا). **إذا ضاع هذا المفتاح تصبح كل النسخ الاحتياطية غير قابلة للقراءة نهائيًا، ولا توجد أي طريقة لاسترجاعها.** احفظ نسخة منه خارج الخادم، مثلًا في مدير كلمات المرور، وفي مكان منفصل عن النسخ الاحتياطية نفسها.
- **اختبار الاستعادة:** `sudo lonora restore-test` يستعيد أحدث نسخة في بيئة مؤقتة معزولة عن الإنترنت (بلا مفاتيح مزودين أو وسيط، فلا تداول ولا اتصال خارجي)، ويتأكد أن التطبيق يعمل عليها، ثم يحذفها. شغّله مرة شهريًا على الأقل.
- **الاستعادة الفعلية:** `sudo lonora restore <ملف> --replace` تستبدل البيانات الحالية بالنسخة.
- **الخادم الحالي (VPS):** لم يُلمس. نقله إلى هذا النظام خطوة يدوية موصوفة في قسم «Moving the existing server» أدناه.

## ما المطلوب منك

كل الأوامر تُشغَّل على الخادم بصلاحية المدير (`sudo`). لا يطبع أي أمر منها أسرارك.

### أولًا: مفتاح النسخ الاحتياطي (مرة واحدة، وهو الأهم)

1. المفتاح موجود في الملف `/opt/lonora/backup.key`.
2. اعرض محتواه مرة واحدة فقط لتنسخه: `sudo cat /opt/lonora/backup.key`
3. احفظه في مدير كلمات المرور (أو أي مكان آمن خارج الخادم)، **وليس** في نفس مكان النسخ الاحتياطية.
4. **إذا ضاع هذا المفتاح، تصبح كل النسخ الاحتياطية غير قابلة للقراءة نهائيًا.** لا توجد طريقة لاسترجاعها.

### ثانيًا: نقل خادمك الحالي إلى النظام الجديد (مرة واحدة، في وقت هادئ)

خادمك الحالي يعمل من `/opt/lonora` بملف Compose معدَّل خاص به. الخطوات:

1. حدّث الملفات: `cd /opt/lonora && sudo git pull`
2. اعرض التعريف الرسمي للنظام (بدون أي أسرار): `sudo infra/compose/lonora config`
   قارنه بملف Compose المعدَّل على خادمك. ضع كل اختلاف حقيقي (منافذ، مجلدات إضافية، خدمات إضافية)
   في ملف واحد، مثلًا `infra/compose/site.yml`، ثم أضف هذا السطر إلى `/opt/lonora/.env`:
   `LONORA_COMPOSE_OVERLAYS=infra/compose/site.yml`
   لا تغيّر اسم المشروع `lonora` ولا أسماء المجلدات `database` و`artifacts`، حتى تبقى بياناتك كما هي.
3. أنشئ مفتاح النسخ الاحتياطي:
   `sudo sh -c 'umask 077; head -c 48 /dev/urandom | base64 >/opt/lonora/backup.key'`
   ثم نفّذ «أولًا» أعلاه واحفظه خارج الخادم.
4. ثبّت الإصدار الذي يعمل الآن (حتى يكون الرجوع إليه ممكنًا):
   `sudo mkdir -m 700 -p /opt/lonora/state`
   `sudo docker image inspect --format '{{index .RepoDigests 0}}' "$(sudo docker inspect lonora-api-1 --format '{{.Image}}')"`
   اكتب الناتج في الملف: `echo "LONORA_IMAGE=<الناتج>" | sudo tee /opt/lonora/state/image.env`
   إذا كان الناتج فارغًا (صورة بُنيت على الخادم)، اكتب اسم الصورة المحلي بدلًا منه، ولا تحذف تلك الصورة حتى ينجح أول تحديث.
5. خذ نسخة احتياطية وجرّب استعادتها:
   `sudo infra/compose/lonora backup`
   `sudo infra/compose/lonora restore-test`
   يجب أن تظهر عبارة `Restore test passed`.
6. أول تحديث: `cd /opt/lonora && sudo infra/compose/lonora update <الإصدار>`
   هذا الأمر يوقف API وGateway، يأخذ نسخة احتياطية مشفرة، يضع ملفات النشر الجديدة، يشغّل الترحيلات خطوةً مستقلة،
   ثم ينتظر `/ready`. إذا فشل أي شيء يعود وحده إلى الإصدار السابق ويستعيد قاعدة البيانات من النسخة التي أخذها قبل التحديث.
   **من الآن لا يشغّل API الترحيلات عند بدئه**؛ الترحيلات تتم فقط عبر `lonora update` أو `lonora start`.
7. فعّل النسخ الاحتياطي اليومي:
   `sudo install -m 644 /opt/lonora/infra/systemd/lonora-backup.* /etc/systemd/system/`
   `sudo systemctl daemon-reload && sudo systemctl enable --now lonora-backup.timer`

### ثالثًا: تثبيت خادم جديد (إن احتجت يومًا)

1. ثبّت Docker مع إضافة Compose، وافتح المنفذين 80 و443، ووجّه نطاقك إلى الخادم.
2. نزّل المثبّت من الصورة نفسها:
   `docker run --rm --entrypoint cat ghcr.io/loorksy/lonorabot:main /app/deploy/infra/compose/install.sh >install.sh`
3. شغّله: `sudo bash install.sh --domain نطاقك --version main`
4. نفّذ «أولًا» أعلاه لحفظ مفتاح النسخ الاحتياطي.
5. افتح `https://نطاقك` وأنشئ حساب المالك. رمز الإعداد الأول تجده بهذا الأمر (لا يُعرض تلقائيًا عن قصد):
   `sudo grep LONORA_BOOTSTRAP_TOKEN /opt/lonora/.env`

### رابعًا: الاستخدام المعتاد

- تحديث: `sudo lonora update <الإصدار>`
- حالة النظام: `sudo lonora status`
- نسخة احتياطية الآن: `sudo lonora backup`
- اختبار الاستعادة (مرة شهريًا على الأقل): `sudo lonora restore-test`
- استعادة فعلية تستبدل البيانات الحالية: `sudo lonora restore /opt/lonora/backups/<الملف> --replace`
- استعادة على خادم جديد بعد كارثة: ثبّت خادمًا جديدًا (ثالثًا)، انسخ ملف النسخة الاحتياطية والمفتاح إليه، ثم:
  `sudo lonora restore <الملف> --replace --with-config`
- انسخ مجلد `/opt/lonora/backups/` إلى خارج الخادم بانتظام (الملفات مشفرة، فأي تخزين يصلح).

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

Running it again is safe: an existing `.env`, `backup.key`, data and volumes are kept.

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

1. The tag is resolved to its exact digest. Only that digest is ever run.
2. The image's release manifest is read. An image without one is refused. If the database is at
   a migration the new image does not know (a downgrade), the update is refused: restore a
   backup made on that version instead.
3. API and Gateway are stopped, so nothing writes during the next steps.
4. An encrypted backup is taken. If it fails, nothing changes and the old version starts again.
5. The new deployment files are copied in and the new digest is pinned.
6. Migrations run as their own step (`migrate` service).
7. All services start and the update waits for `/ready` (default 240 s, `LONORA_READY_TIMEOUT`).
8. **If step 5, 6, 7 or the health gate fails**, `lonora` rolls back by itself: the old deployment
   files and pin come back, the database is **restored from the backup of step 4** — dropped and
   recreated from that dump, not migrated down. An Alembic downgrade after the new version has
   written rows can lose or corrupt data; restoring the pre-update backup cannot. Because API and
   Gateway were stopped before that backup, nothing the owner did is lost, and nothing the failed
   version wrote (including a half-applied migration) survives. Services start and `/ready` is
   checked again. It then says clearly that the update
   was not applied. If even the rollback cannot reach `/ready`, it prints the backup file to
   restore by hand.

`state/history.log` records every update and rollback with the backup that was taken.

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
  credentials), the pinned image, the deployment files, and the mobile APK/OTA releases;
- `manifest.json` — time, image and migration revision; `SHA256SUMS` for every member.

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
is deleted afterwards. A wrong key or a damaged file fails with "Decryption failed".

Run it monthly, and after any change to how you back up.

### Restore

```sh
sudo lonora restore backups/lonora-….tar.gpg --replace
```

Stops API, Gateway and Caddy, replaces the database with a fresh copy from the backup,
replaces the artifact files, starts everything and waits for `/ready`. `--replace` is required.

**Disaster recovery on a new server:** install with the installer (any domain), copy the backup
and `backup.key` over, then

```sh
sudo lonora restore /path/lonora-….tar.gpg --replace --with-config
```

`--with-config` also restores `.env` (domain, passwords, the encryption key for saved
credentials), the pinned image and the release files from the backup. Without it the current
`.env` is kept.

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

## Moving the existing server onto this

Not done by this change: nothing touched the live VPS. The VPS today runs its own customised
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

`infra/compose/deploy-main.sh` (build from source on the server) still works with the same
Compose file: it now backs up with `lonora backup` (so it needs `backup.key`) and runs
migrations as a separate step, because the production API no longer migrates when it starts.

## Testing

`tests/ops/lifecycle_test.sh REPO` runs the whole lifecycle against real Docker on a disposable
machine (it uses the project name `lonora` and ports 80/443): install, seed an owner and an
artifact, encrypted backup (checked for clear secrets and data), restore test, damaged file and
wrong key refused, update, refusal of an image without a manifest, a deliberately broken update
(a schema-changing migration plus a gateway that never gets ready) rolled back with image and
schema, `restore --replace`, and adoption of an old-image installation. `REPO` must hold the tags
`old`, `v1`, `v2` and `v3-broken` described at the top of the script; any local registry
(`docker run -d -p 127.0.0.1:5000:5000 registry:2`) works.

### What was verified, and what still needs a real host

Verified in a development container with Docker 29.9 and Compose 5.6, real images, a real local
registry (real digests), PostgreSQL 16: all 10 lifecycle checks passed.

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
- Adoption of the actual VPS, whose customised Compose file is not in the repository.
