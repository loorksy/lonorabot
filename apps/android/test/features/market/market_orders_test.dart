// The Market tab's own orders: a position's menu (edit, close, its market), a pending order's
// cancel, each behind its review; the outage notice that leads to «التعطل والاستعادة». The fake
// API answers every execute, and an unregistered route fails.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FItem;
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/features/market/market_data.dart';
import 'package:lonora/features/market/market_screen.dart';
import 'package:lonora/features/trading/trade_flows.dart' show positionCard;
import 'package:lonora/features/trading/trade_rules.dart';
import 'package:lonora/features/trading/trade_widgets.dart' show TradeNotice;
import 'package:lonora/features/trading/trades_data.dart';

import '../trading/trade_harness.dart';
import 'market_fixtures.dart' as market;

/// The Market tab's reads, on the strict API.
void _script({List<Json>? connections, Json? account}) {
  final lenient = tradeApi;
  // The market fixtures register on [fakeApi], which is [tradeApi] here.
  market.scriptMarket();
  if (connections != null) {
    lenient.on('GET /trading/connections', (_, _) => connections);
  }
  if (account != null) {
    lenient.on('GET /trading/accounts/acct-1', (_, _) => account);
  }
}

/// Opens the card whose title matches [title] (its ticker and volume are isolated).
Future<void> _menu(WidgetTester tester, String title) async {
  final card = find.textContaining(RegExp(title)).first;
  await scrollTo(tester, card);
  await tapAndSettle(tester, card);
}

void main() {
  setUpAll(setUpWpf);
  setUp(resetTrades);

  testWidgets('a position: its menu, the close review, one order, the toast', (
    tester,
  ) async {
    _script();
    tradeApi.on(
      'POST /trading/execute',
      (body, _) => executorAnswer(body, 'confirmed'),
    );
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await _menu(tester, 'XAUUSD.* · Buy');
    expect(find.widgetWithText(FItem, 'Edit stop and target'), findsOneWidget);
    expect(find.widgetWithText(FItem, 'View the market'), findsOneWidget);
    await tapAndSettle(tester, find.widgetWithText(FItem, 'Close the trade'));
    expect(find.textContaining('The trade on'), findsOneWidget);
    expect(tradeApi.executed, isEmpty);
    await tapAndSettle(tester, buttonLabelled('Close the trade'));
    expect(tradeApi.executed.single['action'], 'close_position');
    expect(tradeApi.executed.single['position_id'], 'p-1');
    expect(find.textContaining('Confirmed'), findsWidgets);
    await settleToasts(tester);
    await unmount(tester);
  });

  testWidgets('a position menu can still open its market', (tester) async {
    _script();
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await _menu(tester, 'EURUSD.* · Sell');
    await tapAndSettle(tester, find.widgetWithText(FItem, 'View the market'));
    expect(find.text('Open an order'), findsOneWidget);
    expect(tradeApi.executed, isEmpty);
    await unmount(tester);
  });

  testWidgets('a pending order is cancelled after its review', (tester) async {
    _script();
    tradeApi.on(
      'POST /trading/execute',
      (body, _) => executorAnswer(body, 'submitted'),
    );
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await _menu(tester, 'GBPUSD');
    await tapAndSettle(tester, find.widgetWithText(FItem, 'Cancel order'));
    await tapAndSettle(tester, buttonLabelled('Cancel order'));
    expect(tradeApi.executed.single, {
      'account_id': 'acct-1',
      'action': 'cancel_order',
      'symbol': 'GBPUSD',
      'order_id': 'o-1',
      'operation_id': tradeApi.executed.single['operation_id'],
    });
    // Unsettled: the card says it is awaiting the broker; the menu now checks.
    expect(find.textContaining('Awaiting broker confirmation'), findsWidgets);
    await settleToasts(tester);
    await _menu(tester, 'GBPUSD');
    expect(find.widgetWithText(FItem, 'Check cancel result'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets(
    'a disconnected account: the notice leads to «التعطل والاستعادة»',
    (tester) async {
      _script(
        connections: [
          {
            ...market.connectionsFixture.first,
            'state': {
              ...asJson(market.connectionsFixture.first['state']),
              'broker_recovery': {'status': 'disconnected'},
            },
          },
        ],
      );
      await pumpWpf(
        tester,
        const MarketScreen(),
        pages: {'/settings/recovery': (s) => Text('recovery:${s.uri.query}')},
      );
      expect(find.text('انقطع اتصال الوسيط'), findsOneWidget);
      expect(find.textContaining('متوقف مؤقتًا'), findsOneWidget);
      // Exits stay: the positions section says new orders are paused.
      await scrollTo(tester, find.textContaining('تتوقف الأوامر الجديدة'));
      await tapAndSettle(tester, find.byType(TradeNotice).first);
      expect(find.text('recovery:account=acct-1'), findsOneWidget);
      await unmount(tester);
    },
  );

  testWidgets('trading not allowed: the menu offers no order', (tester) async {
    _script(account: accountState(tradeAllowed: false));
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await _menu(tester, 'XAUUSD.* · Buy');
    // The entries are there, switched off: a tap opens no review.
    await tester.tap(find.text('Close the trade'), warnIfMissed: false);
    await tester.pumpAndSettle();
    expect(find.textContaining('The trade on'), findsNothing);
    await tester.tap(find.text('Edit stop and target'), warnIfMissed: false);
    await tester.pumpAndSettle();
    expect(find.text('Save'), findsNothing);
    expect(tradeApi.executed, isEmpty);
    await unmount(tester);
  });

  testWidgets(
    'trading not allowed: a held close can still be checked from the menu',
    (tester) async {
      _script(account: accountState(tradeAllowed: false));
      tradeApi.on('POST /trading/execute', (_, _) => throw ApiError.network());
      await tester.runAsync(
        () => OrderDesk.instance.run(
          scope: testScope,
          key: heldKey('close_position', 'acct-1', 'p-1'),
          build: () => closeRequest(
            accountId: 'acct-1',
            p: const MarketPosition(goldPosition),
          ),
          card: positionCard('acct-1', 'p-1'),
        ),
      );
      tradeApi.on(
        'POST /trading/execute',
        (body, _) => executorAnswer(body, 'confirmed'),
      );
      await pumpWpf(tester, const MarketScreen(), locale: 'en');
      await _menu(tester, 'XAUUSD.* · Buy');
      // A new edit stays off; the held close's check is on.
      await tester.tap(find.text('Edit stop and target'), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(find.text('Save'), findsNothing);
      await tapAndSettle(
        tester,
        find.widgetWithText(FItem, 'Check close result'),
      );
      await tapAndSettle(tester, buttonLabelled('Check close result'));
      expect(tradeApi.executed, hasLength(2));
      expect(
        tradeApi.executed[1]['operation_id'],
        tradeApi.executed[0]['operation_id'],
      );
      await settleToasts(tester);
      await unmount(tester);
    },
  );
}
