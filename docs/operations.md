Superseded by VISION.md

# Running Lonora in production

## ملخص بالعربية

- **التثبيت:** خادم جديد يحتاج Docker وgpg فقط، دون Python أو Node أو نسخة من الكود. الأمر `sudo bash install.sh --domain نطاقك` ينزّل الصورة، يثبّت بصمتها (digest)، ينشئ الأسرار ومفتاح النسخ الاحتياطي بصلاحيات 600 دون طباعتها، ويشغّل Lonora ثم ينتظر حتى تنجح `/ready`.
- **التحديث:** `sudo lonora update <الإصدار>` يثبّت بصمة الصورة الجديدة، ويضع النظام في «وضع التحديث» (ما دام API وGateway متوقفين يُجاب كل طلب تعديل بـ «يجري التحديث»؛ وما إن يعمل Gateway حتى تُفتح الطلبات من جديد، فيبقى الإيقاف المؤقت للوكلاء وإغلاق المراكز ورفض الموافقات وسحب الصلاحيات متاحًا لك دائمًا)، ويوقف API وGateway، ويأخذ نسخة احتياطية مشفرة ويتحقق منها، ويشغّل الترحيلات خطوةً مستقلة، ثم API أولًا ثم Gateway، وينتظر `/ready`. إذا فشلت أي خطوة يعود تلقائيًا إلى الإصدار السابق ويستعيد قاعدة البيانات من النسخة التي أُخذت قبل التحديث.
- **ماذا تفعل عند كل نتيجة:**
  - «Rolled back to …»: عاد الإصدار السابق ويعمل. لا تفعل شيئًا.
  - «ROLLBACK HELD»: تغيّرت سجلات التحكم أو التداول (إيقاف الوكلاء مؤقتًا، الصلاحيات، الموافقات، سجل الأوامر) أثناء عمل الإصدار الجديد، فلم تُستعد قاعدة البيانات حتى لا يُلغى قرار لك أو يُمحى أمر أُرسل إلى الوسيط. API وGateway متوقفان. افحص المراكز والأوامر في منصة الوسيط نفسها، ثم اختر: `sudo lonora rollback --force` (استعادة نسخة ما قبل التحديث؛ يضيع ما كُتب بعدها) أو `sudo lonora update <إصدار مُصلَح> --keep-data` (الإبقاء على البيانات والتحديث للأمام).
  - «ROLLBACK HELD» مع «cannot be read»: تعذّرت قراءة سجلات التحكم. أصلح قاعدة البيانات (`sudo lonora logs db`) ثم: `sudo lonora rollback`.
  - «ROLLBACK INCOMPLETE»: فشلت استعادة قاعدة البيانات. أصلح السبب (المساحة مثلًا؛ `sudo lonora status` و`sudo lonora logs db`) ثم: `sudo lonora rollback` (يعيد المحاولة).
  - «ROLLBACK did not reach /ready»: راجع `sudo lonora logs api` و`sudo lonora logs gateway`، ثم: `sudo lonora rollback` (يشغّل ويفحص من جديد).
  - انقطع التحديث (انقطاع SSH أو إعادة تشغيل): `sudo lonora status` يعرض «UPDATE NOT FINISHED»؛ نفّذ `sudo lonora rollback` أو `sudo lonora update <الإصدار>` (يتراجع أولًا ثم يكمل).
  - «Maintenance: on» في `sudo lonora status` وطلبات التعديل مرفوضة: `sudo lonora maintenance off` يفتحها دون انتظار `/ready`.
  - توقف التثبيت قبل أول ترحيل: `sudo lonora start`.
- **النسخ الاحتياطي:** نسخة يومية مشفرة (AES-256 عبر gpg) ومُتحقَّق منها، تشمل قاعدة البيانات والمرفقات وملف الإعدادات والإصدار المثبّت وملفات تحديثات التطبيق. يُحتفظ بآخر 14 نسخة، ولا تُحذف أبدًا نسخة يحتاجها تحديث معلّق أو استعادة جارية. مجلد `backups/` لا يحوي إلا ملفات مشفرة، فيمكن نسخه إلى أي مكان.
- **المفتاح:** الملف `/opt/lonora/backup.key` (صلاحية 600، لا يُطبع ولا يُسجَّل أبدًا). **إذا ضاع هذا المفتاح تصبح كل النسخ الاحتياطية غير قابلة للقراءة نهائيًا، ولا توجد أي طريقة لاسترجاعها.** احفظ نسخة منه خارج الخادم، مثلًا في مدير كلمات المرور، وفي مكان منفصل عن النسخ الاحتياطية نفسها.
- **اختبار الاستعادة:** `sudo lonora restore-test` يستعيد أحدث نسخة في بيئة مؤقتة. تنبيه صريح: قاعدة البيانات المستعادة تحتوي مفاتيح المزودين والوسيط المحفوظة فيها، ومفتاح فكّ تشفيرها يُمرَّر إلى البيئة المؤقتة حتى يعمل التطبيق. ما يمنعها من الاتصال بأي مزود أو وسيط هو الشبكة الداخلية بلا أي مخرج، ويتحقق الأمر من ذلك قبل تشغيل Gateway ويتوقف إن وجد مخرجًا. ثم يحذف كل شيء. شغّله مرة شهريًا على الأقل.
- **الاستعادة الفعلية:** `sudo lonora restore /opt/lonora/backups/<ملف> --replace` توقف API وGateway وتأخذ نسخة احتياطية من الوضع الحالي أولًا، ثم تستبدل البيانات وتشغّل الترحيلات. إذا توقفت في منتصفها: نفّذ الأمر الذي تطبعه (هو الأمر نفسه)، فيُكمل دون نسخة احتياطية ثانية؛ والتحديث والتشغيل مرفوضان حتى تكتمل.
- **بعد كارثة (خادم جديد):** ثبّت خادمًا جديدًا بالمثبّت، ثم `sudo install -m 600 <مفتاحك> /opt/lonora/backup.key`، ثم `sudo lonora restore <ملف> --replace --with-config`. هذا يعيد الأسرار والنطاق، ويحتفظ بكلمة مرور قاعدة البيانات الجديدة وبملفات النشر من الصورة.
- **الخادم الحالي (VPS) — تثبيت جنبًا إلى جنب:** على خادمك يعمل traefik على المنفذين 80 و443 ومعه مشاريع أخرى وLonora القديم. التثبيت الجديد لا يلمس أيًّا منها: يُثبَّت باسم مشروع مستقل ومجلد مستقل، ويستمع على عنوان داخلي واحد فقط، مثلًا:
  `sudo bash install.sh --home /opt/lonora2 --project lonora2 --behind-proxy 127.0.0.1:18030 --domain <اسم تجريبي> --version <الإصدار>`
  يفحص المثبّت قبل أي تغيير: أن المنفذ غير مستخدم، وأن المجلد فارغ من أي تثبيت، وأن اسم المشروع غير مستخدم، وأن الذاكرة والمساحة كافيتان، ويطبع ما وجده ويرفض إن فشل أي فحص. لكل خدمة حدّ للذاكرة والمعالج (نحو 2.3 غيغابايت لـ Lonora، ومساحة العمل حدودها الخاصة)، وخدمات البحث والمتصفح معطلة افتراضيًا.
- **إعادة استخدام الأسرار الحالية:** الخيار `--env-from /opt/lonora/.env` ينسخ من ملف الإعدادات القديم المفاتيح التي يعرفها الإصدار الجديد فقط (مفتاح التشفير الذي تُفك به مفاتيح المزودين والوسيط المحفوظة، وسر الـ webhook، وبصمات passkey لتطبيق أندرويد، والنطاق، وإعدادات الضبط)، ويطبع أسماءها فقط دون أي قيمة، ويُنشئ كلمة مرور جديدة لقاعدة البيانات الجديدة، ويتجاهل الباقي (LiveKit وIMAGE وARTIFACT_ROOT وغيرها) ويذكر أسماءها.
- **مضيف مساحة التحليل:** الخدمة `lonora-analysis.service` على الخادم تبقى كما هي؛ يربطها التثبيت الجديد بالخيار `--overlay infra/analysis/compose.workspace.yml`. إن لم تكن الخدمة تعمل يبدأ Lonora رغم ذلك، وتبقى أدوات التحليل غير متاحة حتى تعمل الخدمة.
- **النطاق:** عند التثبيت مباشرة على الاسم الأساسي استخدم `--domain lonora.lork.cloud`. إن ثبّتّ على اسم تجريبي ثم أردت التحويل: غيّر `LONORA_DOMAIN=lonora.lork.cloud` في `/opt/lonora2/.env` ثم نفّذ `sudo lonora start` قبل تعديل traefik.
- **استعادة غير مكتملة:** `sudo lonora status` يعرض «RESTORE NOT FINISHED». الخيارات: أكملها بالأمر المطبوع، أو ارجع إلى ما قبلها بـ `sudo lonora restore <نسختها الاحتياطية> --replace`، أو `sudo lonora restore --abandon`.
- **التحويل لاحقًا (قرارك أنت ومتى تشاء):** أولًا تجرّب النسخة الجديدة على اسم تجريبي (مثل `next.lonora.lork.cloud`) عبر ملف traefik جديد `lonora-next.yml`. عند التحويل تغيّر سطرًا واحدًا فقط في `lonora.yml` (العنوان `http://127.0.0.1:18010` يصبح `http://127.0.0.1:18030`)، ثم توقف النسخة القديمة دون حذف شيء. تنبيه: ملف معطوب في مجلد traefik قد يعطّل كل المواقع على الخادم، لذا اكتب الملف باسم مؤقت وتحقق منه ثم انقله إلى مكانه. المثبّت لا يكتب في مجلد traefik أبدًا. الخطوات في قسمي «Side by side» و«Switch over later» أدناه.
- **مساحة العمل (الطرفية):** تثبّت هذه النسخة مساحة عمل Linux واحدة دائمة للمالك (الخدمتان `workspace` و`workspace-net`) سيتشاركها كل وكلائه، لكل وكيل مستخدم Unix ومجلد منزلي خاص به، و`/workspace/shared` مشترك بين الجميع. يستخدمها الوكلاء عبر أدوات مساحة العمل (تشغيل أمر، قراءة ملف وكتابته، عرض العمليات وإيقافها)، وكل ما يعود منها يُفحص فتُستبدل قيم الأسرار بـ `[secret:NAME]`. ولأن سجلًا أو عملية قديمة قد تحمل قيمة سرّ أُعطي لأمر، تحتفظ البوابة بكل قيمة أُعطيت مشفّرةً بمفتاح الأسرار 30 يومًا بعد آخر مرة أُعطيت فيها، لتبقى مستبدلة في الفحص؛ فالسرّ المحذوف أو المُبدَّل تبقى قيمته مشفّرة حتى 30 يومًا ثم تُمحى. تصل إلى الإنترنت ولا تصل إلى قاعدة البيانات ولا API ولا Caddy ولا الشبكات الخاصة ولا عناوين الخادم نفسه؛ وكل اتصال TCP منها يمر بمرحّل يقبل من العميل TLS أو HTTP أو SSH فقط، ويرفض أسماء MetaApi ونطاق Lonora، ويرفض العنوان المكتوب بدل الاسم، ويشترط أن يكون العنوان المطلوب من عناوين الاسم المعلن. هذا حماية إضافية لا جدار: اسم يشير إلى عنوان MetaApi لم يتعلّمه الحارس، أو وسيط HTTPS، أو أي شيء عبر SSH يبلغ MetaApi، والإنترنت وSSH مطلوبان. والضمان الذي لا يُتجاوز هو أن مفتاح MetaApi لا يدخل مساحة العمل أبدًا. الملفات والحزم المثبّتة للمستخدم تبقى بعد إعادة التشغيل والتحديث، والعمليات الجارية لا تبقى. يبدأها `lonora` بعد خدمات Lonora ولا ينتظرها: إن لم تبدأ أو تعذّر تجهيز قرصها يُبلَّغ بذلك ويعمل Lonora بدونها. حدودها الافتراضية: معالجان، 4 غيغابايت ذاكرة، قرص 20 غيغابايت، 256 عملية، و10 دقائق للأمر الأمامي؛ تُغيَّر في `.env`. وزن معالجها منخفض وهي أول ما يُقتل عند نفاد ذاكرة الخادم، وقاعدة البيانات وAPI والبوابة تحجز ذاكرتها، فتتنازل مساحة العمل أولًا عند الضغط. على خادمك الحالي (معالجان، 7.9 غيغابايت منها نحو 5.2 متاحة، 25 غيغابايت حرة): `LONORA_WORKSPACE_MEMORY=2g` و`LONORA_WORKSPACE_CPUS=1.0` و`LONORA_WORKSPACE_DISK=10g` (انظر «The workspace» أدناه). أول تحديث إلى إصدار فيه مساحة العمل يُشغَّل بأمر `lonora` الجديد من الصورة نفسها (الأمر في القسم نفسه).
- **الإشعارات على الهاتف:** تصل إشعارة واحدة عند إنشاء بطاقة موافقة على صفقة، أو بطاقة «عملية غير محسومة»، أو بطاقة سرّ ينتظرها وكيل، وإشعارة واحدة لكل انقطاع في حساب الوسيط (رمز مرفوض، حساب غير مُشغَّل، أو اتصال مقطوع لأكثر من دقيقتين)، بنص ثابت وباسم الوكيل، دون سعر أو حجم أو رقم حساب، ولا زر فيها؛ لمسها يفتح المحادثة عند البطاقة. تمرّ عبر خدمة Expo بمشروع Expo يملكه المالك. يحتاج إصدار أندرويد إلى معرّف المشروع `LONORA_EXPO_PROJECT_ID` وملف Firebase للمشروع نفسه `LONORA_ANDROID_GOOGLE_SERVICES_FILE` عند البناء، وهي وحدة أصلية فلا تصل عبر تحديث OTA بل تحتاج APK جديدًا. التفاصيل في قسم «Push to the owner's phone».
- **البناء على الخادم:** ما دام GitHub Actions متوقفًا، يبني الأمر `infra/compose/build-from-source.sh` الصورة على الخادم بحدود معالج وذاكرة، ويضعها في سجل محلي على `127.0.0.1` فقط، ثم يتم التثبيت أو التحديث منها كالمعتاد.

## The pieces

| Piece | Where | What it does |
|---|---|---|
| Deployment definition | `infra/compose/docker-compose.prod.yml` | The one production stack: PostgreSQL, API, Gateway, Caddy (HTTPS), SearXNG web search and the research browser, plus a `migrate` service that runs only when asked. |
| Mode | `infra/compose/mode-direct.yml` or `mode-proxy.yml` | Direct: Caddy owns 80/443 and gets the certificate. Proxy (`LONORA_PROXY_LISTEN` set): Caddy listens in plain HTTP on one loopback address behind an existing reverse proxy; nothing binds 80/443. |
| Optional overlays | `infra/analysis/compose.workspace.yml` | Listed in `LONORA_COMPOSE_OVERLAYS` in `.env` (space separated). `lonora` always adds them. |
| Source build | `infra/compose/build-from-source.sh` | Builds the image on the server into a loopback-only registry, when no published image exists. |
| `lonora` command | `infra/compose/lonora` (linked as `/usr/local/bin/lonora`) | status, start, update, rollback, backup, restore, restore-test, logs. |
| Installer | `infra/compose/install.sh` | Sets up a new server. |
| Release manifest | `/app/release.json` inside every server image | Version, commit, migration head, minimum client version. |

The Compose project name (`LONORA_PROJECT` in `.env`, `--project` at install, default `lonora`)
prefixes every container, volume and network, so one installation never touches another's.
Every service has a memory and CPU limit (below).

All of these files ship **inside the server image** under `/app/deploy`. The installer and
`lonora update` copy them from the image to the server, so the server never needs a source
checkout, Git, Python or Node, and the files on the server always match the image that runs.
Images come from a registry, or are built on the server with `build-from-source.sh` into a
loopback-only registry («Build from source on the server»); either way install and update pin a
digest. There is no host-PostgreSQL variant.

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
/opt/lonora/workspace.img     the workspace disk: a fixed-size ext4 file (LONORA_WORKSPACE_DISK)
/opt/lonora/workspace-disk/   where it is mounted; the workspace container sees it as /workspace
```

## Install a new server

Requirements: Linux with Docker Engine and the Compose plugin, ports 80 and 443 open, and a
domain name pointing at the server. `gpg` is installed automatically on Debian/Ubuntu if missing.

```sh
docker run --rm --entrypoint cat ghcr.io/loorksy/lonorabot:main \
  /app/deploy/infra/compose/install.sh >install.sh
sudo bash install.sh --domain lonora.example.com --version main
```

`--version` takes a tag (`main`, `v0.3.0`), an exact `repo@sha256:…` reference, or an image built on
the server (`127.0.0.1:5055/lonora:v0.3.0`, see «Build from source on the server»). Other options:
`--home DIR` (default `/opt/lonora`), `--project NAME` (default `lonora`), `--behind-proxy
127.0.0.1:PORT` (see «Side by side»), `--env-from FILE`, `--overlay FILE` (repeatable),
`--workspace-memory` (default 4g), `--workspace-cpus` (default 2), `--workspace-disk` (default 20g),
`--min-free-ram-mb` (default 3584 plus the workspace memory: 7680), `--min-free-disk-gb` (default 10
plus the workspace disk plus 2: 32), `--no-systemd`. The preflight also needs 2 CPUs, no fewer than
the workspace's, and the tools of the workspace disk (util-linux, e2fsprogs).

`--env-from /opt/lonora/.env` reuses settings and secrets from an earlier installation. It copies
only keys this version knows — `LONORA_ENCRYPTION_KEY` (provider and broker keys saved in a database
are encrypted with it), `LONORA_BOOTSTRAP_TOKEN`, `LONORA_WEBHOOK_SECRET`,
`LONORA_PASSKEY_ANDROID_FINGERPRINTS` / `_PACKAGE` / `LONORA_PASSKEY_IOS_APP_IDS` (tied to the app's
signing keys), `LONORA_DOMAIN` (unless `--domain` is given), the tuning keys
(`LONORA_MAXIMUM_SUBAGENTS`, `LONORA_MAXIMUM_TOOL_ROUNDS`, `LONORA_RUN_LEASE_SECONDS`,
`LONORA_WORKER_POLL_SECONDS`, `LONORA_SESSION_SECONDS`, `LONORA_LOG_LEVEL`), the MCP declarations and
provider API keys. The database password is always new (a fresh database). Everything else —
`LONORA_POSTGRES_PASSWORD`, `LONORA_IMAGE`, `LONORA_ARTIFACT_ROOT`, `LONORA_LIVEKIT_*` and any other
key — is not copied. It prints the copied and the ignored key **names**, never a value, and the new
`.env` is mode 600.

`--overlay` adds a bundled overlay at install time (`infra/analysis/compose.workspace.yml`); the preflight warns (does not refuse) when the workspace
host socket is missing.

The preflight also reads the whole `--env-from` file before anything is written: `export ` prefixes
and leading spaces are accepted; a Windows line ending (CRLF), a control character or a line that is
not `NAME=VALUE` fails it, naming the line or key (never the value). `--behind-proxy` must be
`127.x.y.z:PORT` with valid octets and a port from 1 to 65535.

First a **preflight**, which changes nothing and prints each finding as `ok` or `FAIL`: the home
directory holds no installation; no `<project>_database` volume and no container of the project
exist; the ports are free (80 and 443, or the `--behind-proxy` port, which must be on a 127.x
address); available memory and free disk are above the minimums. Any `FAIL` stops it with
"Preflight failed; nothing was changed". Then the installer:

1. pulls the image and pins its digest in `state/image.env`;
2. copies the deployment files out of the image, with explicit modes;
3. creates `.env` with a fresh database password, encryption key, bootstrap token and
   webhook secret, and `backup.key` — all mode 600, never printed;
4. enables the daily backup timer (`<project>-backup.timer`, 03:00);
5. runs `lonora start`: database, migrations, services, and waits for `/ready`.

It is for new installations only: on an existing one, `sudo lonora update <version>` updates it, or
starts it again behind the health gates when the version is the one already pinned. The command is
linked as `/usr/local/bin/lonora`, or `/usr/local/bin/lonora-<project>` when that name already
belongs to another installation.

Then:

- copy `/opt/lonora/backup.key` somewhere safe that is not this server (a password manager is fine);
- open `https://your-domain` and create the owner account with the bootstrap token from
  `sudo grep LONORA_BOOTSTRAP_TOKEN /opt/lonora/.env`;
- for host hardening (firewall, unattended security updates) run `sudo bash /opt/lonora/infra/compose/harden-host.sh --apply`
  — only on a server that runs nothing else: it changes the firewall.

### Resource limits

Every service has a memory and CPU limit, overridable in `.env`:

| Service | Memory | CPUs | Variables |
|---|---|---|---|
| db | 512m | 0.5 | `LONORA_DB_MEMORY`, `LONORA_DB_CPUS` |
| api (includes the chart renderer) | 896m | 0.75 | `LONORA_API_MEMORY`, `LONORA_API_CPUS` |
| gateway | 768m | 0.75 | `LONORA_GATEWAY_MEMORY`, `LONORA_GATEWAY_CPUS` |
| caddy | 96m | 0.25 | `LONORA_CADDY_MEMORY`, `LONORA_CADDY_CPUS` |
| searxng (web search) | 384m | 0.25 | `LONORA_SEARXNG_MEMORY`, `LONORA_SEARXNG_CPUS` |
| browser (research browser) | 768m | 0.5 | `LONORA_BROWSER_MEMORY`, `LONORA_BROWSER_CPUS` |
| migrate (runs only during updates) | 512m | 0.5 | `LONORA_MIGRATE_MEMORY`, `LONORA_MIGRATE_CPUS` |

| workspace (the owner's agents' terminal) | 4g | 2 | `LONORA_WORKSPACE_MEMORY`, `LONORA_WORKSPACE_CPUS` |
| workspace-net (its network guard and relay) | 192m | 0.5 | fixed |

The running stack is limited to about 3.4 GB and 3 CPUs; the workspace adds its own limits («The
workspace» below). The limits are ceilings, not reservations, so the stack still runs on a 2-vCPU
host. After changing a limit: `sudo lonora start`.

### The workspace

Each installation runs the owner's one persistent Linux workspace (mandate 7.1): the services
`workspace` (a supervisor that runs each agent's commands under that agent's own Unix user and
home, `/workspace/home/a<uid>`, with `/workspace/shared` writable by all) and `workspace-net` (a
guard that owns the workspace's network). Agents use it through the workspace tools
(`workspace_run`, `workspace_file_read`/`_write`, `workspace_processes`, `workspace_stop`); every
byte that comes back is scanned and each workspace secret becomes `[secret:NAME]`. Because a log
or an older process can still hold a value given to a command, the Gateway keeps every value
given to a command, encrypted with the secret key, for 30 days after it was last given, and the
scan keeps replacing it: a deleted or rotated secret's value stays stored, encrypted, for up to
30 days, then is erased. Python, pip, Node, git, SSH, curl,
compilers and Chromium (headless) come from the server image; agents install more at user level
(`pip install` goes to `~/.local`), which survives updates. System packages come only from the
image: agents have no root. Running processes end when the containers are re-created (every
update) or the host restarts; files do not. `lonora` starts the workspace after Lonora's own
services and does not wait for it: a workspace that does not start, or a disk that cannot be
prepared, is reported and Lonora runs without it (agents get a tool error).

| Setting in `.env` | Default | Meaning |
|---|---|---|
| `LONORA_WORKSPACE_CPUS` | 2 | CPU quota. Its CPU weight is 128 against every other service's 1024, so under contention the Gateway and the database get their CPU first. |
| `LONORA_WORKSPACE_MEMORY` | 4g | Memory, without swap. Its OOM score is the highest on the host, so the kernel kills a workspace process before any Lonora process; the database, API and Gateway reserve their memory. `lonora start` and `update` warn when the host has less memory than Lonora plus this. Disk I/O has no weight (it needs a host I/O scheduler that is not always there). |
| `LONORA_WORKSPACE_DISK` | 20g | Size of `workspace.img`. Grown in place when raised (`sudo lonora start`); never shrunk. |
| `LONORA_WORKSPACE_PROCESSES` | 256 | Processes and threads in the whole workspace. |
| `LONORA_WORKSPACE_FOREGROUND_SECONDS` | 600 | Limit of a foreground command. Background processes have none. |
| `LONORA_WORKSPACE_BLOCKED_ADDRESSES` | empty | More addresses (CIDR, space separated) the workspace may never reach, e.g. this server's public IPv4 when `LONORA_DOMAIN` does not resolve to it. |

**What the workspace can and cannot reach.** It reaches the internet. It cannot reach the
database, the API, the Gateway or Caddy (they are on another Docker network, and every private,
link-local and reserved range is rejected), Docker's internal resolver, the host's own ports,
Lonora's public address (`LONORA_DOMAIN` is refused by name, its addresses and every global
address of the host are rejected), or MetaApi: names under `agiliumtrade.ai` and `metaapi.cloud`
do not resolve, no outside resolver is reachable, and every agent TCP connection passes a relay.
A client that speaks first must speak TLS, HTTP or SSH; the relay refuses an address used as the
name, MetaApi and Lonora names in TLS server names, HTTP hosts and proxy targets, and a dialled
address that is not one of the named host's addresses (CNAME chains into MetaApi included, whose
addresses are then blocked). Agent UDP (except DNS to the guard) and IPv6 TCP are rejected. This
is defence in depth, not a wall: a name that resolves to a MetaApi address the guard has not
learned (wildcard DNS such as sslip.io), an HTTPS proxy and anything carried over SSH still reach
MetaApi, and the internet and SSH must work (7.1.2). What holds is that the MetaApi token never
enters the workspace (7.2.3): reaching a MetaApi host gives a program nothing to trade with. It has no Docker socket, no
`.env` and no Lonora secret; the MetaApi token never enters it. Agent processes have no
capability and cannot gain privileges.

**The disk.** `lonora start`, `update` and `restore` create `workspace.img` on first use (they
refuse when the disk lacks its size plus 5 GB), mount it at `workspace-disk/` and install a
systemd mount unit so it is mounted at boot before Docker. The supervisor refuses to start on an
unmounted directory, so the host's own disk never takes workspace writes. The workspace is **not**
in the backups (it can hold 20 GB of agent files and installed packages); back up
`/opt/lonora/workspace.img` yourself if you want it.

**The owner's current server** (2 vCPU, 7,940 MiB with about 5.2 GiB available, 4 GiB swap, load
1.0-1.5, 25 GB free on `/var/lib/docker`, another stack beside Lonora): the mandate's defaults do
not fit, so its deployment file (the installation's `.env`) sets

```sh
LONORA_WORKSPACE_MEMORY=2g
LONORA_WORKSPACE_CPUS=1.0
LONORA_WORKSPACE_DISK=10g
```

(`/opt/lonora2/.env` for the side-by-side install). Lonora's own ceilings (about 3.4 GB, with
web search and the research browser) plus a 2 GiB workspace come to about 5.5 GB, a little
above the 5.2 GiB available: these are ceilings, not use, and under pressure the workspace is
killed first; at most one CPU leaves the other to Lonora and the other stack even
when the workspace is busy; 10 GiB of the 25 GB free leaves room for images and backups. The
Gateway and the database keep their memory reserved and the Gateway the highest CPU weight
(2048 against the workspace's 128), so reconciliation of uncertain operations keeps running.
For a new install on such a host: `install.sh --workspace-memory 2g --workspace-cpus 1.0
--workspace-disk 10g` (the preflight then needs 5,632 MB free memory and 22 GB free disk; with 5.2 GiB free,
add `--min-free-ram-mb 5120` knowingly, or give the workspace 1536m).

**The first update to a version with the workspace.** `lonora update` runs the `lonora` already
on the server, which does not know the workspace disk. Run the new version's command instead,
once:

```sh
docker run --rm --entrypoint cat ghcr.io/loorksy/lonorabot:<version> /app/deploy/infra/compose/lonora >/tmp/lonora-new
sudo LONORA_HOME=/opt/lonora2 bash /tmp/lonora-new update <version>
```

**Prove it.** `sudo python3 tests/check_workspace_service.py --image <image>` installs a
throwaway project beside the real one (its own name, port and 1 GB disk) and checks every point
above, then removes it.

## Side by side with an existing reverse proxy

On a host where another reverse proxy (for example traefik) already owns ports 80 and 443 and other
projects run — including an older Lonora — install the new one beside them, under its own project
name and directory, behind that proxy:

```sh
sudo bash install.sh --home /opt/lonora2 --project lonora2 \
  --behind-proxy 127.0.0.1:18030 --domain new.example.com --version <version>
```

What this does and does not do:

- Caddy listens in plain HTTP on `127.0.0.1:18030` only; nothing binds 80 or 443, and nothing is
  reachable from outside except through your proxy. Caddy still applies the maintenance gate.
- Every container, volume and network is named `lonora2-…` / `lonora2_…`; the timer is
  `lonora2-backup.timer`. Nothing of another project is read, changed, stopped or restarted. The
  preflight refuses a port, project, volume or directory that is already taken.
- The installer never edits the reverse proxy. Pointing it at the new entry is your step.

### The owner's VPS: traefik file provider

On the owner's VPS, traefik runs on the host network with the file provider watching
`/docker/traefik/dynamic/`, and the certificate resolver is called `letsencrypt`. The old Lonora is
routed by `lonora.yml`: `Host(\`lonora.lork.cloud\`)` → `http://127.0.0.1:18010`, plus a
`/download` router (priority 1000) → `127.0.0.1:18020`. The old stack's volumes are
`lonora-database` and `lonora-artifacts`, its networks `lonora-net` and `lonora-research`; a new
installation under `--project lonora2` uses `lonora2_*` and `lonora2-*`, so nothing collides (the
preflight refuses if any of its own names already exist).

`/opt/lonora-mobile-build` on that server holds the Android signing keystore: never delete or modify
it. `lonora-analysis.service` is shared by the installations and stays when one is removed.

**Neither the installer nor `lonora` ever writes into `/docker/traefik/dynamic/`.** A malformed file
there can break traefik's file provider for every host on the server, so whoever edits it should
validate the YAML first and write atomically: create the file under another name in the same
directory, check it, then `mv` it into place.

**(a) A test host for the new installation** — a NEW file, `/docker/traefik/dynamic/lonora-next.yml`
(the DNS record for `next.lonora.lork.cloud` is the owner's step; install with
`--domain next.lonora.lork.cloud --behind-proxy 127.0.0.1:18030`):

```yaml
http:
  routers:
    lonora-next:
      rule: "Host(`next.lonora.lork.cloud`)"
      entryPoints: ["websecure"]
      service: lonora-next
      tls:
        certResolver: letsencrypt
  services:
    lonora-next:
      loadBalancer:
        servers:
          - url: "http://127.0.0.1:18030"
```

Write it safely, as root:

```sh
cd /docker/traefik/dynamic
cat >.lonora-next.yml.tmp <<'YAML'
…the YAML above…
YAML
python3 -c 'import sys, yaml; yaml.safe_load(open(sys.argv[1]))' .lonora-next.yml.tmp && mv .lonora-next.yml.tmp lonora-next.yml
```

(Without PyYAML, `docker run --rm -v "$PWD":/d mikefarah/yq:4 e . /d/.lonora-next.yml.tmp` checks it
the same way.) Check the entry point names (`websecure` above) against the existing files in that
directory and use the same ones.

### Analysis workspace host

The analysis workspace (agents running analysis code in isolated containers) needs a trusted host
service, `lonora-analysis.service` (a venv in `/opt/lonora-analysis`, socket
`/run/lonora-analysis/host.sock`; `docs/analytical-workspace.md`). It is a host-level control plane
with Docker access, so the installer neither installs nor upgrades it. On the owner's VPS it already
runs for the old stack, and the new installation uses the same socket:

1. Check it runs: `systemctl status lonora-analysis` and `test -S /run/lonora-analysis/host.sock`.
2. Install with `--overlay infra/analysis/compose.workspace.yml`, or on an existing installation add
   `infra/analysis/compose.workspace.yml` to `LONORA_COMPOSE_OVERLAYS` in `.env` and run
   `sudo lonora start`. The overlay mounts only the socket directory, read-only, into the API and the
   Gateway (group 10001), with `LONORA_WORKSPACE_SOCKET` set; it never mounts the Docker socket.
   The directory is created if it is missing, so the API and the Gateway start (and `/ready` passes)
   even when the service is not running — after a reboot Docker may start before it, or it may be
   stopped. Analysis tools then answer that the host is unavailable until the service starts and
   creates its socket in that same directory (systemd reuses an existing `RuntimeDirectory`).
3. When the old stack is deleted, leave the service running: the new installation uses it.
   Upgrading the service itself follows `docs/analytical-workspace.md` (its reviewed venv and image ID).

## Switch over later

Only the owner does this, and only when they decide to; nothing here happens automatically.

1. Check the new installation on its test host: sign in at `https://next.lonora.lork.cloud`,
   `sudo lonora status` shows `/ready: ok`, `sudo lonora backup` and `sudo lonora restore-test` pass.
2. Give the new installation the main name: set `LONORA_DOMAIN=lonora.lork.cloud` in
   `/opt/lonora2/.env`, then `sudo lonora start`. (Passkeys registered on the test name must be
   registered again on the main name.)
3. **(b) Cut over by swapping only the url** in `/docker/traefik/dynamic/lonora.yml`: the main
   router's service url `http://127.0.0.1:18010` becomes `http://127.0.0.1:18030`. Leave the rest
   of the file as it is (the `/download` router can stay on `127.0.0.1:18020` while the old downloads
   service runs). Edit a copy, validate it, move it into place:

   ```sh
   cd /docker/traefik/dynamic
   cp lonora.yml .lonora.yml.before          # keep for going back
   sed 's#http://127.0.0.1:18010#http://127.0.0.1:18030#' lonora.yml >.lonora.yml.tmp
   diff lonora.yml .lonora.yml.tmp           # exactly the one url line
   python3 -c 'import sys, yaml; yaml.safe_load(open(sys.argv[1]))' .lonora.yml.tmp && mv .lonora.yml.tmp lonora.yml
   ```

   Traefik picks the change up by itself. `lonora-next.yml` can be removed afterwards (`rm`, no edit).
4. Stop the old stack, without deleting anything: `cd /opt/lonora && docker compose --env-file .env -f <its compose file> stop`.
   Its data stays in its volumes; archive it later as in «Your current server: start fresh» steps 2–4
   if you want the space back.
5. To go back: `mv .lonora.yml.before lonora.yml` in the traefik directory and start the old stack
   again (`docker compose … start`).

## Build from source on the server

While no published image exists (for example while GitHub Actions is unavailable), build one on the
server from a checkout:

```sh
git clone https://github.com/loorksy/lonorabot /srv/lonorabot && cd /srv/lonorabot && git checkout <commit>
sudo bash infra/compose/build-from-source.sh --source /srv/lonorabot --project lonora2 --version v0.3.0
# it prints the digest, e.g. 127.0.0.1:5055/lonora@sha256:…; use the digest, never the tag:
sudo bash install.sh … --project lonora2 --version 127.0.0.1:5055/lonora@sha256:…   # new install
sudo lonora update 127.0.0.1:5055/lonora@sha256:…                                   # update
```

The loopback registry has no authentication, so a tag there could be repointed by anything on the
host: install and update by the printed digest.

The script starts a registry container (`lonora2-registry`, volume `lonora2_registry`) that listens on
`127.0.0.1:5055` only (`--registry-port`), builds in a dedicated BuildKit container capped at
`--cpus` (default 1) and `--memory` (default 2g) with a low CPU weight (and a low I/O weight where the
kernel supports it), under `nice` and `ionice`, pushes the image there
and prints its digest. Install and update then pin that digest exactly as with a published image,
including backups and automatic rollback. The registry keeps every built version, so a rollback can
always pull the previous one. Needs `git` and the Docker buildx plugin.

## Update

```sh
sudo lonora update v0.3.0     # or: main, or ghcr.io/loorksy/lonorabot@sha256:…
```

Everything is checked before anything changes: the tag resolves to an exact digest, the pinned
image must itself be a `repo@sha256` digest (otherwise a rollback could not return to exactly it),
the new image must carry a release manifest, and the database's migration must be known to the
new image (no downgrades: restore a backup made on that version instead). Then, in order:

1. **Maintenance on.** `maintenance/on` is created. While it exists, Caddy answers every write
   (anything but GET, HEAD and OPTIONS) with `503` and «يجري التحديث، حاول بعد دقائق». It is on only
   while no Gateway runs: **a Gateway never runs while maintenance is on**, so whenever anything could
   trade, the owner's pause, close, approval reject and authority revoke are
   accepted.
2. An in-progress marker (`state/update-in-progress`) is written; API and Gateway are stopped.
3. An encrypted backup is taken **and verified** (decrypted, authenticated, every checksum and the
   whole dump read back). If that fails, nothing changes: marker and maintenance are removed and
   the old version starts again. A missing backup file also stops the update here.
4. The new deployment files are copied in (each renamed into place) and the new digest is pinned.
5. Migrations run as their own step (`migrate` service). Right after, a fingerprint of the
   owner-control and money records is taken (see below).
6. The API starts first, **with the Gateway still stopped**, and must pass `/health`. Then
   maintenance is turned off (writes open again), the Gateway (agent and trading loops) starts, and
   the update waits for `/ready` (default 240 s, `LONORA_READY_TIMEOUT`).
7. Success: marker removed, `state/history.log` updated.

Web search (SearXNG) and the research browser start with every update but are never waited on:
`lonora` waits on `db`, `api`, `caddy` and `gateway` only, so their health can neither fail nor roll
back an update, a restore or a start. One exception: the single update *from* a release that still
had the optional research overlay runs that older `lonora`, which waits on every service, so that
one update still needs SearXNG and the browser to pull and become healthy. Updates after it do not.
An installation that had listed the retired overlay in `LONORA_COMPOSE_OVERLAYS` has it skipped
from then on and removed from `.env` by its next update.

**If step 4, 5, 6 or a health gate fails**, `lonora` rolls back by itself: the old deployment files
and pin come back and the database is **restored from the backup of step 3** — dropped and recreated
from that dump, not migrated down. An Alembic downgrade after the new version has written rows can
lose or corrupt data; restoring the pre-update backup cannot. Because API and Gateway were stopped
before that backup, nothing the owner did before the update is lost, and nothing the failed version
wrote (including a half-applied migration) survives.

**The exception: a held rollback.** Once the new API or Gateway has run, restoring the backup could
undo something that must not be undone: an owner's pause, a revoked
authority, an owner's message, or the record of an order already at the broker. So before restoring,
`lonora` compares the fingerprint of these records with the one from step 5: whole rows (each hashed
on its own) of `ln_account_authorities`, `ln_supervision_grants`,
`ln_supervision_holds`, `ln_owner_actions`, `ln_trade_approvals`, `ln_trading_journal`, paused
agents, the broker connections' enabled flags, paused or cancelled tasks, and the owner's own messages in `ln_messages` (including Telegram and
voice). If any of them changed, or cannot be read, it does **not** restore. It stops API and
Gateway, keeps maintenance on and the failed version pinned, prints `ROLLBACK HELD` with the reason,
and exits with status 2.

**The update runs as the target release's own `lonora`.** Before it changes anything, `lonora
update` reads the target image's `infra/compose/lonora` and, when it differs from the running one,
hands the update to it (same lock, home and command name). The fingerprint's definition is its own
file, `infra/compose/lonora-controls.sh`, and the one in force is the target release's copy:
`lonora update` reads it from the image it installs before anything changes, keeps it next to the
update marker (`state/update-controls.sh`; a held update keeps its own), and uses it for the
baseline of step 5 and for the comparison of any rollback of that update. A release that drops a
table therefore drops it from both sides, and each part is read only when its table exists, so a
removed table never makes the records "unreadable". An image built before this file existed
carries none; the installation's own copy stands in.

**Once, on an installation whose `lonora` predates this** (it has no
`infra/compose/lonora-controls.sh`): that script cannot hand the update over, and it reads the
owner controls with its own definition, which may name a table the target release drops (the
update then stops at "reading the owner-control records" and the rollback holds). Install the
target's two files first, then update as usual:

```
IMAGE=ghcr.io/loorksy/lonorabot:<version>
cd /opt/lonora
sudo docker pull "$IMAGE"
for f in lonora lonora-controls.sh; do
  sudo docker run --rm --network none --entrypoint cat "$IMAGE" /app/deploy/infra/compose/$f | sudo tee infra/compose/$f.new >/dev/null
  sudo chmod 755 infra/compose/$f.new && sudo mv -f infra/compose/$f.new infra/compose/$f
done
sudo lonora update <version>
```

### When an update does not finish: what to do

| You see | It means | Do |
|---|---|---|
| `Rolled back to …; /ready passes` | The previous version runs again. | Nothing. Report the failed version. |
| `ROLLBACK HELD: …` (exit 2) | Owner controls or trading records changed while the new version ran. API and Gateway are stopped. | Check positions and orders in the broker's own terminal since the time shown. Then either `sudo lonora rollback --force` (restore the pre-update backup; what was written since is lost, so note it first) or `sudo lonora update <fixed version> --keep-data` (keep the current data and update forward). |
| `--keep-data` fails again | The forward update did not pass its gates. | It returns to the held state (data kept, services stopped); same two choices. Passing the version that is already pinned starts it again behind the gates. |
| `ROLLBACK HELD: … cannot be read` (exit 2) | The owner-control records could not be read, so it is unknown whether they changed. | Fix the database (`sudo lonora logs db`), then `sudo lonora rollback`. |
| `ROLLBACK INCOMPLETE: restoring the database … failed` | The database was dropped but the restore failed (for example a full disk). | Fix the cause (`sudo lonora status`, `sudo lonora logs db`, `df -h`), then `sudo lonora rollback` — it retries the restore from the same backup. |
| `ROLLBACK did not reach /ready` | The previous version and data are back but do not start; writes are open. | `sudo lonora logs api`, `sudo lonora logs gateway`; when fixed, `sudo lonora rollback` starts and checks again. |
| `The pre-update backup … cannot be opened` | The backup could not be decrypted or extracted (key, disk space). | Fix it, then `sudo lonora rollback`. |
| `Maintenance: on` in `lonora status`, writes answer 503 | Something stopped with maintenance on (only ever while the Gateway and API are stopped). | `sudo lonora maintenance off` opens writes without waiting for `/ready`, then `sudo lonora start`. `sudo lonora maintenance on` stops the Gateway and API first; if they cannot be stopped, maintenance stays off. |
| `Restoring the database failed … run it again: sudo lonora restore FILE --replace` | A restore stopped after the database was dropped. | Fix the cause, then run exactly the printed command: it resumes without a second safety backup. `update` and `start` refuse until it is done. |
| `The database has no migration yet` | An installation stopped before its first migration. | `sudo lonora start`. |
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
starts the database if it is stopped, turns maintenance on and stops API and Gateway, then **takes a
safety backup of the current state** (so nothing written during it is lost), records a
restore-in-progress marker, replaces the database with a fresh copy from the backup, replaces the
artifact files, runs the migrations (so an older backup is brought up to the installed version),
turns maintenance off, starts everything and waits for `/ready`. `--replace` is required. If it
stops part-way it prints the command to run again; that rerun resumes from the marker without a
second safety backup, and `update` and `start` refuse until it is done.

**Disaster recovery on a new server**, exactly:

```sh
sudo bash install.sh --domain <your domain> --version <the backup's version or newer>
sudo install -m 600 /path/to/your/backup.key /opt/lonora/backup.key
sudo lonora restore /path/lonora-….tar.gpg --replace --with-config
```

`--with-config` also restores the secrets and settings in `.env` (domain, encryption key for saved
credentials, bootstrap token, provider keys) and the APK/OTA release files. It never restores what
describes this installation rather than its secrets: the database password (the new server's
database was created with its own), the project name (`LONORA_PROJECT`), the mode and port
(`LONORA_PROXY_LISTEN`), the overlay list, the resource limits, the pinned image or any deployment
file. Without `--with-config` the current `.env` is kept.

**An unfinished restore** (`RESTORE NOT FINISHED` in `lonora status`) blocks `update`, `start` and the
daily backup (a backup of a half-restored database is useless). Three ways out: finish it (the
printed `sudo lonora restore FILE --replace`), go back to the state before it
(`sudo lonora restore <its safety backup> --replace`; the safety backup is named in `lonora status`
and is never rotated away), or `sudo lonora restore --abandon` (asks to type ABANDON, or `--yes`),
which only clears the marker and leaves the database as it is.

## Push to the owner's phone

Push goes through the Expo push service with the owner's own Expo project (VISION 11.4). What
exists at this commit is the phone side: after sign-in the app asks for the notification
permission and registers the phone with `PUT /api/push/devices/<install id>` (owner session
only). The server stores the Expo push token encrypted, bound to the sign-in session that sent
it, and deletes it on sign-out (`POST /api/auth/logout`) or when the app finds the permission
turned off (`DELETE /api/push/devices/<install id>`). The token is never logged and never
shown to a model.

The gateway step `push` sends one push per record, when it is created, to every phone that has
not signed out: a pending Trade Approval card, a Settle Uncertain Operation card, a
Secret card an agent's run is waiting on, and a broker health problem (a rejected MetaApi
token, an undeployed account, or a connection lost for more than two minutes), once per
account and outage however often its reason changes. The text is
Lonora's fixed text for that event in the owner's language under the agent's name; no price,
volume, symbol or account number leaves the server, and the notification has no button. A tap
opens the conversation at the card, and the card itself is where the owner approves or
settles. Quiet hours do not hold these pushes. Execution Receipts and reports never push. Each
push has an effect receipt written before the call to Expo, and a push whose outcome is unknown
(a timeout, a restart) is never sent again, so a record pushes once per phone even across
restarts and two gateways. A push that certainly never reached Expo (no connection, or "too
many requests") is tried again up to five times over about eight minutes. Each phone gets its own request, so a token Expo refuses never
costs another phone its push. When push is first installed it starts from the end of the event
stream: cards that were already waiting do not push.

A phone keeps receiving push until it signs out, even after its sign-in session has expired
(a session lasts `LONORA_SESSION_SECONDS`, default one day): a push carries only the agent's
name and fixed text, and the phone must stay reachable while the app is closed. Signing out
revokes the session and the gateway deletes that phone's row; the app registers again at the
next sign-in.

`LONORA_EXPO_ACCESS_TOKEN` (optional, in `.env`) is sent to Expo only when the Expo project has
"enhanced security for push notifications" turned on. `/ready` reports `"push":
"configured"` once a phone that has not signed out is registered and `"not_configured"` before;
push never makes the server unready.

A native release with push needs, once:

1. An Expo project at expo.dev owned by the owner; its project id (a UUID) is
   `LONORA_EXPO_PROJECT_ID`.
2. A Firebase project with an Android app whose package is `ai.lonora.mobile`; download its
   `google-services.json` and upload the same project's FCM V1 service-account key to the
   Expo project (expo.dev, project credentials, Android, FCM V1). The path of the
   `google-services.json` file is `LONORA_ANDROID_GOOGLE_SERVICES_FILE`.
3. For iOS (no iOS release is built today): an APNs key registered in the same Expo project.

Then build the APK as usual with both variables set:

```bash
LONORA_EXPO_PROJECT_ID=<uuid> LONORA_ANDROID_GOOGLE_SERVICES_FILE=/path/google-services.json \
  pnpm --filter @lonora/mobile android:release
```

The release refuses one variable without the other and prints `Push: built in.`. Without the
variables it prints `Push: not configured`, and that build never asks for the permission or
registers (the notification module is linked into every build, so every APK declares
`POST_NOTIFICATIONS`). The notification module is native code, so an OTA update cannot add it
to an older APK: the phone needs this new APK. The fingerprint `runtimeVersion` includes the
project id and the Firebase file, so publish OTA updates for a push build with the same two
variables set (`scripts/ota-publish.sh` refuses one without the other); an update exported
without them has another runtime and never reaches that phone.

### Telegram

The owner may also receive these alerts in Telegram (VISION 11.4). Link a bot in the web app
(Settings, Integrations, Telegram: the bot token from @BotFather and the agent that receives
your messages). Then pair your chat from chat: write anything to your bot from your own
private chat; it answers with a one-time code, and you send that code to Lonora in the app as
a short message of your own («اربط تيليجرام: CODE»). Lonora links the chat only when the code
stands in your own short typed message, so a code it read anywhere else, or a long pasted text
carrying one, links nothing. A code lasts ten minutes and works once; a chat gets one code at
a time; at most three chats wait, the oldest making room for a newcomer; and nothing a chat
writes before it is linked reaches an agent. Once a chat is linked the bot offers no codes:
to move to another chat, unlink the bot and link it again. From then on the bot sends the
alerts that push, from every agent's conversation (the agent's name and the same fixed text),
once per record, with an effect receipt before each call and no second send of an unconfirmed
one; alerts from before the pairing are not sent. Agents' replies are not sent to Telegram;
read them in the app. What you write to the bot reaches the chosen agent's conversation as
your message: a "yes" there is a message to the agent and never approves or settles a card,
which only the card in the app does. A `/start` message is never passed to an agent, and
neither is a forwarded message or one sent through another bot: those are someone else's
words, not yours.

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
live VPS. On the owner's VPS, which shares the host with other projects behind traefik, use
«Side by side» above: the new installation starts empty under its own project name and the old one
keeps running until the owner switches over.

The steps below are for a server where the new installation should take the old one's place and
name (`lonora`) directly. The new stack then uses the same Compose project name and volume names as
the old one, so the old volumes must be archived and then removed — otherwise the new install would
reuse them (the preflight refuses in that case).

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
machine. It uses the projects `lonora` and `lonora2`, their volume names, ports 80/443 and
`127.0.0.1:18010`/`18030`, so it refuses to run where either project exists. It checks:

1. install: digest pinned, secrets mode 600, bundle modes, refusal of its own home (naming
   `sudo lonora start`) and of a leftover `lonora_database` volume next to a new home;
2. no secret and no legacy deployment path in the image's bundle or `release.json`;
3. seed an owner account and an artifact;
4. backup: not a readable tar; the decrypted copy holds the dump and `.env`, the file neither;
5. restore test: network internal with no route out (checked by `lonora`), nothing left behind;
6. damaged file, wrong key and a forged plaintext backup refused, nothing changed;
7. a failing and a truncating `pg_dump`: the update aborts before pinning, the live database untouched;
8. refusals: a concurrent operation, no pin, a tag (not digest) pin, an image without a manifest;
9. update: API gated before the Gateway, script replaced atomically, writes open again after;
10. a broken update: `503 «يجري التحديث»` while API and Gateway are stopped, writes open while the new
    Gateway runs, rolled back from the pre-update backup, earlier rows kept;
11. the same with `pg_restore` failing after `DROP DATABASE`: the rollback stops at phase
    `restoring` with a working command, and `lonora rollback` retries and completes;
12. an update killed mid-way: marker kept, `start` refused, the next update rolls back and completes;
13. restore from another directory with the database stopped, of the oldest backup while rotation
    would delete it: read-only (503, no Gateway) during its safety backup, file kept, older schema
    migrated up; then a restore failing after `DROP DATABASE`: the printed command resumes without a
    second safety backup while `update` refuses; `KEEP=1` keeps a held backup and `KEEP=0` is refused;
14. an owner-control write during the gate: held; `--keep-data` with the same digest stays held,
    a bad tag changes nothing, another failing version returns to the hold, a fixed version
    updates forward keeping the write;
15. a trading-journal row written during the gate: held; backups during the hold keep its backup;
    `rollback` still holds; `rollback --force` restores;
16. disaster recovery: a newer backup refused on an older image; `--with-config` restores the
    secrets and keeps the new database password;
17. side by side, with `--env-from` an old `.env` (known keys copied, a fresh database password,
    names listed, no value printed): beside a running dummy project named `lonora` (its volumes,
    network `lonora-net`, a service on `127.0.0.1:18010`), the preflight refuses the taken project, a
    used port, a public address, and too little memory or disk, creating nothing; then `lonora2`
    installs in proxy mode, publishes only `127.0.0.1:18030` (`/health` 200 through it), carries the
    memory and CPU limits, updates, backs up and passes a restore test — and the old project's
    container IDs, start times, volumes and network are identical before, during and after;
18. no secret (encryption keys, backup key, database passwords, bootstrap token, webhook secrets,
    the old `.env`'s values) in any log the test wrote or in `state/history.log`.

Also: an install with no schema yet is brought up by `update` of the pinned version and by the named
`sudo lonora start` (1b); a rollback whose `/ready` fails leaves writes open and the next
`lonora rollback` completes (10c); 503 is asserted while API and Gateway are stopped and writes are
open while the new Gateway runs (10); a sampler finds no moment with maintenance on and a Gateway
running through `update <pinned>` and `maintenance on`, and status names the clear command (9b);
an unfinished restore also blocks the daily backup and an unconfirmed `--abandon`; the side-by-side
install also uses the workspace overlay with no socket (still `/ready`), refuses port 70000 and a
CRLF `--env-from` file, and a `lonora2` backup restored `--with-config` into a `lonora3` install
keeps `lonora3`'s project and mode. 22 checks in all.

`REPO` must hold the tags `old`, `v1`, `v2`, `v4-good`, `v3-broken`, `v3-broken2` and `v3-fixed`. Build them with
`tests/ops/build_test_images.sh REPO`, into any registry you control:

```sh
docker run -d --name registry -p 127.0.0.1:5000:5000 registry:2
bash tests/ops/build_test_images.sh localhost:5000/lonora
bash tests/ops/lifecycle_test.sh localhost:5000/lonora
```

It builds `old` from main at `80e195f` (the last commit before this tooling, override with
`OLD_SHA`), `v1` and `v2` from the checkout with different `LONORA_VERSION`, and four probe images
on top of `v2` from `tests/ops/fixtures`: `v4-good` (+ `9998_good_probe`), `v3-broken` (+ 9998 and
`9999_broken_probe`, with a Gateway that never starts), `v3-broken2` (`v3-broken` under another
version) and `v3-fixed` (the same migrations, working). The probes chain onto `v2`'s migration head
at build time and exist only inside those test images. It pushes all seven and prints their digests
(also written to `.runtime/ops-test-images.txt`). Where
the Debian mirror is unreachable, `LONORA_TEST_SKIP_APT=1` drops the Chromium/fonts line;
`LONORA_BUILD_CA_FILE` and `LONORA_BUILD_NETWORK=host` help behind a TLS-intercepting proxy on
`127.0.0.1`. The runs reported here used all three.

### What was verified, and what still needs a real host

Verified with real images, a local registry (real digests), PostgreSQL 16 and Caddy 2.10, on
Docker 29.1.3 and Compose 2.40.3: all 22 lifecycle checks passed (`LONORA_TEST_SKIP_APT=1`).
The fresh-start archive steps in «Your current server: start fresh» are not part of those 22 checks.

`build-from-source.sh` was run here on the checkout (`--cpus 1 --memory 2g`): the BuildKit container
ran with a CPU quota of 100000 and a 2 GiB memory limit on the host network, the registry listened on
`127.0.0.1:5055` only, the image was pushed and its digest printed; `install.sh --project srctest
--behind-proxy 127.0.0.1:18040 --version 127.0.0.1:5055/lonora:src1` then installed it, pinned that
digest, and `/health` answered 200 through `127.0.0.1:18040` with `/ready` passing.

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
- The side-by-side install on the actual VPS next to traefik and the running projects, the traefik
  route files, and the switch-over (only with the owner's permission; the lifecycle test covers the
  same steps beside a dummy project here).
- The fresh-start procedure on a server where the new installation replaces the old one.
