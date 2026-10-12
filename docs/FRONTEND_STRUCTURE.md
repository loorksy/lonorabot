# بنية واجهة Lonora

تُنظم واجهة Lonora على حدود ملفات Tampletgrok: صفحات مساحة العمل، ملفات `pages/shell`، مكونات عرض عمل الوكلاء، مكونات المكالمات، تطبيق Expo Router، وحزم TypeScript مشتركة. المرجع المثبت هو `loorksy/Tampletgrok` عند `20fc9ac862bb833d1578968a7aba5ea18ff88a29`.

الشجرة ليست معيار المنتج؛ معيار Lonora هو تجربة محادثة لوكلاء تداول دائمين. راجعت كذلك Rakazo عند `48f26b19b9a9b0daef81b047700c766ebf172fec`؛ يصف نفسه كبديل مفتوح المصدر لـGrok Bot. نأخذ استمرارية الوكيل وبساطة هويته والذاكرة والمهام والمجموعات، ونربطها بسوق وأوامر وحساب تداول حقيقية عبر Python. لا تعني هذه المقارنة ادعاء تطابق كامل مع منتج مغلق.

هذه خريطة الملفات ووظائفها. يكون الملف جزءًا من البنية عندما يستخدمه التطبيق ويؤدي وظيفة حقيقية عبر Lonora API أو يعالج عرض بياناته. تُحفظ تفاصيل اختبار ما نُفذ في نتائج البناء واختبارات المتصفح؛ وجود المسار وحده لا يثبت اكتمال الميزة.

## حدود الواجهة المنفذة

```text
apps/
├── web/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── theme.overrides.css
│       ├── styles.css
│       ├── i18n/
│       │   ├── config.ts
│       │   ├── direction.ts
│       │   └── locales/{ar,en}/messages.po
│       ├── pages/
│       │   ├── Shell.tsx
│       │   ├── Auth.tsx
│       │   ├── Onboarding.tsx
│       │   ├── ResizableSidePanel.tsx
│       │   ├── Board.tsx
│       │   ├── ActivityList.tsx
│       │   ├── Artifacts.tsx
│       │   ├── SpaceSearch.tsx
│       │   ├── GroupPanel.tsx
│       │   ├── Knowledge.tsx
│       │   ├── KnowledgeSection.tsx
│       │   ├── ScratchpadSection.tsx
│       │   ├── Routines.tsx
│       │   ├── RoutineEditor.tsx
│       │   ├── RoutineSchedule.tsx
│       │   ├── RoutineRunHistory.tsx
│       │   ├── LocalSettings.tsx
│       │   ├── ModelSettingsOverlay.tsx
│       │   ├── VoiceSettingsOverlay.tsx
│       │   ├── McpServersOverlay.tsx
│       │   ├── TradingSettingsPanel.tsx
│       │   ├── UsageSettingsPanel.tsx
│       │   ├── SettingsOverlay.tsx
│       │   ├── Market.tsx
│       │   ├── Trading.tsx
│       │   └── shell/
│       │       ├── bot-panel.tsx
│       │       ├── bot-settings.tsx
│       │       ├── bot-picker.tsx
│       │       ├── bot-roster-row.tsx
│       │       ├── command-palette.tsx
│       │       ├── chat-context.tsx
│       │       ├── shell.css
│       │       ├── chat-context.css
│       │       └── message-cards.tsx
│       ├── components/
│       │   ├── ai/
│       │   │   ├── primitives.tsx
│       │   │   └── CollaborationMarker.tsx
│       │   ├── call/
│       │   │   ├── CallCard.tsx
│       │   │   ├── VoiceChatCard.tsx
│       │   │   ├── RealtimeVoice.tsx
│       │   │   ├── Transcript.tsx
│       │   │   └── VoiceStatus.tsx
│       │   ├── integrations/
│       │   │   └── IntegrationSetup.tsx
│       │   ├── ArtifactFileCard.tsx
│       │   ├── ToolActivityDisclosure.tsx
│       │   ├── ErrorBoundary.tsx
│       │   ├── PdfViewer.tsx
│       │   ├── SandboxedHtmlViewer.tsx
│       │   ├── charts/          # مخططات السوق وحالتها المرتبطة بالخادم
│       │   ├── market/          # أسعار ورموز وتقويم ومراقبات
│       │   └── trading/         # الحساب والمراكز والأوامر والسجل والضوابط
│       ├── hooks/               # جلب البيانات والأحداث والجلسة والتنقل
│       ├── lib/                 # عملاء API وربط الواجهة، دون تكرار عقود البيانات
│       └── providers/
│           └── ClientProvider.tsx
└── mobile/
    ├── package.json
    ├── app.config.ts
    ├── tsconfig.json
    ├── app/
    │   ├── _layout.tsx
    │   ├── +not-found.tsx
    │   ├── index.tsx
    │   ├── sign-in.tsx
    │   ├── thread.tsx
    │   ├── group-thread.tsx
    │   ├── bot-settings.tsx
    │   ├── group-settings.tsx
    │   ├── new.tsx
    │   ├── new-group.tsx
    │   ├── artifacts.tsx
    │   ├── artifact.tsx
    │   ├── image.tsx
    │   ├── routine.tsx
    │   ├── server.tsx
    │   ├── settings.tsx        # مدخل التنقل إلى صفحات إعدادات النظام
    │   └── (settings)/
    │       ├── _layout.tsx
    │       ├── account.tsx
    │       ├── models.tsx
    │       ├── integrations.tsx
    │       └── voice.tsx
    ├── components/
    │   ├── bot-avatar.tsx
    │   ├── group-avatar.tsx
    │   ├── sheet-header.tsx
    │   ├── settings-group.tsx
    │   ├── thread-composer.tsx
    │   ├── time-separator.tsx
    │   ├── WorkingIndicator.tsx
    │   ├── message-bubble.tsx
    │   ├── conversation-row.tsx
    │   └── ui.tsx
    └── lib/
        ├── api.ts
        ├── session.tsx
        ├── storage.ts
        ├── i18n.ts
        ├── agents.ts
        ├── groups.ts
        ├── routine.ts
        └── artifacts.ts

packages/
├── contracts/
│   ├── package.json           # @lonora/contracts: عقود Web وExpo
│   ├── tsconfig.json
│   ├── pyproject.toml         # عقود Python مستقلة عن تصدير TypeScript
│   └── src/
│       ├── index.ts
│       ├── domain.ts          # تعريفات البيانات المشتركة للعملاء
│       ├── auth.ts
│       ├── runs.ts
│       ├── events.ts
│       ├── models.ts
│       ├── trading.ts
│       └── lonora_contracts/  # عقود الخادم الموجودة
├── core/
│   ├── package.json           # @lonora/core: منطق العرض المشترك
│   ├── tsconfig.json
│   ├── pyproject.toml
│   └── src/
│       ├── index.ts
│       ├── run-state.ts
│       ├── composer-mentions.ts
│       ├── attachments.ts
│       ├── user-error.ts
│       └── lonora_core/       # منطق Python الموجود
├── ui-tokens/
│   └── src/{brand,index,appearance,generate-css}.ts
├── ui-web/
│   └── src/                  # الهوية والمكونات الأساسية المشتركة للويب
└── chat-ui/
    └── src/                  # Markdown وعرض الجداول والروابط

tests/
└── web/workspace.spec.mjs
```

تعرض الشجرة حدود الوحدات الأساسية. تضاف ملفات TypeScript داخل `contracts/src` و`core/src` عند فصل عقود أو وظائف مشتركة فعلية، وتصدر من `index.ts`. تبقى ملفات Python الحالية في `src/lonora_contracts` و`src/lonora_core` بأسمائها ووظائفها؛ لا تستبدلها عملية نقل الواجهة.

## مسؤولية الملفات ونقل السلوك

| الموقع | الوظيفة التي يجب أن يحملها |
| --- | --- |
| `pages/Shell.tsx` | تنسيق القائمة والمحادثة ولوحة السياق والمسارات؛ اختيار آخر سياق صالح؛ الرجوع والتركيز وإعدادات النظام |
| `pages/shell/bot-panel.tsx` | نموذج إنشاء الوكيل عبر API؛ نقل التنفيذ الموجود مع بساطة الاسم والصورة واللون |
| `pages/shell/bot-settings.tsx` | تعديل هوية الوكيل وتعليماته وإيقافه؛ حفظ حقيقي وإغلاق لوحة السياق وتفضيلها بصورة متسقة |
| `pages/shell/bot-picker.tsx` | قائمة «إلى»: بحث عن وكيل موجود أو إنشاء وكيل أو مجموعة؛ إزالة المكون السابق بعد نقل استعمالاته |
| `pages/shell/bot-roster-row.tsx` | صف القائمة بهوية وحالة حقيقية وإجراءات قابلة للوصول باللمس والكيبورد |
| `pages/shell/command-palette.tsx` | البحث والتبديل بين الوكلاء واختصار `Ctrl/Cmd+K` |
| `pages/shell/chat-context.tsx` | تنفيذ مساحة المحادثة وComposer وTranscript؛ إرسال الرسائل والمرفقات وSteering والإلغاء وعرض السجل |
| `pages/shell/message-cards.tsx` | عرض الرسائل والمرفقات والتعاون والتنبيه إلى الاستعادة؛ تركيب مكونات الأحداث الفعلية |
| `components/ai/primitives.tsx` | عرض حالة التنفيذ والعمل الجاري والتحميل؛ يعتمد على حالة Run وأحداثه |
| `components/ai/CollaborationMarker.tsx` | إظهار التنفيذ الفرعي والتعاون مع الفصل بين Child Bot وSubagent وPeer |
| `components/ToolActivityDisclosure.tsx` | المصدر الوحيد لعرض مجموعات خطوات الأدوات ونتائجها والفشل والإلغاء؛ تستخدمه المحادثة بدل تكرار التجميع |
| `components/call` | جلسة WebRTC وGPT-Live ونص الصوت وحالته وبطاقته؛ نفس الوكيل وThread والأدوات |
| `components/integrations/IntegrationSetup.tsx` | إعداد التكاملات الموجودة وحفظ أسرارها على الخادم؛ لا ينشئ محاكاة OAuth أو نجاحًا محليًا |
| `pages/Board.tsx` و`ActivityList.tsx` | فصل واجهة Tickets عن سجل Runs؛ تبقى خدمة البيانات مشتركة إذا احتاجت الشاشتان نفس البيانات |
| `pages/SpaceSearch.tsx` | بحث Lonora الحقيقي وروابط نتائج تفتح الوكيل أو Thread أو المعرفة؛ الاسم يطابق حد البحث في القالب |
| `pages/KnowledgeSection.tsx` | `MEMORY.md` والمعرفة الدلالية الاختيارية؛ تحميل وحفظ ونسخ مستقلة عن سجل الرسائل |
| `pages/ScratchpadSection.tsx` | الملاحظات والمهارات المشتركة في تحرير الموارد ذي النسخ، عبر `/scratchpad` و`/skills`؛ إضافة العناصر وتعديلها أو حذفها عبر تخزين الخادم |
| `pages/RoutineEditor.tsx` و`RoutineSchedule.tsx` و`RoutineRunHistory.tsx` | فصل التحرير والجدولة والمنطقة الزمنية عن نتائج تشغيل Routine الفعلية |
| `pages/GroupPanel.tsx` | إنشاء المجموعة وتعديل الاسم والأعضاء وسياسة المشاركة؛ المحادثة تستخدم Thread المجموعة |
| `pages/SettingsOverlay.tsx` | الإعدادات العالمية داخل حوار النظام؛ التوجيه والنماذج والصوت والتكاملات والتداول والاستخدام |
| `components/ArtifactFileCard.tsx` وعوارض الملفات | صفوف وبطاقات ملفات حقيقية؛ معاينة الصور وPDF وHTML المعزول؛ عرض هاتف قابل للاستخدام |
| `mobile/app/thread.tsx` و`group-thread.tsx` | مساران مفهومان للمحادثة الفردية والمجموعة، يركبان عميل الرسائل نفسه مع سياسة العضوية والذكر المناسبة |
| `mobile/app/bot-settings.tsx` و`group-settings.tsx` | نماذج أصلية لتحرير الكيان المحدد، وليست روابط عامة أو بيانات تجريبية |
| `mobile/app/artifacts.tsx` و`artifact.tsx` و`image.tsx` | قائمة الملفات وتفاصيل الملف وعرض الصورة؛ تنزيل أو مشاركة عند توفر واجهة المنصة |
| `mobile/app/routine.tsx` | قراءة المهمة وجدولها وحالتها وسجلها وربط التعديل أو التشغيل بالقدرة التي يدعمها API |
| `mobile/app/server.tsx` | إدارة عنوان خادم Lonora والتحقق منه وعلاقته بالجلسة؛ تمنع بقاء بيانات جلسة خادم سابق |
| `mobile/app/(settings)` | صفحات إعدادات النظام العالمية؛ تعرض بيانات API وتتجنب اختيار نموذج مستقل للوكيل |
| `contracts/src/domain.ts` و`auth.ts` | سجلات الكيانات والرسائل والملفات والجلسة المشتركة بين عملاء Web وExpo، بأسماء حقول JSON التي يعيدها الخادم |
| `contracts/src/runs.ts` و`events.ts` | حالات التنفيذ وسجل Run وعقود الأحداث الدائمة؛ يستخدمها عرض النشاط والمحادثة |
| `contracts/src/models.ts` و`trading.ts` | المزودون المعتمدون والتوجيه العالمي وكتالوج النماذج، وعقود السوق والحساب والتداول بحسب الاستخدام الحقيقي |
| `core/src/run-state.ts` و`composer-mentions.ts` | تفسير حالات Run ومعالجة ذكر الأعضاء بصورة مشتركة؛ لا تنشئ تنفيذًا أو سياسة تداول جديدة |
| `core/src/attachments.ts` و`user-error.ts` | حدود المرفقات وأكواد الأخطاء المشتركة؛ يبقى تحقق الخادم مرجعًا نهائيًا، وتبقى جدولة Cron في Python |
| `ui-tokens/src/brand.ts` | اسم Lonora ومخطط الروابط وهوية التطبيق؛ تستخدمه التطبيقات بدل نسخ ثوابت الهوية في كل شاشة |

يمكن أن يكون ملف المسار صغيرًا عندما يضبط كيانًا أو مسارًا ويركب مكونًا حقيقيًا مشتركًا. يشترط أن يؤدي هذا التركيب وظيفة محددة يمكن اختبارها؛ لا تضاف ملفات فارغة أو ملفات تعيد تصدير اسم قديم فقط لإكمال الرسم.

## طريقة النقل

1. نقل تطبيقات المكونات إلى حدودها الجديدة وتحديث جميع الاستيرادات. حذف النسخة السابقة بعد التأكد من استخدام النسخة المنقولة.
2. فصل أجزاء صفحات النشاط والمعرفة والروتين إلى وحدات القالب، مع بقاء المعاملات ونسخ البيانات والأخطاء الحقيقية في الوظيفة المنقولة.
3. استخراج عقود TypeScript المشتركة من `web/lib/api.ts` و`mobile/lib/types.ts` إلى `@lonora/contracts`، وإبقاء عملاء HTTP والجلسة خاصين بمنصتهم.
4. نقل الوظائف المشتركة المستعملة فعلًا إلى `@lonora/core` وربط مستهلكيها في Web وExpo؛ تسجل اختبارات هذه الوظائف سلوكًا له معنى، مثل ترتيب الرسائل أو حدود المرفقات.
5. نقل هوية المنتج إلى `brand.ts` وتطبيقها على إعداد Expo وعناوين Web ومفاتيح التشغيل، مع حفظ النسب القانوني في ملفات الترخيص.
6. بناء Web وحزم TypeScript وExpo، ثم تشغيل اختبارات API والمتصفح والتنقل الأصلية المتاحة. تبقى واجهات السوق والتداول إضافات Lonora بجانب بنية القالب.

## حدود الوظائف في الشجرة

| مسارات القالب | قرار Lonora |
| --- | --- |
| `computer`, `terminal`, `teach-computer` وأوامر الجهاز | لا تدخل الشجرة؛ عمل الوكيل المقيم هنا معرفة وروتين وسوق وتداول، وفق الرؤية الحالية |
| `BillingSettingsPanel`, `Paywall`, الاشتراك وSSO والتسجيل العام | لا تدخل تطبيق Single-owner؛ يبقى الدخول والإعداد الأول والجلسة الفعلية |
| `new-space`, مساحات Private/Team، إعداد مشاركة بيانات الذكاء الاصطناعي الخاص بالقالب | لا تضاف من دون نموذج خدمة وتخزين ومتطلبات Lonora لها |
| `archived-bots` وإجراءات التثبيت والأقسام أو تغيير كلمة المرور التي لا يوفرها API الحالي | تضاف عندما توجد خدمة دائمة فعلية لها، مع عقود واختبارات؛ لا تظهر كإجراء ناجح يحفظ محليًا فقط |
| `packages/mock-adapters` | لا يدخل مسار التشغيل؛ كل شاشة تتصل ببيانات Lonora |
| وحدة Notifications أصلية باسم سابق ومفاتيحها | لا تنقل؛ أي إشعارات أصلية تحتاج وحدة Lonora قابلة للبناء وخدمة تشغيل حقيقية |
| `mobile/(settings)/voice` | يمكنها قراءة إعداد وحالة صوت الخادم؛ لا تعد مكالمة Native جاهزة قبل دمج SDK واختبار الصوت على جهاز |
| ملفات اختبارات القالب | تُنقل الاختبارات المناسبة لسلوك احتُفظ به بعد تعديل عقوده؛ لا تُنسخ مئات الاختبارات غير المتصلة بقدرات Lonora |

## التحقق من المطابقة

- كل صفحة في الشجرة تصل إليها واجهة أو مسار فعلي، وتعرض حالات تحميل وفراغ وفشل ونجاح مناسبة.
- تطابق Web وExpo على أنواع البيانات المشتركة، مع بقاء Cookie وCSRF للمتصفح وSecureStore للجلسة الأصلية.
- لا توجد نسختان فعالتان من Composer أو رسالة أو تجميع أدوات أو إعداد كيان بعد النقل.
- تبقى المحادثات والملفات والمهام الموجودة محفوظة، وتبقى النماذج عالمية وتشغيل الوكلاء على الخادم.
- يثبت اختبار المتصفح إنشاء الوكيل وTickets والمحادثة والإلغاء والرجوع وRTL وعرض 800px و390px، وتوضح نتائج Expo المنصات التي جرى تشغيلها فعلًا.

## وظائف تداول Lonora وما استُلهم من المرجع

| فلسفة الواجهة | التكييف لوكيل التداول |
| --- | --- |
| محادثة دائمة وهوية مستقلة | Thread مستمر وملف تعليمات وذاكرة لكل وكيل تداول؛ الإنشاء بالاسم والصورة واللون |
| Routines وسجل العمل | مراجعات السوق والمراكز المجدولة، سجل تشغيل فعلي، تعديل الجدولة وإيقافها |
| Skills وScratchpad | قوائم فحص تداول ومعرفة وملاحظات محفوظة ومعاملات تعديل ذات نسخ |
| عمل فريق من الوكلاء | مجموعات بإشارات الأعضاء، تنفيذ فرعي وتعاون يُعرض من Run والأحداث الفعلية |
| ملفات ومخرجات في المحادثة | تقارير وصور ومرفقات قابلة للمعاينة والتنزيل، دون مساحة كمبيوتر |
| لوحة السياق | روابط إلى السوق والمخططات، حساب الوسيط والمراكز والأوامر وسجل العمليات |
| إعدادات النظام | توجيه نموذج عالمي، اتصالات وسيط، التداول OFF/ON والإيقاف الطارئ من الخادم |

صفحات Native للنماذج والتكاملات والصوت تقرأ حالة الخادم، وتحيل تعديل الاتصال والمكالمات إلى Web. تعديل الوكيل والذاكرة والمجموعة والمهام المجدولة وعرض الملفات يعمل في Expo نفسه. بنية القالب لا تقتضي تفعيل مساحات أو حوسبة سحابية أو أدوات برمجة.

## التحقق المحفوظ في المستودع

- `bash scripts/build.sh`: Ruff وPyright وBiome وأنواع الحزم السبع، بناء Web، وتصدير Expo Web/iOS/Android.
- `pnpm test:web`: خمسة سيناريوهات فعلية على PostgreSQL، تشمل المحادثة والرجوع وRTL وTickets وإعادة إرسال نفس القصد والمهارات والمهام المجدولة.
- `pnpm test:mobile`: سيناريو Expo Web متكامل للهوية والذاكرة والجدولة وسجلها والمجموعات والملفات والتنزيل والجلسة والإعدادات واللغتين.
- `tests/check_clients.py`: أحد عشر تحققًا للجلسة الأصلية وCookie/CSRF والمحادثة الدائمة وإنشاء واحد تحت التزامن.

اختبار Expo هنا يعمل في Chromium على تصدير Web. تُصدّر حزم iOS/Android بنجاح، لكن التشغيل على جهاز أصلي والتوقيع وSecureStore والمشاركة الأصلية تحتاج بيئة Android SDK/Xcode واختبار جهاز. اتصال مزود نموذج أو وسيط فعلي يحتاج مفاتيح المالك، ولا تثبته هذه الاختبارات.
