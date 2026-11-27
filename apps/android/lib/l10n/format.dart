/// Number and time formatting.
///
/// Digits: in Arabic, dates and times of day read in Arabic-Indic digits («٢٤ نوفمبر ٧:٥٤ م»);
/// durations, sizes, percentages, counts, versions and prices keep Latin digits, as English does
/// everywhere. [formatDate] and every date or time built by hand go through [dateDigits], so one
/// date label never mixes the two systems, whichever date symbols are loaded (`intl`'s own `ar`
/// symbols print Latin digits, flutter_localizations' print Arabic-Indic ones). English times use
/// a plain space before AM/PM, as JavaScript engines print them.
library;

import 'dart:math' as math;

import 'package:intl/date_symbol_data_local.dart';
import 'package:intl/intl.dart';

import 'core/text.dart';
import 'core/values.dart';

/// Loads the date symbols of both app languages (DateFormat needs them); [L10n.load] runs it.
Future<void> ensureDateFormatting() async {
  await initializeDateFormatting('ar');
  await initializeDateFormatting('en');
}

/// `Intl.DateTimeFormat` output of an `intl` pattern, with ICU's narrow no-break space before
/// AM/PM printed as the space JavaScript engines use, and the digits of [dateDigits].
String formatDate(String pattern, String locale, DateTime date) => dateDigits(
  DateFormat(pattern, locale).format(date).replaceAll('\u{202f}', ' '),
  locale,
);

/// [text] with its digits as a date or time of day shows them in [locale]: Arabic-Indic
/// (U+0660–0669) in Arabic, Latin otherwise. Native digits are read by value first, so the
/// result does not depend on which digits produced [text]. Use it for dates and times only:
/// durations, sizes, counts and the like stay Latin.
String dateDigits(String text, String locale) {
  final latin = text.replaceAllMapped(_nativeDigit, _latin);
  if (language(locale) != 'ar') return latin;
  return latin.replaceAllMapped(
    _latinDigit,
    (digit) => String.fromCharCode(0x0660 + digit[0]!.codeUnitAt(0) - 0x30),
  );
}

// Arabic-Indic (U+0660–0669) and Extended Arabic-Indic (U+06F0–06F9) digits.
final RegExp _nativeDigit = RegExp('[\u0660-\u0669\u06f0-\u06f9]');
final RegExp _latinDigit = RegExp('[0-9]');

String _latin(Match digit) =>
    String.fromCharCode(0x30 + (digit[0]!.codeUnitAt(0) & 0xF));

/// HH:mm in local time, as the chat list and search rows show it
/// (apps/mobile/components/shell/thread-row.tsx:25-27 `clockTime`), in [lang]'s date digits;
/// Latin digits when [lang] is omitted.
String clockTime(Object at, {String? lang}) {
  final date = parseDate(at);
  if (date == null) return 'Invalid Date';
  String two(int value) => value.toString().padLeft(2, '0');
  final clock = '${two(date.hour)}:${two(date.minute)}';
  return lang == null ? clock : dateDigits(clock, lang);
}

/// A voice note's length as m:ss (apps/mobile/components/message-bubble.tsx:98-101), or mm:ss
/// with [twoDigitMinutes] (the recorder's timer). A duration: Latin digits in every language.
String voiceClock(num seconds, {bool twoDigitMinutes = false}) {
  final s = seconds.isNaN ? 0 : seconds.round().clamp(0, 1 << 52).toInt();
  final minutes = '${s ~/ 60}'.padLeft(twoDigitMinutes ? 2 : 1, '0');
  return '$minutes:${(s % 60).toString().padLeft(2, '0')}';
}

/// A number as `value.toLocaleString(locale)` prints it (grouping, up to 3 decimals).
String formatNumber(num value, String locale) =>
    NumberFormat.decimalPattern(language(locale)).format(value);

/// A file size in B, KB, MB or GB, one decimal at most
/// (apps/mobile/lib/artifacts.ts:46-52 `formatFileSize`).
String formatFileSize(num? size, String locale) {
  final value = size == null || size.isNaN ? 0 : size;
  final safe = value < 0 ? 0 : value;
  if (safe < 1024) return '${formatNumber(safe, locale)} B';
  final exponent = math.min((math.log(safe) / math.log(1024)).floor(), 3);
  const units = ['B', 'KB', 'MB', 'GB'];
  final scaled = safe / math.pow(1024, exponent);
  final format = NumberFormat.decimalPattern(language(locale))
    ..maximumFractionDigits = 1;
  return '${format.format(scaled)} ${units[exponent]}';
}
