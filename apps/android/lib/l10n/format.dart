/// Number and time formatting as the Expo app shows it.
///
/// Arabic uses Latin digits, as the Expo app's `Intl` does for `ar`. `intl`'s own `ar` date
/// symbols do too, but flutter_localizations' (loaded with GlobalMaterialLocalizations) print
/// Arabic-Indic digits, so [formatDate] maps them back. English times use a plain space before
/// AM/PM, as JavaScript engines print them.
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
/// AM/PM printed as the space JavaScript engines use, and Latin digits whichever date symbols
/// are loaded.
String formatDate(String pattern, String locale, DateTime date) =>
    DateFormat(pattern, locale)
        .format(date)
        .replaceAll('\u{202f}', ' ')
        .replaceAllMapped(_nativeDigit, _latin);

// Arabic-Indic (U+0660–0669) and Extended Arabic-Indic (U+06F0–06F9) digits.
final RegExp _nativeDigit = RegExp('[\u0660-\u0669\u06f0-\u06f9]');

String _latin(Match digit) =>
    String.fromCharCode(0x30 + (digit[0]!.codeUnitAt(0) & 0xF));

/// HH:mm with Latin digits in local time, as the chat list and search rows show it
/// (apps/mobile/components/shell/thread-row.tsx:25-27 `clockTime`).
String clockTime(Object at) {
  final date = parseDate(at);
  if (date == null) return 'Invalid Date';
  String two(int value) => value.toString().padLeft(2, '0');
  return '${two(date.hour)}:${two(date.minute)}';
}

/// A voice note's length as m:ss (apps/mobile/components/message-bubble.tsx:98-101).
String voiceClock(num seconds) {
  final s = seconds.isNaN ? 0 : seconds.round().clamp(0, 1 << 52).toInt();
  return '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';
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
