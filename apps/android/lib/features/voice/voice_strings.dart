// Android-only labels of voice calls and voice notes. Lonora's own keys are reused where they
// exist (`endCall`, `muteCall`, `unmuteCall`, `minimizeCall`, `reopenCall`, `callListening`,
// `callSpeaking`, `voiceNote`, `voice_*` error codes); the rest take the wording of Lonora's Web
// client (apps/web/src/shell/call/CallPages.tsx, conversation/Composer.tsx and their Arabic in
// apps/web/src/i18n/locales/ar/messages.po) and apps/mobile/lib/incoming-call-labels.json.
import '../../l10n/l10n.dart';

L10n? _registeredFor;

/// Registers the voice labels once per catalog (idempotent).
void registerVoiceStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (identical(_registeredFor, target)) return;
  _registeredFor = target;
  target.register(_strings);
}

const _strings = <String, List<String>>{
  // Calls (the call controls: Speaker · Mute · End call · Minimize).
  'vc_calling': ['جارٍ الاتصال…', 'Calling…'],
  'vc_callEnded': ['انتهت المكالمة', 'Call ended'],
  'vc_ending': ['جارٍ إنهاء المكالمة', 'Ending call'],
  'vc_micMuted': ['الميكروفون مكتوم', 'Microphone muted'],
  'vc_listeningToYou': ['أستمع إليك', 'Listening to you'],
  'vc_speaker': ['السماعة', 'Speaker'],
  'vc_mute': ['كتم', 'Mute'],
  'vc_unmute': ['إلغاء الكتم', 'Unmute'],
  'vc_end': ['إنهاء', 'End'],
  'vc_minimize': ['تصغير', 'Minimize'],
  'vc_callWith': ['مكالمة مع {0}', 'Call with {0}'],
  'vc_ongoing': ['مكالمة جارية', 'Ongoing call'],
  'vc_returnToCall': ['العودة إلى المكالمة', 'Return to the call'],
  'vc_openSettings': ['فتح الإعدادات', 'Open settings'],
  // Incoming calls (apps/mobile/lib/incoming-call-labels.json).
  'vc_incomingTitle': ['لونورا يريد التحدث معك', 'Lonora would like to talk'],
  'vc_answer': ['رد', 'Answer'],
  'vc_decline': ['رفض', 'Decline'],
  'vc_replyMessage': ['الرد برسالة', 'Reply with a message'],
  // Voice notes (apps/web/src/conversation/Composer.tsx).
  'vn_hold': [
    'اضغط مطولًا لتسجيل رسالة صوتية',
    'Hold to record a voice message',
  ],
  'vn_holdHint': [
    'اضغط مطولًا على الميكروفون للتسجيل، وأفلت للإرسال.',
    'Hold the microphone to record, release to send.',
  ],
  'vn_slideCancel': ['اسحب للإلغاء', 'Slide to cancel'],
  'vn_delete': ['حذف التسجيل', 'Delete the recording'],
  'vn_length': ['مدة التسجيل', 'Recording length'],
  'vn_pause': ['إيقاف التسجيل مؤقتًا', 'Pause recording'],
  'vn_resume': ['متابعة التسجيل', 'Continue recording'],
  'vn_send': ['إرسال الرسالة الصوتية', 'Send the voice message'],
  'vn_micDenied': [
    'اسمح للتطبيق باستخدام الميكروفون لتسجيل رسالة صوتية.',
    'Allow microphone access to record a voice message.',
  ],
  'vn_unavailable': [
    'الميكروفون غير متاح.',
    'The microphone is not available.',
  ],
};
