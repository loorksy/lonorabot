# Proposals

Specifications of behaviour that is **not built yet**. Each is `Proposed` until the owner approves it; documents in
`docs/` describe the system as built (VISION §0.4), these describe what would be built. When a proposal ships, its
behaviour is documented in `docs/` in the same change and the proposal is marked "Shipped".

## ملخص بالعربية

| المواصفة | ماذا تضيف | أهم ما فيها |
|---|---|---|
| [agent-environment.md](agent-environment.md) | وكيل Lonora بفلسفة Claude Code: «يتصل بأي شيء ويفعل أي شيء» | Lonora يطابق Claude Code أصلاً في معظم الأدوات ويتقدّم عليه في المهام والذاكرة والجدولة والأسرار؛ أربع فجوات: تعديل الملفات بدقة، أدوات MCP كأدوات أصلية، الوصول لأي خادم بإذن المالك، وإكمال أوامر التداول في CLI |

**حقيقة مهمة:** أوامر التداول في الـCLI داخل مساحة العمل (`trade`، `close`، `modify`، `cancel`) **غير مبنية بعد**، مع أن
VISION §7.3 تفرضها. إكمالها هو الخطوة الأولى.

## Order of work

1. Workspace CLI order commands (VISION §7.3) — gap G4.
2. The other agent environment gaps (G1, G2, G3, G5).
