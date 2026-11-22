# Lonora Cloud — the plan to run Lonora as a company

**Status: Proposed. Not binding.** `VISION.md` §17 says multi-user hosting is out of scope. Nothing in this
folder may be implemented until the owner issues Amendment 3 (draft: [AMENDMENT-3-DRAFT.md](AMENDMENT-3-DRAFT.md))
and confirms the decisions in [DECISIONS.md](DECISIONS.md) that the phase depends on.

---

## ملخص بالعربية

### الفكرة في سطر
شركة تستضيف لكل عميل **نسخة Lonora خاصة به بالكامل** (خادم مستقل، قاعدة بيانات، مفاتيح، مساحة عمل، نسخ
احتياطية) — مثل نموذج myclaw.ai — مع بوابة عملاء، فوترة، لوحة إدارة، لوحة مشرفين، دعم فني، عمليات،
أمان وامتثال وقانون وتسويق.

### أين وصلنا (2026-11-22)
- **منفّذ وموجود على `main`:**
  - التعديل 2 في VISION: **MT5 فقط**، على أي رمز يدعمه وسيط العميل.
  - القاعدة نفسها في دليل الوكيل.
  - حظر نطاقات منصات التداول الأخرى في الطرفية، بالاسم فقط.
  - خريطة الكود (`floorplan/`)، وهذه الخطة، والمقترحات في `docs/proposals/`.
- **لم يُنفَّذ بعد:** كل مراحل السحابة (0–9 وM)، ومسار المنتج (أوامر CLI الوكيل PT-3، وبيئة الوكيل PT-4، والبحث
  الهجين PT-6).
- **قرارات المالك المسجّلة:** MetaApi من حساب الشركة (D27)؛ MT5 فقط ولا كريبتو (VISION 2، D33)؛ التطبيق هو المنتج
  والموقع للاشتراك والحساب فقط (D36–D39)؛ لا CLI للمالك (D42)؛ الباقات والأسعار لاحقاً (D13، D14)؛ **العميل يضع حساب
  مزوّد النماذج ومفتاحه بنفسه**، والشركة لا تدفع ثمن النماذج (D6، D41).
- **موانع قبل أي تنفيذ:**
  - **الـCI على GitHub معطّل** (P0-T10).
  - التعديل 3 لم يصدر بعد.
  - القرارات المقترحة تنتظر التأكيد.
  - القانون، ومزوّد الدفع، واتفاق MetaApi، وترخيص TradingView.
- **رحلة العميل كاملة:** [JOURNEY.md](JOURNEY.md).

### لماذا نسخة لكل عميل وليس قاعدة بيانات مشتركة
- قاعدة Lonora تفرض **مالكاً واحداً بنيوياً**: `get_owner()` يقرأ `OwnerRow.singleton == 1`
  (`packages/db/src/lonora_db/owner.py`). تحويلها لقاعدة مشتركة يعني إعادة كتابة كل مسار وكل جدول ونواة الأمان.
- النشر الإنتاجي (`infra/compose/docker-compose.prod.yml`) والمثبّت والأمر `lonora` (تحديث برجوع تلقائي، نسخ
  احتياطي مشفّر، اختبار استعادة) **مصمَّمة أصلاً لخادم مالك واحد** — نعيد استخدامها كما هي لكل عميل.
- مساحة العمل تشغّل كوداً عشوائياً من الوكلاء مع اتصال إنترنت؛ وضعها على نفس النواة مع مفاتيح وسطاء عملاء آخرين
  غير مقبول لمنتج تداول ← **وحدة العزل الافتراضية = آلة افتراضية (VM) لكل عميل**.

### الوعد للعميل (ميزة تنافسية)
«Lonora الخاص بك، مفاتيحك، حساباتك. نحن نشغّل الخوادم فقط؛ **Lonora الخاص بك وحده يتداول على حسابك**، لا نخزّن
كلمة مرور الوسيط أبداً، ولا نستطيع الدخول إلى Lonora الخاص بك ولا قراءة مفاتيح نماذجك.» تسجيل الدخول إلى النسخة
مستقل عن البوابة، ومفاتيح النماذج يجلبها العميل (BYOK) كما تفرض VISION §12.

### ربط حساب التداول (قرار المالك 2026-11-22)
العميل يكتب **رقم الحساب والخادم وكلمة المرور فقط** — بلا حساب MetaApi وبلا توكن. الشركة تملك حساب MetaApi وتدفع
تكلفته وتحاسب العميل ضمن الباقة (D27، التصميم في PLAN §3.8):
- خدمة واحدة معزولة (`broker-provisioner`) هي الوحيدة التي تملك مفتاح MetaApi الرئيسي، و**شبكياً لا تصل** إلا إلى
  خوادم التوفير وإدارة التوكنات في MetaApi، فلا تستطيع التداول حتى لو اختُرقت.
- كل نسخة عميل تأخذ **توكناً محصوراً بحساباتها هي فقط** (14 يوماً، يُجدَّد كل 3 أيام)، وتتداول به كما تفعل اليوم
  تماماً — باب التنفيذ ونواة الأمان دون أي تغيير.
- كلمة المرور تمر **مرة واحدة في الذاكرة** إلى MetaApi ولا تُخزَّن ولا تُسجَّل.
- حدّ صادق يُذكر في صفحة الأمان: مفتاح الشركة يصل إلى الاتصالات التي أنشأها؛ لذلك له أشد الضوابط، وكل استخدام له
  يظهر للعميل.

### وكيل مفتوح مثل Grok Bot — الاستضافة لا تقلّص شيئاً (التعديل 3 §11)
كل وكلاء العميل يملكون حاسوبهم الخاص كما في النسخة الذاتية اليوم:
- **أي API:** إنترنت، أي أداة سطر أوامر، `pip`/`npm`، SSH، عمليات خلفية، متصفح، وأسرار من أي نوع.
- **أي خادم MCP بعيد:** يثق به المالك برسالة، مع OAuth. وخوادم MCP المحلية تعمل داخل مساحة العمل.
- **مهارات** من مستودعات GitHub موثوقة، أو يكتبها الوكلاء بأنفسهم.
- **التداول: MT5 فقط** (التعديل 2 في VISION، صادر) عبر باب التنفيذ، على **أي رمز يدعمه وسيط العميل**: عملات، ذهب ومعادن،
  مؤشرات، طاقة، وعقود CFD على الأسهم أو الكريبتو إن كان الوسيط يعرضها. التداول على أي منصة أخرى ممنوع عبر أي طريق، حتى لو طلبه المالك.
- الحدود الوحيدة المضافة: لا وصول إلى خوادم العملاء الآخرين ولا طبقة التحكم، ومنفذ SMTP 25 مغلق، وسلّم مكافحة الإساءة
  (لا يوقف Lonora نفسه أبداً).
- حدود الشبكة الحقيقية (موجودة اليوم): الاتصالات عبر TLS/HTTP/SSH **بالاسم** — يغطي كل خدمات الويب وWebSocket —
  ويُرفض الاتصال بعنوان رقمي مجرد وبالشبكات الخاصة.

### التطبيق هو المنتج (قرار المالك 2026-11-22، D36)
- **الموقع للتسجيل والدفع وإدارة الحساب فقط.** بعد التسجيل كل شيء في **تطبيق أندرويد أصلي**: الوكلاء والمحادثات
  والبطاقات والصوت والإعدادات.
- التطبيق موجود أصلاً (`apps/mobile`، Expo، APK موقّع، تحديثات OTA، وشاشة «إعداد Lonora» لإنشاء المالك)، لكنه اليوم
  **«واجهة مرافقة»**: إعداد المزوّدين والتكاملات، وأدوات التحكم في التنفيذ المالي، واللوحات، وتعديل المهارات والمعرفة،
  والصوت المباشر ما زالت في الويب. إكمالها هو المرحلة M (تفرضه VISION §13 أصلاً).
- الانتقال من الموقع للتطبيق برابط «افتح في التطبيق» يملأ عنوان الخادم ورمز الإعداد تلقائياً، والعميل يختار كلمة مروره
  ومفتاح المرور بنفسه.
- **Google Play أولاً** وملف APK موقّع من الموقع احتياطياً. **لا بيع داخل التطبيق**: الدفع على الموقع فقط، احتراماً
  لسياسات المتجر.
- iOS لاحقاً من نفس الكود.

### ما الذي يُبنى
| النظام | ماذا يفعل | أين |
|---|---|---|
| **نسخة العميل** | Lonora كما هو، على VM خاص، خلف Cloudflare | هذا المستودع + تعديلات صغيرة إضافية |
| **طبقة التحكم** | التسجيل، الباقات، التوفير الآلي، التحديثات، النسخ الاحتياطي، المراقبة | مستودع جديد `lonora-cloud` |
| **وكيل المضيف** | برنامج صغير على كل VM ينفّذ أوامر `lonora` المسموحة فقط (موقَّعة) | `lonora-cloud` |
| **خدمة ربط الوسطاء** | تنشئ اتصالات MetaApi من حساب الشركة وتصدر لكل نسخة توكناً محصوراً بحساباتها | `lonora-cloud` |
| **التطبيق (أندرويد أصلي)** | المنتج كله بعد التسجيل: الوكلاء، المحادثات، البطاقات، الصوت، الإعدادات | `apps/mobile` في هذا المستودع |
| **الموقع وبوابة العملاء** | الاشتراك والدفع وإدارة الحساب فقط: الفواتير، النسخ، نافذة الصيانة، التصدير، صفحة الحذف، الدعم | `lonora-cloud` |
| **لوحة الإدارة** | العملاء، الأسطول، الإصدارات، الفوترة، الحوادث، الأمان، السجل | `lonora-cloud` |
| **لوحة المشرفين** | طوابير الدعم، SLA، أداء الموظفين، الموافقات، التصعيد، الجودة | ضمن لوحة الإدارة بصلاحيات |
| **الدعم الفني** | تذاكر، دردشة، قاعدة معرفة عربي/إنجليزي، مساعد ذكي، حزمة تشخيص بموافقة العميل | `lonora-cloud` |

### المراحل (التفاصيل في [PHASES.md](PHASES.md))
0. قرارات المالك + التعديل 3 على VISION + الشركة والقانون والدفع (ابدأ مبكراً: موافقات الدفع تأخذ أسابيع).
1. **تجهيز النسخة** في هذا المستودع: `lonora status --json`، رابط الإعداد، شهادة Cloudflare، الإيقاف الآمن،
   مرحّل الإشعارات، ربط الجوال بـQR، حزمة التشخيص — كلها إضافية ومطفأة افتراضياً للمستضيف الذاتي.
2. هيكل طبقة التحكم (مستودع جديد، قاعدة بيانات، مصادقة، سجل تدقيق، طابور مهام).
3. محرّك التوفير الآلي + وكيل المضيف: من «ادفع» إلى «Lonora جاهز» آلياً في دقائق.
4. بوابة العملاء + الفوترة.
5. لوحة الإدارة + الصلاحيات + **لوحة المشرفين** + نظام الدعم.
6. العمليات: نسخ احتياطية خارجية، اختبار استعادة أسبوعي، مراقبة، صفحة حالة، إصدارات على حلقات في نافذة نهاية
   الأسبوع (سوق الفوركس مغلق)، حوادث، تعافٍ من الكوارث.
7. الأمان والامتثال والوثائق القانونية ومكافحة الإساءة.
8. الإطلاق: ألفا خاصة ← بيتا ← إطلاق عام، موقع تسويقي، مركز مساعدة، إحالات.
9. التوسّع وخفض التكلفة: خلايا كثيفة معزولة، مناطق متعددة، باقة مؤسسات، SOC 2.

**المرحلة M — التطبيق هو المنتج** (بالتوازي مع 2–4): جرد ما ينقص التطبيق عن الويب وإكماله، رابط الإعداد،
الإشعارات والصوت، والنشر على Google Play.

### أهم المخاطر (بالترتيب)
1. **القانون والترخيص المالي** حسب بلد الشركة والعملاء — يحسمه محامٍ مرخّص قبل الإطلاق.
2. **مزوّد الدفع** قد يصنّف برمجيات التداول الآلي «عالية المخاطر» — تحقّق قبل البرمجة.
3. **ترخيص TradingView Advanced Charts** مسجّل باسم المالك — يجب تأكيد أنه يغطي خدمة مستضافة لعملاء كُثر.
4. **اتفاق مكتوب مع MetaApi** — لم أجد شروط شراكة أو إعادة بيع منشورة؛ خدمة العملاء من حساب الشركة تحتاج موافقته
   وتسعيراً للحجم (D32). وامتلاك مفتاح يصل لكل اتصالات العملاء يحتاج رأي المحامي أيضاً.
5. **التكلفة لكل عميل** (VM لكل عميل + اتصالات MetaApi عالية الموثوقية) — تُقاس في المرحلة 3 قبل تثبيت الأسعار.
6. إساءة استخدام مساحات العمل (هجمات/سبام من خوادمنا) — مراقبة وحظر وسياسة استخدام.
7. **Google Play** قد يرفض التطبيق أو يزيله (سياسة التطبيقات المالية أو سياسة الدفع) — مراجعة السياسات قبل الإرسال،
   وملف APK موقّع من الموقع احتياطياً.
8. **الـCI معطّل اليوم**، فلا شيء يحمي `main` — يُصلح أولاً (P0-T10).

---

## Files

| File | What it is |
|---|---|
| [DECISIONS.md](DECISIONS.md) | Owner decisions, each with a recommendation and its status. Claude Code reads this first. |
| [AMENDMENT-3-DRAFT.md](AMENDMENT-3-DRAFT.md) | Draft text of VISION.md Amendment 3, for the owner to edit and issue. |
| [PLAN.md](PLAN.md) | The full design: architecture, isolation, lifecycle, portal, admin, supervisors, support, billing, operations, security, legal, go-to-market, KPIs, risks. |
| [PHASES.md](PHASES.md) | The executable roadmap: phases, tasks with IDs, acceptance criteria, verification, and a starter prompt per phase. |
| [JOURNEY.md](JOURNEY.md) | The customer journey end to end, step by step, with what happens behind each step and where the plan specifies it. |
| [../proposals/](../proposals/README.md) | Product specifications that are not built yet: agent environment, web research. |

## Rules for Claude Code sessions executing this plan

1. **Read before acting:** `VISION.md` (including Amendment 3 once issued), `AGENTS.md`, `CLAUDE.md`,
   [DECISIONS.md](DECISIONS.md), then the phase in [PHASES.md](PHASES.md). If Amendment 3 is not yet in
   `VISION.md`, stop and tell the owner; do not implement.
2. **A decision marked `Proposed` that the task depends on is not yours to settle.** Ask the owner, then record the
   answer in DECISIONS.md in the same pull request.
3. **Never touch the invisible safety core** (VISION §6): `ExecutionService.execute`, the trading journal, idempotency,
   reconciliation, preflight checks, send serialization, exact approval, run integrity, provenance. Instance-side
   changes in Phase 1 are additive, read-only towards trading, and off unless their setting is present.
4. **The control plane never enters the Lonora image.** It lives in its own repository (D2). The Lonora `Dockerfile`
   copies `packages/` whole, so control-plane code must not be added under `packages/` here.
5. **Zero access is a feature:** no task may give the control plane a way to sign in as an owner, read instance secrets,
   chats, memory, broker data or model keys, or place, modify, close or cancel an order. The one broker action the
   control plane takes is the MetaApi connection lifecycle by `broker-provisioner` (create, deploy, undeploy, update,
   remove, narrowed tokens), under PLAN §3.8 and Amendment 3 §10; it must never gain a path to trading hosts or store a
   broker password.
6. **One task family per branch and pull request**, titled `cloud(P<phase>-T<n>): …`, based on the latest `main`
   (AGENTS.md). Tests ship with the change. In this repository run `bash scripts/build.sh` and the affected test suites;
   in `lonora-cloud` run its `make check`.
7. **No secrets in either repository.** Staging uses provider test modes, a separate cloud project and test domains.
8. **Arabic and right-to-left first** for every customer-facing and staff-facing screen and email (VISION §17).
9. **Find code with the map:** `floorplan/architecture.json` and `floorplan/descriptions/` describe every module and
   file; regenerate the viewer with the floorplan plugin. The map can lag recent edits, so confirm in the code.
10. **Verification without CI:** while GitHub Actions is down (P0-T10), run the local checks of PHASES.md (definition of
    done, item 8), list them in the pull request, and push to `main` only with the owner's explicit permission.
