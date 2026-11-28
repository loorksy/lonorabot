// «فتح أمر»: the order ticket (TradeActionCard.tsx) with every rule checked before its review,
// the review the owner confirms, the held order shown locked with «فحص العملية الحالية», and
// the pauses. Every execute is answered by the fake API.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FButton;
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/market/market_data.dart';
import 'package:lonora/features/market/market_screen.dart';
import 'package:lonora/features/trading/trade_rules.dart';
import 'package:lonora/features/trading/trade_sheets.dart';
import 'package:lonora/features/trading/trades_data.dart';

import '../market/market_fixtures.dart' as market;
import 'trade_harness.dart';

String _label(MarketConnection c) => c.id == 'acct-1'
    ? 'Lonora Sim · 5021 · Paper-1'
    : 'Demo Broker · 880021 · Live-3';

class _Host extends StatelessWidget {
  const _Host({this.connections});

  final List<Map<String, Object?>>? connections;

  @override
  Widget build(BuildContext context) => Center(
    child: BlockButton(
      label: 'open',
      expand: false,
      onPressed: () => showOrderTicket(
        context,
        connections: [
          for (final c in connections ?? [simConnection, liveConnection()])
            MarketConnection.fromJson(c),
        ],
        accountId: 'acct-1',
        symbol: 'XAUUSD',
        label: _label,
      ),
    ),
  );
}

Future<void> _open(
  WidgetTester tester, {
  String locale = 'ar',
  Brightness brightness = Brightness.light,
  List<Map<String, Object?>>? connections,
}) async {
  await pumpWpf(
    tester,
    _Host(connections: connections),
    locale: locale,
    brightness: brightness,
    store: tradeStore(locale: locale),
  );
  await tapAndSettle(tester, find.text('open'));
}

Finder _field(String label) => find.descendant(
  of: find.ancestor(of: find.text(label), matching: find.byType(LnTextField)),
  matching: find.byType(TextField),
);

void main() {
  setUpAll(setUpWpf);
  setUp(resetTrades);

  testWidgets(
    'a market order: no price field, reviewed, sent once with exact decimals',
    (tester) async {
      scriptTrades();
      tradeApi.on(
        'POST /trading/execute',
        (body, _) => executorAnswer(
          body,
          'confirmed',
          details: {
            'verification': {'status': 'verified'},
            'price': '2381.20',
          },
        ),
      );
      await _open(tester, locale: 'en');
      expect(find.text('Trade action'), findsOneWidget);
      expect(find.text('XAUUSD'), findsOneWidget);
      expect(find.text('Order price'), findsNothing);
      await tester.enterText(_field('Volume'), '٠٫١٠');
      await tester.enterText(_field('Stop loss · optional'), '2365');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, buttonLabelled('Review the order'));
      expect(
        find.bySemanticsLabel(RegExp(r'^Type: At market price')),
        findsOneWidget,
      );
      expect(find.bySemanticsLabel(RegExp(r'^Volume: .*0\.1')), findsOneWidget);
      expect(find.bySemanticsLabel(RegExp(r'^Take profit: —')), findsOneWidget);
      expect(find.textContaining('real money'), findsNothing);
      expect(tradeApi.executed, isEmpty);
      await tapAndSettle(tester, buttonLabelled('Execute'));
      final body = tradeApi.executed.single;
      expect(body, {
        'account_id': 'acct-1',
        'action': 'buy',
        'symbol': 'XAUUSD',
        'volume': '0.1',
        'stop_loss': '2365',
        'operation_id': body['operation_id'],
      });
      expect(find.textContaining('Confirmed'), findsWidgets);
      expect(find.textContaining('Broker price'), findsWidgets);
      // Settled: the form is free again, its values kept.
      expect(find.widgetWithText(FButton, 'Review the order'), findsOneWidget);
      await settleToasts(tester);
      await unmount(tester);
    },
  );

  testWidgets(
    'a pending entry needs its price; every rule is checked before the review',
    (tester) async {
      scriptTrades();
      await _open(tester, locale: 'en');
      // The broker's limits are shown with the volume.
      expect(find.textContaining('Minimum volume'), findsOneWidget);
      await tapAndSettle(tester, find.text('Buy limit'));
      expect(find.text('Order price'), findsOneWidget);
      await tapAndSettle(tester, buttonLabelled('Review the order'));
      expect(find.text('This field is required.'), findsNWidgets(2));
      await tester.enterText(_field('Volume'), '0.015');
      await tester.enterText(_field('Order price'), '2350.005');
      await tester.enterText(_field('Take profit · optional'), '0');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, buttonLabelled('Review the order'));
      expect(
        find.text('The volume goes up from 0.01 in steps of 0.01.'),
        findsOneWidget,
      );
      expect(
        find.text('The price must be a multiple of 0.01.'),
        findsOneWidget,
      );
      expect(find.text('The value must be greater than zero.'), findsOneWidget);
      expect(tradeApi.executed, isEmpty);
      await unmount(tester);
    },
  );

  testWidgets(
    'an unsettled order locks the form, even reopened; the check resends it',
    (tester) async {
      scriptTrades();
      final statuses = ['ambiguous', 'resolved'];
      tradeApi.on(
        'POST /trading/execute',
        (body, _) => executorAnswer(body, statuses.removeAt(0)),
      );
      await _open(tester);
      await tester.enterText(_field('الحجم'), '0.2');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, buttonLabelled('مراجعة الأمر'));
      await tapAndSettle(tester, buttonLabelled('تنفيذ'));
      expect(find.textContaining('لن يُرسل هذا الطلب مجددًا'), findsWidgets);
      expect(
        find.widgetWithText(FButton, 'فحص العملية الحالية'),
        findsOneWidget,
      );
      expect(tester.widget<TextField>(_field('الحجم')).enabled, isFalse);
      // Closed and opened again: still the held order, locked.
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      await settleToasts(tester);
      await tapAndSettle(tester, find.text('open'));
      expect(tester.widget<TextField>(_field('الحجم')).controller!.text, '0.2');
      expect(tester.widget<TextField>(_field('الحجم')).enabled, isFalse);
      await tapAndSettle(tester, buttonLabelled('فحص العملية الحالية'));
      await tapAndSettle(tester, buttonLabelled('فحص العملية الحالية'));
      expect(tradeApi.executed, hasLength(2));
      expect(
        tradeApi.executed[1]['operation_id'],
        tradeApi.executed[0]['operation_id'],
      );
      expect(OrderDesk.instance.held(testScope, openKey('acct-1')), isNull);
      await settleToasts(tester);
      await unmount(tester);
    },
  );

  testWidgets(
    'a check confirmed after the journal settled the order sends nothing more',
    (tester) async {
      scriptTrades();
      tradeApi.on(
        'POST /trading/execute',
        (body, _) => executorAnswer(body, 'submitted'),
      );
      await _open(tester, locale: 'en');
      await tester.enterText(_field('Volume'), '0.2');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, buttonLabelled('Review the order'));
      await tapAndSettle(tester, buttonLabelled('Execute'));
      final id = tradeApi.executed.single['operation_id'] as String;
      await settleToasts(tester);
      await tapAndSettle(tester, buttonLabelled('Check existing operation'));
      expect(
        find.bySemanticsLabel(RegExp(r'^Existing operation since: ')),
        findsOneWidget,
      );
      // Meanwhile the Market tab's journal reload settles it (filled).
      await tester.runAsync(
        () => OrderDesk.instance.settle(testScope, 'acct-1', [
          JournalEntry(
            journalRow(
              id,
              action: 'buy',
              status: 'resolved',
              agentId: null,
              extraRequest: {'volume': '0.2'},
              resolution: {'source': 'owner', 'outcome': 'executed'},
            ),
          ),
        ]),
      );
      await tester.pump();
      // The owner confirms what the review calls a check: nothing new is sent.
      await tapAndSettle(tester, buttonLabelled('Check existing operation'));
      expect(tradeApi.executed, hasLength(1));
      expect(OrderDesk.instance.held(testScope, openKey('acct-1')), isNull);
      // The form is free again, its values kept.
      expect(find.widgetWithText(FButton, 'Review the order'), findsOneWidget);
      expect(
        tester.widget<TextField>(_field('Volume')).controller!.text,
        '0.2',
      );
      await settleToasts(tester);
      await unmount(tester);
    },
  );

  testWidgets(
    'a refusal before anything was journaled unlocks the form, values kept',
    (tester) async {
      scriptTrades();
      tradeApi.on(
        'POST /trading/execute',
        (_, _) => throw ApiError(status: 409, code: 'market_quote_stale'),
      );
      await _open(tester);
      await tester.enterText(_field('الحجم'), '0.2');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, buttonLabelled('مراجعة الأمر'));
      await tapAndSettle(tester, buttonLabelled('تنفيذ'));
      expect(find.textContaining('سعر السوق قديم الآن'), findsOneWidget);
      expect(find.widgetWithText(FButton, 'مراجعة الأمر'), findsOneWidget);
      expect(tester.widget<TextField>(_field('الحجم')).enabled, isTrue);
      expect(tester.widget<TextField>(_field('الحجم')).controller!.text, '0.2');
      await unmount(tester);
    },
  );

  testWidgets(
    'a broker account is chosen from the ticket; its review warns of real money',
    (tester) async {
      scriptTrades();
      await _open(tester, locale: 'en');
      await tapAndSettle(tester, find.text('Demo Broker · 880021 · Live-3'));
      await tester.enterText(_field('Volume'), '1');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, buttonLabelled('Review the order'));
      expect(
        find.textContaining('may execute with real money'),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel(RegExp(r'^Account: .*Demo Broker')),
        findsOneWidget,
      );
      await tapAndSettle(tester, buttonLabelled('Cancel'));
      expect(tradeApi.executed, isEmpty);
      await unmount(tester);
    },
  );

  testWidgets(
    'no order while the broker refuses trading or cannot be verified',
    (tester) async {
      scriptTrades(account: accountState(investorMode: true));
      await _open(tester, locale: 'en');
      expect(
        find.text(
          'This broker account does not permit trading. Check its trading permissions.',
        ),
        findsOneWidget,
      );
      expect(
        tester.widget<FButton>(buttonLabelled('Review the order')).onPress,
        isNull,
      );
      await unmount(tester);
      final recovering = <Map<String, Object?>>[
        {
          ...simConnection,
          'state': {
            'broker_recovery': {'status': 'recovering'},
          },
        },
      ];
      scriptTrades(connections: recovering);
      await _open(tester, locale: 'en', connections: recovering);
      expect(
        find.textContaining('new orders and protection changes are paused'),
        findsOneWidget,
      );
      expect(
        tester.widget<FButton>(buttonLabelled('Review the order')).onPress,
        isNull,
      );
      await unmount(tester);
    },
  );

  testWidgets('an instrument that cannot be read stops the review', (
    tester,
  ) async {
    scriptTrades();
    tradeApi.on(
      'GET /market/instrument',
      (_, _) =>
          throw ApiError(status: 503, code: 'broker_instrument_unavailable'),
    );
    await _open(tester, locale: 'en');
    expect(
      find.text(
        'The broker specifications are unavailable for this exact symbol.',
      ),
      findsOneWidget,
    );
    expect(
      tester.widget<FButton>(buttonLabelled('Review the order')).onPress,
      isNull,
    );
    await unmount(tester);
  });

  testWidgets('the Market symbol sheet opens the ticket', (tester) async {
    market.scriptMarket();
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await tapAndSettle(tester, find.text('XAUUSD').first);
    await scrollTo(tester, find.text('Open an order'));
    await tapAndSettle(tester, find.text('Open an order'));
    expect(find.text('Trade action'), findsOneWidget);
    expect(find.text('Exact broker symbol'), findsOneWidget);
    expect(tradeApi.executed, isEmpty);
    await unmount(tester);
  });

  testWidgets('48 dp fields and chips; English left to right', (tester) async {
    scriptTrades();
    await _open(tester, locale: 'en');
    expect(
      Directionality.of(tester.element(find.byType(OrderTicket))),
      TextDirection.ltr,
    );
    for (final chip in find.byType(LnChoiceChip).evaluate()) {
      expect(
        tester.getSize(find.byWidget(chip.widget)).height,
        greaterThanOrEqualTo(48),
      );
    }
    // The kit keeps forui's field box and lays a touch band of at least 48 dp around it.
    for (final f in find.byType(LnTextField).evaluate()) {
      final band = find.ancestor(
        of: find.descendant(
          of: find.byWidget(f.widget),
          matching: find.byType(TextField),
        ),
        matching: find.byWidgetPredicate(
          (w) => w.runtimeType.toString() == '_TouchBand',
        ),
      );
      expect(band, findsOneWidget);
      expect(tester.getSize(band).height, greaterThanOrEqualTo(48));
    }
    await unmount(tester);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ticket ${v.name}', (tester) async {
      scriptTrades();
      await withRealShadows(() async {
        await _open(tester, locale: v.locale, brightness: v.brightness);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/ticket_${v.name}.png'),
        );
      });
      await unmount(tester);
    });

    testWidgets('golden review of a live order ${v.name}', (tester) async {
      scriptTrades();
      await withRealShadows(() async {
        await _open(tester, locale: v.locale, brightness: v.brightness);
        await tapAndSettle(tester, find.text('Demo Broker · 880021 · Live-3'));
        await tapAndSettle(
          tester,
          find.text(v.locale == 'ar' ? 'شراء بحد سعري' : 'Buy limit'),
        );
        await tester.enterText(
          _field(v.locale == 'ar' ? 'الحجم' : 'Volume'),
          '0.5',
        );
        await tester.enterText(
          _field(v.locale == 'ar' ? 'سعر الأمر' : 'Order price'),
          '2350.5',
        );
        await tester.enterText(
          _field(
            v.locale == 'ar' ? 'وقف الخسارة · اختياري' : 'Stop loss · optional',
          ),
          '2330',
        );
        await tester.pumpAndSettle();
        await tapAndSettle(
          tester,
          buttonLabelled(
            v.locale == 'ar' ? 'مراجعة الأمر' : 'Review the order',
          ),
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/ticket_review_${v.name}.png'),
        );
      });
      expect(tradeApi.executed, isEmpty);
      await unmount(tester);
    });
  }
}
