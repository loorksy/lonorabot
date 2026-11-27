import '../../l10n/l10n.dart';

/// Android-only labels of the skills page: the Web's words (apps/web/src/shell/domain/
/// SkillsPages.tsx: enable toasts, «سجل الإصدارات», restore) that the Expo catalog lacks.
/// Every other label is Lonora's own `skills*` key.
void registerSkillsStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('sk_enabled')) return;
  target.register(_skillsStrings);
}

const Map<String, List<String>> _skillsStrings = {
  'sk_enabled': ['فُعّلت المهارة', 'Skill enabled'],
  'sk_disabled': ['عُطّلت المهارة', 'Skill disabled'],
  'sk_history': ['سجل الإصدارات', 'Version history'],
  'sk_versionN': ['الإصدار {0}', 'Version {0}'],
  'sk_restore': ['استعادة', 'Restore'],
  'sk_restored': [
    'استُعيدت المهارة إلى الإصدار {0}',
    'Skill restored to version {0}',
  ],
  'sk_noVersions': ['لا توجد إصدارات سابقة.', 'No previous versions.'],
  'sk_saved': ['حُفظت المهارة', 'Skill saved'],
  'sk_created': ['أُنشئت المهارة', 'Skill created'],
  'sk_deleted': ['حُذفت المهارة', 'Skill deleted'],
  'sk_blocked': ['حُظر الإصدار', 'Version blocked'],
  'sk_block': ['حظر', 'Block'],
  'sk_tool': ['الأداة', 'Tool'],
  'sk_toolNone': ['بلا أداة', 'None'],
  'sk_toolWeb': ['البحث على الويب', 'Web search'],
  'sk_toolRead': ['قراءة الملفات', 'Read files'],
  'sk_toolReports': ['إعداد التقارير', 'Prepare reports'],
  'sk_import': ['استيراد مهارة', 'Import a skill'],
  'sk_imported': ['استُوردت المهارة', 'Skill imported'],
  'sk_importedDescription': ['مهارة مستوردة', 'Imported skill'],
  'sk_importTooLarge': [
    'اختر ملفًا أصغر من 600 KB.',
    'Choose a file smaller than 600 KB.',
  ],
  'sk_invalidId': [
    'استخدم أحرفًا إنجليزية صغيرة وأرقامًا وشرطة أو شرطة سفلية.',
    'Use lowercase English letters, numbers, hyphens or underscores.',
  ],
};
