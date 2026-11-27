import '../../l10n/l10n.dart';

/// Android-only labels of «يحتاج انتباهك». The rows' own words are Lonora's attention labels
/// (`attention.<code>`, attentionOwnerQuestion, attentionNothing).
void registerAttentionStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('at_byUrgency')) return;
  target.register(_attentionStrings);
}

const Map<String, List<String>> _attentionStrings = {
  'at_byUrgency': ['حسب الأهمية', 'By urgency'],
  'at_byAgent': ['حسب الوكيل', 'By agent'],
  'at_decisions': ['بانتظار قرارك', 'Waiting for your decision'],
  'at_health': ['حالة الخدمة', 'Service health'],
  'at_alerts': ['تنبيهات الوكلاء', 'Agent alerts'],
  'at_openHint': [
    'يفتح محادثته حيث تقف البطاقة أو السؤال؛ الفتح لا يقرر شيئًا.',
    'Opens its conversation, where the card or question stands; opening decides nothing.',
  ],
};
