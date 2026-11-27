// Charts: scene parsing and windowing, the chart chips, the native candle chart with overlays,
// RSI pane, annotations, crosshair readout, range selector, refresh request, live scene updates,
// creation (no automatic symbol pick), empty / initialising states; goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/charts
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/charts/candle_chart.dart';
import 'package:lonora/features/charts/charts_data.dart';
import 'package:lonora/features/charts/charts_screen.dart';
import 'package:lonora/features/market/market_data.dart';
import 'package:lonora/l10n/l10n.dart';

import '../market/market_fixtures.dart';
import '../market/wpf_harness.dart';

List<double?> ema(List<Json> candles, int period) {
  final out = <double?>[];
  double? prev;
  final k = 2 / (period + 1);
  for (final (i, c) in candles.indexed) {
    final close = double.parse(c['close']! as String);
    prev = prev == null ? close : close * k + prev * (1 - k);
    out.add(i < period - 1 ? null : double.parse(prev.toStringAsFixed(2)));
  }
  return out;
}

List<double?> rsi(List<Json> candles) => [
  for (final (i, _) in candles.indexed)
    i < 14 ? null : 50 + 22 * ((i * 7 % 13) / 13 - 0.5) + (i > 80 ? -8 : 6),
];

Json sceneFixture({String id = 'c-1', int n = 120, int version = 7}) {
  final candles = hourlyCandles('XAUUSD', n);
  return {
    'chart_id': id,
    'revision': 4,
    'scene_version': version,
    'status': 'ready',
    'updated_at': '2026-11-27T09:40:00Z',
    'symbol': 'XAUUSD',
    'timeframe': '1h',
    'candles': candles,
    'quote': quoteFor('XAUUSD'),
    'indicators': [
      {
        'name': 'ema',
        'period': 20,
        'series': {'value': ema(candles, 20)},
      },
      {
        'name': 'rsi',
        'period': 14,
        'series': {'value': rsi(candles)},
      },
    ],
    'annotations': [
      {'type': 'horizontal_line', 'price': 2395, 'label': 'Resistance 2395'},
      {'type': 'note', 'text': 'الاختراق فوق 2395 يؤكد الاتجاه.'},
    ],
  };
}

/// Every drawing kind an agent can save (lonora_core chart_annotations), inside the last 60
/// hourly candles of [sceneFixture], plus two scoped elsewhere that must stay hidden.
final drawingsFixture = <Json>[
  {'type': 'horizontal_line', 'price': 2395, 'label': 'Resistance 2395'},
  {
    'type': 'trend_line',
    'source': 'agent',
    'label': 'Support',
    'start': {'time': '2026-11-27T14:00:00Z', 'price': 2384},
    'end': {'time': '2026-11-29T10:00:00Z', 'price': 2392},
  },
  {
    'type': 'ray',
    'style': {'color': '#d95a64', 'line_style': 'dashed', 'line_width': 2},
    'start': {'time': '2026-11-28T00:00:00Z', 'price': 2398},
    'end': {'time': '2026-11-28T12:00:00Z', 'price': 2394},
  },
  {
    'type': 'channel',
    'source': 'agent',
    'start': {'time': '2026-11-27T16:00:00Z', 'price': 2376},
    'end': {'time': '2026-11-29T16:00:00Z', 'price': 2386},
    'parallel': {'time': '2026-11-28T12:00:00Z', 'price': 2391},
  },
  {
    'type': 'price_zone',
    'label': 'Demand',
    'start': {'time': '2026-11-28T06:00:00Z', 'price': 2372},
    'end': {'time': '2026-11-29T06:00:00Z', 'price': 2376},
  },
  {
    'type': 'fibonacci',
    'style': {'line_style': 'dotted'},
    'start': {'time': '2026-11-27T20:00:00Z', 'price': 2370},
    'end': {'time': '2026-11-29T20:00:00Z', 'price': 2400},
  },
  {
    'type': 'arrow',
    'source': 'agent',
    'start': {'time': '2026-11-29T12:00:00Z', 'price': 2378},
    'end': {'time': '2026-11-29T20:00:00Z', 'price': 2383},
  },
  {
    'type': 'scenario',
    'source': 'agent',
    'label': 'Long idea',
    'start': {'time': '2026-11-28T18:00:00Z', 'price': 2380},
    'end': {'time': '2026-11-29T22:00:00Z', 'price': 2392},
    'stop': 2374,
  },
  {
    'type': 'note',
    'text': 'Breakout?',
    'time': '2026-11-28T08:00:00Z',
    'price': 2396,
  },
  {'type': 'note', 'text': 'الاختراق فوق 2395 يؤكد الاتجاه.'},
  {
    'type': 'horizontal_line',
    'price': 2200,
    'label': 'Weekly only',
    'timeframes': ['4h'],
  },
  {
    'type': 'price',
    'price': 1.08,
    'label': 'Euro level',
    'scope': {'account_id': 'acct-1', 'symbol': 'EURUSD', 'chart_id': 'c-1'},
  },
];

List<double?> wave(int n, double mid, double amp, {int from = 26}) => [
  for (var i = 0; i < n; i++)
    i < from ? null : mid + amp * ((i * 5 % 17) / 17 - 0.5),
];

/// [sceneFixture] with every drawing kind and the MACD and ATR panes.
Json drawnScene() {
  final base = sceneFixture();
  final n = (base['candles']! as List).length;
  return {
    ...base,
    'indicators': [
      ...(base['indicators']! as List),
      {
        'name': 'macd',
        'period': 12,
        'series': {
          'macd': wave(n, 0.4, 3),
          'signal': wave(n, 0.2, 2, from: 34),
          'histogram': wave(n, 0.1, 1.5, from: 34),
        },
      },
      {
        'name': 'atr',
        'period': 14,
        'series': {'value': wave(n, 4.2, 1.6, from: 14)},
      },
    ],
    'annotations': drawingsFixture,
  };
}

final chartRows = <Json>[
  ...chartsFixture,
  {
    'id': 'c-2',
    'agent_id': 'a-research',
    'thread_id': 't-research',
    'version': 1,
    'payload': {
      'account_id': 'acct-1',
      'symbol': 'EURUSD',
      'timeframe': '4h',
      'indicators': [],
      'annotations': [],
    },
    'state': {},
  },
];

void scriptCharts() {
  fakeApi
    ..on('GET /charts', (_, _) => chartRows)
    ..on('GET /charts/c-1/scene', (_, _) => sceneFixture())
    ..on(
      'GET /charts/c-2/scene',
      (_, _) => {
        ...sceneFixture(id: 'c-2', n: 0),
        'symbol': 'EURUSD',
        'timeframe': '4h',
      },
    )
    ..on('POST /charts/c-1/refresh', (_, _) => {'requested': true})
    ..on('GET /trading/connections', (_, _) => connectionsFixture)
    ..on('GET /market/symbols', (_, _) => ['XAUUSD', 'EURUSD', 'US30']);
}

void main() {
  setUpAll(setUpWpf);
  setUp(resetWpf);

  group('data', () {
    test('scene parsing, levels, notes, update order', () {
      final scene = ChartScene.fromJson(sceneFixture());
      expect(scene.candles, hasLength(120));
      expect(scene.quote!.bid, '2401.74');
      expect(scene.indicators.first.overlay, isTrue);
      expect(scene.indicators.last.overlay, isFalse);
      expect(scene.indicators.last.bounded, isTrue);
      expect(scene.indicators.first.label, 'EMA 20');
      final level = scene.drawings().first;
      expect(
        (level.kind, level.price, level.label),
        ('horizontal_line', 2395, 'Resistance 2395'),
      );
      expect(scene.notes().single, startsWith('الاختراق'));
      final older = ChartScene.fromJson(sceneFixture(version: 6));
      expect(scene.acceptsUpdate(older), isFalse);
      expect(older.acceptsUpdate(scene), isTrue);
    });

    test('drawings: every kind, scope and timeframes', () {
      final scene = ChartScene.fromJson(drawnScene());
      final drawings = scene.drawings(accountId: 'acct-1');
      expect(
        [for (final d in drawings) d.kind],
        [
          'horizontal_line',
          'trend_line',
          'ray',
          'channel',
          'price_zone',
          'fibonacci',
          'arrow',
          'scenario',
          'note',
          'note',
        ],
      );
      final ray = drawings[2];
      expect(
        (ray.color, ray.lineStyle, ray.lineWidth),
        (0xFFD95A64, 'dashed', 2),
      );
      expect(drawings[1].byAgent, isTrue);
      expect(drawings[3].parallel!.price, 2391);
      expect(drawings[5].levels, fibonacciLevels);
      expect(drawings[7].stop, 2374);
      expect(drawings[7].prices, [2380, 2392, 2374]);
      expect(drawings[8].onChart, isTrue);
      expect(drawings[9].onChart, isFalse);
      expect(scene.notes(accountId: 'acct-1').single, startsWith('الاختراق'));
      // A drawing of another account is not this chart's.
      expect(
        ChartScene.fromJson({
          ...drawnScene(),
          'annotations': [
            {
              'type': 'price',
              'price': 2390,
              'scope': {
                'account_id': 'acct-2',
                'symbol': 'XAUUSD',
                'chart_id': 'c-1',
              },
            },
          ],
        }).drawings(accountId: 'acct-1'),
        isEmpty,
      );
      expect(ChartDrawing.fromJson({'type': 'trend_line'}), isNull);
      expect(ChartDrawing.fromJson({'type': 'unknown', 'price': 1}), isNull);
      final macd = scene.indicators.firstWhere((i) => i.name == 'macd');
      expect((macd.overlay, macd.bounded), (false, false));
      expect(macd.series.keys, ['macd', 'signal', 'histogram']);
    });

    test('visible window keeps series aligned with candles', () {
      final candles = candlesFrom(hourlyCandles('X', 10));
      final w = visibleWindow(candles, [
        [for (var i = 0; i < 10; i++) i.toDouble()],
        [7.0, 8.0, 9.0],
      ], 4);
      expect(w.candles, hasLength(4));
      expect(w.candles.first.time, candles[6].time);
      expect(w.series[0], [6.0, 7.0, 8.0, 9.0]);
      expect(w.series[1], [null, 7.0, 8.0, 9.0]);
      expect(visibleWindow(candles, const [], null).candles, hasLength(10));
    });

    test('price range, decimals and axis times', () {
      final r = priceRange(candlesFrom(dailyFor('XAUUSD')));
      expect(r.min, lessThan(2371));
      expect(r.max, greaterThan(2405));
      expect(priceDecimals(30), 1);
      expect(priceDecimals(0.004), 5);
      final t = DateTime(2026, 11, 27, 9, 5);
      expect(axisTime(t, '1h'), '09:05');
      expect(axisTime(t, '1d'), '27/11');
      expect(readoutTime(t), '2026-11-27 09:05');
      expect(chartTimeframes, hasLength(21));
      expect(chartTimeframes.last, '1mn');
    });
  });

  testWidgets('draws the selected chart with its readout and quote', (
    tester,
  ) async {
    scriptCharts();
    await pumpWpf(tester, const ChartsScreen(chartId: 'c-1'), locale: 'en');
    expect(find.text('XAUUSD · 1h'), findsOneWidget);
    expect(find.text('EURUSD · 4h'), findsOneWidget);
    expect(find.byType(CandleChart), findsOneWidget);
    expect(find.byType(IndicatorPane), findsOneWidget);
    expect(find.textContaining('RSI 14$dotSeparator'), findsOneWidget);
    expect(find.textContaining('O 2'), findsOneWidget);
    expect(fakeApi.callsTo('GET', '/charts/c-1/scene'), isNotEmpty);
    // Crosshair: a tap on the chart reads that candle.
    final before = (tester.widget<Text>(find.textContaining(' · O ')).data)!;
    await tester.tapAt(
      tester.getTopLeft(find.byType(CandleChart)) + const Offset(40, 100),
    );
    await tester.pump();
    final after = (tester.widget<Text>(find.textContaining(' · O ')).data)!;
    expect(after, isNot(before));
    // ma:C3: the quote's source is named under the market sheet's label.
    await scrollTo(tester, find.text('Source'));
    expect(find.text('Simulation'), findsOneWidget);
    expect(find.text('simulation'), findsNothing);
    expect(find.text('Details'), findsNothing);
    await unmount(tester);
  });

  testWidgets('MACD and ATR get their own panes', (tester) async {
    scriptCharts();
    fakeApi.on('GET /charts/c-1/scene', (_, _) => drawnScene());
    await pumpWpf(tester, const ChartsScreen(), locale: 'en');
    expect(find.byType(IndicatorPane), findsNWidgets(3));
    // ma:C10: the series read by name, not by their keys.
    expect(
      find.textContaining('MACD 12$dotSeparator${isolate('MACD')} '),
      findsOneWidget,
    );
    expect(
      find.textContaining('$dotSeparator${isolate('Signal')} '),
      findsOneWidget,
    );
    expect(
      find.textContaining('$dotSeparator${isolate('Histogram')} '),
      findsOneWidget,
    );
    expect(find.textContaining('macd'), findsNothing);
    expect(find.textContaining('ATR 14$dotSeparator'), findsOneWidget);
    // The unanchored note is listed; the anchored one is drawn on the chart.
    await scrollTo(tester, find.text('Chart notes'));
    expect(find.textContaining('الاختراق'), findsOneWidget);
    expect(find.text('Breakout?'), findsNothing);
    await unmount(tester);
  });

  testWidgets('crosshair: one cursor for chart, readout and panes', (
    tester,
  ) async {
    scriptCharts();
    await pumpWpf(tester, const ChartsScreen(), locale: 'en');
    CandleChart chart() => tester.widget<CandleChart>(find.byType(CandleChart));
    String readout() => tester.widget<Text>(find.textContaining(' · O ')).data!;
    final idle = readout();
    final at =
        tester.getTopLeft(find.byType(CandleChart)) + const Offset(40, 100);
    await tester.tapAt(at);
    await tester.pump();
    final pinned = chart().cursor;
    expect(pinned, isNotNull);
    expect(readout(), isNot(idle));
    expect(
      tester.widget<IndicatorPane>(find.byType(IndicatorPane)).cursor,
      pinned,
    );
    // A second tap on the same candle lets go.
    await tester.tapAt(at);
    await tester.pump();
    expect(chart().cursor, isNull);
    expect(readout(), idle);
    // A new range lets go too: the chart never keeps a candle the readout dropped.
    await tester.tapAt(at);
    await tester.pump();
    expect(chart().cursor, isNotNull);
    await scrollTo(tester, find.text('All'));
    await tapAndSettle(tester, find.text('All'));
    expect(chart().cursor, isNull);
    await unmount(tester);
  });

  testWidgets('in Arabic the update time reads in Arabic-Indic digits; the '
      'axes stay Latin', (tester) async {
    scriptCharts();
    await pumpWpf(tester, const ChartsScreen(), locale: 'ar');
    final updated = find.textContaining('آخر تحديث · ');
    await tester.scrollUntilVisible(
      updated,
      200,
      scrollable: find
          .byWidgetPredicate(
            (w) => w is Scrollable && w.axisDirection == AxisDirection.down,
          )
          .first,
    );
    final line = tester.widget<Text>(updated).data!;
    final local = DateTime.parse('2026-11-27T09:40:00Z').toLocal();
    expect(line, contains(dateDigits(readoutTime(local), 'ar')));
    expect(RegExp('[0-9]').hasMatch(line), isFalse, reason: line);
    // Axis labels: hours in Latin digits.
    final axis = find.descendant(
      of: find.byType(CandleChart),
      matching: find.textContaining(RegExp(r'^\d{2}:\d{2}$')),
    );
    expect(axis, findsWidgets);
    expect(
      find.descendant(
        of: find.byType(CandleChart),
        matching: find.textContaining(RegExp('[٠-٩]')),
      ),
      findsNothing,
    );
    await unmount(tester);
  });

  testWidgets('a live scene update is read; other charts are not', (
    tester,
  ) async {
    scriptCharts();
    await pumpWpf(tester, const ChartsScreen(), locale: 'en');
    final reads = fakeApi.callsTo('GET', '/charts/c-1/scene').length;
    fakeRealtime.emit('cloud_charts.scene_updated', {'id': 'c-2'});
    await tester.pump();
    expect(fakeApi.callsTo('GET', '/charts/c-1/scene'), hasLength(reads));
    fakeRealtime.emit('cloud_charts.scene_updated', {'id': 'c-1'});
    await tester.pump();
    expect(fakeApi.callsTo('GET', '/charts/c-1/scene'), hasLength(reads + 1));
    await unmount(tester);
  });

  testWidgets('a failed later read is shown over the last chart', (
    tester,
  ) async {
    scriptCharts();
    await pumpWpf(tester, const ChartsScreen(), locale: 'en');
    expect(find.byType(CandleChart), findsOneWidget);
    fakeApi.on(
      'GET /charts/c-1/scene',
      (_, _) => throw ApiError(status: 409, code: 'chart_data_unavailable'),
    );
    fakeRealtime.emit('cloud_charts.scene_updated', {'id': 'c-1'});
    await tester.pumpAndSettle();
    expect(find.byType(CandleChart), findsOneWidget);
    expect(
      find.text(L10n.instance.errorText('chart_data_unavailable')),
      findsOneWidget,
    );
    await unmount(tester);
  });

  testWidgets('range selector and refresh request', (tester) async {
    scriptCharts();
    await pumpWpf(tester, const ChartsScreen(), locale: 'en');
    CandleChart chart() => tester.widget<CandleChart>(find.byType(CandleChart));
    expect(chart().candles, hasLength(60));
    await scrollTo(tester, find.text('All'));
    await tapAndSettle(tester, find.text('All'));
    expect(chart().candles, hasLength(120));
    // The range's «30», not the RSI guide's.
    await tapAndSettle(
      tester,
      find.descendant(
        of: find.byType(LnSegmented<int>),
        matching: find.text('30'),
      ),
    );
    expect(chart().candles, hasLength(30));
    await tester.drag(find.byType(Scrollable).first, const Offset(0, 600));
    await tester.pumpAndSettle();
    await tapAndSettle(tester, find.bySemanticsLabel('Refresh'));
    expect(fakeApi.callsTo('POST', '/charts/c-1/refresh'), hasLength(1));
    expect(find.text('Chart refresh requested'), findsOneWidget);
    await settleToasts(tester);
    await unmount(tester);
  });

  testWidgets('switching charts and an empty scene', (tester) async {
    scriptCharts();
    await pumpWpf(tester, const ChartsScreen(), locale: 'en');
    bool selected(String label) => tester
        .widget<LnChoiceChip>(find.widgetWithText(LnChoiceChip, label))
        .selected;
    expect(selected('XAUUSD · 1h'), isTrue);
    await tapAndSettle(tester, find.text('EURUSD · 4h'));
    expect(selected('EURUSD · 4h'), isTrue);
    expect(selected('XAUUSD · 1h'), isFalse);
    expect(find.text('No saved candles yet'), findsOneWidget);
    expect(find.text('Open conversation'), findsOneWidget);
    await tapAndSettle(tester, find.text('Open conversation'));
    expect(shownRoute(tester), '/chats/thread/t-research');
    await unmount(tester);
  });

  testWidgets('a chart still initialising says so', (tester) async {
    scriptCharts();
    fakeApi.on(
      'GET /charts/c-1/scene',
      (_, _) => throw ApiError(status: 409, code: 'chart_initializing'),
    );
    await pumpWpf(tester, const ChartsScreen(), locale: 'en', settle: false);
    expect(find.text('Preparing chart'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('creates a chart without picking a symbol for the owner', (
    tester,
  ) async {
    scriptCharts();
    fakeApi
      ..on('GET /charts', (_, _) => [])
      ..on(
        'POST /charts',
        (body, _) => {
          'id': 'c-new',
          'payload': (body! as Map)['payload'],
          'version': 1,
        },
      );
    await pumpWpf(tester, const ChartsScreen(threadId: 't-gold'), locale: 'en');
    expect(find.text('No charts yet'), findsOneWidget);
    await tapAndSettle(tester, find.text('Create chart').last);
    await tapAndSettle(tester, find.textContaining('Lonora Sim'));
    expect(find.text('US30'), findsOneWidget);
    // No symbol is chosen yet, so Save is disabled.
    await tapAndSettle(tester, find.text('Save'));
    expect(fakeApi.callsTo('POST', '/charts'), isEmpty);
    await tapAndSettle(tester, find.text('US30'));
    await tester.scrollUntilVisible(
      find.text('4h'),
      100,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, find.text('4h'));
    fakeApi.on(
      'GET /charts',
      (_, _) => [
        {
          'id': 'c-new',
          'thread_id': 't-gold',
          'payload': {
            'account_id': 'acct-1',
            'symbol': 'US30',
            'timeframe': '4h',
          },
        },
      ],
    );
    await tapAndSettle(tester, find.text('Save'));
    expect(fakeApi.callsTo('POST', '/charts').single.body, {
      'payload': {
        'account_id': 'acct-1',
        'symbol': 'US30',
        'timeframe': '4h',
        'indicators': [],
        'annotations': [],
      },
      'agent_id': null,
      'thread_id': 't-gold',
    });
    expect(find.text('US30 · 4h'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('an agent bound to a market only sees its charts', (
    tester,
  ) async {
    scriptCharts();
    await pumpWpf(tester, const ChartsScreen(agentId: 'a-gold'), locale: 'en');
    expect(find.text('XAUUSD · 1h'), findsOneWidget);
    expect(find.text('EURUSD · 4h'), findsNothing);
    await unmount(tester);
  });

  testWidgets('text scale 1.3 does not overflow', (tester) async {
    scriptCharts();
    await pumpWpf(tester, const ChartsScreen(), textScale: 1.3);
    expect(tester.takeException(), isNull);
    await scrollTo(tester, find.text('الكل'));
    expect(tester.takeException(), isNull);
    await unmount(tester);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      scriptCharts();
      await withRealShadows(() async {
        await pumpWpf(
          tester,
          const ChartsScreen(),
          brightness: v.brightness,
          locale: v.locale,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/charts_${v.name}.png'),
        );
      });
      await unmount(tester);
    });
  }

  for (final v in [goldenVariants[0], goldenVariants[3]]) {
    testWidgets('golden drawings ${v.name}', (tester) async {
      scriptCharts();
      fakeApi.on('GET /charts/c-1/scene', (_, _) => drawnScene());
      await withRealShadows(() async {
        await pumpWpf(
          tester,
          const ChartsScreen(),
          brightness: v.brightness,
          locale: v.locale,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/charts_drawings_${v.name}.png'),
        );
        await tester.drag(find.byType(Scrollable).first, const Offset(0, -420));
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/charts_panes_${v.name}.png'),
        );
      });
      await unmount(tester);
    });
  }

  testWidgets('golden crosshair and lower part', (tester) async {
    scriptCharts();
    await pumpWpf(tester, const ChartsScreen(), locale: 'ar');
    final gesture = await tester.startGesture(
      tester.getTopLeft(find.byType(CandleChart)) + const Offset(150, 120),
    );
    await tester.pump(const Duration(milliseconds: 600));
    await gesture.moveBy(const Offset(30, 0));
    await tester.pump();
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/charts_crosshair_ar.png'),
    );
    await gesture.up();
    await tester.pumpAndSettle();
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -500));
    await tester.pumpAndSettle();
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/charts_lower_ar.png'),
    );
    await unmount(tester);
  });

  testWidgets('golden create sheet', (tester) async {
    scriptCharts();
    await pumpWpf(tester, const ChartsScreen(), locale: 'ar');
    await tapAndSettle(tester, find.bySemanticsLabel('إنشاء رسم بياني'));
    await tapAndSettle(tester, find.textContaining('Lonora Sim'));
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/charts_create_ar.png'),
    );
    await unmount(tester);
  });
}
