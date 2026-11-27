// Q2: dates and times of day read in Arabic-Indic digits in Arabic and in Latin digits in English,
// whichever date symbols are loaded; durations, sizes, counts and versions stay Latin, and one
// date label never mixes the two systems. The app registers GlobalMaterialLocalizations, whose
// `ar` symbols print Arabic-Indic digits (ZERODIGIT '٠'); `intl`'s own `ar` symbols print Latin
// ones. The groups run in order: first with intl's symbols, then with the app's.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';
import 'package:lonora/l10n/l10n.dart';

final _indic = RegExp('[٠-٩]');
final _latin = RegExp('[0-9]');

/// One date label uses one digit system.
Matcher get _oneSystem => predicate<String>(
  (s) => !(_indic.hasMatch(s) && _latin.hasMatch(s)),
  'uses one digit system',
);

/// The isolated values (between U+2068 and U+2069) of a metadata line.
final _value = RegExp('\u2068([^\u2069]*)\u2069');

/// A value that is a date or a time of day: a clock or an Arabic month name.
final _dated = RegExp(
  ':|يناير|فبراير|مارس|أبريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|أكتوبر|نوفمبر|ديسمبر',
);

Map<String, Object?> _m(Object? value) =>
    (value as Map).cast<String, Object?>();

void main() {
  setUpAll(ensureDateFormatting);

  final date = DateTime(2026, 11, 26, 8, 15);
  final now = DateTime(2026, 11, 27, 16, 30);
  final samples = <String, String>{};

  String separator(Object at, String locale) =>
      formatTimeSeparator(at, locale, now: now);

  Map<String, String> sample() => {
    'd MMM y': formatDate('d MMM y', 'ar', date),
    'jm': formatDate('jm', 'ar', date),
    'separator': separator(DateTime(2026, 11, 24, 19, 54), 'ar'),
    'readiness': readinessTime('2026-11-25T21:40:00', 'ar', now),
  };

  group('dateDigits', () {
    test('Arabic-Indic in Arabic, Latin in English', () {
      expect(dateDigits('24 نوفمبر 7:54 م', 'ar'), '٢٤ نوفمبر ٧:٥٤ م');
      expect(dateDigits('24 نوفمبر 7:54 م', 'ar-EG'), '٢٤ نوفمبر ٧:٥٤ م');
      expect(dateDigits('Nov 24 7:54 PM', 'en'), 'Nov 24 7:54 PM');
    });

    test('native digits are read by value, so the result is stable', () {
      expect(dateDigits('٢٤ ۲۵', 'en'), '24 25');
      expect(dateDigits('٢٤ ۲۵ 26', 'ar'), '٢٤ ٢٥ ٢٦');
      expect(dateDigits(dateDigits('09:05', 'ar'), 'ar'), '٠٩:٠٥');
    });

    test('text without digits is unchanged', () {
      expect(dateDigits('الثلاثاء', 'ar'), 'الثلاثاء');
      expect(dateDigits('', 'ar'), '');
    });
  });

  group('with intl\'s own symbols', () {
    test('intl prints Latin digits for ar, formatDate maps them', () {
      expect(DateFormat('d MMM y', 'ar').format(date), contains('26'));
      expect(formatDate('d MMM y', 'ar', date), '٢٦ نوفمبر ٢٠٢٦');
      expect(formatDate('jm', 'ar', date), '٨:١٥ ص');
      samples.addAll(sample());
    });
  });

  group('with the app\'s symbols', () {
    setUpAll(() async {
      await GlobalMaterialLocalizations.delegate.load(const Locale('ar'));
      // intl keeps the last locale's symbols; another locale makes it read the new `ar` ones.
      DateFormat('y', 'en').format(date);
    });

    test('the loaded Arabic symbols print Arabic-Indic digits', () {
      expect(DateFormat('d MMM y', 'ar').format(date), contains('٢٦'));
    });

    test('formatDate prints the same text whichever symbols are loaded', () {
      expect(samples, isNotEmpty);
      expect(sample(), samples);
    });

    test('Arabic dates and times read in Arabic-Indic digits', () {
      final text = formatDate('d MMM y', 'ar', date);
      expect(text, '٢٦ نوفمبر ٢٠٢٦');
      expect(formatDate('jm', 'ar', date), '٨:١٥ ص');
      expect(text, isNot(contains(_latin)));
    });

    test('English is unchanged', () {
      expect(formatDate('d MMM y', 'en', date), '26 Nov 2026');
      expect(formatDate('jm', 'en', date), '8:15 AM');
    });

    test('hand-built clocks follow when given the language', () {
      expect(clockTime('2026-11-27T09:05:00', lang: 'ar'), '٠٩:٠٥');
      expect(clockTime('2026-11-27T21:40:00', lang: 'en'), '21:40');
      // Without a language: Latin, as before (callers pass their language).
      expect(clockTime('2026-11-27T09:05:00'), '09:05');
    });

    test('durations, sizes and counts keep Latin digits in Arabic', () {
      expect(voiceClock(65), '1:05');
      expect(voiceClock(5, twoDigitMinutes: true), '00:05');
      expect(voiceClock(3600, twoDigitMinutes: true), '60:00');
      expect(formatFileSize(1024 * 1024 * 18.16, 'ar'), '18.2 MB');
      expect(formatNumber(1234.5, 'ar'), '1,234.5');
      expect(
        [
          voiceClock(65),
          formatFileSize(2048, 'ar'),
          formatNumber(12, 'ar'),
        ].join(),
        isNot(contains(_indic)),
      );
    });

    test('trading and capability dates follow, isolated', () {
      expect(
        readinessTime('2026-11-27T09:05:00', 'ar', now),
        isolate('٠٩:٠٥ ص'),
      );
      expect(
        readinessTime('2026-11-25T21:40:00', 'ar', now),
        isolate('٢٥ نوفمبر، ٠٩:٤٠ م'),
      );
      expect(
        readinessTime('2026-11-25T21:40:00', 'en', now),
        isolate('Nov 25, 09:40 PM'),
      );
      final line = sourceLine({
        'kind': 'github',
        'label': 'anthropics',
        'added_via': 'owner',
        'active': true,
        'last_used_at': '2026-11-25T10:00:00',
      }, 'ar');
      expect(line, contains(isolate('٢٥ نوفمبر')));
    });

    test('no date label mixes the two systems', () {
      final labels = [
        ...sample().values,
        separator(DateTime(2025, 3, 2, 7, 15), 'ar'),
        formatDate('yMd', 'ar', date),
        formatDate('MMMMd', 'ar', date),
        clockTime(date, lang: 'ar'),
        readinessTime('2026-11-27T09:05:00', 'ar', now),
      ];
      for (final label in labels) {
        expect(label, _oneSystem, reason: label);
        expect(label, contains(_indic), reason: label);
      }
    });
  });

  // The composite lines of the dated functions (the TS ports compared digit by value in
  // core_cases_test.dart) keep each value in one system: a date or time of day in Arabic-Indic, a
  // count, volume or account number in Latin, side by side on one line.
  group('dated lines, one system per value', () {
    final cases = (jsonDecode(
      File('test/l10n/fixtures/core_cases.json').readAsStringSync(),
    ) as List).cast<Map<String, dynamic>>();
    final now = DateTime(2026, 11, 27, 16, 30);

    /// The Arabic rows of [fn], run through [call].
    List<String> arabic(String fn, Object? Function(List<dynamic> a) call) => [
      for (final row in cases)
        if (row['fn'] == fn && (row['args'] as List).contains('ar'))
          jsonEncode(call(row['args'] as List)),
    ];

    final functions = <String, Object? Function(List<dynamic> a)>{
      'ownerActionCard': (a) =>
          ownerActionCard(_m(a[0]), a[1], DateTime.parse(a[2])).toJson(),
      'watchUntil': (a) => watchUntil(_m(a[0]), a[1], DateTime.parse(a[2])),
      'agentStatusLine': (a) =>
          agentStatusLine(_m(a[0]), a[1], DateTime.parse(a[2])),
      'sourceLine': (a) => sourceLine(_m(a[0]), a[1]),
      'serverLine': (a) => serverLine(_m(a[0]), a[1]),
      'readinessTime': (a) => readinessTime(a[0], a[1], DateTime.parse(a[2])),
      'tradingReadinessLine': (a) {
        final names = _m(a[3]);
        return tradingReadinessLine(
          _m(a[0]),
          a[1],
          DateTime.parse(a[2]),
          (id) => names[id] as String?,
        );
      },
    };

    for (final MapEntry(key: fn, value: call) in functions.entries) {
      test('$fn: dates and times Arabic-Indic, other values Latin', () {
        var dated = 0;
        for (final out in arabic(fn, call)) {
          for (final match in _value.allMatches(out)) {
            final value = match[1]!;
            expect(value, _oneSystem, reason: out);
            if (_dated.hasMatch(value) && value.contains(RegExp('[0-9٠-٩]'))) {
              dated++;
              expect(value, isNot(contains(_latin)), reason: out);
            } else {
              expect(value, isNot(contains(_indic)), reason: out);
            }
          }
        }
        expect(dated, greaterThan(0), reason: 'no dated Arabic row for $fn');
      });
    }

    test('the lines read as pinned', () {
      final card = ownerActionCard(
        {
          'id': 'card-1',
          'kind': 'settle_operation',
          'status': 'pending',
          'facts': {
            'several_accounts': false,
            'operation': {
              'operation_id': 'op1',
              'action': 'buy',
              'symbol': 'XAUUSD',
              'volume': '0.10',
              'has_ticket': false,
              'status': 'ambiguous',
              'submitted_at': '2026-11-27T09:05:00',
              'by_agent_name': 'Atlas',
              'by_owner': false,
            },
          },
          'expires_at': '2026-11-27T16:30:00',
        },
        'ar',
        now,
      );
      expect(
        card.lines[1],
        'شراء سوقي ${isolate('0.10')} ${isolate('XAUUSD')}$dotSeparatorفي '
        '${isolate('٠٩:٠٥ ص')}$dotSeparatorمن ${isolate('Atlas')}',
      );
      expect(
        watchUntil({'expires_at': '2026-11-25T21:40:00'}, 'ar', now),
        'حتى ${isolate('٢٥ نوفمبر، ٠٩:٤٠ م')}',
      );
      expect(
        agentStatusLine(
          {
            'state': 'idle',
            'phase': 'monitoring',
            'watch_count': 3,
            'watches': [
              {
                'kind': 'price',
                'symbol': 'XAUUSD',
                'condition': 'above',
                'level': '2100',
                'expires_at': '2026-11-27T09:05:00',
                'lifecycle': 'active',
              },
            ],
          },
          'ar',
          now,
        ),
        'يراقب ${isolate('XAUUSD')} حتى ${isolate('٠٩:٠٥ ص')}$dotSeparator'
        '${isolate('2')} أخرى',
      );
      expect(
        serverLine({
          'name': 'Docs',
          'enabled': true,
          'trusted_tier': 'read',
          'trusted_tools': ['a', 'b'],
          'last_used_at': '2026-11-25T21:40:00',
        }, 'ar'),
        endsWith('آخر استخدام ${isolate('٢٥ نوفمبر')}'),
      );
      expect(
        tradingReadinessLine(
          {
            'state': 'on_its_own',
            'params': {
              'symbol_scope': 'account',
              'valid_until': '2026-11-27T09:05:00',
            },
          },
          'ar',
          now,
          (_) => null,
        ),
        endsWith('حتى ${isolate('٠٩:٠٥ ص')}'),
      );
    });
  });

  group('time separators', () {
    test('today: the time alone, 12-hour with ص/م', () {
      expect(separator(DateTime(2026, 11, 27, 8, 56), 'ar'), '٨:٥٦ ص');
      expect(separator(DateTime(2026, 11, 27, 19, 31), 'ar'), '٧:٣١ م');
      expect(separator('2026-11-27T00:05:00', 'ar'), '١٢:٠٥ ص');
      expect(separator(DateTime(2026, 11, 27, 8, 56), 'en'), '8:56 AM');
    });

    test('any other day: day and month, then the time', () {
      // Yesterday and the days of this week are dates too (no «أمس», no weekday).
      expect(separator('2026-11-26T23:59:00', 'ar'), '٢٦ نوفمبر ١١:٥٩ م');
      expect(
        separator(DateTime(2026, 11, 24, 19, 54), 'ar'),
        '٢٤ نوفمبر ٧:٥٤ م',
      );
      expect(separator('2026-01-05T08:00:00', 'ar'), '٥ يناير ٨:٠٠ ص');
      expect(
        separator(DateTime(2026, 11, 24, 19, 54), 'en'),
        'November 24 7:54 PM',
      );
      expect(separator('2026-11-28T01:00:00', 'ar'), '٢٨ نوفمبر ١:٠٠ ص');
    });

    test('another year: with the year', () {
      expect(separator('2025-03-02T07:15:00', 'ar'), '٢ مارس ٢٠٢٥ ٧:١٥ ص');
      expect(separator('2025-03-02T07:15:00', 'en'), 'March 2, 2025 7:15 AM');
    });

    test('an invalid date reads nothing; today/yesterday are ignored', () {
      expect(separator('not a date', 'ar'), '');
      expect(
        formatTimeSeparator(
          DateTime(2026, 11, 26, 9, 5),
          'ar',
          today: 'اليوم',
          yesterday: 'أمس',
          now: now,
        ),
        '٢٦ نوفمبر ٩:٠٥ ص',
      );
    });
  });
}
