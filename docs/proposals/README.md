# Proposals

Specifications of behaviour that is **not built yet**. Each is `Proposed` until the owner approves it; documents in
`docs/` describe the system as built (VISION §0.4), these describe what would be built. When a proposal ships, its
behaviour is documented in `docs/` in the same change and the proposal is marked "Shipped".

## ملخص بالعربية

| المواصفة | ماذا تضيف | أهم ما فيها |
|---|---|---|
| [crypto-door-adapter.md](crypto-door-adapter.md) | الكريبتو (Binance أولاً: Spot ثم العقود الدائمة) عبر **باب التنفيذ** بكل ضماناته | معرّف أمر مشتق من رقم العملية + مطابقة بلا إعادة إرسال؛ ملكية المراكز بقاعدة الحساب الصافي؛ لا يوجد أي كود للسحب أو التحويل؛ شهادة لكل منصة على شبكة الاختبار قبل تفعيلها |
| [agent-environment.md](agent-environment.md) | وكيل Lonora بفلسفة Claude Code: «يتصل بأي شيء ويفعل أي شيء» | Lonora يطابق Claude Code أصلاً في معظم الأدوات ويتقدّم عليه في المهام والذاكرة والجدولة والأسرار؛ أربع فجوات: تعديل الملفات بدقة، أدوات MCP كأدوات أصلية، الوصول لأي خادم بإذن المالك، وإكمال أوامر التداول في CLI |
| [owner-cli.md](owner-cli.md) | تطبيق طرفية للمالك على أسلوب nanobot (`lonora`) | محادثات حيّة، البطاقات الثابتة، أوامر نصية بـ`--json`؛ دخول بموافقة من المتصفح؛ الموافقة على الصفقات تفاعلية فقط |

**حقيقة مهمة:** أوامر التداول في الـCLI داخل مساحة العمل (`trade`، `close`، `modify`، `cancel`) **غير مبنية بعد**، مع أن
VISION §7.3 تفرضها. إكمالها هو الخطوة الأولى المشتركة بين المواصفات الثلاث.

## Order of work

1. Workspace CLI order commands (VISION §7.3) — shared prerequisite (crypto E0, agent G4, owner CLI §9).
2. Crypto door adapter E1–E4 and the agent environment gaps, in parallel.
3. Owner CLI C0–C5.
