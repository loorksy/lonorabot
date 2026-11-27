// The chat list's times follow the date-digit rule: clock times, weekdays and dates in
// Arabic-Indic digits in Arabic and Latin in English, one system per label.
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/features/chats/chat_text.dart';
import 'package:lonora/l10n/l10n.dart';

void main() {
  setUpAll(ensureDateFormatting);

  final now = DateTime(2026, 11, 27, 12);

  test('today: the clock; this week: the weekday; else the date', () {
    expect(listTime(DateTime(2026, 11, 27, 9, 5), 'en', now: now), '09:05');
    expect(listTime(DateTime(2026, 11, 27, 9, 5), 'ar', now: now), '٠٩:٠٥');
    expect(listTime(DateTime(2026, 11, 24, 9), 'en', now: now), 'Tuesday');
    expect(listTime(DateTime(2026, 11, 2), 'en', now: now), 'Nov 2');
    expect(listTime(DateTime(2026, 11, 2), 'ar', now: now), '٢ نوفمبر');
    expect(listTime(DateTime(2025, 11, 2), 'ar', now: now), contains('٢٠٢٥'));
  });

  test('no Arabic label mixes the two digit systems', () {
    for (final at in [
      DateTime(2026, 11, 27, 19, 54),
      DateTime(2026, 11, 2),
      DateTime(2024, 3, 14, 8, 1),
    ]) {
      final label = listTime(at, 'ar', now: now);
      expect(RegExp('[0-9]').hasMatch(label), isFalse, reason: label);
    }
  });
}
