import '../../l10n/l10n.dart';

/// Android-only labels of the sign-in, server and connect screens. Everything else on those
/// screens uses Lonora's own catalog (apps/mobile/lib/i18n.ts keys). The two error-code keys
/// (`invalid_email`, `invalid_password`) are the server's own codes for `POST /onboarding`, so
/// `L10n.errorText` finds them.
void registerAuthStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('auth_sessionEnded')) return;
  target.register(_authStrings);
}

const Map<String, List<String>> _authStrings = {
  // Web wording «انتهت جلستك» (apps/web AuthFlow.tsx:167) with the next step.
  'auth_sessionEnded': [
    'انتهت جلستك. سجّل الدخول مجددًا.',
    'Your session ended. Sign in again.',
  ],
  'auth_change': ['تغيير', 'Change'],
  'auth_continue': ['متابعة', 'Continue'],
  'auth_checking': ['جارٍ التحقق من الخادم…', 'Checking the server…'],
  'auth_httpsRequired': [
    'يجب أن يبدأ عنوان الخادم بـ https://. يُقبل http:// للعناوين المحلية فقط.',
    'The server address must start with https://. http:// is accepted only for local addresses.',
  ],
  'auth_notLonora': [
    'لم يُجب هذا العنوان كخادم Lonora. تحقق من العنوان.',
    'This address did not answer as a Lonora server. Check the address.',
  ],
  'auth_showPassword': ['إظهار كلمة المرور', 'Show password'],
  'auth_hidePassword': ['إخفاء كلمة المرور', 'Hide password'],
  'auth_switchLanguage': ['تغيير اللغة', 'Change language'],
  // Under «تسجيل الدخول»: a Lonora Cloud account is made on the website (the second part opens
  // https://lonora.io/#start in the browser).
  'auth_noAccount': ['ما عندك حساب؟', 'No account?'],
  'auth_signUpAt': ['سجّل من lonora.io', 'Sign up at lonora.io'],
  'invalid_email': [
    'أدخل بريدًا إلكترونيًا صحيحًا.',
    'Enter a valid email address.',
  ],
  'invalid_password': [
    'كلمة المرور 12 حرفًا على الأقل.',
    'The password must be at least 12 characters.',
  ],
};
