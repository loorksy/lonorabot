// Lonora's persistent market charts (`/api/charts`, apps/mobile lib/charts.ts): the catalog,
// the stored scene (`GET /charts/{id}/scene`: candles, quote, indicator series, annotations),
// a refresh request and chart creation (`POST /charts`, as the Expo app's Save does).
import 'package:flutter/foundation.dart';

import '../../app/services.dart';
import '../../core/json.dart';
import '../market/market_data.dart';

/// The 21 canonical MT5 intervals, with the official SDK's monthly spelling
/// (apps/mobile/lib/charts.ts `CHART_TIMEFRAMES`).
const chartTimeframes = [
  '1m',
  '2m',
  '3m',
  '4m',
  '5m',
  '6m',
  '10m',
  '12m',
  '15m',
  '20m',
  '30m',
  '1h',
  '2h',
  '3h',
  '4h',
  '6h',
  '8h',
  '12h',
  '1d',
  '1w',
  '1mn',
];

/// A chart resource row of `GET /charts` (its catalog state omits the scene).
@immutable
class ChartRow {
  const ChartRow(this.raw);

  final Json raw;

  String get id => asStr(raw['id']);
  String? get agentId => asString(raw['agent_id']);
  String? get threadId => asString(raw['thread_id']);
  Json get payload => asJson(raw['payload']);
  String get accountId => asStr(payload['account_id']);
  String get symbol => asStr(payload['symbol']);
  String get timeframe => asStr(payload['timeframe']);
  DateTime? get updatedAt => asDate(raw['updated_at']);
}

/// One indicator of a scene: its name, period and series (key → values aligned to candles).
@immutable
class SceneIndicator {
  const SceneIndicator({
    required this.name,
    required this.period,
    required this.series,
  });

  factory SceneIndicator.fromJson(Json j) => SceneIndicator(
    name: asStr(j['name']).toLowerCase(),
    period: asInt(j['period']),
    series: {
      for (final e in asJson(j['series']).entries)
        if (e.value is List)
          e.key: [for (final v in e.value as List) asDouble(v)],
    },
  );

  final String name;
  final int? period;
  final Map<String, List<double?>> series;

  /// Drawn over the candles (lonora_charts scene_snapshot: SMA, EMA, Bollinger); every
  /// other indicator (RSI, MACD, ATR) gets its own pane under them.
  bool get overlay =>
      const {'ema', 'sma', 'bollinger_bands', 'bollinger'}.contains(name);

  /// Its pane is the fixed 0–100 scale with 30 / 70 guides (RSI); other panes span their
  /// own values.
  bool get bounded => name == 'rsi';

  String get label => [name.toUpperCase(), ?period?.toString()].join(' ');
}

/// `GET /charts/{id}/scene` (apps/mobile lib/charts.ts `ChartScene`).
@immutable
class ChartScene {
  const ChartScene({
    required this.chartId,
    required this.revision,
    required this.sceneVersion,
    required this.symbol,
    required this.timeframe,
    required this.candles,
    this.quote,
    this.indicators = const [],
    this.annotations = const [],
    this.updatedAt,
  });

  factory ChartScene.fromJson(Json j) {
    final quote = asJson(j['quote']);
    return ChartScene(
      chartId: asStr(j['chart_id']),
      revision: asInt(j['revision']) ?? 0,
      sceneVersion: asInt(j['scene_version']) ?? 0,
      symbol: asStr(j['symbol']),
      timeframe: asStr(j['timeframe']),
      candles: candlesFrom(j['candles']),
      quote: quote.isEmpty ? null : MarketQuote.fromJson(quote),
      indicators: asJsonList(j['indicators'])
          .map(SceneIndicator.fromJson)
          .toList(),
      annotations: asJsonList(j['annotations']),
      updatedAt: asDate(j['updated_at']),
    );
  }

  final String chartId;
  final int revision;
  final int sceneVersion;
  final String symbol;
  final String timeframe;
  final List<MarketCandle> candles;
  final MarketQuote? quote;
  final List<SceneIndicator> indicators;
  final List<Json> annotations;
  final DateTime? updatedAt;

  /// Whether [next] may replace this scene: an older revision or scene version never does
  /// (apps/mobile app/charts.tsx scene refresh).
  bool acceptsUpdate(ChartScene next) =>
      next.chartId != chartId ||
      (next.revision >= revision && next.sceneVersion >= sceneVersion);

  /// The drawings of this chart on [accountId]: those scoped to another chart, market or
  /// account, or to other timeframes, are left out (apps/web lib/tradingview-drawings.ts
  /// `drawingVisible`).
  List<ChartDrawing> drawings({String? accountId}) => [
    for (final a in annotations)
      if (_visible(a, accountId)) ?ChartDrawing.fromJson(a),
  ];

  bool _visible(Json a, String? accountId) {
    final scope = asJson(a['scope']);
    bool same(String key, String? value) {
      final v = asString(scope[key]);
      return v == null || v.isEmpty || value == null || v == value;
    }

    final frames = a['timeframes'];
    return same('chart_id', chartId) &&
        same('symbol', symbol) &&
        same('account_id', accountId) &&
        (frames is! List || frames.contains(timeframe));
  }

  /// The notes not anchored on the chart, listed under it.
  List<String> notes({String? accountId}) => [
    for (final d in drawings(accountId: accountId))
      if (d.kind == 'note' && !d.onChart && d.label.trim().isNotEmpty)
        d.label.trim(),
  ];
}

/// A point of a drawing.
@immutable
class ChartPoint {
  const ChartPoint(this.time, this.price);

  final DateTime time;
  final double price;

  static ChartPoint? fromJson(Object? value) {
    final j = asJson(value);
    final time = asDate(j['time']);
    final price = asDouble(j['price']);
    return time == null || price == null ? null : ChartPoint(time, price);
  }
}

/// The ten drawing kinds of a chart (lonora_core chart_annotations `ANNOTATION_TYPES`).
const chartDrawingKinds = {
  'price',
  'horizontal_line',
  'trend_line',
  'note',
  'price_zone',
  'ray',
  'channel',
  'fibonacci',
  'arrow',
  'scenario',
};

/// A Fibonacci drawing's levels when it names none (lonora_core `FIBONACCI_LEVELS`).
const fibonacciLevels = [0.0, 0.236, 0.382, 0.5, 0.618, 1.0];

/// One saved drawing in time and price, with its inert style. Levels (`price`,
/// `horizontal_line`) and notes have a price (a note may also have a time); the other kinds
/// run from [start] to [end] (a channel adds [parallel], a scenario its [stop]).
@immutable
class ChartDrawing {
  const ChartDrawing({
    required this.kind,
    this.label = '',
    this.price,
    this.time,
    this.start,
    this.end,
    this.parallel,
    this.stop,
    this.levels = fibonacciLevels,
    this.color,
    this.lineWidth = 1,
    this.lineStyle = 'solid',
    this.byAgent = false,
  });

  /// Null for an unknown kind or missing geometry (the server validated it; nothing is
  /// guessed here).
  static ChartDrawing? fromJson(Json a) {
    final kind = asStr(a['type']);
    if (!chartDrawingKinds.contains(kind)) return null;
    final style = asJson(a['style']);
    final hex = asString(style['color']);
    final color = hex != null && RegExp(r'^#[0-9a-fA-F]{6}$').hasMatch(hex)
        ? 0xFF000000 | int.parse(hex.substring(1), radix: 16)
        : null;
    final start = ChartPoint.fromJson(a['start']);
    final end = ChartPoint.fromJson(a['end']);
    final price = asDouble(a['price']);
    final line = kind == 'price' || kind == 'horizontal_line';
    if (line && price == null) return null;
    if (!line && kind != 'note' && (start == null || end == null)) return null;
    final levels = [
      for (final v in a['levels'] is List ? a['levels'] as List : const [])
        ?asDouble(v),
    ];
    return ChartDrawing(
      kind: kind,
      label: asString(a['label']) ?? asString(a['text']) ?? '',
      price: price,
      time: asDate(a['time']),
      start: start,
      end: end,
      parallel: ChartPoint.fromJson(a['parallel']),
      stop: asDouble(a['stop']),
      levels: levels.length >= 2 ? levels : fibonacciLevels,
      color: color,
      lineWidth: (asDouble(style['line_width']) ?? 1).clamp(1, 5).toDouble(),
      lineStyle: asString(style['line_style']) ?? 'solid',
      byAgent: a['source'] == 'agent',
    );
  }

  final String kind;
  final String label;
  final double? price;
  final DateTime? time;
  final ChartPoint? start;
  final ChartPoint? end;
  final ChartPoint? parallel;
  final double? stop;
  final List<double> levels;

  /// `#RRGGBB` of the drawing's style as an opaque ARGB value, or null (the chart's own).
  final int? color;
  final double lineWidth;

  /// `solid`, `dashed` or `dotted`.
  final String lineStyle;
  final bool byAgent;

  /// Drawn on the chart; a note without a time and a price is listed under it instead.
  bool get onChart => kind != 'note' || (time != null && price != null);

  /// Every price the drawing reaches (the chart's price range covers them).
  List<double> get prices => [
    ?price,
    ?start?.price,
    ?end?.price,
    ?parallel?.price,
    ?stop,
  ];
}

/// The last [count] candles (all when null or larger), and each series cut the same way so
/// that values stay aligned with their candle.
({List<MarketCandle> candles, List<List<double?>> series}) visibleWindow(
  List<MarketCandle> candles,
  List<List<double?>> series,
  int? count,
) {
  final n = count == null || count >= candles.length ? candles.length : count;
  final start = candles.length - n;
  return (
    candles: candles.sublist(start),
    series: [
      for (final s in series)
        // A series aligned to the candles ends with the last candle.
        s.length >= n
            ? s.sublist(s.length - n)
            : [...List.filled(n - s.length, null), ...s],
    ],
  );
}

/// The price range of [candles] and the [extra] prices in view (overlay values, drawings),
/// padded by 7 % as the Expo chart is.
({double min, double max}) priceRange(
  List<MarketCandle> candles, {
  List<double> extra = const [],
}) {
  var lo = double.infinity, hi = double.negativeInfinity;
  for (final c in candles) {
    if (c.low < lo) lo = c.low;
    if (c.high > hi) hi = c.high;
  }
  for (final v in extra) {
    if (!v.isFinite) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (!lo.isFinite || !hi.isFinite) return (min: 0, max: 1);
  final range = (hi - lo) > 0
      ? hi - lo
      : (lo.abs() * 0.001).clamp(1e-9, double.infinity);
  return (min: lo - range * 0.07, max: hi + range * 0.07);
}

Future<List<ChartRow>> fetchCharts({String? threadId}) async =>
    asJsonList(await api.get('/charts', query: {'thread_id': ?threadId}))
        .map(ChartRow.new)
        .toList();

Future<ChartScene> fetchScene(String id) async => ChartScene.fromJson(
  asJson(await api.get('/charts/${Uri.encodeComponent(id)}/scene')),
);

Future<void> requestChartRefresh(String id) async {
  await api.post('/charts/${Uri.encodeComponent(id)}/refresh', const {});
}

/// `POST /charts` with an empty set of indicators and annotations (the Expo app's Save).
Future<ChartRow> createChart({
  required String accountId,
  required String symbol,
  required String timeframe,
  String? agentId,
  String? threadId,
}) async => ChartRow(
  asJson(
    await api.post('/charts', {
      'payload': {
        'account_id': accountId,
        'symbol': symbol,
        'timeframe': timeframe,
        'indicators': <Object?>[],
        'annotations': <Object?>[],
      },
      'agent_id': agentId,
      'thread_id': threadId,
    }),
  ),
);
