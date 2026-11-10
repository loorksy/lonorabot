# Running Lonora in production

## ملخص بالعربية

- **التثبيت:** خادم جديد يحتاج Docker وgpg فقط، دون Python أو Node أو نسخة من الكود. الأمر `sudo bash install.sh --domain نطاقك` ينزّل الصورة، يثبّت بصمتها (digest)، ينشئ الأسرار ومفتاح النسخ الاحتياطي بصلاحيات 600 دون طباعتها، ويشغّل Lonora ثم ينتظر حتى تنجح `/ready`.
- **التحديث:** `sudo lonora update <الإصدار>` يثبّت بصمة الصورة الجديدة، ويضع النظام في «وضع التحديث» (كل طلب تعديل يُجاب بـ «يجري التحديث» حتى ينتهي)، ويوقف API وGateway، ويأخذ نسخة احتياطية مشفرة ويتحقق منها، ويشغّل الترحيلات خطوةً مستقلة، ثم API أولًا ثم Gateway، وينتظر `/ready`. إذا فشلت أي خطوة يعود تلقائيًا إلى الإصدار السابق ويستعيد قاعدة البيانات من النسخة التي أُخذت قبل التحديث.
- **ماذا تفعل عند كل نتيجة:**
  - «Rolled back to …»: عاد الإصدار السابق ويعمل. لا تفعل شيئًا.
  - «ROLLBACK HELD»: تغيّرت سجلات التحكم أو التداول (إيقاف التداول، القيود، الصلاحيات، الموافقات، سجل الأوامر) أثناء عمل الإصدار الجديد، فلم تُستعد قاعدة البيانات حتى لا يُلغى قرار لك أو يُمحى أمر أُرسل إلى الوسيط. API وGateway متوقفان. افحص المراكز والأوامر في منصة الوسيط نفسها، ثم اختر: `sudo lonora rollback --force` (استعادة نسخة ما قبل التحديث؛ يضيع ما كُتب بعدها) أو `sudo lonora update <إصدار مُصلَح> --keep-data` (الإبقاء على البيانات والتحديث للأمام).
  - «ROLLBACK INCOMPLETE»: فشلت استعادة قاعدة البيانات. أصلح السبب (المساحة مثلًا؛ `sudo lonora status` و`sudo lonora logs db`) ثم: `sudo lonora rollback` (يعيد المحاولة).
  - «ROLLBACK did not reach /ready»: راجع `sudo lonora logs api` و`sudo lonora logs gateway`، ثم: `sudo lonora rollback` (يشغّل ويفحص من جديد).
  - انقطع التحديث (انقطاع SSH أو إعادة تشغيل): `sudo lonora status` يعرض «UPDATE NOT FINISHED»؛ نفّذ `sudo lonora rollback` أو `sudo lonora update <الإصدار>` (يتراجع أولًا ثم يكمل).
- **النسخ الاحتياطي:** نسخة يومية مشفرة (AES-256 عبر gpg) ومُتحقَّق منها، تشمل قاعدة البيانات والمرفقات وملف الإعدادات والإصدار المثبّت وملفات تحديثات التطبيق. يُحتفظ بآخر 14 نسخة، ولا تُحذف أبدًا نسخة يحتاجها تحديث معلّق أو استعادة جارية. مجلد `backups/` لا يحوي إلا ملفات مشفرة، فيمكن نسخه إلى أي مكان.
- **المفتاح:** الملف `/opt/lonora/backup.key` (صلاحية 600، لا يُطبع ولا يُسجَّل أبدًا). **إذا ضاع هذا المفتاح تصبح كل النسخ الاحتياطية غير قابلة للقراءة نهائيًا، ولا توجد أي طريقة لاسترجاعها.** احفظ نسخة منه خارج الخادم، مثلًا في مدير كلمات المرور، وفي مكان منفصل عن النسخ الاحتياطية نفسها.
- **اختبار الاستعادة:** `sudo lonora restore-test` يستعيد أحدث نسخة في بيئة مؤقتة. تنبيه صريح: قاعدة البيانات المستعادة تحتوي مفاتيح المزودين والوسيط المحفوظة فيها، ومفتاح فكّ تشفيرها يُمرَّر إلى البيئة المؤقتة حتى يعمل التطبيق. ما يمنعها من الاتصال بأي مزود أو وسيط هو الشبكة الداخلية بلا أي مخرج، ويتحقق الأمر من ذلك قبل تشغيل Gateway ويتوقف إن وجد مخرجًا. ثم يحذف كل شيء. شغّله مرة شهريًا على الأقل.
- **الاستعادة الفعلية:** `sudo lonora restore /opt/lonora/backups/<ملف> --replace` تأخذ نسخة احتياطية من الوضع الحالي أولًا، ثم تستبدل البيانات وتشغّل الترحيلات. إذا توقفت في منتصفها: أعد الأمر نفسه.
- **بعد كارثة (خادم جديد):** ثبّت خادمًا جديدًا بالمثبّت، ثم `sudo install -m 600 <مفتاحك> /opt/lonora/backup.key`، ثم `sudo lonora restore <ملف> --replace --with-config`. هذا يعيد الأسرار والنطاق، ويحتفظ بكلمة مرور قاعدة البيانات الجديدة وبملفات النشر من الصورة.
- **الخادم الحالي (VPS):** لم يُلمس. المسار المعتمد بداية جديدة بقاعدة بيانات فارغة: تُحفظ نسخة كاملة من التثبيت القديم وتُنحّى جانبًا، ثم يُثبَّت النظام الجديد. الخطوات في قسم «Your current server: start fresh» أدناه.

## The pieces

| Piece | Where | What it does |
|---|---|---|
| Deployment definition | `infra/compose/docker-compose.prod.yml` | The one production stack: PostgreSQL, API, Gateway, Caddy (HTTPS), plus a `migrate` service that runs only when asked. |
| Optional overlays | `infra/research/compose.research.yml`, `infra/analysis/compose.workspace.yml` | Listed in `LONORA_COMPOSE_OVERLAYS` in `.env` (space separated). `lonora` always adds them. |
| `lonora` command | `infra/compose/lonora` (linked as `/usr/local/bin/lonora`) | status, start, update, rollback, backup, restore, restore-test, logs. |
| Installer | `infra/compose/install.sh` | Sets up a new server. |
| Release manifest | `/app/release.json` inside every server image | Version, commit, migration head, minimum client version. |

All of these files ship **inside the server image** under `/app/deploy`. The installer and
`lonora update` copy them from the image to the server, so the server never needs a source
checkout, Git, Python or Node, and the files on the server always match the image that runs.
There is no other way to deploy: no build-from-source script on the server, no host-PostgreSQL
variant.

Layout on a server (default `/opt/lonora`):

```
/opt/lonora/.env              configuration and secrets (mode 600)
/opt/lonora/backup.key        backup encryption key (mode 600) — copy it off the server
/opt/lonora/state/            mode 700: the pinned image (image.env), history.log, the lock,
                              the update marker, and scratch space (.work) for clear dumps
/opt/lonora/backups/          encrypted backups only, lonora-YYYYMMDDTHHMMSSZ.tar.gpg
/opt/lonora/maintenance/on    exists while an update, rollback or restore runs
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
2. copies the deployment files out of the image, with explicit modes;
3. creates `.env` with a fresh database password, encryption key, bootstrap token and
   webhook secret, and `backup.key` — all mode 600, never printed;
4. enables the daily backup timer (`lonora-backup.timer`, 03:00);
5. runs `lonora start`: database, migrations, services, and waits for `/ready`.

It is for new installations only. It refuses a directory that already has one (there,
`sudo lonora update <version>` updates it, or starts it again behind the health gates when the
version is the one already pinned), and it refuses when a Docker volume `lonora_database` already
exists, because the new install would silently reuse that old data.

Then:

- copy `/opt/lonora/backup.key` somewhere safe that is not this server (a password manager is fine);
- open `https://your-domain` and create the owner account with the bootstrap token from
  `sudo grep LONORA_BOOTSTRAP_TOKEN /opt/lonora/.env`;
- for host hardening (firewall, unattended security updates) run `sudo bash /opt/lonora/infra/compose/harden-host.sh --apply`.

## Update

```sh
sudo lonora update v0.3.0     # or: main, or ghcr.io/loorksy/lonorabot@sha256:…
```

Everything is checked before anything changes: the tag resolves to an exact digest, the pinned
image must itself be a `repo@sha256` digest (otherwise a rollback could not return to exactly it),
the new image must carry a release manifest, and the database's migration must be known to the
new image (no downgrades: restore a backup made on that version instead). Then, in order:

1. **Maintenance on.** `maintenance/on` is created. While it exists, Caddy answers every write
   (anything but GET, HEAD and OPTIONS) with `503` and «يجري التحديث، حاول بعد دقائق», so the owner
   cannot change trading controls, restrictions or authorities while the update decides what the
   database will be. Reads keep working when the API is up.
2. An in-progress marker (`state/update-in-progress`) is written; API and Gateway are stopped.
3. An encrypted backup is taken **and verified** (decrypted, authenticated, every checksum and the
   whole dump read back). If that fails, nothing changes: marker and maintenance are removed and
   the old version starts again.
4. The new deployment files are copied in (each renamed into place) and the new digest is pinned.
5. Migrations run as their own step (`migrate` service). Right after, a fingerprint of the
   owner-control and money records is taken (see below).
6. The API starts first, **with the Gateway still stopped**, and must pass `/health`. Only then does
   the Gateway (agent and trading loops) start, and the update waits for `/ready` (default 240 s,
   `LONORA_READY_TIMEOUT`).
7. Success: marker and maintenance removed, `state/history.log` updated.

**If step 4, 5, 6 or a health gate fails**, `lonora` rolls back by itself: the old deployment files
and pin come back and the database is **restored from the backup of step 3** — dropped and recreated
from that dump, not migrated down. An Alembic downgrade after the new version has written rows can
lose or corrupt data; restoring the pre-update backup cannot. Because API and Gateway were stopped
before that backup, nothing the owner did before the update is lost, and nothing the failed version
wrote (including a half-applied migration) survives.

**The exception: a held rollback.** Once the new API or Gateway has run, restoring the backup could
undo something that must not be undone: an owner's "stop trading", a new restriction, a revoked
authority, or the record of an order already at the broker. So before restoring, `lonora` compares
the fingerprint of these records with the one from step 5: whole rows of `ln_trading_restrictions`,
`ln_account_authorities`, `ln_supervision_grants`, `ln_owner_actions`, `ln_trade_approvals`,
`ln_trading_journal`, and the trading switch and emergency stop in `ln_settings`. If any of them
changed, or cannot be read, it does **not** restore. It stops API and Gateway, keeps maintenance on
and the failed version pinned, prints `ROLLBACK HELD` with the reason, and exits with status 2.

### When an update does not finish: what to do

| You see | It means | Do |
|---|---|---|
| `Rolled back to …; /ready passes` | The previous version runs again. | Nothing. Report the failed version. |
| `ROLLBACK HELD: …` (exit 2) | Owner controls or trading records changed while the new version ran. API and Gateway are stopped. | Check positions and orders in the broker's own terminal since the time shown. Then either `sudo lonora rollback --force` (restore the pre-update backup; what was written since is lost, so note it first) or `sudo lonora update <fixed version> --keep-data` (keep the current data and update forward). |
| `--keep-data` fails again | The forward update did not pass its gates. | It returns to the held state (data kept, services stopped); same two choices. Passing the version that is already pinned starts it again behind the gates. |
| `ROLLBACK INCOMPLETE: restoring the database … failed` | The database was dropped but the restore failed (for example a full disk). | Fix the cause (`sudo lonora status`, `sudo lonora logs db`, `df -h`), then `sudo lonora rollback` — it retries the restore from the same backup. |
| `ROLLBACK did not reach /ready` | The previous version and data are back but do not start. | `sudo lonora logs api`, `sudo lonora logs gateway`; when fixed, `sudo lonora rollback` starts and checks again. |
| `UPDATE NOT FINISHED` in `lonora status` | The update was interrupted (SSH dropped, reboot). `start` and `restore` refuse to run. | `sudo lonora rollback`, or `sudo lonora update <version>`, which rolls the unfinished one back first (same rules, including the hold) and then updates. |

Only one of update, restore, restore-test, rollback, start and backup runs at a time (a lock in
`state/`); the daily backup waits for a running update. Whoever takes the lock first removes
scratch files a killed run left behind. `state/history.log` records every update and rollback with
the backup that was taken. Expect a short outage (stop → backup → migrate → start), usually under a
minute plus backup time.

## Backups

```sh
sudo lonora backup
```

One file per backup, `backups/lonora-<time>.tar.gpg`, mode 600: a single gpg file (AES-256, key
stretched with SHA-512) containing

- `database.dump` — the full PostgreSQL database (`pg_dump -Fc`);
- `artifacts.tar.gz` — all files agents and charts produced;
- `config.tar.gz` — `.env` (which holds the key that decrypts saved provider and broker
  credentials), the pinned image (for information) and the mobile APK/OTA releases. Deployment
  files are not in backups: they always come from the image;
- `manifest.json` — time, image and migration revision; `SHA256SUMS` for every member.

Every backup is verified before it is kept: decrypted, authenticated, every checksum checked and
the whole dump read with `pg_restore`. A backup that fails any step is deleted. The clear dump and
decrypted copies exist only in `state/.work` (mode 700, never in `backups/`) and are removed on
every exit path; gpg's home (it holds only its agent socket) is a short-lived directory in `/tmp`.
So `backups/` only ever holds encrypted files, and can be copied anywhere.

**If the key is lost, every backup is unreadable for good** — there is no recovery, by design.
Keep a copy off the server (a password manager is fine), separate from where backups are stored.
The key comes from `LONORA_BACKUP_KEY` in the environment if set, otherwise from `backup.key` (or
`LONORA_BACKUP_KEY_FILE`). It is handed to gpg on a file descriptor; it never appears in a command
line, a log or the output.

The newest 14 backups are kept (`LONORA_BACKUP_KEEP`), except that rotation never deletes the backup
an unfinished or held update would roll back to, nor the backup being restored. Not included:
Caddy's TLS certificates (re-issued automatically). Copy `backups/` off the server regularly, and
keep `backup.key` in a different place.

### Prove a backup restores

```sh
sudo lonora restore-test                                   # newest backup
sudo lonora restore-test /opt/lonora/backups/lonora-….tar.gpg
```

This decrypts and authenticates the backup, checks every checksum and refuses anything unexpected
inside, then builds a **separate, throwaway** stack: a fresh PostgreSQL, the backup restored into
it, the migrations run, the API and then the Gateway started on it. It passes only if `/ready`
passes. Afterwards every container, volume and the network are deleted.

Be clear about what is inside: the restored database still holds the provider and broker
credentials saved in it, and the encryption key that opens them is passed in so the app can start
(the bootstrap token too; no other `.env` value). What stops the test stack from reaching any model
provider or broker is the network: an internal Docker network with no route out. `lonora` checks
that before starting the Gateway — the network must be internal and a connection out must fail —
and stops if either check fails.

A wrong key, a damaged file or a forged one fails with "Decryption failed": only a file gpg really
decrypts and authenticates with this key is accepted; a plain, unencrypted OpenPGP file is refused.
Run it monthly, and after any change to how you back up.

### Restore

```sh
sudo lonora restore /opt/lonora/backups/lonora-….tar.gpg --replace
```

A relative path is read from the current directory, or else from `/opt/lonora`. Restore refuses a
backup whose migration is newer than the installed image knows (update to that image first). It
starts the database if it is stopped, **takes a safety backup of the current state first**, turns
maintenance on, stops API and Gateway, replaces the database with a fresh copy from the backup,
replaces the artifact files, runs the migrations (so an older backup is brought up to the installed
version), starts everything and waits for `/ready`. `--replace` is required. If it stops part-way,
it prints the same command to run again; a rerun with no current database skips the safety backup
and says so.

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
 "built_at": "2026-11-10T00:00:00Z", "migration_head": "0053_remove_shadow_trading",
 "min_client_version": "0.2.8"}
```

It is generated at image build time by `scripts/release_manifest.py`, which reads the single
Alembic head from the migration files (a build with two heads fails) and the minimum client
version from `infra/release/compatibility.json`. **Raise `min_client_version` there** in the
same change that makes the server stop working with older mobile/web clients. The CI publish
workflow stamps the tag or branch, the commit and the build time. `lonora status` prints the
manifest of the running image.

## Your current server: start fresh

The owner decided the new system starts from an empty database: no agents or data are carried
over, and there is no in-place adoption of the old installation. Nothing in this change touched the
live VPS. Do this at a quiet time, as root, on the server. The new stack uses the same Compose
project name (`lonora`) and volume names as the old one, so the old volumes must be archived and
then removed — otherwise the new install would reuse them (the installer refuses in that case).

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
   `backup.key` off the server. The installer replaces the old backup timer.
6. Optional: to keep the existing Android download and OTA updates working, copy them over
   before clients update: `cp -a /opt/lonora-old/.runtime/releases/. /opt/lonora/.runtime/releases/`
7. Check: `sudo lonora status` shows `/ready: ok`; open the site and create the owner account;
   then `sudo lonora backup` and `sudo lonora restore-test`.

Once the new system has run well for a while, `/opt/lonora-old` and `/opt/lonora-old-archive`
can be deleted. Until then they are the only way back to the old system.

## Testing

`tests/ops/lifecycle_test.sh REPO` runs the whole lifecycle against real Docker on a disposable
machine. It uses the project name `lonora`, its volume names and ports 80/443, so it refuses to run
where a Lonora installation exists. It checks:

1. install: digest pinned, secrets mode 600, bundle modes, refusal of its own home and of a
   leftover `lonora_database` volume next to a new home;
2. no secret and no legacy deployment path in the image's bundle or `release.json`;
3. seed an owner account and an artifact;
4. backup: not a readable tar; the decrypted copy holds the dump and `.env`, the file neither;
5. restore test: network internal with no route out (checked by `lonora`), nothing left behind;
6. damaged file, wrong key and a forged plaintext backup refused, nothing changed;
7. a failing and a truncating `pg_dump`: the update aborts before pinning, the live database untouched;
8. refusals: a concurrent operation, no pin, a tag (not digest) pin, an image without a manifest;
9. update: API gated before the Gateway, script replaced atomically, writes open again after;
10. a broken update: writes answered `503 «يجري التحديث»` during it, rolled back from the pre-update
    backup, earlier rows kept;
11. the same with `pg_restore` failing after `DROP DATABASE`: the rollback stops at phase
    `restoring` with a working command, and `lonora rollback` retries and completes;
12. an update killed mid-way: marker kept, `start` refused, the next update rolls back and completes;
13. restore from another directory with the database stopped, of the oldest backup while rotation
    would delete it: safety backup, file kept, older schema migrated up;
14. a restriction written during the gate: held; `--keep-data` with the same digest stays held, a
    bad tag changes nothing, a fixed version updates forward keeping the restriction;
15. a trading-journal row written during the gate: held; backups during the hold keep its backup;
    `rollback` still holds; `rollback --force` restores;
16. disaster recovery: a newer backup refused on an older image; `--with-config` restores the
    secrets and keeps the new database password;
17. no secret (encryption key, backup key, database passwords, bootstrap token, webhook secret) in
    any log the test wrote or in `state/history.log`.

`REPO` must hold the tags `old`, `v1`, `v2`, `v4-good`, `v3-broken` and `v3-fixed`. Build them with
`tests/ops/build_test_images.sh REPO`, into any registry you control:

```sh
docker run -d --name registry -p 127.0.0.1:5000:5000 registry:2
bash tests/ops/build_test_images.sh localhost:5000/lonora
bash tests/ops/lifecycle_test.sh localhost:5000/lonora
```

It builds `old` from main at `80e195f` (the last commit before this tooling, override with
`OLD_SHA`), `v1` and `v2` from the checkout with different `LONORA_VERSION`, and three probe images
on top of `v2` from `tests/ops/fixtures`: `v4-good` (+ `9998_good_probe`), `v3-broken` (+ 9998 and
`9999_broken_probe`, with a Gateway that never starts) and `v3-fixed` (the same migrations, working).
The probes chain onto `v2`'s migration head at build time and exist only inside those test images.
It pushes all six and prints their digests (also written to `.runtime/ops-test-images.txt`). Where
the Debian mirror is unreachable, `LONORA_TEST_SKIP_APT=1` drops the Chromium/fonts line;
`LONORA_BUILD_CA_FILE` and `LONORA_BUILD_NETWORK=host` help behind a TLS-intercepting proxy on
`127.0.0.1`. The runs reported here used all three.

### What was verified, and what still needs a real host

Verified in a development container with Docker 29.9 and Compose 5.6, real images, a real local
registry (real digests), PostgreSQL 16 and Caddy 2.10: all 17 lifecycle checks passed. The
fresh-start steps 2, 4 and 5 were also run here against volumes named like the old ones: both
archives were complete, and the new install came up with `/ready` passing and an empty database.

Still to be checked on a real server:

- The test images were built from the real `Dockerfile` with only the Chromium and font `apt-get`
  line removed (the development container cannot reach the Debian package mirror). That line stays
  in the production `Dockerfile` unchanged: Chromium drives the server chart renderer (TradingView
  image capture, `LONORA_CHART_BROWSER_EXECUTABLE=/usr/bin/chromium`) and the fonts render chart text.
  `/ready` does not depend on them; chart capture was not exercised here.
- Caddy obtaining a real certificate for a public domain (the test used `localhost`).
- The systemd backup timer (installed with `--no-systemd` in the test).
- Pulling from `ghcr.io` (the test used a local registry), and the CI publish workflow, which
  cannot run while GitHub Actions is unavailable.
- The fresh-start procedure on the actual VPS (its customised Compose file is not in the repository).
