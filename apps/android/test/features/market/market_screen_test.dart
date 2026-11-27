// Market tab: data helpers, the account strip, followed markets, read-only positions, watches
// with the owner's brake, the symbol search and sheet, empty / error states; goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/market
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderParagraph;
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/design/design.dart'
    show
        ExploreSkeleton,
        LargeTitleHeader,
        LnChoiceChip,
        LnPalette,
        SectionHeader,
        WideTile;
import 'package:lonora/features/market/market_data.dart';
import 'package:lonora/features/market/market_kit.dart';
import 'package:lonora/features/market/market_screen.dart';
import 'package:lonora/features/market/market_widgets.dart' show CalendarRow;
import 'package:lonora/features/market/symbol_sheet.dart';
import 'package:lonora/features/market/watch_sheet.dart';

import 'market_fixtures.dart';
import 'wpf_harness.dart';

void main() {
  setUpAll(setUpWpf);
  setUp(resetWpf);

  group('data', () {
    test(
      'followed symbols: positions, agents, watches, opportunities, charts',
      () {
        final agents = fixtureAgents.map(Agent.fromJson);
        final symbols = followedSymbols(
          accountId: 'acct-1',
          positions: [
            const MarketPosition({'symbol': 'EURUSD'}),
            const MarketPosition({'symbol': 'EURUSD'}),
          ],
          agents: agents,
          watches: watchesFixture.map(MarketWatch.new).toList(),
          opportunities: opportunitiesFixture.map(Opportunity.new).toList(),
          charts: [
            const ChartRef(
              id: 'c',
              accountId: 'acct-1',
              symbol: 'US30',
              timeframe: '1h',
            ),
            const ChartRef(
              id: 'd',
              accountId: 'other',
              symbol: 'BTCUSD',
              timeframe: '1h',
            ),
          ],
        );
        expect(symbols, ['EURUSD', 'XAUUSD', 'US30']);
        expect(
          followedSymbols(
            accountId: 'acct-1',
            positions: [
              for (var i = 0; i < 20; i++) MarketPosition({'symbol': 'S$i'}),
            ],
          ),
          hasLength(12),
        );
      },
    );

    test('close change, spread, default account, money', () {
      expect(closeChange(const []), isNull);
      final change = closeChange(candlesFrom(dailyFor('XAUUSD')));
      expect(change, closeTo(0.6496, 0.001));
      expect(MarketQuote.fromJson(quoteFor('XAUUSD')).spread, '0.32');
      expect(MarketQuote.fromJson(quoteFor('EURUSD')).spread, '0.00006');
      final connections = connectionsFixture
          .map(MarketConnection.fromJson)
          .toList();
      expect(defaultAccount(connections, const []), 'acct-1');
      expect(
        defaultAccount(connections, [
          Agent.fromJson({'id': 'x', 'trading_account_id': 'acct-2'}),
        ]),
        'acct-2',
      );
      expect(defaultAccount(const [], const []), isNull);
      expect(money(10248.6), '10,248.60');
      expect(signedMoney(-3), '-3.00');
      expect(signedMoney(212.4), '+212.40');
      expect(signedPercent(0.6496), '+0.65%');
    });

    test('watch states', () {
      final w = watchesFixture.map(MarketWatch.new).toList();
      expect(w[0].paused, isFalse);
      expect(w[0].ended, isFalse);
      expect(w[1].paused, isTrue);
      expect(w[2].cancelled, isTrue);
      expect(w[2].ended, isTrue);
      expect(w[1].summary['indicator'], 'rsi');
      expect(w[0].summary['indicator'], isNull);
    });

    test('events map onto the parts they make stale', () {
      expect(marketPartsOf('cloud_charts.scene_updated'), isEmpty);
      expect(marketPartsOf('cloud_charts.refresh_requested'), isEmpty);
      expect(marketPartsOf('cloud_charts.created'), {MarketPart.charts});
      expect(marketPartsOf('market_watches.updated'), {MarketPart.watches});
      expect(marketPartsOf('watch.confirmed'), {MarketPart.watches});
      expect(marketPartsOf('opportunity.transition'), {
        MarketPart.opportunities,
      });
      expect(marketPartsOf('trading.operation_updated'), {MarketPart.account});
      expect(marketPartsOf('broker.external_activity'), {MarketPart.account});
      expect(marketPartsOf('broker_sessions.updated'), {
        MarketPart.connections,
        MarketPart.account,
      });
      expect(marketPartsOf('market_data.recovered'), {MarketPart.quotes});
      expect(marketPartsOf('message.created'), isEmpty);
      expect(marketPartsOf('market.quote_updated'), isEmpty);
    });

    test('quotes never go back in time', () {
      MarketQuote q(String at) =>
          MarketQuote.fromJson({...quoteFor('XAUUSD'), 'observed_at': at});
      final shown = q('2026-11-27T10:00:00Z');
      expect(q('2026-11-27T10:00:01Z').supersedes(shown), isTrue);
      expect(q('2026-11-27T10:00:00Z').supersedes(shown), isFalse);
      expect(q('2026-11-27T10:00:00Z').supersedes(shown, orSame: true), isTrue);
      expect(
        q('2026-11-27T09:59:00Z').supersedes(shown, orSame: true),
        isFalse,
      );
      expect(shown.supersedes(null), isTrue);
    });

    test('a watch past its expiry is over; one with an expiry extends', () {
      Json at(String? expires, [String lifecycle = 'pending']) => {
        ...watchesFixture[0],
        'payload': {
          ...(watchesFixture[0]['payload']! as Map),
          'expires_at': expires,
        },
        'state': {'lifecycle': lifecycle},
      };
      expect(MarketWatch(at('2020-01-01T00:00:00Z')).ended, isTrue);
      expect(MarketWatch(at('2099-01-01T00:00:00Z')).ended, isFalse);
      expect(MarketWatch(at('2099-01-01T00:00:00Z')).extendable, isTrue);
      expect(MarketWatch(at(null)).extendable, isFalse);
      expect(MarketWatch(at(null, 'expired')).ended, isTrue);
    });

    test('each watch source sends its own fields', () {
      Json payload(String kind, String condition) => watchPayload(
        kind: kind,
        accountId: 'acct-1',
        symbol: 'XAUUSD',
        condition: condition,
        level: '30',
        prompt: 'p',
        indicator: 'macd',
        period: 26,
        timeframe: '4h',
        metric: kind == 'position' ? 'volume' : 'margin',
        positionId: 'p-1',
        integrationId: 'feed-1',
      );
      final base = {'account_id': 'acct-1', 'symbol': 'XAUUSD', 'prompt': 'p'};
      expect(payload('indicator', 'below'), {
        'kind': 'indicator',
        ...base,
        'condition': 'below',
        'level': '30',
        'indicator': 'macd',
        'period': 26,
        'timeframe': '4h',
      });
      expect(payload('account', 'changed'), {
        'kind': 'account',
        ...base,
        'condition': 'changed',
        'metric': 'margin',
      });
      expect(payload('position', 'closed'), {
        'kind': 'position',
        ...base,
        'condition': 'closed',
        'metric': 'volume',
        'position_id': 'p-1',
      });
      expect(payload('calendar', 'due'), {
        'kind': 'calendar',
        ...base,
        'condition': 'due',
        'integration_id': 'feed-1',
      });
      expect(watchConditionsFor('calendar'), ['due']);
      expect(watchConditionsFor('position').take(3), [
        'changed',
        'closed',
        'opened',
      ]);
      expect(defaultWatchCondition('account'), 'changed');
    });

    test('account snapshot sums open profit', () {
      final s = AccountSnapshot.fromJson(accountFixture);
      expect(s.openProfit, closeTo(248.6, 1e-9));
      expect(s.positions.first.isSell, isFalse);
      expect(s.orders.single.side, 'buy_limit');
    });
  });

  testWidgets('shows the account, followed markets and read-only positions', (
    tester,
  ) async {
    scriptMarket();
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    expect(find.text('Market'), findsOneWidget);
    expect(find.textContaining('Lonora Sim'), findsWidgets);
    expect(find.text('10,248.60 USD'), findsOneWidget);
    // The account card is the kit's wide tile; its label is what a screen reader hears.
    final account = tester.widget<WideTile>(find.byType(WideTile));
    expect(account.label, contains('10,248.60 USD'));
    expect(find.bySemanticsLabel(account.label), findsOneWidget);
    expect(tester.getSize(find.byType(WideTile)), const Size(296, 128));
    expect(find.text('XAUUSD'), findsWidgets);
    expect(find.text('2401.74'), findsOneWidget);
    expect(find.text('+0.65%'), findsOneWidget);
    expect(find.text('Simulation · imported snapshot'), findsOneWidget);
    await scrollTo(tester, find.text('Positions'));
    expect(find.textContaining('Open price'), findsWidgets);
    expect(find.text('View only: no order is sent from here.'), findsOneWidget);
    // Nothing on this screen may reach the order executor.
    expect(fakeApi.calls.where((c) => c.path.contains('execute')), isEmpty);
    expect(fakeApi.calls.where((c) => c.method != 'GET'), isEmpty);
    await unmount(tester);
  });

  testWidgets('cancelling a watch asks first, then uses the control brake', (
    tester,
  ) async {
    scriptMarket();
    fakeApi.on(
      'POST /watches/w-1/control',
      (_, _) => {
        ...watchesFixture[0],
        'payload': {
          ...(watchesFixture[0]['payload']! as Map),
          'enabled': false,
        },
        'state': {'lifecycle': 'pending', 'code': 'watch_cancelled'},
      },
    );
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    final watch = find.textContaining('crosses above');
    await scrollTo(tester, watch);
    await tapAndSettle(tester, watch);
    await tapAndSettle(tester, find.text('Cancel watch'));
    expect(find.text('Cancel this watch?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Keep'));
    expect(fakeApi.callsTo('POST', '/watches/w-1/control'), isEmpty);

    await tapAndSettle(tester, watch);
    await tapAndSettle(tester, find.text('Cancel watch'));
    await tapAndSettle(tester, find.text('Cancel watch').last);
    expect(fakeApi.callsTo('POST', '/watches/w-1/control').single.body, {
      'action': 'cancel',
    });
    expect(find.textContaining('crosses above'), findsNothing);
    await settleToasts(tester);
    await unmount(tester);
  });

  List<String> reads() => [
    for (final c in fakeApi.calls) '${c.method} ${c.path}',
  ];

  /// Delivers the events, then lets the 800 ms debounce run out.
  Future<void> settleEvents(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
  }

  testWidgets('events re-read only their part, never the calendar', (
    tester,
  ) async {
    scriptMarket();
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    fakeApi.calls.clear();
    // A live chart updates its scene all the time: the Market tab reads nothing for it.
    for (var i = 0; i < 5; i++) {
      fakeRealtime
        ..emit('cloud_charts.scene_updated', {'id': 'c-1'})
        ..emit('cloud_charts.refresh_requested', {'id': 'c-1'});
      await tester.pump(const Duration(milliseconds: 300));
    }
    await settleEvents(tester);
    expect(reads(), isEmpty);
    fakeRealtime.emit('market_watches.updated', {'id': 'w-1'});
    await settleEvents(tester);
    expect(reads(), ['GET /watches']);
    fakeApi.calls.clear();
    fakeRealtime.emit('trading.operation_updated');
    await settleEvents(tester);
    expect(reads().toSet(), {
      'GET /trading/accounts/acct-1',
      'GET /trading/journal',
    });
    fakeApi.calls.clear();
    // A new chart on a market not followed yet: its list, then that market's quote and day.
    fakeApi.on(
      'GET /charts',
      (_, _) => [
        ...chartsFixture,
        {
          'id': 'c-9',
          'payload': {
            'account_id': 'acct-1',
            'symbol': 'US30',
            'timeframe': '1h',
          },
        },
      ],
    );
    fakeRealtime.emit('cloud_charts.created', {'id': 'c-9'});
    await settleEvents(tester);
    expect(reads().toSet(), {
      'GET /charts',
      'GET /market/quote',
      'GET /market/candles',
    });
    expect(
      [
        for (final c in fakeApi.callsTo('GET', '/market/quote'))
          c.query?['symbol'],
      ],
      ['US30'],
    );
    await unmount(tester);
  });

  testWidgets('hidden, it reads nothing and catches up when shown', (
    tester,
  ) async {
    scriptMarket();
    final shown = ValueNotifier(true);
    await pumpWpf(
      tester,
      ValueListenableBuilder<bool>(
        valueListenable: shown,
        builder: (_, on, _) =>
            TickerMode(enabled: on, child: const MarketScreen()),
      ),
      locale: 'en',
    );
    fakeApi.calls.clear();
    shown.value = false;
    await tester.pump();
    fakeRealtime
      ..emit('market_watches.updated', {'id': 'w-1'})
      ..emit('opportunity.transition');
    await tester.pump(const Duration(seconds: 2));
    // The quote tick is skipped too.
    await tester.pump(MarketScreen.quoteEvery);
    expect(reads(), isEmpty);
    shown.value = true;
    await settleEvents(tester);
    expect(reads().toSet(), {'GET /watches', 'GET /trading/opportunities'});
    await unmount(tester);
  });

  testWidgets('the quote tick reads quotes only; resume reads the live parts', (
    tester,
  ) async {
    scriptMarket();
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    fakeApi.calls.clear();
    await tester.pump(MarketScreen.quoteEvery);
    await tester.pump();
    expect(reads().toSet(), {'GET /market/quote'});
    expect(fakeApi.callsTo('GET', '/market/quote'), hasLength(2));
    fakeApi.calls.clear();
    // The notification shade only makes the app inactive: nothing was missed.
    final binding = tester.binding;
    binding
      ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
      ..handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await settleEvents(tester);
    expect(reads(), isEmpty);
    binding
      ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
      ..handleAppLifecycleStateChanged(AppLifecycleState.hidden)
      ..handleAppLifecycleStateChanged(AppLifecycleState.paused)
      ..handleAppLifecycleStateChanged(AppLifecycleState.hidden)
      ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
      ..handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await settleEvents(tester);
    expect(reads().toSet(), {
      'GET /trading/connections',
      'GET /watches',
      'GET /trading/opportunities',
      'GET /charts',
      'GET /trading/accounts/acct-1',
      'GET /trading/journal',
      'GET /market/quote',
    });
    await unmount(tester);
  });

  testWidgets('streamed and read quotes never go back in time', (tester) async {
    scriptMarket();
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    Json quote(String bid, String at) => {
      'connection_id': 'acct-1',
      'symbol': 'XAUUSD',
      'quote': {...quoteFor('XAUUSD'), 'bid': bid, 'observed_at': at},
    };
    fakeRealtime.emit(
      'market.quote_updated',
      quote('2410.00', '2026-11-27T09:59:45Z'),
    );
    await tester.pumpAndSettle();
    expect(find.text('2410.00'), findsOneWidget);
    fakeRealtime.emit(
      'market.quote_updated',
      quote('2300.00', '2026-11-27T09:00:00Z'),
    );
    await tester.pumpAndSettle();
    expect(find.text('2300.00'), findsNothing);
    // The next read returns an older observation (09:59:30): the newer stays.
    fakeApi.calls.clear();
    await tester.pump(MarketScreen.quoteEvery);
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('GET', '/market/quote'), isNotEmpty);
    expect(find.text('2410.00'), findsOneWidget);
    expect(find.text('2401.74'), findsNothing);
    await unmount(tester);
  });

  testWidgets('extend, and a cancel undone from its toast', (tester) async {
    scriptMarket();
    Json expiring(Json w, {String? state}) => {
      ...w,
      'payload': {
        ...(w['payload']! as Map),
        'expires_at': '2099-01-01T00:00:00Z',
      },
      'state': {'lifecycle': 'pending', 'code': ?state},
    };
    fakeApi
      ..on(
        'GET /watches',
        (_, _) => [
          expiring(watchesFixture[0]),
          // Past its expiry: no longer listed, even before the server marks it.
          {
            ...watchesFixture[1],
            'payload': {
              ...(watchesFixture[1]['payload']! as Map),
              'enabled': true,
              'expires_at': '2020-01-01T00:00:00Z',
            },
          },
        ],
      )
      ..on(
        'POST /watches/w-1/control',
        (body, _) => expiring(
          watchesFixture[0],
          state: (body! as Map)['action'] == 'cancel'
              ? 'watch_cancelled'
              : null,
        ),
      );
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    final watch = find.textContaining('crosses above');
    await scrollTo(tester, watch);
    expect(find.textContaining('RSI'), findsNothing);
    await tapAndSettle(tester, watch);
    await tapAndSettle(tester, find.text('Extend two hours'));
    expect(fakeApi.callsTo('POST', '/watches/w-1/control').single.body, {
      'action': 'extend',
      'hours': 2,
    });
    expect(find.text('Extended by two hours'), findsOneWidget);
    await settleToasts(tester);
    await tapAndSettle(tester, watch);
    await tapAndSettle(tester, find.text('Cancel watch'));
    await tapAndSettle(tester, find.text('Cancel watch').last);
    expect(find.text('Watch cancelled'), findsOneWidget);
    expect(find.textContaining('crosses above'), findsNothing);
    await tapAndSettle(tester, find.text('Undo'));
    expect(fakeApi.callsTo('POST', '/watches/w-1/control').map((c) => c.body), [
      {'action': 'extend', 'hours': 2},
      {'action': 'cancel'},
      {'action': 'resume'},
    ]);
    expect(find.textContaining('crosses above'), findsOneWidget);
    await settleToasts(tester);
    await unmount(tester);
  });

  testWidgets('pausing a watch posts pause', (tester) async {
    scriptMarket();
    fakeApi.on('POST /watches/w-1/control', (_, _) => watchesFixture[1]);
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    final watch = find.textContaining('crosses above');
    await scrollTo(tester, watch);
    await tapAndSettle(tester, watch);
    await tapAndSettle(tester, find.text('Pause'));
    expect(fakeApi.callsTo('POST', '/watches/w-1/control').single.body, {
      'action': 'pause',
    });
    await unmount(tester);
  });

  testWidgets('symbol search opens the market sheet and its chart', (
    tester,
  ) async {
    scriptMarket();
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await tapAndSettle(tester, find.text('Search broker symbols'));
    expect(find.text('USDJPY'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'xau');
    await tester.pumpAndSettle();
    expect(find.text('USDJPY'), findsNothing);
    await tapAndSettle(tester, find.text('XAUUSD').last);
    expect(find.text('Gold vs US Dollar'), findsOneWidget);
    expect(find.text('Spread'), findsOneWidget);
    expect(find.text('0.32'), findsOneWidget);
    expect(find.textContaining('Gold desk'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Open chart'),
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, find.text('Open chart'));
    expect(shownRoute(tester), '/charts?chart=c-1');
    await unmount(tester);
  });

  testWidgets('creates a price watch from a market sheet', (tester) async {
    scriptMarket();
    fakeApi.on(
      'POST /watches',
      (body, _) => {
        'id': 'w-new',
        'agent_id': (body! as Map)['agent_id'],
        'payload': {...((body as Map)['payload'] as Map), 'enabled': true},
        'state': {'lifecycle': 'pending'},
      },
    );
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await tapAndSettle(tester, find.text('XAUUSD').first);
    final create = find.text('Create watch');
    await tester.scrollUntilVisible(
      create,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, create);
    expect(find.text('Gold desk'), findsOneWidget);
    await tapAndSettle(tester, find.text('Below'));
    await tester.enterText(find.byType(TextField).first, '2350');
    await tester.enterText(find.byType(TextField).last, 'Review the stop');
    await tester.pumpAndSettle();
    await tapAndSettle(tester, find.text('Create watch').last);
    expect(fakeApi.callsTo('POST', '/watches').single.body, {
      'payload': {
        'kind': 'price',
        'account_id': 'acct-1',
        'symbol': 'XAUUSD',
        'condition': 'below',
        'level': '2350',
        'prompt': 'Review the stop',
      },
      'agent_id': 'a-gold',
      'thread_id': null,
    });
    expect(find.text('Watch created'), findsOneWidget);
    await settleToasts(tester);
    await scrollTo(tester, find.textContaining('2350'));
    await unmount(tester);
  });

  Finder inSheet<T>(Finder f) =>
      find.descendant(of: find.byType(T), matching: f);

  Future<void> openCreateWatch(WidgetTester tester) async {
    await tapAndSettle(tester, find.text('XAUUSD').first);
    final create = find.text('Create watch');
    await tester.scrollUntilVisible(
      create,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, create);
  }

  Future<void> sheetTap(WidgetTester tester, Finder f) async {
    await tester.scrollUntilVisible(
      f,
      120,
      scrollable: inSheet<CreateWatchSheet>(find.byType(Scrollable)).first,
    );
    await tapAndSettle(tester, f);
  }

  void echoWatch() => fakeApi.on(
    'POST /watches',
    (body, _) => {
      'id': 'w-new',
      'agent_id': (body! as Map)['agent_id'],
      'payload': {...((body as Map)['payload'] as Map), 'enabled': true},
      'state': {'lifecycle': 'pending'},
    },
  );

  testWidgets('creates an indicator watch', (tester) async {
    scriptMarket();
    echoWatch();
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await openCreateWatch(tester);
    await sheetTap(tester, inSheet<CreateWatchSheet>(find.text('Indicator')));
    await sheetTap(tester, find.text('MACD'));
    await sheetTap(tester, find.text('4h'));
    expect(
      tester
          .widget<LnChoiceChip>(find.widgetWithText(LnChoiceChip, '4h'))
          .selected,
      isTrue,
    );
    final fields = inSheet<CreateWatchSheet>(find.byType(TextField));
    // Period, level, task.
    expect(fields, findsNWidgets(3));
    await tester.enterText(fields.at(0), '26');
    await tester.enterText(fields.at(1), '-0.5');
    await tester.enterText(fields.at(2), 'Momentum turned');
    await tester.pumpAndSettle();
    await tapAndSettle(tester, find.text('Create watch').last);
    expect(fakeApi.callsTo('POST', '/watches').single.body, {
      'payload': {
        'kind': 'indicator',
        'account_id': 'acct-1',
        'symbol': 'XAUUSD',
        'condition': 'cross_above',
        'level': '-0.5',
        'prompt': 'Momentum turned',
        'indicator': 'macd',
        'period': 26,
        'timeframe': '4h',
      },
      'agent_id': 'a-gold',
      'thread_id': null,
    });
    await settleToasts(tester);
    await unmount(tester);
  });

  testWidgets('a calendar watch needs a feed and is due, with no level', (
    tester,
  ) async {
    scriptMarket();
    echoWatch();
    fakeApi.on(
      'GET /integrations',
      (_, _) => [
        {
          'id': 'feed-1',
          'payload': {'type': 'economic_calendar', 'name': 'ForexFactory'},
        },
        {
          'id': 'mcp-1',
          'payload': {'type': 'mcp', 'name': 'Other'},
        },
      ],
    );
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await openCreateWatch(tester);
    await sheetTap(
      tester,
      inSheet<CreateWatchSheet>(find.text('Economic calendar')),
    );
    expect(fakeApi.callsTo('GET', '/integrations'), hasLength(1));
    expect(find.text('Other'), findsNothing);
    expect(find.text('Event is due'), findsOneWidget);
    expect(find.text('Crosses above'), findsNothing);
    // The only feed is chosen; no level is asked.
    final fields = inSheet<CreateWatchSheet>(find.byType(TextField));
    expect(fields, findsOneWidget);
    await tester.enterText(fields, 'Prepare for the release');
    await tester.pumpAndSettle();
    await tapAndSettle(tester, find.text('Create watch').last);
    expect(
      (fakeApi.callsTo('POST', '/watches').single.body! as Map)['payload'],
      {
        'kind': 'calendar',
        'account_id': 'acct-1',
        'symbol': 'XAUUSD',
        'condition': 'due',
        'prompt': 'Prepare for the release',
        'integration_id': 'feed-1',
      },
    );
    await settleToasts(tester);
    await unmount(tester);
  });

  testWidgets('a position watch offers the open positions of the market', (
    tester,
  ) async {
    scriptMarket();
    echoWatch();
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await openCreateWatch(tester);
    await sheetTap(tester, inSheet<CreateWatchSheet>(find.text('Position')));
    // The volume is isolated left to right inside the label.
    await sheetTap(
      tester,
      inSheet<CreateWatchSheet>(find.textContaining(RegExp(r'^Buy .*0\.10'))),
    );
    expect(find.text('Closes'), findsOneWidget);
    await sheetTap(tester, inSheet<CreateWatchSheet>(find.text('Profit')));
    final fields = inSheet<CreateWatchSheet>(find.byType(TextField));
    await tester.enterText(fields.last, 'Review the trade');
    await tester.pumpAndSettle();
    await tapAndSettle(tester, find.text('Create watch').last);
    expect(
      (fakeApi.callsTo('POST', '/watches').single.body! as Map)['payload'],
      {
        'kind': 'position',
        'account_id': 'acct-1',
        'symbol': 'XAUUSD',
        'condition': 'closed',
        'prompt': 'Review the trade',
        'metric': 'profit',
        'position_id': 'p-1',
      },
    );
    await settleToasts(tester);
    await unmount(tester);
  });

  testWidgets('a market without a chart creates one and opens it', (
    tester,
  ) async {
    scriptMarket();
    fakeApi.on(
      'POST /charts',
      (body, _) => {
        'id': 'c-new',
        'payload': (body! as Map)['payload'],
        'version': 1,
      },
    );
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await tapAndSettle(tester, find.text('EURUSD').first);
    final create = find.text('Create chart');
    await tester.scrollUntilVisible(
      create,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, create);
    expect(fakeApi.callsTo('POST', '/charts').single.body, {
      'payload': {
        'account_id': 'acct-1',
        'symbol': 'EURUSD',
        'timeframe': '1h',
        'indicators': [],
        'annotations': [],
      },
      'agent_id': null,
      'thread_id': null,
    });
    expect(shownRoute(tester), '/charts?chart=c-new');
    await unmount(tester);
  });

  testWidgets('the market sheet keeps its quote fresh', (tester) async {
    scriptMarket();
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await tapAndSettle(tester, find.text('XAUUSD').first);
    final sheet = find.byType(SymbolSheet);
    expect(
      find.descendant(of: sheet, matching: find.text('2401.74')),
      findsWidgets,
    );
    fakeApi.on(
      'GET /market/quote',
      (_, q) => {
        ...quoteFor('${q?['symbol']}'),
        'bid': '2403.10',
        'observed_at': '2026-11-27T10:00:05Z',
      },
    );
    await tester.pump(SymbolSheet.quoteEvery);
    await tester.pumpAndSettle();
    expect(
      find.descendant(of: sheet, matching: find.text('2403.10')),
      findsWidgets,
    );
    fakeRealtime.emit('market.quote_updated', {
      'connection_id': 'acct-1',
      'symbol': 'XAUUSD',
      'quote': {
        ...quoteFor('XAUUSD'),
        'bid': '2404.20',
        'observed_at': '2026-11-27T10:00:09Z',
      },
    });
    await tester.pumpAndSettle();
    expect(
      find.descendant(of: sheet, matching: find.text('2404.20')),
      findsWidgets,
    );
    await unmount(tester);
  });

  testWidgets('every account is listed and numbered; a disabled one waits', (
    tester,
  ) async {
    scriptMarket();
    fakeApi.on(
      'GET /trading/connections',
      (_, _) => [
        {
          'id': 'acct-0',
          'version': 1,
          'payload': {'provider': 'metaapi', 'enabled': false},
          'state': {},
        },
        ...connectionsFixture,
      ],
    );
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    await tapAndSettle(
      tester,
      find.bySemanticsLabel(RegExp('^Change account')),
    );
    expect(find.text('Unverified broker account · 1'), findsOneWidget);
    // The Web and Expo number over every connection: the second metaapi one is «3».
    expect(find.text('Unverified broker account · 3'), findsOneWidget);
    expect(find.text('Disabled'), findsOneWidget);
    await tapAndSettle(tester, find.text('Unverified broker account · 1'));
    expect(fakeApi.callsTo('GET', '/trading/accounts/acct-0'), isEmpty);
    await unmount(tester);
  });

  testWidgets('the symbol search is a 48 dp target', (tester) async {
    scriptMarket();
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    expect(
      tester.getSize(find.bySemanticsLabel('Search broker symbols')).height,
      48,
    );
    await unmount(tester);
  });

  testWidgets('without a broker account it offers to link one', (tester) async {
    scriptMarket(noAccounts: true);
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    expect(
      find.text('Link a trading account from Settings first.'),
      findsOneWidget,
    );
    expect(fakeApi.callsTo('GET', '/trading/accounts/acct-1'), isEmpty);
    await tapAndSettle(
      tester,
      find.text('Link a trading account from Settings first.'),
    );
    expect(shownRoute(tester), '/settings/integrations');
    await unmount(tester);
  });

  testWidgets('offline first load shows the retry state', (tester) async {
    for (final r in [
      '/trading/connections',
      '/watches',
      '/market/calendar',
      '/trading/opportunities',
      '/charts',
    ]) {
      fakeApi.on('GET $r', (_, _) => throw ApiError.network());
    }
    await pumpWpf(tester, const MarketScreen(), locale: 'en');
    expect(find.text('Retry'), findsOneWidget);
    scriptMarket();
    await tapAndSettle(tester, find.text('Retry'));
    expect(find.text('10,248.60 USD'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('event and order times read in Arabic-Indic digits in Arabic; '
      'prices stay Latin', (tester) async {
    scriptMarket();
    await pumpWpf(tester, const MarketScreen(), locale: 'ar');
    await scrollTo(tester, find.text('ECB Press Conference'));
    final rows = tester.widgetList<CalendarRow>(find.byType(CalendarRow));
    expect(rows, isNotEmpty);
    for (final row in rows) {
      expect(row.time, matches(RegExp('^[٠-٩]+/[٠-٩]+ [٠-٩]{2}:[٠-٩]{2}\$')));
    }
    await scrollTo(tester, find.text('سجل الأوامر'), delta: 300);
    final order = RegExp('[٠-٩]+/[٠-٩]+ [٠-٩]{2}:[٠-٩]{2}');
    expect(find.textContaining(order), findsWidgets);
    expect(
      find.textContaining(RegExp('[0-9]+/[0-9]+ [0-9]{2}:[0-9]{2}')),
      findsNothing,
    );
    // The order's volume is a count: Latin.
    expect(find.textContaining('0.10'), findsWidgets);
    await unmount(tester);
  });

  testWidgets('text scale 1.3 does not overflow', (tester) async {
    scriptMarket();
    await pumpWpf(tester, const MarketScreen(), locale: 'ar', textScale: 1.3);
    expect(tester.takeException(), isNull);
    await scrollTo(tester, find.text('سجل الأوامر'), delta: 300);
    expect(tester.takeException(), isNull);
    await unmount(tester);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      scriptMarket();
      await withRealShadows(() async {
        await pumpWpf(
          tester,
          const TabFrame(child: MarketScreen()),
          brightness: v.brightness,
          locale: v.locale,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/market_${v.name}.png'),
        );
        await tester.drag(find.byType(Scrollable).first, const Offset(0, -700));
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/market_${v.name}_scrolled.png'),
        );
      });
      await unmount(tester);
    });
  }

  testWidgets('golden symbol sheet', (tester) async {
    scriptMarket();
    await withRealShadows(() async {
      await pumpWpf(tester, const MarketScreen(), locale: 'ar');
      await tapAndSettle(tester, find.text('XAUUSD').first);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/market_symbol_sheet_ar.png'),
      );
    });
    await unmount(tester);
  });

  testWidgets('golden skeleton', (tester) async {
    scriptMarket();
    // The first read never answers: the tab stays on its skeleton.
    final never = Completer<Object?>();
    fakeApi.on('GET /trading/connections', (_, _) => never.future);
    await pumpWpf(
      tester,
      const TabFrame(child: MarketScreen()),
      locale: 'ar',
      settle: false,
    );
    expect(find.byType(ExploreSkeleton), findsOneWidget);
    expect(find.bySemanticsLabel('جارٍ التحميل'), findsOneWidget);
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/market_skeleton_ar.png'),
    );
    await unmount(tester);
  });

  testWidgets('golden empty', (tester) async {
    scriptMarket(noAccounts: true);
    fakeApi
      ..on('GET /watches', (_, _) => [])
      ..on('GET /market/calendar', (_, _) => [])
      ..on('GET /trading/opportunities', (_, _) => []);
    await pumpWpf(
      tester,
      const TabFrame(child: MarketScreen()),
      locale: 'ar',
      brightness: Brightness.dark,
    );
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/market_empty_dark_ar.png'),
    );
    await unmount(tester);
  });
  group('integration 3', () {
    // WCAG contrast of [fg] over [bg] (both opaque).
    double contrast(Color fg, Color bg) {
      final a = fg.computeLuminance(), b = bg.computeLuminance();
      return (math.max(a, b) + 0.05) / (math.min(a, b) + 0.05);
    }

    for (final dark in [false, true]) {
      testWidgets('ma:C0 the account card reads in solid white, its pill on a darker fill '
          '(${dark ? 'dark' : 'light'})', (tester) async {
        scriptMarket();
        await pumpWpf(
          tester,
          const MarketScreen(),
          locale: 'en',
          brightness: dark ? Brightness.dark : Brightness.light,
        );
        final brand = (dark ? LnPalette.dark : LnPalette.light).brand;
        final line = tester.widget<Text>(find.textContaining('Balance'));
        expect(line.style!.color, LnPalette.inkWhite);
        final pill = tester.widget<Container>(
          find
              .ancestor(
                of: find.text('Simulation'),
                matching: find.byType(Container),
              )
              .first,
        );
        final fill = Color.alphaBlend(
          (pill.decoration! as BoxDecoration).color!,
          brand,
        );
        expect(contrast(LnPalette.inkWhite, fill), greaterThan(4.5));
        await unmount(tester);
      });
    }

    testWidgets('ma:C3 the quote source is named, under one label', (
      tester,
    ) async {
      scriptMarket();
      await pumpWpf(tester, const MarketScreen(), locale: 'en');
      await tapAndSettle(tester, find.text('XAUUSD').first);
      await scrollTo(tester, find.text('Source'));
      expect(find.text('Simulation'), findsWidgets);
      expect(find.text('simulation'), findsNothing);
      await unmount(tester);
    });

    testWidgets(
      'ma:C6 an English event name sits beside its currency in Arabic',
      (tester) async {
        scriptMarket();
        await pumpWpf(tester, const MarketScreen(), locale: 'ar');
        await scrollTo(tester, find.text('ECB Press Conference'));
        for (final (name, currency) in [
          ('Non-Farm Payrolls', 'USD'),
          ('ECB Press Conference', 'EUR'),
        ]) {
          final row = find.ancestor(
            of: find.text(name),
            matching: find.byType(CalendarRow),
          );
          final para = tester.renderObject<RenderParagraph>(find.text(name));
          final boxes = para.getBoxesForSelection(
            TextSelection(baseOffset: 0, extentOffset: name.length),
          );
          final inkRight = para
              .localToGlobal(
                Offset(boxes.map((b) => b.right).reduce(math.max), 0),
              )
              .dx;
          final code = tester.getRect(
            find.descendant(of: row, matching: find.text(currency)),
          );
          // The 8 dp gap after the currency (the row is right to left).
          expect(inkRight, closeTo(code.left - 8, 1), reason: name);
        }
        await unmount(tester);
      },
    );

    testWidgets('ma:C11 an empty section starts where its header does', (
      tester,
    ) async {
      scriptMarket(noAccounts: true);
      fakeApi
        ..on('GET /watches', (_, _) => [])
        ..on('GET /market/calendar', (_, _) => []);
      await pumpWpf(tester, const MarketScreen(), locale: 'ar');
      for (final (header, body) in [
        ('المراقبات', 'لا شيء بعد.'),
        ('التقويم الاقتصادي', null),
      ]) {
        final headerText = find.descendant(
          of: find.byType(SectionHeader),
          matching: find.text(header),
        );
        await scrollTo(tester, headerText);
        final bodyText = body == null
            ? find
                  .descendant(
                    of: find.byType(Footnote),
                    matching: find.byType(Text),
                  )
                  .last
            : find.text(body);
        expect(
          tester.getRect(bodyText).right,
          tester.getRect(headerText).right,
          reason: header,
        );
      }
      await unmount(tester);
    });

    testWidgets('ma:C13 the account selector uses the free width', (
      tester,
    ) async {
      scriptMarket();
      await pumpWpf(tester, const MarketScreen(), locale: 'en');
      final label = find.descendant(
        of: find.byType(LargeTitleHeader),
        matching: find.textContaining('Lonora Sim'),
      );
      expect(
        tester.renderObject<RenderParagraph>(label).didExceedMaxLines,
        isFalse,
      );
      await unmount(tester);
    });

    testWidgets(
      'ma:C13 the selector takes the header\'s width, not the window\'s',
      (tester) async {
        scriptMarket();
        // Laid out narrower than the window: the title keeps its width, the label gives way.
        await pumpWpf(
          tester,
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 60),
            child: MarketScreen(),
          ),
          locale: 'en',
        );
        RenderParagraph paragraph(Finder text) => tester.renderObject(
          find.descendant(of: find.byType(LargeTitleHeader), matching: text),
        );
        expect(paragraph(find.text('Market')).didExceedMaxLines, isFalse);
        expect(
          paragraph(find.textContaining('Lonora Sim')).didExceedMaxLines,
          isTrue,
        );
        await unmount(tester);
      },
    );

    testWidgets('Q7 a rise reads in the text-safe green', (tester) async {
      scriptMarket();
      await pumpWpf(tester, const MarketScreen(), locale: 'en');
      expect(
        tester.widget<Text>(find.text('+0.65%')).style!.color,
        LnPalette.light.positiveText,
      );
      await unmount(tester);
    });
  });
}
