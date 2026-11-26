# Proposals

Specifications of behaviour that is **not built yet**. Each is `Proposed` until the owner approves it; documents in
`docs/` describe the system as built (VISION §0.4), these describe what would be built. When a proposal ships, its
behaviour is documented in `docs/` in the same change and the proposal is marked "Shipped".

## ملخص بالعربية

| المواصفة | ماذا تضيف | أهم ما فيها |
|---|---|---|
| [agent-environment.md](agent-environment.md) | وكيل Lonora بفلسفة Claude Code: «يتصل بأي شيء ويفعل أي شيء» | Lonora يطابق Claude Code أصلاً في معظم الأدوات ويتقدّم عليه في المهام والذاكرة والجدولة والأسرار؛ أربع فجوات: تعديل الملفات بدقة، أدوات MCP كأدوات أصلية، الوصول لأي خادم بإذن المالك، وإكمال أوامر التداول في CLI |
| [web-research.md](web-research.md) | بحث الوكيل في الإنترنت: **هجين** كما يفعل الوكلاء العالميون | البحث المدمج لدى المزوّد أولاً (Anthropic ثم DeepSeek ثم OpenAI) مع تعليم المحتوى كخارجي وحفظ المصادر وعرض تكلفته؛ احتياطياً SearXNG + GDELT للأخبار (مجاني)؛ قراءة صفحات أفضل (تحويلات، محتوى رئيسي، PDF) |
| [mcp-oauth.md](mcp-oauth.md) | ربط خوادم MCP التي تتطلب **تسجيل الدخول بـ OAuth** (D45، مؤكد) | بطاقة «تسجيل الدخول» في المحادثة تفتح صفحة المزوّد؛ Lonora لا يرى كلمة المرور؛ الرموز مشفّرة عند المالك وتُجدَّد تلقائياً؛ تسجيل الدخول ليس ثقة (الثقة تبقى برسالة المالك)؛ كل نسخة عميل تطبيق OAuth مستقل والشركة لا ترى أي رمز؛ ودعم إصدار MCP الجديد عديم الحالة |
| [model-catalog-and-chatgpt-signin.md](model-catalog-and-chatgpt-signin.md) | قائمة نماذج **ثابتة** هي قائمة rakazo، و**تسجيل الدخول بـ ChatGPT** (التعديل 4، مؤكد) | لا يُقرأ أي كتالوج من المزوّد إلا خادم المالك؛ OpenAI عبر Responses API؛ اشتراك ChatGPT بالطريق الرسمي فقط (لا معرّف Codex)؛ لا اشتراك Claude لأن Anthropic تمنعه؛ Lonora Cloud بمفاتيح فقط حتى توافق OpenAI |

**حقيقة مهمة:** أوامر التداول في الـCLI داخل مساحة العمل (`trade`، `close`، `modify`، `cancel`) **غير مبنية بعد**، مع أن
VISION §7.3 تفرضها. إكمالها هو الخطوة الأولى.

## Order of work

1. Workspace CLI order commands (VISION §7.3) — gap G4.
2. The other agent environment gaps (G1, G2, G3, G5) and web research stages S1–S6 (`web-research.md`).
3. MCP sign-in with OAuth, stages S1–S6 (`mcp-oauth.md`).

| [roadmap-2026-11.md](roadmap-2026-11.md) | الخطة الشاملة بعد دراسة OpenMausBot وrakazo (مؤكدة) | عشر مشاكل يجب إصلاحها أولاً، ثم قدرات جديدة، وقرارات المالك الأربعة عشر |
| [trading-expertise.md](trading-expertise.md) | خبرة التداول **مهاراتٍ للنموذج** بلا أرقام ثابتة (مؤكدة؛ المهارات الـ18 مبنية، TX1 وTX2) | 18 مهارة، ومراجعة كل صفقة ودروس وإحصاءات تُعرض دليلاً لا قاعدة، ولا اختبار تاريخي ولا أقفال |
