// The L10n runtime: loading, lookup and fallbacks, filling, registration, locale changes,
// the delegate, error text precedence, attention titles and RTL detection.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/l10n/core/values.dart' show jsString;
import 'package:lonora/l10n/l10n.dart';

List<Map<String, dynamic>> fixture(String name) =>
    (jsonDecode(File('test/l10n/fixtures/$name').readAsStringSync()) as List)
        .cast<Map<String, dynamic>>();

L10n small() => L10n(
  ar: {'hello': 'مرحبًا {name}', 'count': '{0} من {1}', 'arOnly': 'فقط'},
  en: {'hello': 'Hello {name}', 'count': '{0} of {1}', 'enOnly': 'Only'},
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late L10n l10n;

  setUp(() async {
    l10n = await L10n.load();
  });

  group('load', () {
    test('reads both catalogs from the assets, Arabic first', () {
      expect(l10n.keys.length, 815);
      expect(L10n.instance, same(l10n));
      expect(l10n.locale, const Locale('ar'));
      expect(l10n.isRtl, isTrue);
      expect(l10n.textDirection, TextDirection.rtl);
      expect(l10n.t('today'), 'اليوم');
      expect(l10n.translate('today', 'en'), 'Today');
      expect(l10n.t('incoming.accept'), 'رد');
    });
  });

  group('t', () {
    test('returns the raw label without values', () {
      expect(l10n.t('sh_unreadN'), '{count} غير مقروءة');
    });

    test('fills positional and named placeholders', () {
      expect(l10n.t('sh_unreadN', const [], {'count': 3}), '3 غير مقروءة');
      l10n.setLocale(const Locale('en'));
      expect(l10n.t('sh_unreadN', const [], {'count': 3}), '3 unread');
      expect(l10n.t('running_stopOne', ['npm test']), 'Stop npm test');
      final labels = small();
      expect(labels.t('count', [1, 2]), '1 من 2');
      expect(labels.t('hello', const [], {'name': 'سارة'}), 'مرحبًا سارة');
    });

    test('fill matches the TS fill() on every fixture', () {
      for (final row in fixture('fill.json')) {
        final values = row['values'];
        final out = row['mode'] == 'named'
            ? fill(
                row['template'] as String,
                null,
                (values as Map).cast<String, Object?>(),
              )
            : fill(row['template'] as String, (values as List).cast<Object?>());
        expect(out, row['out'], reason: jsonEncode(row));
      }
    });

    test('prints values as JavaScript does', () {
      expect(fill('{0}', [2.0]), '2');
      expect(fill('{0}', [1.5]), '1.5');
      expect(fill('{0}', [double.nan]), 'NaN');
      expect(fill('{0}', [true]), 'true');
      expect(fill('{n}', null, {'n': -0.0}), '0');
      expect(jsString(1e21), '1e+21');
      expect(fill('{0} {name}', ['a'], {'name': 'b'}), 'a b');
    });
  });

  group('fallbacks', () {
    test('a key missing in the current language reads in English', () {
      final labels = small();
      expect(labels.t('enOnly'), 'Only');
      expect(labels.debugMissingKeys, contains('ar:enOnly'));
    });

    test('a key missing everywhere reads as the key', () {
      final labels = small();
      expect(labels.t('nope'), 'nope');
      expect(labels.debugMissingKeys, contains('ar:nope'));
      labels.setLocale(const Locale('en'));
      expect(labels.t('arOnly'), 'arOnly');
    });
  });

  group('register', () {
    test('adds Android-only labels as [ar, en]', () {
      l10n.register({
        'android_battery': ['البطارية', 'Battery'],
      });
      expect(l10n.t('android_battery'), 'البطارية');
      expect(l10n.translate('android_battery', 'en'), 'Battery');
      // The same words again are fine.
      l10n.register({
        'android_battery': ['البطارية', 'Battery'],
      });
    });

    test('never replaces Lonora\'s own words', () {
      expect(
        () => l10n.register({
          'today': ['يوم', 'Day'],
        }),
        throwsA(isA<AssertionError>()),
      );
      expect(l10n.t('today'), 'اليوم');
      expect(
        () => l10n.register({
          'bad': ['one'],
        }),
        throwsArgumentError,
      );
    });
  });

  group('locale', () {
    test('setLocale normalises to ar or en and notifies', () {
      final seen = <Locale>[];
      l10n.localeListenable.addListener(
        () => seen.add(l10n.localeListenable.value),
      );
      l10n.setLocale(const Locale('en', 'GB'));
      l10n.setLocale(const Locale('ar', 'SA'));
      l10n.setLocale(const Locale('fr'));
      expect(seen, const [Locale('en'), Locale('ar'), Locale('en')]);
      expect(l10n.lang, 'en');
      expect(l10n.isRtl, isFalse);
    });

    testWidgets('the delegate and context.t follow the app locale', (
      tester,
    ) async {
      Widget app(Locale locale) => Localizations(
        locale: locale,
        delegates: [l10n.delegate, GlobalWidgetsLocalizations.delegate],
        child: Builder(
          builder: (context) => Text(
            '${context.t('today')} ${context.l10n.chatsWord(2)}',
            textDirection: context.l10n.textDirection,
          ),
        ),
      );
      await tester.pumpWidget(app(const Locale('ar')));
      expect(find.text('اليوم محادثتان'), findsOneWidget);
      await tester.pumpWidget(app(const Locale('en')));
      await tester.pump();
      expect(find.text('Today 2 chats'), findsOneWidget);
      expect(l10n.lang, 'en');
      expect(l10n.delegate.isSupported(const Locale('de')), isFalse);
    });
  });

  group('errorText', () {
    test('no HTTP answer reads network', () {
      expect(l10n.errorText(null), l10n.t('network'));
    });

    test('each shared table answers for its own codes', () {
      expect(
        l10n.errorText('agent_analysis_only'),
        agentPermissionError('agent_analysis_only', 'ar'),
      );
      expect(
        l10n.errorText('broker_state_changed'),
        financialBoundaryError('broker_state_changed', 'ar'),
      );
      expect(
        l10n.errorText('owner_action_not_found'),
        ownerActionErrors['owner_action_not_found']!.ar,
      );
      expect(
        l10n.errorText('chatgpt_state_mismatch'),
        chatgptErrors['chatgpt_state_mismatch']!.ar,
      );
      expect(
        l10n.errorText('invalid_timezone'),
        ownerProfileErrors['invalid_timezone']!.ar,
      );
    });

    test(
      'then the app label with the same key, the fallback, request_failed',
      () {
        expect(
          l10n.errorText('voice_permission_denied'),
          l10n.t('voice_permission_denied'),
        );
        expect(l10n.errorText('nope', fallback: 'Custom'), 'Custom');
        expect(l10n.errorText('nope'), l10n.t('request_failed'));
        l10n.setLocale(const Locale('en'));
        expect(l10n.errorText('nope'), 'The request failed. Try again.');
      },
    );

    test('the shared tables come before a label with the same key', () {
      final tables = [
        'agent_analysis_only',
        'broker_state_changed',
        'owner_action_not_found',
        'chatgpt_state_mismatch',
        'invalid_timezone',
      ];
      for (final code in tables) {
        expect(
          errorTextFor(
            code,
            'en',
            label: (_) => 'LABEL',
            hasLabel: (_) => true,
          ),
          isNot('LABEL'),
          reason: code,
        );
      }
    });
  });

  group('attentionTitle', () {
    test('names each code with its label', () {
      expect(
        attentionTitle(l10n, 'approval_required'),
        l10n.t('attentionApproval'),
      );
      expect(
        attentionTitle(l10n, 'brand_new_code'),
        l10n.t('attentionUpdated'),
      );
    });

    test('a refused model names its provider and the failure family', () {
      l10n.setLocale(const Locale('en'));
      expect(
        attentionTitle(
          l10n,
          'model_access_failed',
          reason: 'auth',
          providerName: 'OpenAI',
        ),
        'Model key rejected by OpenAI',
      );
      expect(
        attentionTitle(l10n, 'model_access_failed', reason: 'auth'),
        'Model key rejected by your OpenAI-compatible endpoint',
      );
      expect(
        attentionTitle(l10n, 'model_access_failed', reason: 'weird'),
        l10n.t('attentionModelAccessFailed'),
      );
    });
  });

  group('direction', () {
    test('any Arabic letter reads right to left', () {
      expect(isRtlText('مرحبا'), isTrue);
      expect(isRtlText('Hello مرحبا'), isTrue);
      expect(isRtlText('Hello'), isFalse);
      expect(isRtlText('١٢٣ ٪'), isFalse);
      expect(readingDirection('Hello'), TextDirection.ltr);
      expect(readingDirection('123'), isNull);
      expect(textDirectionFor('123', TextDirection.rtl), TextDirection.rtl);
    });

    test('isolate and ltr wrap a value and drop its own controls', () {
      expect(isolate('XAUUSD'), '\u{2068}XAUUSD\u{2069}');
      expect(isolate('a\u{2069}b'), '\u{2068}ab\u{2069}');
      expect(ltr('https://x.io/a'), '\u{2066}https://x.io/a\u{2069}');
      expect(ltr('\u{202e}x'), '\u{2066}x\u{2069}');
      expect(listSeparator('ar'), '، ');
      expect(listSeparator('en'), ', ');
    });
  });

  group('formatting', () {
    test('voice notes read m:ss, the recorder mm:ss', () {
      expect(voiceClock(0), '0:00');
      expect(voiceClock(5.4), '0:05');
      expect(voiceClock(65), '1:05');
      expect(voiceClock(-3), '0:00');
      expect(voiceClock(3600), '60:00');
      expect(voiceClock(5.4, twoDigitMinutes: true), '00:05');
      expect(voiceClock(65, twoDigitMinutes: true), '01:05');
    });

    test('the separator is the time today, else the date and time', () {
      final now = DateTime(2026, 11, 27, 16, 30);
      expect(
        l10n.timeSeparator(DateTime(2026, 11, 27, 9, 5), now: now),
        '٩:٠٥ ص',
      );
      expect(
        l10n.timeSeparator('2026-11-26T21:40:00', now: now),
        '٢٦ نوفمبر ٩:٤٠ م',
      );
      l10n.setLocale(const Locale('en'));
      expect(
        l10n.timeSeparator('2026-11-26T21:40:00', now: now),
        'November 26 9:40 PM',
      );
      expect(formatNumber(1234.5, 'ar'), '1,234.5');
    });
  });
}
