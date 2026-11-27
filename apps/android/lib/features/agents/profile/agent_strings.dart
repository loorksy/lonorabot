import '../../../l10n/l10n.dart';

/// Android-only labels of the agent profile, agent settings, agent memory and «ما أعرفه عنك»
/// pages. Lonora's own catalog keys are used wherever they exist; these are the Web's words
/// (apps/web/src/shell/agent/AgentPage.tsx, NotifyPages.tsx, GoalsKnowledgePages.tsx) for
/// what the Expo catalog lacks, and a few Android layout labels.
void registerAgentStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('ag_message')) return;
  target.register(_agentStrings);
}

const Map<String, List<String>> _agentStrings = {
  // Profile hub.
  'ag_message': ['مراسلة', 'Message'],
  'ag_call': ['اتصال', 'Call'],
  'ag_settings': ['الإعدادات', 'Settings'],
  'ag_configuration': ['التهيئة', 'Configuration'],
  'ag_viewAll': ['عرض الكل', 'View all'],
  'ag_routinesCount': ['{0} مجدولة', '{0} scheduled'],
  'ag_trading': ['التداول', 'Trading'],
  'ag_watches': ['المراقبات', 'Watches'],
  'ag_noWatches': ['لا توجد مراقبات.', 'No watches.'],
  'ag_watchPausedNow': ['متوقفة مؤقتًا', 'Paused for now'],
  'ag_watchCancel': ['إيقاف المراقبة', 'Stop the watch'],
  'ag_watchCancelQ': ['إيقاف هذه المراقبة؟', 'Stop this watch?'],
  'ag_watchCancelBody': [
    'يتوقف الوكيل عن مراقبة هذا الشرط.',
    'The agent stops watching this condition.',
  ],
  'ag_watchCancelled': ['أُوقفت المراقبة', 'Watch stopped'],
  'ag_watchPaused': ['أُوقفت المراقبة مؤقتًا', 'Watch paused'],
  'ag_watchResumed': ['استُؤنفت المراقبة', 'Watch resumed'],
  'ag_tradingAccount': ['حساب التداول', 'Trading account'],
  'ag_noAccountChosen': [
    'لم يُختر حساب تداول · اختر حسابًا',
    'No trading account chosen · choose an account',
  ],
  'ag_noAccountLinked': [
    'لا يوجد حساب تداول مرتبط · اربط حسابًا',
    'No trading account linked · link an account',
  ],
  'ag_mandateInSettings': [
    'يتغيّر التفويض من إعدادات الوكيل، ببطاقة التفويض فقط.',
    'The trading mode changes in the agent settings, through the Mandate card only.',
  ],
  'ag_callsNotSetUp': ['المكالمات غير مهيأة', 'Calls are not set up'],
  'ag_callsNeedProvider': [
    'الاتصال بوكيل يحتاج مزوّد صوت. أضفه من إعدادات الصوت.',
    'Calling an agent needs a voice provider. Add one in the voice settings.',
  ],
  'ag_openVoiceSettings': ['فتح إعدادات الصوت', 'Open voice settings'],
  'ag_pauseAgent': ['إيقاف الوكيل', 'Stop the agent'],
  'ag_resumeAgent': ['تشغيل الوكيل', 'Turn the agent on'],
  'ag_agentPaused': ['أُوقف الوكيل مؤقتًا', 'Agent paused'],
  'ag_agentResumed': ['عاد الوكيل إلى العمل', 'Agent turned on'],
  'ag_deleteAgent': ['حذف الوكيل', 'Delete agent'],
  'ag_deleteAgentQ': ['حذف «{0}»؟', 'Delete «{0}»?'],
  'ag_deleteAgentBody': [
    'يُحذف الوكيل مع ملاحظاته وروابطه. تنتقل صفقاته المفتوحة وأوامره المعلّقة إلى Lonora، وتبقى سجلاته المالية. لا يمكن التراجع عن ذلك.',
    'The agent and its notes and links are removed. Its open positions and pending orders move to Lonora, and its financial records stay. This cannot be undone.',
  ],
  'ag_agentDeleted': ['حُذف الوكيل', 'Agent deleted'],
  // Settings.
  'ag_identity': ['الهوية', 'Identity'],
  'ag_roleField': ['الدور', 'Role'],
  'ag_identitySaved': ['حُفظت الهوية', 'Identity saved'],
  'ag_instructionsHint': [
    'ما يتبعه الوكيل في كل محادثة وكل مهمة.',
    'What this agent follows in every conversation and every task.',
  ],
  'ag_instructionsSaved': ['حُفظت التعليمات', 'Instructions saved'],
  'ag_discardQ': ['تجاهل التغييرات؟', 'Discard the changes?'],
  'ag_discardBody': ['لديك تغييرات لم تُحفظ.', 'You have unsaved changes.'],
  'ag_discard': ['تجاهل', 'Discard'],
  'ag_keepEditing': ['متابعة التعديل', 'Keep editing'],
  'ag_avatarSaved': ['حُفظ الأفاتار', 'Avatar saved'],
  'ag_notifications': ['الإشعارات', 'Notifications'],
  'ag_inApp': ['رسائل داخل التطبيق', 'In-app messages'],
  'ag_agentCalls': ['مكالمات الوكيل', 'Agent calls'],
  'ag_dailyLimit': ['الحد اليومي للإشعارات', 'Daily notification limit'],
  'ag_noLimit': ['بلا حد', 'No limit'],
  'ag_urgentAlways': [
    'التنبيهات العاجلة تصل دائمًا ولا تُحتسب.',
    'Urgent alerts always arrive and do not count.',
  ],
  'ag_quietHoursElsewhere': [
    'أوقات الهدوء في الإعدادات، ضمن «الإشعارات والتواصل».',
    'Quiet hours are in Settings, under Notifications and contact.',
  ],
  'ag_limitInvalid': [
    'أدخل عددًا بين 1 و100، أو اتركه فارغًا بلا حد.',
    'Enter a number from 1 to 100, or leave it empty for no limit.',
  ],
  'ag_modeUnknown': ['التفويض غير معروف', 'Trading mode unknown'],
  'ag_marketSaved': ['حُفظ نطاق الوكيل', 'Market scope saved'],
  // Create an agent, the avatar studio and the group sheet.
  'ag_agentName': ['اسم الوكيل', 'Agent name'],
  'ag_chooseColor': ['اختيار اللون', 'Choose a color'],
  'ag_colorN': ['اللون {0}', 'Color {0}'],
  'ag_searchAgents': ['ابحث عن وكيل', 'Search agents'],
  'ag_removeMember': ['إزالة {0}', 'Remove {0}'],
  // «اطلب من … أن يتذكر»: a line the owner sends to the agent's conversation from its memory.
  'ag_rememberHint': ['اطلب من {0} أن يتذكر…', 'Ask {0} to remember…'],
  'ag_rememberMessage': ['تذكّر: {0}', 'Remember: {0}'],
  'ag_rememberSent': [
    'أُرسل إلى محادثتك مع {0}',
    'Sent to your conversation with {0}',
  ],
  // Memory and knowledge.
  'ag_memoryTab': ['الذاكرة', 'Memory'],
  'ag_knowledgeTab': ['المعرفة', 'Knowledge'],
  'ag_memoryEmpty': [
    'لا شيء في ذاكرة الوكيل بعد.',
    'Nothing in this agent’s memory yet.',
  ],
  'ag_editMemory': ['تعديل الذاكرة', 'Edit memory'],
  'ag_memorySaved': ['حُفظت الذاكرة', 'Memory saved'],
  'ag_updatedAt': ['آخر تحديث {0}', 'Updated {0}'],
  'ag_restoredBadge': ['استُعيدت', 'Restored'],
  'ag_noKnowledge': [
    'لا توجد مصادر لهذا الوكيل.',
    'No sources for this agent.',
  ],
  'ag_addKnowledge': ['إضافة معرفة', 'Add knowledge'],
  'ag_editKnowledge': ['تعديل المعرفة', 'Edit knowledge'],
  'ag_note': ['ملاحظة', 'Note'],
  'ag_link': ['رابط', 'Link'],
  'ag_titleField': ['العنوان', 'Title'],
  'ag_urlField': ['الرابط', 'Link'],
  'ag_contentField': ['المحتوى', 'Content'],
  'ag_titleRequired': ['أدخل عنوانًا.', 'Enter a title.'],
  'ag_contentRequired': ['أدخل المحتوى.', 'Enter the content.'],
  'ag_invalidUrl': [
    'أدخل رابطًا يبدأ بـ https:// أو http://',
    'Enter a link that starts with https:// or http://',
  ],
  'ag_knowledgeSaved': ['حُفظت المعرفة', 'Knowledge saved'],
  'ag_deleteKnowledgeQ': ['حذف هذه المعرفة؟', 'Delete this knowledge?'],
  'ag_deleteKnowledgeBody': [
    'لن يجدها الوكيل بعد الآن.',
    'The agent will no longer find it.',
  ],
  'ag_knowledgeDeleted': ['حُذفت المعرفة', 'Knowledge deleted'],
  // Goals, scratchpad and semantic memory (apps/web GoalsKnowledgePages.tsx, Knowledge.tsx,
  // ScratchpadSection.tsx, KnowledgeSection.tsx).
  'ag_goalsTab': ['الأهداف', 'Goals'],
  'ag_scratchpadTab': ['مسودة العمل', 'Scratchpad'],
  'ag_noGoals': ['لا توجد أهداف لهذا الوكيل.', 'No goals for this agent.'],
  'ag_addGoal': ['إضافة هدف', 'Add a goal'],
  'ag_editGoal': ['تحرير الهدف', 'Edit goal'],
  'ag_goalTitle': ['عنوان الهدف', 'Goal title'],
  'ag_noScratchpad': [
    'لا شيء في مسودة العمل بعد.',
    'Nothing in the scratchpad yet.',
  ],
  'ag_addScratch': ['إضافة', 'Add'],
  'ag_editScratch': ['تعديل', 'Edit'],
  'ag_deleteScratchQ': ['حذف هذه الملاحظة؟', 'Delete this note?'],
  'ag_deleteScratchBody': [
    'لن يجدها الوكيل في مسودة عمله بعد الآن.',
    'The agent will no longer find it in its scratchpad.',
  ],
  'ag_scratchDeleted': ['حُذفت الملاحظة', 'Note deleted'],
  'ag_semanticTitle': [
    'الذاكرة الدلالية · اختيارية',
    'Semantic memory · optional',
  ],
  'ag_semanticHint': [
    'ابحث في الملاحظات المعرفية المنفصلة باستخدام تضمينات فعلية من نموذج OpenAI تختاره عالميًا.',
    'Search separate knowledge notes using real embeddings from a globally selected OpenAI model.',
  ],
  'ag_semanticEnable': ['تفعيل الاسترجاع الدلالي', 'Enable semantic retrieval'],
  'ag_semanticModel': ['نموذج التضمين العام', 'Global embedding model'],
  'ag_chooseModel': ['اختر نموذجًا', 'Choose a model'],
  'ag_semanticNote': ['ملاحظة معرفية', 'Knowledge note'],
  'ag_indexNote': ['فهرسة الملاحظة', 'Index note'],
  'ag_noteIndexed': ['فُهرست الملاحظة', 'Note indexed'],
  // «ما أعرفه عنك».
  'ag_editAsText': ['تعديل كنص', 'Edit as text'],
  'ag_profileSaved': ['حُفظ الملف', 'Profile saved'],
  'ag_deleteFactQ': ['حذف هذه المعلومة؟', 'Delete this fact?'],
  'ag_deleteFactBody': [
    'يُسجَّل الحذف بكلمتك، ولن يقرأها أي وكيل بعد الآن.',
    'The deletion is recorded as your word; no agent reads it any more.',
  ],
  'ag_factRemoved': ['حُذفت المعلومة', 'The fact is removed'],
  'ag_factCorrected': ['صُحّحت المعلومة', 'The fact is corrected'],
  'ag_forgetHabitQ': ['نسيان هذه العادة؟', 'Forget this habit?'],
  'ag_forgetHabitBody': [
    'يعود موجز الصباح إلى الساعة 07:00 حتى تُتعلَّم العادة من جديد.',
    'Your morning brief goes back to 07:00 until the habit is learned again.',
  ],
  'ag_habitForgotten': ['نُسيت العادة', 'Forgotten'],
  'ag_forget': ['انسَ', 'Forget'],
  // Error codes the catalogs do not word yet (errorText falls back to the label of the code).
  'agent_not_found': ['الوكيل غير موجود', 'Agent not found'],
  'knowledge_note_not_found': [
    'هذه الملاحظة لم تعد موجودة.',
    'This note no longer exists.',
  ],
  'owner_profile_line_not_found': [
    'تغيّر هذا السطر. حدّث القائمة ثم حاول مجددًا.',
    'This line changed. Refresh the list and try again.',
  ],
  // The same words as the integrations table (L10n.register asserts identical words).
  'broker_disabled': [
    'اتصال الوسيط هذا معطّل.',
    'This broker connection is disabled.',
  ],
  'semantic_model_required': [
    'اختر نموذج التضمين قبل تفعيل الاسترجاع الدلالي.',
    'Choose an embedding model before turning on semantic retrieval.',
  ],
  'memory_note_required': ['اكتب نص الملاحظة.', 'Write the note text.'],
  'memory_too_large': [
    'هذا النص أطول من المسموح.',
    'This text is longer than allowed.',
  ],
  'symbol_not_found': [
    'هذا الرمز غير موجود لدى الوسيط.',
    'The broker does not list this symbol.',
  ],
};
