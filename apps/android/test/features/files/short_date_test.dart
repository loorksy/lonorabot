// The files' short dates follow the date-digit rule: Arabic-Indic digits in Arabic, Latin in
// English; and a capture's stamp prints its date and time (not the literal pattern).
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/features/files/files_data.dart';
import 'package:lonora/features/rich/visual/visual_view.dart';
import 'package:lonora/l10n/l10n.dart';

void main() {
  setUpAll(ensureDateFormatting);

  final now = DateTime(2026, 11, 27);

  test('shortDate: day/month this year, day/month/yy before', () {
    expect(shortDate(DateTime(2026, 11, 24), now: now), '24/11');
    expect(shortDate(DateTime(2025, 1, 3), now: now), '3/1/25');
    expect(shortDate(DateTime(2026, 11, 24), now: now, lang: 'ar'), '٢٤/١١');
    expect(shortDate(DateTime(2025, 1, 3), now: now, lang: 'ar'), '٣/١/٢٥');
  });

  test('a capture\'s stamp is its date and its time', () {
    final at = DateTime(2026, 11, 24, 19, 54);
    final en = captureStamp('en', at);
    expect(en, contains('2026'));
    expect(en, contains('7:54'));
    expect(en, isNot(contains('j')));
    final ar = captureStamp('ar', at);
    expect(ar, contains('٢٠٢٦'));
    expect(ar, contains('٧:٥٤'));
    expect(RegExp('[0-9]').hasMatch(ar), isFalse);
  });
}
