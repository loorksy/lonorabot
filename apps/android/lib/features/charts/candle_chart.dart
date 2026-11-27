// Native market charts on fl_chart: candlesticks with indicator overlays and the scene's ten
// drawing kinds, a crosshair that reads one candle (touch and drag), indicator panes and a
// sparkline. The geometry follows the Expo app's native fallback (apps/mobile
// components/candlestick-chart.tsx: 7 % price padding, rising/falling colours, overlays for
// EMA/SMA/Bollinger, RSI 30/70 pane) and draws what the server's own renderer draws (lonora_charts
// scene_snapshot.py: every indicator not overlaid in a pane, levels, trend lines, rays, channels,
// zones, Fibonacci, arrows, scenarios, anchored notes). Time runs left to right in both languages,
// prices sit on the right edge and every number is laid out left to right, so Arabic never
// mirrors the axes.
import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../design/design.dart';
import '../../l10n/l10n.dart'
    show L10nContext, dotSeparator, isolate, readingDirection;
import '../market/market_data.dart';
import 'charts_data.dart';

/// Width of the price axis on the right edge (shared by every pane so they line up).
const double priceAxisWidth = 58;
const double _timeAxisHeight = 22;

/// Digits after the point for axis labels covering [span].
int priceDecimals(double span) {
  if (!span.isFinite || span <= 0) return 2;
  final d = (2 - (math.log(span) / math.ln10).floor()).clamp(0, 6);
  return d;
}

String _two(int v) => v.toString().padLeft(2, '0');

/// A candle's time on the axis: hours for intraday frames, day/month for daily and longer.
String axisTime(DateTime t, String timeframe) {
  final daily =
      timeframe.endsWith('d') || timeframe.endsWith('w') || timeframe == '1mn';
  return daily ? '${t.day}/${t.month}' : '${_two(t.hour)}:${_two(t.minute)}';
}

/// A candle's full time for the readout: 2026-11-27 14:00.
String readoutTime(DateTime t) =>
    '${t.year}-${_two(t.month)}-${_two(t.day)} ${_two(t.hour)}:${_two(t.minute)}';

/// A candle chart. The crosshair is the parent's: [cursor] is the candle it reads (null: none)
/// and [onCursor] reports touches, so the chart, the readout and the panes below never
/// disagree. A drag or a long press follows the finger and lets go on release; a tap pins a
/// candle and a second tap on it lets go.
class CandleChart extends StatelessWidget {
  const CandleChart({
    super.key,
    required this.candles,
    required this.timeframe,
    this.overlays = const [],
    this.drawings = const [],
    this.height = 280,
    this.cursor,
    this.onCursor,
    this.semanticLabel,
  });

  final List<MarketCandle> candles;
  final String timeframe;

  /// Series aligned with [candles] (same length, null gaps).
  final List<List<double?>> overlays;

  /// The scene's drawings (levels, lines, zones, Fibonacci, scenarios, anchored notes).
  final List<ChartDrawing> drawings;
  final double height;
  final int? cursor;
  final ValueChanged<int?>? onCursor;
  final String? semanticLabel;

  int _indexAt(double dx, double plotWidth) {
    final n = candles.length;
    final i = (dx / plotWidth * n - 0.5).round();
    return i.clamp(0, n - 1);
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final n = candles.length;
    final shownCursor = cursor != null && cursor! < n ? cursor : null;
    final onChart = [
      for (final d in drawings)
        if (d.onChart) d,
    ];
    final range = priceRange(
      candles,
      extra: [
        for (final s in overlays)
          for (final v in s) ?v,
        for (final d in onChart) ...d.prices,
      ],
    );
    final decimals = priceDecimals(range.max - range.min);
    final labelStyle = ln.text.micro.copyWith(color: c.fgMuted);
    final every = math.max(1, (n / 4).floor());

    FlTitlesData titles({required bool visible}) => FlTitlesData(
      leftTitles: const AxisTitles(),
      topTitles: const AxisTitles(),
      rightTitles: AxisTitles(
        sideTitles: SideTitles(
          showTitles: true,
          reservedSize: priceAxisWidth,
          minIncluded: false,
          maxIncluded: false,
          getTitlesWidget: (value, meta) => visible
              ? SideTitleWidget(
                  meta: meta,
                  space: 6,
                  child: Text(
                    value.toStringAsFixed(decimals),
                    style: labelStyle,
                  ),
                )
              : const SizedBox.shrink(),
        ),
      ),
      bottomTitles: AxisTitles(
        sideTitles: SideTitles(
          showTitles: true,
          reservedSize: _timeAxisHeight,
          interval: 1,
          getTitlesWidget: (value, meta) {
            final i = value.round();
            // Anchored on the latest candle, clear of both plot edges.
            final shown =
                visible &&
                i == value &&
                i >= 2 &&
                i <= n - 3 &&
                (n - 1 - i) % every == every ~/ 2;
            if (!shown) return const SizedBox.shrink();
            return SideTitleWidget(
              meta: meta,
              space: 4,
              child: Text(
                axisTime(candles[i].time, timeframe),
                style: labelStyle,
              ),
            );
          },
        ),
      ),
    );

    final grid = FlGridData(
      drawVerticalLine: false,
      getDrawingHorizontalLine: (_) => FlLine(color: c.border, strokeWidth: 1),
    );

    final candleChart = CandlestickChart(
      CandlestickChartData(
        candlestickSpots: [
          for (final (i, k) in candles.indexed)
            CandlestickSpot(
              x: i.toDouble(),
              open: k.open,
              high: k.high,
              low: k.low,
              close: k.close,
            ),
        ],
        minX: -0.5,
        maxX: n - 0.5,
        minY: range.min,
        maxY: range.max,
        titlesData: titles(visible: true),
        gridData: grid,
        borderData: FlBorderData(show: false),
        candlestickTouchData: CandlestickTouchData(enabled: false),
        candlestickPainter: DefaultCandlestickPainter(
          candlestickStyleProvider: (spot, _) {
            final color = spot.close >= spot.open ? c.positive : c.negative;
            final body = math.max(1.0, 160 / math.max(n, 1)).clamp(1.0, 9.0);
            return CandlestickStyle(
              lineColor: color,
              lineWidth: 1,
              bodyStrokeColor: color,
              bodyStrokeWidth: 0,
              bodyFillColor: color,
              bodyWidth: body,
              bodyRadius: 1,
            );
          },
        ),
      ),
      duration: Duration.zero,
    );

    final overlayColors = [c.warning, c.brand, c.selection];
    final lines = [
      for (final (i, s) in overlays.indexed)
        LineChartBarData(
          spots: [
            for (final (x, v) in s.indexed)
              v == null || !v.isFinite
                  ? FlSpot.nullSpot
                  : FlSpot(x.toDouble(), v),
          ],
          color: overlayColors[i % overlayColors.length],
          barWidth: 1.4,
          isCurved: false,
          dotData: const FlDotData(show: false),
        ),
    ];
    final overlay = LineChart(
      LineChartData(
        minX: -0.5,
        maxX: n - 0.5,
        minY: range.min,
        maxY: range.max,
        lineBarsData: lines,
        titlesData: titles(visible: false),
        gridData: const FlGridData(show: false),
        borderData: FlBorderData(show: false),
        lineTouchData: const LineTouchData(enabled: false),
        // Nothing is drawn over the axes.
        clipData: const FlClipData.all(),
      ),
      duration: Duration.zero,
    );

    return Semantics(
      image: true,
      label: semanticLabel,
      child: Directionality(
        textDirection: TextDirection.ltr,
        child: SizedBox(
          height: height,
          child: LayoutBuilder(
            builder: (context, box) {
              final plotWidth = box.maxWidth - priceAxisWidth;
              final plotHeight = height - _timeAxisHeight;
              int? at(Offset p) => n == 0 || plotWidth <= 0
                  ? null
                  : _indexAt(p.dx.clamp(0, plotWidth), plotWidth);
              void follow(Offset p, {bool start = false}) {
                final i = at(p);
                if (i == null || i == shownCursor) return;
                if (start) HapticFeedback.selectionClick();
                onCursor?.call(i);
              }

              void release() {
                if (shownCursor != null) onCursor?.call(null);
              }

              return GestureDetector(
                behavior: HitTestBehavior.opaque,
                onLongPressStart: (d) => follow(d.localPosition, start: true),
                onLongPressMoveUpdate: (d) => follow(d.localPosition),
                onLongPressEnd: (_) => release(),
                onHorizontalDragStart: (d) =>
                    follow(d.localPosition, start: true),
                onHorizontalDragUpdate: (d) => follow(d.localPosition),
                onHorizontalDragEnd: (_) => release(),
                onTapUp: (d) {
                  final i = at(d.localPosition);
                  if (i == null) return;
                  HapticFeedback.selectionClick();
                  onCursor?.call(i == shownCursor ? null : i);
                },
                child: Stack(
                  children: [
                    Positioned.fill(child: candleChart),
                    if (lines.isNotEmpty)
                      Positioned.fill(child: IgnorePointer(child: overlay)),
                    if (onChart.isNotEmpty && n > 0)
                      Positioned.fill(
                        child: IgnorePointer(
                          child: CustomPaint(
                            painter: _DrawingsPainter(
                              drawings: onChart,
                              times: [
                                for (final k in candles)
                                  k.time.millisecondsSinceEpoch,
                              ],
                              min: range.min,
                              max: range.max,
                              plotWidth: plotWidth,
                              plotHeight: plotHeight,
                              userColor: c.warning,
                              agentColor: c.selection,
                              stopColor: c.negative,
                              plate: c.bg.withValues(alpha: 0.85),
                              labelStyle: labelStyle,
                              decimals: decimals,
                            ),
                          ),
                        ),
                      ),
                    if (shownCursor != null)
                      Positioned.fill(
                        child: IgnorePointer(
                          child: CustomPaint(
                            painter: _CrosshairPainter(
                              x: (shownCursor + 0.5) / n * plotWidth,
                              y:
                                  (range.max - candles[shownCursor].close) /
                                  (range.max - range.min) *
                                  plotHeight,
                              plotWidth: plotWidth,
                              plotHeight: plotHeight,
                              color: c.fgMuted,
                              tagColor: c.fg,
                              tagText: candles[shownCursor].close
                                  .toStringAsFixed(decimals),
                              tagStyle: labelStyle.copyWith(color: c.bg),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

/// The scene's drawings over the plot, in the geometry of lonora_charts scene_snapshot: a
/// time maps onto the candles (between two candles, in proportion; outside them, at the
/// average candle spacing), a price onto the price range. Clipped to the plot.
class _DrawingsPainter extends CustomPainter {
  _DrawingsPainter({
    required this.drawings,
    required this.times,
    required this.min,
    required this.max,
    required this.plotWidth,
    required this.plotHeight,
    required this.userColor,
    required this.agentColor,
    required this.stopColor,
    required this.plate,
    required this.labelStyle,
    required this.decimals,
  });

  final List<ChartDrawing> drawings;
  final List<int> times;
  final double min;
  final double max;
  final double plotWidth;
  final double plotHeight;
  final Color userColor;
  final Color agentColor;
  final Color stopColor;
  final Color plate;
  final TextStyle labelStyle;
  final int decimals;

  double _index(DateTime t) {
    final ms = t.millisecondsSinceEpoch;
    final n = times.length;
    if (n == 1) return 0;
    final step = (times.last - times.first) / (n - 1);
    final spacing = step > 0 ? step : 1.0;
    if (ms <= times.first) return (ms - times.first) / spacing;
    if (ms >= times.last) return n - 1 + (ms - times.last) / spacing;
    var lo = 0, hi = n - 1;
    while (hi - lo > 1) {
      final mid = (lo + hi) >> 1;
      if (times[mid] <= ms) {
        lo = mid;
      } else {
        hi = mid;
      }
    }
    final span = times[hi] - times[lo];
    return lo + (span > 0 ? (ms - times[lo]) / span : 0);
  }

  double _x(DateTime t) => (_index(t) + 0.5) / times.length * plotWidth;
  double _y(double price) => (max - price) / (max - min) * plotHeight;
  Offset _at(ChartPoint p) => Offset(_x(p.time), _y(p.price));

  @override
  void paint(Canvas canvas, Size size) {
    canvas
      ..save()
      ..clipRect(Rect.fromLTWH(0, 0, plotWidth, plotHeight));
    for (final d in drawings) {
      final color = d.color != null
          ? Color(d.color!)
          : (d.byAgent ? agentColor : userColor);
      final paint = Paint()
        ..color = color
        ..strokeWidth = d.lineWidth
        ..style = PaintingStyle.stroke;
      final dash = switch (d.lineStyle) {
        'dashed' => const [5.0, 4.0],
        'dotted' => const [1.0, 3.0],
        _ => null,
      };
      void line(Offset a, Offset b, {Paint? stroke}) =>
          _segment(canvas, a, b, stroke ?? paint, dash);

      switch (d.kind) {
        case 'price' || 'horizontal_line':
          final y = _y(d.price!);
          line(Offset(0, y), Offset(plotWidth, y));
          _label(
            canvas,
            d.label.isEmpty ? d.price!.toStringAsFixed(decimals) : d.label,
            Offset(4, y),
            color,
          );
        case 'note':
          final p = Offset(_x(d.time!), _y(d.price!));
          canvas.drawCircle(p, 2.5, Paint()..color = color);
          _label(canvas, d.label, p + const Offset(4, 0), color);
        default:
          final start = _at(d.start!), end = _at(d.end!);
          final left = math.min(start.dx, end.dx);
          switch (d.kind) {
            case 'price_zone':
              final rect = Rect.fromPoints(start, end);
              canvas.drawRect(
                rect,
                Paint()..color = color.withValues(alpha: 0.12),
              );
              line(rect.topLeft, rect.topRight);
              line(rect.bottomLeft, rect.bottomRight);
            case 'fibonacci':
              final right = math.max(start.dx, end.dx);
              for (final level in d.levels) {
                final y = start.dy + level * (end.dy - start.dy);
                line(Offset(left, y), Offset(right, y));
                _label(canvas, _level(level), Offset(left + 2, y), color);
              }
            case 'scenario':
              // Entry → target, and the stop it would be wrong at (apps/web
              // tradingview-drawings: an arrow and a red stop line). An illustration only.
              _arrow(canvas, start, end, paint, dash);
              if (d.stop != null) {
                final y = _y(d.stop!);
                line(
                  Offset(start.dx, y),
                  Offset(end.dx, y),
                  stroke: Paint()
                    ..color = stopColor
                    ..strokeWidth = d.lineWidth
                    ..style = PaintingStyle.stroke,
                );
              }
            case 'arrow':
              _arrow(canvas, start, end, paint, dash);
            case 'ray':
              final dx = end.dx - start.dx;
              final edge = dx >= 0 ? plotWidth : 0.0;
              final t = dx == 0 ? 0.0 : (edge - start.dx) / dx;
              line(start, start + (end - start) * math.max(1.0, t));
            default: // trend_line, channel
              line(start, end);
              final parallel = d.parallel;
              if (d.kind == 'channel' && parallel != null) {
                final p = _at(parallel);
                final dx = end.dx - start.dx;
                final onLine = dx == 0
                    ? start.dy
                    : start.dy + (end.dy - start.dy) * (p.dx - start.dx) / dx;
                final offset = Offset(0, p.dy - onLine);
                line(start + offset, end + offset);
              }
          }
          if (d.label.isNotEmpty && d.kind != 'fibonacci') {
            // Over a zone's top edge, else at the line's left end.
            final anchor = d.kind == 'price_zone'
                ? Offset(left, math.min(start.dy, end.dy))
                : (start.dx <= end.dx ? start : end);
            _label(canvas, d.label, anchor + const Offset(2, 0), color);
          }
      }
    }
    canvas.restore();
  }

  static String _level(double level) {
    final text = level.toStringAsFixed(3);
    return text.replaceFirst(RegExp(r'\.?0+$'), '');
  }

  void _segment(
    Canvas canvas,
    Offset a,
    Offset b,
    Paint paint,
    List<double>? dash,
  ) {
    if (dash == null) {
      canvas.drawLine(a, b, paint);
      return;
    }
    final length = (b - a).distance;
    if (length == 0) return;
    final dir = (b - a) / length;
    for (var d = 0.0; d < length; d += dash[0] + dash[1]) {
      canvas.drawLine(
        a + dir * d,
        a + dir * math.min(d + dash[0], length),
        paint,
      );
    }
  }

  void _arrow(
    Canvas canvas,
    Offset start,
    Offset end,
    Paint paint,
    List<double>? dash,
  ) {
    _segment(canvas, start, end, paint, dash);
    final angle = math.atan2(end.dy - start.dy, end.dx - start.dx);
    for (final delta in const [-0.45, 0.45]) {
      canvas.drawLine(
        end,
        end - Offset(math.cos(angle + delta), math.sin(angle + delta)) * 10,
        paint,
      );
    }
  }

  /// [text] just above [anchor] (its start at the anchor), on a plate of the page colour so
  /// it reads over candles; in its own reading direction.
  void _label(Canvas canvas, String text, Offset anchor, Color color) {
    if (text.trim().isEmpty) return;
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: labelStyle.copyWith(color: color),
      ),
      textDirection: readingDirection(text) ?? TextDirection.ltr,
      maxLines: 1,
      ellipsis: '…',
    )..layout(maxWidth: math.max(0, plotWidth - anchor.dx - 4));
    final rect = Rect.fromLTWH(
      anchor.dx,
      anchor.dy - tp.height - 3,
      tp.width + 6,
      tp.height + 2,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, const Radius.circular(3)),
      Paint()..color = plate,
    );
    tp.paint(canvas, rect.topLeft + const Offset(3, 1));
  }

  @override
  bool shouldRepaint(_DrawingsPainter old) =>
      !identical(old.drawings, drawings) ||
      old.min != min ||
      old.max != max ||
      old.plotWidth != plotWidth ||
      old.plotHeight != plotHeight ||
      old.userColor != userColor ||
      old.times.length != times.length ||
      (times.isNotEmpty && old.times.last != times.last);
}

class _CrosshairPainter extends CustomPainter {
  _CrosshairPainter({
    required this.x,
    required this.y,
    required this.plotWidth,
    required this.plotHeight,
    required this.color,
    required this.tagColor,
    required this.tagText,
    required this.tagStyle,
  });

  final double x;
  final double y;
  final double plotWidth;
  final double plotHeight;
  final Color color;
  final Color tagColor;
  final String tagText;
  final TextStyle tagStyle;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1;
    void dashed(Offset a, Offset b) {
      final length = (b - a).distance;
      final dir = (b - a) / length;
      for (var d = 0.0; d < length; d += 6) {
        canvas.drawLine(a + dir * d, a + dir * math.min(d + 3, length), paint);
      }
    }

    dashed(Offset(x, 0), Offset(x, plotHeight));
    dashed(Offset(0, y), Offset(plotWidth, y));
    final tp = TextPainter(
      text: TextSpan(text: tagText, style: tagStyle),
      textDirection: TextDirection.ltr,
    )..layout();
    final rect = RRect.fromRectAndRadius(
      Rect.fromLTWH(
        plotWidth + 2,
        (y - tp.height / 2 - 2).clamp(0, plotHeight - tp.height - 4),
        tp.width + 8,
        tp.height + 4,
      ),
      const Radius.circular(4),
    );
    canvas.drawRRect(rect, Paint()..color = tagColor);
    tp.paint(canvas, Offset(rect.left + 4, rect.top + 2));
  }

  @override
  bool shouldRepaint(_CrosshairPainter old) =>
      old.x != x || old.y != y || old.tagText != tagText || old.color != color;
}

/// An indicator in its own pane under the candles, its plot lined up with them: RSI on the
/// fixed 0–100 scale with dashed 30 / 70 guides, MACD, ATR and the others over their own
/// values (a zero line when they cross it). The label reads the values at the crosshair.
class IndicatorPane extends StatelessWidget {
  const IndicatorPane({
    super.key,
    required this.label,
    required this.series,
    this.bounded = false,
    this.cursor,
    this.height = 72,
  });

  final String label;

  /// Series name → values aligned with the candles in view.
  final Map<String, List<double?>> series;

  /// RSI's 0–100 scale.
  final bool bounded;
  final int? cursor;
  final double height;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final lists = series.values.toList();
    final n = lists.isEmpty ? 0 : lists.first.length;
    final style = ln.text.micro.copyWith(color: c.fgMuted);
    final values = [
      for (final s in lists) ...[
        for (final v in s)
          if (v != null && v.isFinite) v,
      ],
    ];
    var lo = bounded ? 0.0 : (values.isEmpty ? 0.0 : values.reduce(math.min));
    var hi = bounded ? 100.0 : (values.isEmpty ? 1.0 : values.reduce(math.max));
    if (!bounded) {
      final pad = hi - lo > 0 ? (hi - lo) * 0.08 : (hi.abs() * 0.01 + 1e-9);
      lo -= pad;
      hi += pad;
    }
    final decimals = bounded ? 1 : priceDecimals(hi - lo);
    final at = cursor != null && cursor! < n ? cursor! : n - 1;
    String read(List<double?> s) {
      final v = at >= 0 && at < s.length ? s[at] : null;
      return v == null || !v.isFinite ? '—' : v.toStringAsFixed(decimals);
    }

    // Known series by their name in the interface language; another key as the server sends it.
    String name(String key) => context.l10n.has('ch_series_$key')
        ? isolate(context.t('ch_series_$key'))
        : key;
    final readout = [
      label,
      if (series.length == 1)
        read(lists.first)
      else
        for (final e in series.entries) '${name(e.key)} ${read(e.value)}',
    ].join(dotSeparator);
    final colors = [c.warning, c.selection, c.brand];
    final guides = bounded ? const [30.0, 70.0] : [if (lo < 0 && hi > 0) 0.0];
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            readout,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: style,
          ),
          const SizedBox(height: 4),
          SizedBox(
            height: height,
            child: LineChart(
              LineChartData(
                minX: -0.5,
                maxX: n - 0.5,
                minY: lo,
                maxY: hi,
                lineBarsData: [
                  for (final (i, s) in lists.indexed)
                    LineChartBarData(
                      spots: [
                        for (final (x, v) in s.indexed)
                          v == null || !v.isFinite
                              ? FlSpot.nullSpot
                              : FlSpot(x.toDouble(), v),
                      ],
                      color: colors[i % colors.length],
                      barWidth: 1.4,
                      dotData: const FlDotData(show: false),
                    ),
                ],
                titlesData: FlTitlesData(
                  leftTitles: const AxisTitles(),
                  topTitles: const AxisTitles(),
                  bottomTitles: const AxisTitles(),
                  rightTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: priceAxisWidth,
                      // Titles are asked at multiples of the interval: 30 and 70 are two.
                      interval: bounded ? 10 : null,
                      getTitlesWidget: (value, meta) =>
                          bounded && (value == 30 || value == 70)
                          ? SideTitleWidget(
                              meta: meta,
                              space: 6,
                              child: Text(
                                value.toStringAsFixed(0),
                                style: style,
                              ),
                            )
                          : const SizedBox.shrink(),
                    ),
                  ),
                ),
                gridData: const FlGridData(show: false),
                borderData: FlBorderData(show: false),
                lineTouchData: const LineTouchData(enabled: false),
                clipData: const FlClipData.all(),
                extraLinesData: ExtraLinesData(
                  horizontalLines: [
                    for (final y in guides)
                      HorizontalLine(
                        y: y,
                        color: c.border,
                        strokeWidth: 1,
                        dashArray: const [4, 4],
                      ),
                  ],
                  verticalLines: [
                    if (cursor != null && cursor! < n)
                      VerticalLine(
                        x: cursor!.toDouble(),
                        color: c.fgMuted,
                        strokeWidth: 1,
                        dashArray: const [3, 3],
                      ),
                  ],
                ),
              ),
              duration: Duration.zero,
            ),
          ),
        ],
      ),
    );
  }
}

/// A small closing-price line (symbol sheet), green when the last close is at or above the
/// first, red otherwise, with a soft fill under it.
class PriceSparkline extends StatelessWidget {
  const PriceSparkline({
    super.key,
    required this.candles,
    this.height = 96,
    this.semanticLabel,
  });

  final List<MarketCandle> candles;
  final double height;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    if (candles.length < 2) return SizedBox(height: height);
    final up = candles.last.close >= candles.first.close;
    final color = up ? c.positive : c.negative;
    var lo = double.infinity, hi = double.negativeInfinity;
    for (final k in candles) {
      lo = math.min(lo, k.close);
      hi = math.max(hi, k.close);
    }
    final pad = (hi - lo) == 0 ? (hi.abs() * 0.001 + 1e-9) : (hi - lo) * 0.1;
    return Semantics(
      image: true,
      label: semanticLabel,
      child: Directionality(
        textDirection: TextDirection.ltr,
        child: SizedBox(
          height: height,
          child: LineChart(
            LineChartData(
              minY: lo - pad,
              maxY: hi + pad,
              lineBarsData: [
                LineChartBarData(
                  spots: [
                    for (final (i, k) in candles.indexed)
                      FlSpot(i.toDouble(), k.close),
                  ],
                  color: color,
                  barWidth: 2,
                  isCurved: true,
                  curveSmoothness: 0.2,
                  dotData: const FlDotData(show: false),
                  belowBarData: BarAreaData(
                    show: true,
                    color: color.withValues(alpha: 0.12),
                  ),
                ),
              ],
              titlesData: const FlTitlesData(show: false),
              gridData: const FlGridData(show: false),
              borderData: FlBorderData(show: false),
              lineTouchData: const LineTouchData(enabled: false),
            ),
            duration: Duration.zero,
          ),
        ),
      ),
    );
  }
}
