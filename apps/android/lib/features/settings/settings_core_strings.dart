import '../../l10n/l10n.dart';

/// Android-only labels of the account, appearance, notifications, voice and about pages.
/// Where the Web already says the same thing, its wording is reused (apps/web NotifyPages.tsx,
/// VoiceSettingsOverlay.tsx, SettingsRoot.tsx and their ar catalog).
void registerSettingsCoreStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('set_followSystem')) return;
  target.register(_settingsStrings);
}

const Map<String, List<String>> _settingsStrings = {
  // Appearance and language.
  'set_followSystem': ['حسب النظام', 'Follow system'],
  'set_languageHint': [
    '«حسب النظام» يستخدم العربية ما لم تكن لغة الهاتف الإنجليزية.',
    '“Follow system” uses Arabic unless the phone is set to English.',
  ],
  // Notifications on this phone.
  'set_thisPhone': ['على هذا الهاتف', 'On this phone'],
  'set_phoneNotifications': ['إشعارات الهاتف', 'Phone notifications'],
  'set_notifOn': ['الإشعارات مفعّلة', 'Notifications on'],
  'set_notifOff': ['الإشعارات متوقفة', 'Notifications off'],
  'set_allow': ['السماح', 'Allow'],
  'set_openPhoneSettings': ['فتح إعدادات الهاتف', 'Open phone settings'],
  'set_delivery': [
    'عندما يكون Lonora مفتوحًا تظهر الردود وما يحتاج انتباهك فورًا. وعندما يكون مغلقًا يتحقق الهاتف في الخلفية من حين لآخر بحسب ما يسمح به Android، لذا قد يتأخر التنبيه. الإشعارات الفورية غير متاحة في هذا التطبيق بعد: يرسلها خادمك إلى تطبيق Lonora المبني بـ Expo فقط.',
    'While Lonora is open, replies and what needs you show up at once. When it is closed, the phone checks in the background from time to time, as Android allows, so an alert can arrive late. Instant push is not available in this app yet: your server sends push only to the Lonora app built with Expo.',
  ],
  'set_notifications': ['الإشعارات', 'Notifications'],
  'set_inApp': ['إشعارات داخل التطبيق', 'In-app notifications'],
  'set_inAppSub': [
    'شريط أعلى الشاشة عند وصول رد في محادثة أخرى',
    'A bar at the top of the screen when a reply arrives in another conversation',
  ],
  'set_preview': ['معاينة النص', 'Text preview'],
  'set_previewSub': [
    'إظهار بداية الرسالة في الإشعار',
    'Show the start of the message in the notification',
  ],
  'set_opportunities': [
    'أبلغني بالفرص المؤكدة',
    'Notify me about confirmed opportunities',
  ],
  'set_opportunitiesSub': [
    'تنبيه عندما يؤكد وكيل فرصة',
    'An alert when an agent confirms an opportunity',
  ],
  'set_muteAtNight': ['كتم الإشعارات ليلًا', 'Mute notifications at night'],
  'set_fromTo': ['من {0} إلى {1}', 'From {0} to {1}'],
  'set_from': ['من', 'From'],
  'set_to': ['إلى', 'To'],
  'set_quietSame': [
    'يجب أن تبدأ ساعات الهدوء وتنتهي في وقتين مختلفين.',
    'Quiet hours must start and end at different times.',
  ],
  'set_urgent': ['العاجل يصل دائمًا', 'Urgent always arrives'],
  'set_urgentSub': [
    'طلب موافقة أو عملية غير مؤكَّدة',
    'An approval request or an unconfirmed operation',
  ],
  'set_timeZone': ['المنطقة الزمنية: {0}', 'Time zone: {0}'],
  // The Web's «لكل وكيل» list (NotifyPages.tsx).
  'set_perAgent': ['لكل وكيل', 'Per agent'],
  'set_callRings': ['تصل المكالمة إلى هذا الجهاز', 'A call rings this device'],
  'set_passkeyElsewhere': [
    'تسجيل جهاز بمفتاح المرور غير متاح في هذا التطبيق بعد. سجّل جهازك من Lonora على الويب.',
    'Registering a device with a passkey is not available in this app yet. Register your device from Lonora on the web.',
  ],
  // Account.
  'set_nameFooter': [
    'يقرأ كل وكلائك اسمك وطريقة مخاطبتك.',
    'Every agent reads your name and form of address.',
  ],
  'set_sessionEnds': ['تنتهي هذه الجلسة', 'This session ends'],
  'set_phoneZone': ['منطقة هذا الهاتف', 'This phone’s time zone'],
  'set_otherZone': ['منطقة أخرى…', 'Another time zone…'],
  'set_passkeyDevices': ['أجهزة مفتاح المرور', 'Passkey devices'],
  'set_noPasskeyDevices': [
    'لا توجد أجهزة مسجلة بمفتاح المرور.',
    'No devices are registered with a passkey.',
  ],
  // Voice.
  'set_voiceTitle': ['محادثة مباشرة', 'Realtime conversation'],
  'set_voiceBody': [
    'تُحفظ المهام الصوتية في المحادثة الحالية. يستطيع GPT-Live مواصلة الاستماع والتحدث أثناء تنفيذ الوكيل نفسه للمهام المفوضة.',
    'Spoken tasks are saved in the current conversation. GPT-Live can keep listening and speaking while the same agent performs delegated work.',
  ],
  'set_voiceRouting': [
    'يتصل GPT-Live مباشرة عبر WebRTC باستخدام مفتاح OpenAI المحفوظ على الخادم. اختر نموذج الصوت في التوجيه العام؛ وينفذ وكيل Lonora نفسه المهام المفوضة بأدواته.',
    'GPT-Live connects directly over WebRTC using your server-stored OpenAI credential. Choose the voice model in global routing; delegated work uses the same Lonora agent and tools.',
  ],
  'set_voiceModel': ['النموذج', 'Model'],
  // Expo's `nativeCallHint` without «calls end when the app enters the background»: here a
  // call keeps running behind a foreground notification (lib/features/voice/voice_api.dart).
  'set_callHint': [
    'ابدأ مكالمة من زر الاتصال أعلى محادثة الوكيل. تستخدم المكالمة ذاكرة الوكيل والمحادثة نفسها. تستمر المكالمة في الخلفية مع «إنهاء المكالمة» في إشعارها، وتنتهي عند إغلاق التطبيق.',
    'Start a call from the call button in your agent conversation. Calls use the same agent memory and thread. A call keeps going in the background, with End call on its notification, and ends when the app is closed.',
  ],
  'set_microphone': ['الميكروفون', 'Microphone'],
  'set_micAllowed': ['مسموح', 'Allowed'],
  'set_micBlocked': ['غير مسموح', 'Not allowed'],
  'set_micNote': [
    'تحتاج المكالمات إلى الميكروفون.',
    'Calls need the microphone.',
  ],
  // About.
  'set_versionLine': [
    'Lonora · الإصدار {version}',
    'Lonora · version {version}',
  ],
  'set_aboutBody': [
    'يعمل Lonora على خادمك، ويواصل وكلاؤك العمل عليه حتى عندما يكون الهاتف مغلقًا.',
    'Lonora runs on your server. Your agents keep working there even when your phone is closed.',
  ],
  'set_appVersion': ['إصدار التطبيق', 'App version'],
  'set_serverVersion': ['إصدار الخادم', 'Server version'],
  'set_openWeb': ['فتح Lonora على الويب', 'Open Lonora on the web'],
  'set_licenses': ['تراخيص البرمجيات المفتوحة', 'Open-source licenses'],
  'set_linkFailed': ['تعذر فتح الرابط.', 'The link could not be opened.'],
};
