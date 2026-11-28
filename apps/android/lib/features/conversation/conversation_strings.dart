import '../../l10n/l10n.dart';

final Expando<bool> _registered = Expando('conversation strings');

/// Android-only conversation labels (Lonora's catalog has no counterpart). Everything else in
/// the conversation uses Lonora's own keys. Registers once per [L10n] (default
/// [L10n.instance]); the screen calls it on its first build.
void registerConversationStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (_registered[target] == true) return;
  _registered[target] = true;
  target.register({
    // Message long-press menu: Reply · Copy · Select text · ….
    'conv_selectText': ['تحديد النص', 'Select text'],
    // Attach menu: Camera · Photos · Files · Web search.
    'conv_camera': ['الكاميرا', 'Camera'],
    // Confirmation before an unsent message is removed from this device.
    'conv_discardUnsentQ': [
      'حذف الرسالة غير المرسلة؟',
      'Delete the unsent message?',
    ],
    'conv_discardUnsentBody': [
      'لم تصل هذه الرسالة إلى الخادم، وستُحذف من هذا الجهاز فقط.',
      'This message never reached the server; it is removed from this device only.',
    ],
    // A thread or an agent that no longer exists.
    'conv_unavailable': [
      'هذه المحادثة لم تعد متاحة.',
      'This conversation is no longer available.',
    ],
    'conv_agentUnavailable': [
      'هذا الوكيل لم يعد متاحًا.',
      'This agent is no longer available.',
    ],
    // The composer hint of a direct conversation names its agent.
    'conv_messageTo': ['أرسل رسالة إلى {0}', 'Message {0}'],
    // The empty, unfocused composer: a long press records a voice note, a tap types.
    'conv_holdToTalk': [
      'اضغط مطولاً للتحدث، انقر للكتابة',
      'Hold to talk, tap to type',
    ],
    // The first row of the header capsule's actions menu (a direct conversation).
    'conv_agentProfile': ['ملف الوكيل', 'Agent profile'],
    // The header capsule's hint and menu name in a group conversation (`actions` names an
    // agent's).
    'conv_groupActions': ['إجراءات المجموعة', 'Group actions'],
    // The composer's @ list (Lonora Web's wording, apps/web/src/i18n/locales/ar/messages.po).
    'conv_mentionList': ['الإشارة إلى وكيل', 'Mention an agent'],
    'conv_groupMembers': ['أعضاء المجموعة', 'Group members'],
    'conv_bringAgent': [
      'إشراك وكيل في المحادثة',
      'Bring an agent into the conversation',
    ],
    'conv_lead': ['القائد', 'Lead'],
    // The «@الكل» token and row.
    'conv_all': ['الكل', 'all'],
    // The «/» list (Web's wording).
    'conv_noCommand': ['لا يوجد أمر بهذا الاسم', 'No command by that name'],
    'conv_skillsOf': ['مهارات {0}', "{0}'s skills"],
  });
}
