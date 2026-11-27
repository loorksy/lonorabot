/// Port of packages/core/src/time-separators.ts: local calendar boundaries and quiet gaps
/// separate persistent chat history. On Android the separator reads the time alone today
/// («٩:٠٥ ص») and the date with the time on any other day («٢٤ نوفمبر ٧:٥٤ م»).
library;

import '../format.dart';
import 'text.dart';
import 'values.dart';

int _localDay(DateTime date) =>
    DateTime.utc(date.year, date.month, date.day).millisecondsSinceEpoch ~/
    86400000;

/// Whether a separator goes above [current]: the first dated message, a new local day, or 15
/// minutes or more since [previous] (time-separators.ts:6-15). Dates are ISO strings or
/// DateTimes.
bool needsTimeSeparator(Object current, [Object? previous]) {
  final next = parseDate(current);
  if (next == null) return false;
  if (previous == null || previous == '') return true;
  final prior = parseDate(previous);
  return prior != null &&
      (_localDay(next) != _localDay(prior) ||
          next.difference(prior).inMilliseconds >= 900000);
}

/// The separator's title: the time alone today («٩:٠٥ ص», "9:05 AM"); the day and month, then
/// the time, on any other day («٢٤ نوفمبر ٧:٥٤ م», "November 24 7:54 PM"), with the year when it
/// is not this year; '' for an invalid date. Digits follow [dateDigits]. The separator no longer
/// names the day: [today] and [yesterday] are ignored and only kept so existing callers compile.
String formatTimeSeparator(
  Object createdAt,
  String locale, {
  String? today,
  String? yesterday,
  DateTime? now,
}) {
  final date = parseDate(createdAt);
  if (date == null) return '';
  final clock = (now ?? DateTime.now()).toLocal();
  final lang = language(locale);
  final time = formatDate('jm', lang, date);
  if (_localDay(clock) == _localDay(date)) return time;
  final day = formatDate(
    date.year != clock.year ? 'yMMMMd' : 'MMMMd',
    lang,
    date,
  );
  return '$day $time';
}

/// The ids of the messages a separator goes above, in order; messages without a valid
/// `createdAt` are skipped (time-separators.ts:40-51).
Set<String> timeSeparatorIds(
  Iterable<({String id, String? createdAt})> messages,
) {
  final ids = <String>{};
  String? previous;
  for (final message in messages) {
    final createdAt = message.createdAt;
    if (createdAt == null || parseDate(createdAt) == null) continue;
    if (needsTimeSeparator(createdAt, previous)) ids.add(message.id);
    previous = createdAt;
  }
  return ids;
}
