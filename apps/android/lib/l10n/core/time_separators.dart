/// Port of packages/core/src/time-separators.ts: local calendar boundaries and quiet gaps
/// separate persistent chat history; the separator reads «اليوم 9:05 ص», a weekday, or a date.
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

/// The separator's title: «[today] 9:05 ص», «[yesterday] …», the weekday within the week,
/// else the date (with the year when it is not this year); '' for an invalid date. [today]
/// and [yesterday] are the app's `today` / `yesterday` labels (time-separators.ts:17-38).
String formatTimeSeparator(
  Object createdAt,
  String locale, {
  required String today,
  required String yesterday,
  DateTime? now,
}) {
  final date = parseDate(createdAt);
  if (date == null) return '';
  final clock = (now ?? DateTime.now()).toLocal();
  final lang = language(locale);
  final age = _localDay(clock) - _localDay(date);
  final time = formatDate('jm', lang, date);
  if (age == 0) return '$today $time';
  if (age == 1) return '$yesterday $time';
  if (age >= 2 && age <= 6) return '${formatDate('EEEE', lang, date)} $time';
  final day = formatDate(
    date.year != clock.year ? 'yMMMd' : 'MMMd',
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
