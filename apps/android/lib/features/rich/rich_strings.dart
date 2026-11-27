import '../../l10n/l10n.dart';

final Expando<bool> _registered = Expando('rich-strings');

/// Android-only labels of the rich message renderer (everything else reuses Lonora's keys).
/// The renderer calls it on first build with `context.l10n`; the lead may call
/// `registerRichStrings(L10n.instance)` at startup instead.
void registerRichStrings(L10n l10n) {
  if (_registered[l10n] == true) return;
  _registered[l10n] = true;
  l10n.register(richStrings);
}

const Map<String, List<String>> richStrings = {
  // Web's code block header: the language, else «code»; its copy button (Q36).
  'rich_code': ['كود', 'Code'],
  'rich_copyCode': ['نسخ الكود', 'Copy code'],
  // A remote Markdown image never loads by itself (chat-ui `inlineMarkdownImageSrc`).
  'rich_openImage': ['فتح الصورة', 'Open image'],
  // Voice note playback.
  'rich_play': ['تشغيل', 'Play'],
  'rich_transcribing': ['جارٍ تحويل الصوت إلى نص…', 'Transcribing…'],
  'rich_transcriptFailed': ['تعذّر تحويل الصوت إلى نص', 'Could not transcribe'],
  'rich_voiceFailed': [
    'تعذّر تشغيل الرسالة الصوتية',
    'Could not play the voice message',
  ],
};
