// Q2: Arabic dates keep Latin digits with the date symbols the app really loads. The app registers
// GlobalMaterialLocalizations, whose `ar` symbols print Arabic-Indic digits (ZERODIGIT '٠');
// the other l10n tests run with intl's own symbols, which print Latin digits.
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';
import 'package:lonora/l10n/l10n.dart';

void main() {
  setUpAll(() async {
    await ensureDateFormatting();
    await GlobalMaterialLocalizations.delegate.load(const Locale('ar'));
  });

  final date = DateTime(2026, 11, 26, 8, 15);

  test('the loaded Arabic symbols print Arabic-Indic digits', () {
    expect(DateFormat('d MMM y', 'ar').format(date), contains('٢٦'));
  });

  test('formatDate prints Latin digits in Arabic', () {
    final text = formatDate('d MMM y', 'ar', date);
    expect(text, '26 نوفمبر 2026');
    expect(formatDate('jm', 'ar', date), '8:15 ص');
    expect(text, isNot(contains(RegExp('[٠-٩۰-۹]'))));
  });

  test('the conversation separator and capability dates follow', () {
    final now = DateTime(2026, 11, 26, 12);
    expect(
      formatTimeSeparator(
        date,
        'ar',
        today: 'اليوم',
        yesterday: 'أمس',
        now: now,
      ),
      'اليوم 8:15 ص',
    );
    expect(
      formatTimeSeparator(
        DateTime(2025, 3, 14, 9, 5),
        'ar',
        today: 'اليوم',
        yesterday: 'أمس',
        now: now,
      ),
      '14 مارس 2025 9:05 ص',
    );
  });

  test('English is unchanged', () {
    expect(formatDate('d MMM y', 'en', date), '26 Nov 2026');
  });
}
