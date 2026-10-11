# Lonora — ملف تعريف المشروع

![Project](https://img.shields.io/badge/Project-Lonora-111827?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active%20Development-2563eb?style=for-the-badge)
![Backend](https://img.shields.io/badge/Backend-Python%203.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![API](https://img.shields.io/badge/API-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Database](https://img.shields.io/badge/Database-PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Web](https://img.shields.io/badge/Web-React%20%2B%20TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![RTL](https://img.shields.io/badge/Arabic-RTL%20First-7c3aed?style=for-the-badge)

---

# 1. اسم المشروع

**Lonora**

الاسم الرسمي للنظام والمنتج هو:

> **Lonora**

Lonora ليس اسم Agent واحد، بل اسم النظام كاملًا.

---

# 2. تعريف المشروع

**Lonora** هو نظام وكلاء ذكاء اصطناعي دائمين يعملون على مدار الساعة، مبني على نفس فلسفة الوكيل المقيم والدائم التي نراها في أنظمة مثل Grok Bot، لكن مع تركيز قوي على السوق والتداول.

Lonora لا يعمل كبوت محادثة مؤقت.

الوكيل داخل Lonora يستطيع أن:

- يتذكر.
- يحتفظ بسياق طويل الأمد.
- يعمل في الخلفية.
- ينفذ مهام مجدولة.
- يراقب السوق.
- يستخدم أدوات.
- يتعاون مع وكلاء آخرين.
- يستخدم Subagents.
- يتواصل صوتيًا مع المستخدم.
- يحلل الأسواق.
- يقرأ الحساب.
- ينفذ عمليات تداول عندما يكون التداول مفعّلًا.
- يستمر في العمل حتى عند إغلاق المتصفح.
- يتعافى من إعادة تشغيل الخادم أو Worker.

---

# 3. الأصل المعماري

Lonora مبني على فلسفة وبنية **Rakazo**.

المصدر المرجعي:

```text
https://github.com/elie222/rakazo
```

النسخة المرجعية المثبتة:

```text
2d666c4e98db201c1f7988e09e76a52db20cea69
```

يتم استخدام Rakazo كمصدر فعلي للتحويل:

```text
Rakazo file
→ قراءة الملف
→ قراءة dependencies
→ قراءة tests
→ فهم السلوك
→ تحويله إلى Lonora
```

Backend المطلوب يتم تحويله إلى Python.

أما Web فيبقى React/TypeScript ويتم نسخه وتعديله بدل إعادة بنائه من الصفر.

---

# 4. التطبيقات الحالية

```text
apps/
├── api/       Python
├── worker/    Python
└── web/       React / TypeScript
```

المؤجل حاليًا:

```text
apps/desktop/  DEFERRED
apps/mobile/   DEFERRED
apps/www/      يمكن تأجيله إذا بقي موقعًا تسويقيًا فقط
```

---

# 5. حزمة التقنية

## Backend

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Durable%20State-4169E1?logo=postgresql&logoColor=white)

المكونات:

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy 2 async
- Alembic
- PostgreSQL
- asyncio
- httpx
- pytest
- Ruff
- Pyright strict

## Frontend

![React](https://img.shields.io/badge/React-Web-61DAFB?logo=react&logoColor=111827)
![TypeScript](https://img.shields.io/badge/TypeScript-Web-3178C6?logo=typescript&logoColor=white)

واجهة Web مستمدة من Rakazo وتحافظ على نفس فلسفة التصميم والتفاعل.

---

# 6. مزودو الذكاء الاصطناعي

المزودون المتفق عليهم:

![OpenAI](https://img.shields.io/badge/OpenAI-Supported-111111?logo=openai&logoColor=white)
![Anthropic](https://img.shields.io/badge/Anthropic-Supported-d97757)
![DeepSeek](https://img.shields.io/badge/DeepSeek-Supported-4D6BFE)
![Z.ai](https://img.shields.io/badge/Z.ai-Supported-7c3aed)
![OpenRouter](https://img.shields.io/badge/OpenRouter-Supported-6366F1)

1. **OpenAI**
2. **Anthropic / Claude**
3. **DeepSeek**
4. **Z.ai**
5. **OpenRouter**

---

# 7. التوجيه العالمي للنماذج

في Lonora إعدادات النماذج **عالمية**.

لا يوجد Model/Provider مستقل لكل Agent أو Routine.

## Unified Mode

اختيار عالمي موحد للمهام المتوافقة.

## Custom Global Routing

يمكن تحديد نموذج عالمي مختلف حسب القدرة:

- Conversation
- Reasoning
- Research
- Vision
- Realtime Voice
- STT
- TTS
- Background Tasks

يمكن للـRun تسجيل النموذج الفعلي الذي نفذ المهمة كـmetadata، لكن هذا لا يتحول إلى إعداد لكل Agent.

---

# 8. اكتشاف النماذج

لا نضع قوائم Models وهمية أو ثابتة بلا تحقق.

القواعد:

- استخدام API رسمي عند توفر model discovery.
- التحقق من capabilities.
- عدم افتراض القدرات من اسم النموذج فقط.
- OpenRouter يعامل كمزود ديناميكي متعدد النماذج.

قدرات النموذج التي يهتم بها النظام:

```text
text
streaming
tools
reasoning
vision
realtime audio
STT
TTS
```

---

# 9. قدرات الوكلاء

كل Agent في Lonora يستطيع، بحسب الأدوات والصلاحيات:

1. محادثات دائمة.
2. سجل رسائل مستمر.
3. Context طويل الأمد.
4. MEMORY.md.
5. Semantic Memory عند توفرها.
6. Scratchpad.
7. Skills.
8. Tools.
9. Background Work.
10. Routines.
11. Steering أثناء التنفيذ.
12. الاستمرار بعد restart.
13. Child Bots.
14. Subagents.
15. Bot-to-Bot Messaging.
16. Outcome Return.
17. Group Chats.
18. Engagement / Silence.
19. Search / Research.
20. Artifacts / Files.
21. Boards / Tickets.
22. Market Monitoring.
23. Market Analysis.
24. Chart Analysis.
25. Account Reading.
26. Positions / Orders.
27. Trading عند السماح.
28. Market Watches.
29. Realtime Voice.
30. استخدام نفس الأدوات عبر النص والصوت.

---

# 10. أدوات الوكلاء

الفئات الأساسية:

1. Memory Tools
2. Skill Tools
3. Routine Tools
4. Search / Research Tools
5. File / Artifact Tools
6. Group / Collaboration Tools
7. MCP / Connector Tools
8. Market Tools
9. Chart Tools
10. Account Tools
11. Trade Tools
12. Watch Tools

---

# 11. الذاكرة

Lonora يفرق بين:

```text
Conversation History
MEMORY.md
Semantic Memory
Scratchpad
History Compaction
```

ولا يتم دمج هذه الطبقات في مفهوم واحد.

---

# 12. التعاون بين الوكلاء

هناك فرق بين:

```text
Child Bot
Subagent
Bot-to-Bot
Group Chat
External Team Chat
```

- **Child Bot:** وكيل دائم له هوية وThread وحالة.
- **Subagent:** تنفيذ فرعي مؤقت.
- **Bot-to-Bot:** وكيل موجود يرسل مهمة لوكيل آخر موجود.
- **Group Chat:** عدة Agents داخل Thread واحد، ولا يجب أن يرد الجميع دائمًا.

---

# 13. التشغيل 24/7

Lonora يعمل من خلال:

```text
PostgreSQL
+
Worker
+
Runs
+
Leases
+
Fences
+
Recovery
+
Routines
+
Watches
+
Durable Events
```

المتصفح ليس Runtime.

---

# 14. Run Lifecycle

الحالات تشمل وفق Runtime المحول:

```text
queued
leased
running
waiting_input
waiting_takeover
completed
failed
cancelled
```

وتستخدم آلية:

```text
lease_owner
lease_fence
lease_expires_at
```

للاستعادة ومنع الكتابات المتأخرة من Worker قديم.

---

# 15. Steering

إذا أرسل المستخدم رسالة أثناء Run نشط، يمكن تحويلها إلى Steering Message بدل إنشاء تنفيذ متنافس بلا ضوابط.

---

# 16. Routines

Routines هي مهام مجدولة تستخدم نفس Agent Runtime.

مثال:

```text
كل يوم الساعة 08:00
→ حلل الذهب
→ راجع الأخبار
→ راجع المراكز
→ أرسل ملخصًا
```

---

# 17. Boards

Boards تبقى جزءًا من Lonora لأنها مرتبطة بـ:

- Web.
- API.
- Worker.
- Tickets.
- أدوات الوكيل.

---

# 18. الصوت

الصوت realtime ويستخدم نفس Agent.

المسار:

```text
WebRTC
→ STT
→ Same Agent
→ Same Context
→ Same Tools
→ LLM
→ TTS
→ WebRTC
```

لا يوجد Voice Agent منفصل.

الاتجاه التقني المتفق عليه:

```text
LiveKit + WebRTC
```

بعد التحقق النهائي من الوثائق والترخيص وقت التنفيذ.

---

# 19. التداول

التداول Capability داخل نفس Agent Framework.

لا يوجد Framework منفصل باسم TradingAgent.

الفئات الأساسية:

```text
Market
Chart
Account
Trade
Watch
```

---

# 20. Broker Layer

يستخدم Lonora Broker-neutral interface.

مفهوميًا:

```text
Lonora
↓
Broker Interface
├── MetaApi Adapter
├── Future Broker Adapter
└── Fake / Demo Broker
```

MetaApi يمكن أن يكون أول Adapter، لكن Core لا يرتبط به بشكل دائم.

---

# 21. قاعدة الرمز الحقيقي

إذا الوسيط يعيد:

```text
XAUUSDm
```

يبقى نفس الرمز في:

- Market
- Chart
- Analysis
- Watch
- Trade
- Position
- Journal

ولا يتم تغييره تلقائيًا إلى `XAUUSD`.

---

# 22. تحليل السوق

يمكن للوكيل جمع:

1. Quote.
2. Candles.
3. Multi-timeframe data.
4. Indicators.
5. Market structure.
6. Account state.
7. Positions.
8. Orders.
9. News.
10. Economic calendar.
11. Memory.
12. Outcomes من Agents آخرين.

ثم يستخدم Model Router للاستدلال.

---

# 23. Charts

Chart ليس مجرد Component داخل المتصفح.

يجب أن توجد Market/Chart state على الخادم حتى يستطيع Agent العمل والمتصفح مغلق.

يمكن استخدام:

```text
TradingView Lightweight Charts
```

كـWeb renderer إذا بقي مناسبًا عند التحقق النهائي.

---

# 24. Trading Controls

المتفق عليه:

```text
Trading OFF
Trading ON
Emergency Stop
```

وتطبق server-side.

---

# 25. لا يوجد Risk Engine معقد إلزامي

لا نضيف تلقائيًا:

- Manager Agent.
- Risk Agent.
- Mandates.
- Per-trade approval.
- Allocation workflows معقدة.

إلا إذا طُلب ذلك لاحقًا.

---

# 26. تنفيذ الصفقة

```text
Agent
↓
Trade Tool
↓
Validation
↓
Trading Control
↓
Execution Service
↓
Idempotency
↓
Broker Adapter
↓
Broker
↓
Trading Journal
↓
Reconciliation
↓
Tool Result
↓
Agent
```

---

# 27. منع التكرار

كل عملية مالية تحتاج:

- Operation ID.
- Idempotency.
- Durable Journal.
- Reconciliation.
- Duplicate protection.

عند Timeout:

```text
Ambiguous
→ Reconcile
→ فحص حالة الوسيط
→ تحديد النتيجة الحقيقية
```

ولا تتم إعادة الصفقة عميانيًا.

---

# 28. Market Watches

Watches:

- تعمل والمتصفح مغلق.
- تحفظ في PostgreSQL.
- تستمر بعد restart.
- تستخدم نفس Worker.
- توقظ نفس Agent Runtime.

---

# 29. Voice + Trading

الصوت يستخدم نفس Trade Tools.

```text
Voice
→ Transcript
→ Same Agent
→ Trade Tool
→ Trading ON/OFF
→ Validation
→ Broker
→ Journal
```

لا يوجد مسار تداول خاص بالصوت.

---

# 30. واجهة المستخدم

واجهة Lonora تحافظ على فلسفة Rakazo Web.

الأقسام الأساسية حسب scope النهائي:

- Agents
- Conversations
- Groups
- Search
- Boards
- Routines
- Memory
- Artifacts
- Settings
- Market / Charts
- Trading
- Activity

---

# 31. إنشاء Agent

إنشاء Agent يبقى بسيطًا:

```text
Name
Avatar
Shape / Style
Color
Create
```

ولا نضع داخله:

- Provider
- Model
- Broker
- Risk configuration

---

# 32. العربية

العربية هي اللغة الأولى.

المتطلبات:

- RTL كامل.
- قابلية إضافة لغات أخرى.
- لا يوجد Human-facing text ثابت في Components.

النصوص التقنية مثل:

```text
XAUUSDm
BTCUSD
0.10
model IDs
URLs
```

يجب أن تبقى صحيحة باستخدام bidi isolation.

---

# 33. ممنوع النصوص الثابتة

قاعدة مطلقة.

لا نضع user-facing strings ثابتة في:

- Buttons
- Menus
- Placeholders
- Errors
- Notifications
- Voice UI
- Chart UI
- Trading UI
- Accessibility labels

Backend يعيد machine-readable codes، والـFrontend يترجمها.

---

# 34. الأمان

الأسرار تبقى server-side:

- AI Provider keys.
- Broker credentials.
- MCP secrets.
- Integration secrets.

الـModel يرى Tool Interface فقط ولا يرى الأسرار.

---

# 35. Authentication

Single-owner لا يعني No Authentication.

APIs والـWebSocket والملفات والصوت والتداول تحتاج حماية حقيقية.

---

# 36. قاعدة البيانات

PostgreSQL هي Durable Source of Truth.

ومن الكيانات المتوقعة حسب الميزات المحتفظ بها:

```text
Bots
Threads
Messages
Runs
SteeringMessages
MemoryDocuments
ScratchpadItems
AgentSkills
Routines
Groups
Boards
Events
Artifacts
Watches
TradingAccounts
TradingJournal
GlobalSettings
```

---

# 37. تدفق التنفيذ العام

```text
User
↓
Web
↓
API
↓
Thread / Message
↓
Run
↓
Worker
↓
Lease + Fence
↓
Context Assembly
↓
Global Model Router
↓
Model
↓
Tool Calls
↓
Tool Results
↓
Model
↓
Assistant Message
↓
Durable Event
↓
Web / Voice
```

---

# 38. الشارات المختصرة للمشروع

![Persistent Agents](https://img.shields.io/badge/Agents-Persistent-0f766e)
![24x7](https://img.shields.io/badge/Runtime-24x7-16a34a)
![Memory](https://img.shields.io/badge/Memory-Durable-7c3aed)
![Voice](https://img.shields.io/badge/Voice-WebRTC-0284c7)
![Trading](https://img.shields.io/badge/Trading-Agent%20Capability-f59e0b)
![Global Routing](https://img.shields.io/badge/Models-Global%20Routing-db2777)
![Arabic](https://img.shields.io/badge/UI-Arabic%20RTL-9333ea)
![Broker Neutral](https://img.shields.io/badge/Broker-Neutral-334155)
![PostgreSQL](https://img.shields.io/badge/State-PostgreSQL-4169E1)

---

# 39. الرؤية النهائية

> **Lonora هو نظام وكلاء ذكاء اصطناعي دائمين يعملون على مدار الساعة، مبني على إطار وفلسفة Rakazo ومخصص بقوة للسوق والتداول، بحيث يستطيع كل وكيل التذكر، التحليل، استخدام الأدوات، التعاون، العمل في الخلفية، مراقبة السوق، التواصل صوتيًا، والوصول إلى التداول من خلال طبقة تنفيذ آمنة، مع بقاء النموذج والمزود قابلين للتغيير عالميًا دون تغيير هوية الوكيل.**

الهدف ليس بناء:

> منصة تداول مع شات.

بل بناء:

> **فريق وكلاء دائم يعيش داخل السوق ويعمل مع المستخدم باستمرار.**
