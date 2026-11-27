import '../../l10n/l10n.dart';

/// Android-only labels of the Me tab. Entry titles use Lonora's own catalog; the sign-out
/// confirmation reuses the Web's wording (apps/web SettingsRoot.tsx «Sign out?»).
void registerMeStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('me_signOutQ')) return;
  target.register(_meStrings);
}

const Map<String, List<String>> _meStrings = {
  'me_signOutQ': ['تسجيل الخروج؟', 'Sign out?'],
  'me_signOutBody': [
    'ستحتاج إلى تسجيل الدخول مجددًا. محادثاتك تبقى محفوظة في Lonora.',
    'You will need to sign in again. Your conversations stay saved in Lonora.',
  ],
  'me_signedInAs': ['مسجَّل الدخول باسم {0}', 'Signed in as {0}'],
  'me_clearCache': ['مسح الذاكرة المؤقتة', 'Clear cache'],
  'me_clearCacheQ': ['مسح الذاكرة المؤقتة؟', 'Clear the cache?'],
  'me_clearCacheBody': [
    'تُحذف من هذا الهاتف النسخ المحفوظة من المحادثات والملفات المؤقتة، وتُحمَّل من خادمك من جديد. الرسائل التي لم تُرسل بعد تبقى.',
    'Saved copies of chats and temporary files are removed from this phone and load again from your server. Messages not sent yet stay.',
  ],
  'me_cacheCleared': ['مُسحت الذاكرة المؤقتة', 'Cache cleared'],
  'me_about': ['حول Lonora', 'About Lonora'],
  'me_openAccount': ['فتح الحساب', 'Open the account'],
};
