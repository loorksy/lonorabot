// Text helpers of the chat list and search: a port of packages/core/src/plain-line.ts
// (`plainLine`) and search-fold.ts (`foldSearch`, `highlightRange`), the agent role line of
// apps/mobile/components/shell/kit.tsx:22-26, and the row time.
import '../../core/models/models.dart';
import '../../l10n/l10n.dart';

final _controls = RegExp(r'[\u202a-\u202e\u2066-\u2069]');
final _signedNumber = RegExp(
  r'(^|[\s(\[«:،|·])([+\-−][$€£]?\d[\d,]*(?:\.\d+)?%?)',
);

/// Markdown as one plain line, signed numbers isolated left to right (plain-line.ts:42-50).
String plainLine(String text, {int? max}) {
  final line = _plainWords(text);
  var cut = line;
  if (max != null && line.length > max) {
    final space = line.lastIndexOf(' ', max);
    cut = '${line.substring(0, space > 0 ? space : max).trimRight()}…';
  }
  return cut.replaceAllMapped(
    _signedNumber,
    (m) => '${m[1]}\u2066${m[2]}\u2069',
  );
}

String _plainWords(String text) => text
    .replaceAll(_controls, '')
    .replaceAll(RegExp(r'```[\s\S]*?(```|$)'), ' ')
    .replaceAllMapped(RegExp(r'`([^`\n]+)`'), (m) => m[1]!)
    .replaceAllMapped(RegExp(r'\*\*([^*\n]+)\*\*'), (m) => m[1]!)
    .replaceAllMapped(
      RegExp(r'(^|[\s(])_([^_\n]+)_(?=[\s.,،)!?؟]|$)'),
      (m) => '${m[1]}${m[2]}',
    )
    .replaceAllMapped(
      RegExp(r'\[([^\]\n]+)\]\((https?://[^\s)]+)\)'),
      (m) => m[1]!,
    )
    .replaceAll(
      RegExp(r'^[ \t]*\|?[ \t]*:?-{2,}[-:| \t]*$', multiLine: true),
      '',
    )
    .replaceAll(RegExp(r'^[ \t]*\|[ \t]*|[ \t]*\|[ \t]*$', multiLine: true), '')
    .replaceAll(RegExp(r'[ \t]*\|[ \t]*'), ' · ')
    .replaceAll(
      RegExp(r'^[ \t]*(#{1,3}[ \t]+|>[ \t]?|[-*•][ \t]+)', multiLine: true),
      '',
    )
    .replaceAll(RegExp(r'\s+'), ' ')
    .trim();

const _alefVariants = 'أإآٱ';
const _tashkeel = 'ًٌٍَُِّْٰ';
const _tatweel = 'ـ';

String _foldChar(String char) {
  final buffer = StringBuffer();
  for (final unit in char.toLowerCase().split('')) {
    if (_alefVariants.contains(unit)) {
      buffer.write('ا');
    } else if (unit == 'ى') {
      buffer.write('ي');
    } else if (unit == 'ة') {
      buffer.write('ه');
    } else if (_tashkeel.contains(unit) || unit == _tatweel) {
      // folds to nothing
    } else {
      buffer.write(unit);
    }
  }
  return buffer.toString();
}

final _space = RegExp(r'\s');

/// The owner's search folding, identical to `lonora_core.search_fold` (search-fold.ts:23-27).
String foldSearch(String text) {
  final buffer = StringBuffer();
  for (final rune in text.runes) {
    final char = String.fromCharCode(rune);
    buffer.write(_space.hasMatch(char) ? ' ' : _foldChar(char));
  }
  return buffer.toString().trim().replaceAll(RegExp(r'\s+'), ' ');
}

/// Where the folded query first occurs in [text], as [start, end) over the original string
/// (UTF-16 offsets), or null (search-fold.ts:33-63).
(int, int)? highlightRange(String text, String query) {
  final needle = foldSearch(query);
  if (needle.isEmpty) return null;
  final folded = StringBuffer();
  final origins = <int>[];
  var index = 0;
  var lastSpace = true;
  for (final rune in text.runes) {
    final char = String.fromCharCode(rune);
    if (_space.hasMatch(char)) {
      if (!lastSpace) {
        folded.write(' ');
        origins.add(index);
      }
      lastSpace = true;
    } else {
      lastSpace = false;
      final out = _foldChar(char);
      for (var unit = 0; unit < out.length; unit++) {
        folded.write(out[unit]);
        origins.add(index);
      }
    }
    index += char.length;
  }
  final at = folded.toString().indexOf(needle);
  if (at < 0) return null;
  final lastOrigin = origins[at + needle.length - 1];
  final lastChar = String.fromCharCode(text.substring(lastOrigin).runes.first);
  return (origins[at], lastOrigin + lastChar.length);
}

/// An agent's role line: its title or description; the personal agent's is «مساعدك الشخصي».
String agentRole(L10n l10n, Agent agent) => agent.title.isNotEmpty
    ? agent.title
    : agent.description.isNotEmpty
    ? agent.description
    : agent.isPersonal
    ? l10n.t('sh_personalRole')
    : '';

/// The clock the list's times are read against (tests pin it).
DateTime Function() chatClock = DateTime.now;

/// A row's time: the clock today (HH:mm, Latin digits, as Lonora's clockTime), the weekday within
/// the week, else the date.
String listTime(DateTime at, String lang, {DateTime? now}) {
  final local = at.toLocal();
  final clock = (now ?? chatClock()).toLocal();
  int day(DateTime d) =>
      DateTime.utc(d.year, d.month, d.day).millisecondsSinceEpoch ~/ 86400000;
  final age = day(clock) - day(local);
  if (age <= 0) return clockTime(local);
  if (age <= 6) return formatDate('EEEE', lang, local);
  return _latinDigits(
    formatDate(local.year == clock.year ? 'MMMd' : 'yMMMd', lang, local),
  );
}

/// Lonora shows Latin digits in Arabic too (as the Expo app's clockTime does).
String _latinDigits(String text) => text.replaceAllMapped(
  RegExp('[\u0660-\u0669\u06f0-\u06f9]'),
  (m) => '${m[0]!.codeUnitAt(0) & 0xf}',
);
