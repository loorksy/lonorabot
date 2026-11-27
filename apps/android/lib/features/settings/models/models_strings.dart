import '../../../l10n/l10n.dart';

/// Android-only labels of the models page. The Web's wording is reused (apps/web
/// ModelsPage.tsx and its ar catalog); the confirmation, the voice hint and the per-agent
/// section are Android's («Android»).
void registerModelsStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('md_globalRouting')) return;
  target.register(_modelsStrings);
}

const Map<String, List<String>> _modelsStrings = {
  'md_globalRouting': ['التوجيه العام', 'Global routing'],
  'md_mode': ['الوضع', 'Mode'],
  'md_unifiedMode': ['نموذج واحد للمهام النصية', 'One model for text work'],
  'md_customMode': ['التوجيه حسب القدرة', 'Route by capability'],
  'md_unifiedModel': ['النموذج الموحد', 'Unified model'],
  'md_chooseModel': ['اختر نموذجًا', 'Choose a model'],
  'md_cap_conversation': ['المحادثة', 'Conversation'],
  'md_cap_reasoning': ['الاستدلال', 'Reasoning'],
  'md_cap_research': ['البحث المعمق', 'Research'],
  'md_cap_vision': ['الرؤية', 'Vision'],
  'md_cap_realtime_voice': ['صوت مباشر', 'Realtime voice'],
  'md_cap_stt': ['تحويل الكلام إلى نص', 'Speech recognition'],
  'md_cap_tts': ['تحويل النص إلى كلام', 'Speech synthesis'],
  'md_cap_background': ['العمل في الخلفية', 'Background work'],
  'md_routingNote': [
    'تنطبق هذه الإعدادات على جميع الوكلاء والمهام المجدولة. تتطلب المسارات الصوتية نماذج تدعم الصوت.',
    'These settings apply to every agent and routine. Voice routes require models that support audio.',
  ],
  'md_saveRouting': ['حفظ التوجيه العام', 'Save global routing'],
  'md_saveRoutingQ': ['حفظ التوجيه العام؟', 'Save the global routing?'],
  'md_noModels': [
    'تظهر النماذج هنا بعد إضافة مزوّد نماذج.',
    'Models appear here after you add a model provider.',
  ],
  'md_availableModels': ['النماذج المتاحة ({0})', 'Available models ({0})'],
  'md_verified': ['بيانات مؤكدة', 'Verified metadata'],
  'md_unverified': ['القدرات غير مؤكدة', 'Capabilities unverified'],
  'md_voiceNeedsOpenAi': [
    'تستخدم المسارات الصوتية نماذج الكلام من OpenAI: أضف مفتاح OpenAI لاختيارها.',
    "Voice routes use OpenAI's speech models: add an OpenAI key to choose them.",
  ],
  'md_perAgent': ['نموذج كل وكيل', "Each agent's model"],
  'md_perAgentNote': [
    'يمكن لكل وكيل أن يستخدم نموذجًا غير نموذجك العام؛ اختره من إعدادات الوكيل.',
    "An agent can use a model other than your global one; choose it in the agent's settings.",
  ],
};
