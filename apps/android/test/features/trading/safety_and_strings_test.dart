// The order executor's one door, and the words of the owner's orders.
//
// Safety: `POST /trading/execute` appears in one file only, reached only through the review
// sheets; no agent-facing, notification, background or deep-link code imports the order desk.
// Strings: every feature table registers at start-up without an L10n.register clash, each
// trading label has Arabic and English, and errors read Lonora's words — a send without an
// answer never invites a plain retry.
import 'dart:io';

import 'package:flutter/widgets.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/app_strings.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/features/trading/trade_text.dart';
import 'package:lonora/features/trading/trades_data.dart';
import 'package:lonora/features/trading/trading_strings.dart';
import 'package:lonora/l10n/l10n.dart';

/// Arabic letters (the Arabic decimal mark «٫» may be quoted in English).
final _arabic = RegExp(r'[\u0620-\u064A]');

Iterable<File> _dart(String dir) =>
    Directory(dir)
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'));

String _rel(File f) => f.path.replaceFirst(RegExp(r'^.*?/lib/'), 'lib/');

/// [f]'s source without its line comments.
String _code(File f) => f.readAsStringSync().replaceAll(RegExp(r'//.*'), '');

void main() {
  group('the executor has one door', () {
    test(
      'only trades_data.dart names /trading/execute or sends postWithin',
      () {
        final literal = RegExp(r'''['"]/trading/execute['"]''');
        final named = [
          for (final f in _dart('lib'))
            if (literal.hasMatch(f.readAsStringSync())) _rel(f),
        ];
        expect(named, ['lib/features/trading/trades_data.dart']);
        final senders = [
          for (final f in _dart('lib'))
            if (f.readAsStringSync().contains('postWithin(')) _rel(f),
        ]..sort();
        expect(senders, [
          'lib/core/api/api_client.dart',
          'lib/features/trading/trades_data.dart',
        ]);
      },
    );

    test('the desk runs only from the review flows', () {
      // The desk is declared in trades_data.dart and re-exported nowhere: any `.run` (whatever
      // the order of its arguments, as a cascade or a tear-off) in a file importing it.
      final desk = RegExp(r"""(import|export) '[^']*trades_data\.dart""");
      final run = RegExp(r'\.\s*run\b');
      final importers = [
        for (final f in _dart('lib'))
          if (desk.hasMatch(_code(f))) f,
      ];
      expect([
        for (final f in importers)
          if (RegExp(r"export '[^']*trades_data").hasMatch(_code(f))) _rel(f),
      ], isEmpty);
      final runs = [
        for (final f in importers)
          if (run.hasMatch(_code(f))) _rel(f),
      ];
      expect(runs, ['lib/features/trading/trade_flows.dart']);
      final flows = _code(File('lib/features/trading/trade_flows.dart'));
      // One send, in sendReviewed, which every flow calls after its review.
      expect(run.allMatches(flows), hasLength(1));
      expect(
        flows,
        matches(RegExp(r'Future<void> sendReviewed\([\s\S]*?\.\s*run\(')),
      );
      final callers = <String>[];
      for (final f in _dart('lib')) {
        final source = _code(f);
        final sends = RegExp(r'(?<!Future<void> )\bsendReviewed\b')
            .allMatches(source)
            .length;
        if (sends == 0) continue;
        callers.add(_rel(f));
        final reviews = 'showOrderReview('.allMatches(source).length;
        // Each send follows its own review in the same flow.
        expect(reviews, greaterThanOrEqualTo(sends), reason: _rel(f));
      }
      expect(callers..sort(), [
        'lib/features/trading/trade_flows.dart',
        'lib/features/trading/trade_sheets.dart',
      ]);
    });

    test(
      'no agent, card, notification, background or deep-link code imports it',
      () {
        final desk = RegExp(
          r'''import '[^']*(trades_data|trade_flows|trade_sheets)\.dart''',
        );
        final importers = [
          for (final f in _dart('lib'))
            if (desk.hasMatch(f.readAsStringSync())) _rel(f),
        ];
        for (final path in importers) {
          expect(
            path.startsWith('lib/features/trading/') ||
                path == 'lib/features/market/market_screen.dart',
            isTrue,
            reason: path,
          );
        }
      },
    );
  });

  group('words', () {
    setUpAll(() async {
      TestWidgetsFlutterBinding.ensureInitialized();
      await L10n.load();
    });

    test(
      'every table registers at start-up; trading again changes nothing',
      () {
        registerAllStrings();
        registerTradingStrings();
        expect(L10n.instance.has('tr_title'), isTrue);
        expect(L10n.instance.has('rc_title'), isTrue);
      },
    );

    test('each trading label has Arabic and English', () {
      final l = L10n(ar: const {}, en: const {});
      registerTradingStrings(l);
      expect(l.keys.length, greaterThan(100));
      for (final key in l.keys) {
        expect(l.translate(key, 'ar'), contains(_arabic), reason: key);
        expect(l.translate(key, 'en'), isNot(contains(_arabic)), reason: key);
      }
    });

    test(
      'a send without an answer says to check the trades, never to retry',
      () {
        final l10n = L10n.instance;
        for (final lang in ['ar', 'en']) {
          l10n.setLocale(Locale(lang));
          final noAnswer = l10n.t('broker_gateway_no_answer');
          expect(tradeErrorText(l10n, ApiError.network('timeout')), noAnswer);
          expect(tradeErrorText(l10n, ApiError.network()), noAnswer);
          expect(
            tradeErrorText(l10n, ApiError(status: 502, code: 'request_failed')),
            noAnswer,
          );
          expect(
            tradeErrorText(l10n, ApiError(status: 500, code: 'request_failed')),
            l10n.t('tr_uncertainSend'),
          );
          expect(
            tradeErrorText(l10n, const TradeAnswerUnknown()),
            l10n.t('tr_uncertainSend'),
          );
          expect(
            tradeErrorText(
              l10n,
              ApiError(status: 503, code: 'broker_gateway_unavailable'),
            ),
            l10n.t('broker_gateway_unavailable'),
          );
        }
        l10n.setLocale(const Locale('ar'));
      },
    );

    test('known codes read their words; unknown ones the generic line with the code', () {
      final l10n = L10n.instance..setLocale(const Locale('en'));
      String text(String code, [int status = 409]) =>
          tradeErrorText(l10n, ApiError(status: status, code: code));
      expect(text('volume_step_mismatch', 400), contains('volume step'));
      expect(text('position_not_found', 404), contains('no longer open'));
      expect(text('broker_trading_not_allowed'), contains('does not permit'));
      expect(
        text('broker_observation_unavailable'),
        contains('could not be verified'),
      );
      expect(text('broker_account_stale'), l10n.t('tr_accountUnverified'));
      expect(text('market_quote_invalid'), l10n.t('tr_quoteUnusable'));
      final unknown = text('brand_new_refusal');
      expect(unknown, contains('could not be completed'));
      expect(unknown, contains('brand_new_refusal'));
      expect(unknown, contains('\u2066'));
      l10n.setLocale(const Locale('ar'));
    });

    test('a status line: stage, reason, «not sent again» only while unsettled, broker words', () {
      final l10n = L10n.instance..setLocale(const Locale('en'));
      expect(
        outcomeLines(l10n, const TicketOutcome(status: 'submitted')),
        contains(l10n.t('tr_notSentAgain')),
      );
      final rejected = outcomeLines(
        l10n,
        const TicketOutcome(
          status: 'failed',
          code: 'broker_order_rejected',
          details: {'description': 'Market closed'},
        ),
      );
      expect(rejected.first, 'Failed');
      expect(rejected, contains('The broker rejected this order.'));
      expect(rejected.last, contains('Market closed'));
      expect(rejected, isNot(contains(l10n.t('tr_notSentAgain'))));
      final notSent = outcomeLines(
        l10n,
        const TicketOutcome(
          status: 'failed',
          code: 'broker_observation_unavailable',
          details: {'send_state': 'not_sent'},
        ),
      );
      expect(notSent.first, 'Not sent');
      expect(notSent[1], contains('could not be verified'));
      final uncertain = outcomeLines(
        l10n,
        const TicketOutcome(
          status: 'ambiguous',
          code: 'broker_result_ambiguous',
        ),
      );
      expect(uncertain.first, contains('uncertain'));
      expect(uncertain, isNot(contains(l10n.t('tr_notSentAgain'))));
      final confirmed = outcomeLines(
        l10n,
        const TicketOutcome(
          status: 'confirmed',
          brokerId: 'T-1',
          details: {
            'verification': {'status': 'pending'},
            'price': '2380.5',
          },
        ),
      );
      expect(confirmed.first, 'Awaiting broker confirmation');
      expect(confirmed, contains(contains('T-1')));
      expect(confirmed, contains(contains('2380.5')));
      l10n.setLocale(const Locale('ar'));
    });
  });
}
