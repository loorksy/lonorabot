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
    // Attach sheet: Camera · Photos · Files.
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
    'conv_messageTo': ['اكتب رسالة إلى {0}…', 'Message {0}…'],
    // The header capsule's hint: a tap opens the agent's profile.
    'conv_agentProfile': ['ملف الوكيل', 'Agent profile'],
  });
}
