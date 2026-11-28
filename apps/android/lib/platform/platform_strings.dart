// Android-only labels of the platform package (notification channels, the update prompt).
// Lonora's own keys are reused where they exist (`sh_updates`, `newMessage`, `reply`,
// `download`); the Arabic of the update texts follows apps/web/src/i18n/locales/ar.
import '../features/trading/trading_strings.dart';
import '../l10n/l10n.dart';

L10n? _registeredFor;

/// Registers the platform labels once per catalog (idempotent).
void registerPlatformStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (identical(_registeredFor, target)) return;
  _registeredFor = target;
  target.register(_strings);
  // «التعطل والاستعادة» names the button of a broker health heads-up.
  registerTradingStrings(target);
}

const _strings = <String, List<String>>{
  'pf_channelMessages': ['الرسائل', 'Messages'],
  'pf_channelMessagesDesc': [
    'ردود وكلائك عندما يكون لونورا في الخلفية',
    "Your agents' replies while Lonora is in the background",
  ],
  'pf_channelAttentionDesc': [
    'الطلبات التي تنتظر قرارك، مثل الموافقات',
    'Requests that wait for your decision, such as approvals',
  ],
  'pf_channelCalls': ['المكالمات', 'Calls'],
  'pf_channelCallsDesc': [
    'المكالمة الجارية مع وكيلك',
    'The ongoing call with your agent',
  ],
  'pf_channelStatus': ['حالة الخلفية', 'Background status'],
  'pf_channelStatusDesc': [
    'تنبيهات هادئة عن النشاط والتحديثات',
    'Quiet notices about activity and updates',
  ],
  'pf_newMessages': ['رسائل جديدة: {0}', 'New messages: {0}'],
  'pf_updateAvailable': ['تحديث متاح', 'Update available'],
  'pf_updateVersion': ['الإصدار {0}', 'Version {0}'],
  'pf_update': ['تحديث', 'Update'],
  'pf_updateLater': ['لاحقًا', 'Later'],
  'pf_updatePlayHint': [
    'يُنزِّل Google Play التحديث في الخلفية، وعند اكتماله تعيد تشغيل التطبيق لتثبيته.',
    'Google Play downloads the update in the background; when it is ready, you restart the app to install it.',
  ],
  'pf_updateReady': [
    'اكتمل تنزيل التحديث. أعد تشغيل التطبيق لتثبيته.',
    'The update is downloaded. Restart the app to install it.',
  ],
  'pf_restart': ['إعادة التشغيل', 'Restart'],
  'pf_updateTap': ['اضغط لعرض التحديث.', 'Tap to see the update.'],
  // The row the About screen can offer for `checkForUpdates` (update_sheet.dart).
  'pf_checkForUpdates': ['التحقق من التحديثات', 'Check for updates'],
  'pf_updateCheckFailed': [
    'تعذر التحقق من التحديثات.',
    'Could not check for updates.',
  ],
  'pf_updatesOff': [
    'لا تتوفر تحديثات داخل التطبيق لهذا الإصدار.',
    'In-app updates are not available for this build.',
  ],
  'pf_updateDownloadHint': [
    'يفتح الرابط في المتصفح لتنزيل الإصدار الجديد، وتثبّته أنت بنفسك.',
    'Opens the link in your browser to download the new version; you install it yourself.',
  ],
  'pf_updateFailed': ['تعذر بدء التحديث.', 'The update could not start.'],
  'pf_upToDate': ['لديك أحدث إصدار.', 'You have the latest version.'],
};
