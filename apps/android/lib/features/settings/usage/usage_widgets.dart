// The usage dashboard's cards, built from the kit's card surface, segmented control, chips and
// type scale, with an fl_chart bar chart in the app's tokens. Lonora's counterpart of apps/web
// UsagePage.tsx (`PeriodFilter`, `Hero`, `MonthCard`, `Chart`, `Kpis`, `Ranked`). No spending
// cap exists: the month card shows month-to-date spend and its projection, never a limit.
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart' show Colors;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:intl/intl.dart' show NumberFormat;

import '../../../avatar/avatar.dart';
import '../../../core/models/models.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../integrations/ext_common.dart';
import 'usage_data.dart';

/// The width the chart keeps for its dollar axis, on the start side (left in English, right in
/// Arabic); the date labels under the bars start after it.
const double _axisWidth = 44;

/// The heights of the month meter and of the token split bar.
const double _meterHeight = 6;
const double _splitHeight = 4;

/// The rounding of a bar's top.
const double _rodRadius = 3;

/// Today · 7 days · 30 days, with a selection click.
class UsagePeriodSelector extends StatelessWidget {
  const UsagePeriodSelector({
    super.key,
    required this.period,
    required this.onChanged,
  });

  final UsagePeriod period;
  final ValueChanged<UsagePeriod> onChanged;

  @override
  Widget build(BuildContext context) => Semantics(
    label: context.t('us_period'),
    child: LnSegmented<UsagePeriod>(
      segments: [
        LnSegment(value: UsagePeriod.day, label: context.t('today')),
        LnSegment(value: UsagePeriod.week, label: context.t('us_7days')),
        LnSegment(value: UsagePeriod.month, label: context.t('us_30days')),
      ],
      selected: period,
      onChanged: (p) {
        HapticFeedback.selectionClick();
        if (p != period) onChanged(p);
      },
    ),
  );
}

/// The window's words: «the last 30 days» and «the previous thirty days».
({String window, String compare}) periodWords(
  BuildContext context,
  UsagePeriod p,
) => switch (p) {
  UsagePeriod.day => (
    window: context.t('us_todaySoFar'),
    compare: context.t('us_sameTimeYesterday'),
  ),
  UsagePeriod.week => (
    window: context.t('us_last7'),
    compare: context.t('us_prev7'),
  ),
  UsagePeriod.month => (
    window: context.t('us_last30'),
    compare: context.t('us_prev30'),
  ),
};

/// A card at the page gutter.
class UsageCard extends StatelessWidget {
  const UsageCard({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Gutter(
    bottom: LnSpace.md,
    child: LnCardSurface(
      child: Padding(
        padding: const EdgeInsets.all(LnSpace.cardPadding),
        child: child,
      ),
    ),
  );
}

class _Eyebrow extends StatelessWidget {
  const _Eyebrow(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text,
    style: context.ln.text.footnoteStrong.copyWith(
      color: context.ln.colors.fgMuted,
    ),
  );
}

/// Up / down / no change against the previous window.
class UsageDelta extends StatelessWidget {
  const UsageDelta({super.key, required this.current, required this.previous});

  final double current;
  final double previous;

  @override
  Widget build(BuildContext context) {
    final pct = percentChange(current, previous);
    if (pct == null) return const SizedBox.shrink();
    if (pct.abs() < 1) {
      return StatusChip(label: context.t('us_noChange'), icon: FIcons.minus);
    }
    final up = pct > 0;
    return Semantics(
      label: context.t(up ? 'us_up' : 'us_down', [ltr('${pct.abs()}%')]),
      excludeSemantics: true,
      child: StatusChip(
        label: ltr('${pct.abs()}%'),
        icon: up ? FIcons.arrowUp : FIcons.arrowDown,
        kind: up ? StatusChipKind.waiting : StatusChipKind.success,
      ),
    );
  }
}

/// «Cost · the last 30 days», the figure, the change and the previous window.
class UsageHero extends StatelessWidget {
  const UsageHero({super.key, required this.series, this.lead});

  final UsageSeries series;
  final Widget? lead;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final words = periodWords(context, series.period);
    return UsageCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (lead != null) ...[lead!, const SizedBox(height: LnSpace.md)],
          _Eyebrow(context.t('us_costWindow', [words.window])),
          const SizedBox(height: LnSpace.xxs),
          Row(
            children: [
              Flexible(
                child: Text(
                  usd(series.totals.cost),
                  textDirection: TextDirection.ltr,
                  style: ln.text.largeTitle.copyWith(color: c.fg),
                ),
              ),
              const SizedBox(width: LnSpace.sm),
              UsageDelta(
                current: series.totals.cost,
                previous: series.previous.cost,
              ),
            ],
          ),
          const SizedBox(height: LnSpace.xxs),
          Text(
            context.t('us_comparedWith', [
              words.compare,
              ltr(usd(series.previous.cost)),
            ]),
            style: ln.text.footnote.copyWith(color: c.fgMuted),
          ),
        ],
      ),
    );
  }
}

/// Month to date, its projection and the days elapsed; never a limit.
class UsageMonthCard extends StatelessWidget {
  const UsageMonthCard({super.key, required this.series});

  final UsageSeries series;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final lang = context.l10n.lang;
    final m = series.month;
    final month = formatDate('MMMM', lang, m.start);
    final end = formatDate('d MMMM', lang, m.end);
    final fraction = (m.dayOfMonth / m.daysInMonth).clamp(0.0, 1.0);
    return UsageCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Eyebrow(context.t('us_monthSoFar', [month])),
          const SizedBox(height: LnSpace.xxs),
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.end,
            spacing: LnSpace.xs,
            children: [
              Text(
                usd(m.spentUsd),
                textDirection: TextDirection.ltr,
                style: ln.text.display.copyWith(color: c.fg),
              ),
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Text(
                  context.t('us_projected', [ltr(usd(m.projectedUsd))]),
                  style: ln.text.footnote.copyWith(color: c.fgMuted),
                ),
              ),
            ],
          ),
          const SizedBox(height: LnSpace.sm),
          Semantics(
            label: context.t('us_dayOf', [m.dayOfMonth, m.daysInMonth]),
            value: '${(fraction * 100).round()}%',
            child: ClipRRect(
              borderRadius: const BorderRadius.all(
                Radius.circular(LnRadius.stadium),
              ),
              child: _Meter(
                height: _meterHeight,
                fraction: fraction,
                track: c.fill3,
                fill: c.success,
              ),
            ),
          ),
          const SizedBox(height: LnSpace.xs),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  context.t('us_dayOf', [m.dayOfMonth, m.daysInMonth]),
                  style: ln.text.small.copyWith(color: c.fgMuted),
                ),
              ),
              const SizedBox(width: LnSpace.xs),
              Flexible(
                child: Text(
                  context.t('us_projectedTo', [end, ltr(usd(m.projectedUsd))]),
                  textAlign: TextAlign.end,
                  style: ln.text.small.copyWith(color: c.fgMuted),
                ),
              ),
            ],
          ),
          const SizedBox(height: LnSpace.sm),
          Row(
            children: [
              Icon(FIcons.circleCheck, size: 16, color: c.success),
              const SizedBox(width: LnSpace.xs),
              Expanded(
                child: Text(
                  context.t('us_noCap'),
                  style: ln.text.footnote.copyWith(color: c.fg),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// The label of one bucket: «14:00 · now», «Today · Friday 27 November».
String pointLabel(BuildContext context, UsageSeries series, int index) {
  final point = series.points[index];
  final lang = context.l10n.lang;
  if (series.hourly) {
    final hh = point.start.hour.toString().padLeft(2, '0');
    final mm = point.start.minute.toString().padLeft(2, '0');
    final now = index == series.lastStarted ? ' · ${context.t('us_now')}' : '';
    return '${ltr('$hh:$mm')}$now';
  }
  final last = series.points.length - 1;
  final prefix = index == last
      ? '${context.t('today')} · '
      : index == last - 1
      ? '${context.t('yesterday')} · '
      : '';
  return '$prefix${formatDate('EEEE d MMMM', lang, point.start)}';
}

/// The cost per hour (today) or per day, as bars or as a table. A tap or a drag on a column
/// reads it out (selection click).
class UsageChartCard extends StatefulWidget {
  const UsageChartCard({super.key, required this.series});

  final UsageSeries series;

  @override
  State<UsageChartCard> createState() => _UsageChartCardState();
}

class _UsageChartCardState extends State<UsageChartCard> {
  int? _selected;
  bool _table = false;

  int get _sel {
    final last = widget.series.lastStarted;
    final s = _selected;
    return s != null && s <= last ? s : last;
  }

  void _pick(int index) {
    final clamped = index.clamp(0, widget.series.lastStarted);
    if (clamped == _sel && _selected != null) return;
    HapticFeedback.selectionClick();
    setState(() => _selected = clamped);
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final series = widget.series;
    final points = series.points;
    if (points.isEmpty) return const SizedBox.shrink();
    final sel = _sel;
    final head = Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Semantics(
            liveRegion: true,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  usd(points[sel].figures.cost),
                  textDirection: TextDirection.ltr,
                  style: ln.text.headline.copyWith(color: c.fg),
                ),
                Text(
                  pointLabel(context, series, sel),
                  style: ln.text.footnote.copyWith(color: c.fgMuted),
                ),
              ],
            ),
          ),
        ),
        // The label and state sit on the tappable's own node, which keeps its tap action.
        LnTappable(
          onTap: () => setState(() => _table = !_table),
          semanticLabel: context.t(_table ? 'us_showChart' : 'us_showTable'),
          child: Semantics(
            toggled: _table,
            child: ExcludeSemantics(
              child: SizedBox.square(
                dimension: 48,
                child: Icon(
                  _table ? FIcons.chartColumn : FIcons.table,
                  color: c.fgMuted,
                ),
              ),
            ),
          ),
        ),
      ],
    );
    return UsageCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          head,
          const SizedBox(height: LnSpace.sm),
          if (_table) _UsageTable(series: series) else _bars(context),
        ],
      ),
    );
  }

  Widget _bars(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final series = widget.series;
    final points = series.points;
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final top = chartTop(points.map((p) => p.figures.cost));
    final n = points.length;
    final sel = _sel;
    // fl_chart lays groups out left to right; in Arabic time runs from the right.
    int slot(int index) => rtl ? n - 1 - index : index;
    final axisStyle = ln.text.micro.copyWith(color: c.fgMuted);
    final titles = AxisTitles(
      sideTitles: SideTitles(
        showTitles: true,
        reservedSize: _axisWidth,
        interval: top / 2,
        getTitlesWidget: (value, meta) => Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Text(
            axisTick(value),
            textDirection: TextDirection.ltr,
            style: axisStyle,
            maxLines: 1,
          ),
        ),
      ),
    );
    const none = AxisTitles();
    final width = (220 / n).clamp(4.0, 22.0);
    final chart = SizedBox(
      height: 160,
      child: Semantics(
        label: context.t(series.hourly ? 'us_costPerHour' : 'us_dailyCost'),
        child: BarChart(
          duration: Duration.zero,
          BarChartData(
            minY: 0,
            maxY: top,
            alignment: BarChartAlignment.spaceBetween,
            barGroups: [
              for (var x = 0; x < n; x++)
                () {
                  final index = slot(x);
                  final f = points[index].figures;
                  final value = f.future
                      ? 0.0
                      : f.cost <= 0
                      ? top * 0.008
                      : f.cost < top * 0.008
                      ? top * 0.008
                      : f.cost;
                  return BarChartGroupData(
                    x: x,
                    barRods: [
                      BarChartRodData(
                        toY: value,
                        width: width,
                        color: f.future
                            ? Colors.transparent
                            : index == sel
                            ? c.selection
                            : c.fgSubtle,
                        borderRadius: const BorderRadius.vertical(
                          top: Radius.circular(_rodRadius),
                        ),
                        backDrawRodData: BackgroundBarChartRodData(
                          show: true,
                          toY: top,
                          color: Colors.transparent,
                        ),
                      ),
                    ],
                  );
                }(),
            ],
            gridData: FlGridData(
              drawVerticalLine: false,
              horizontalInterval: top / 2,
              getDrawingHorizontalLine: (_) =>
                  FlLine(color: c.border, strokeWidth: 1),
            ),
            borderData: FlBorderData(
              show: true,
              border: Border(bottom: BorderSide(color: c.fill4)),
            ),
            titlesData: FlTitlesData(
              leftTitles: rtl ? none : titles,
              rightTitles: rtl ? titles : none,
              topTitles: none,
              bottomTitles: none,
            ),
            barTouchData: BarTouchData(
              handleBuiltInTouches: false,
              allowTouchBarBackDraw: true,
              touchCallback: (event, response) {
                final spot = response?.spot;
                if (spot == null || !event.isInterestedForInteractions) return;
                _pick(slot(spot.touchedBarGroupIndex));
              },
            ),
          ),
        ),
      ),
    );
    final lang = context.l10n.lang;
    final axis = series.hourly
        ? ['00:00', '12:00', '23:00'].map(ltr).toList()
        : [
            formatDate('d MMMM', lang, points.first.start),
            formatDate('d MMMM', lang, points[(n - 1) ~/ 2].start),
            context.t('today'),
          ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        chart,
        const SizedBox(height: LnSpace.xs),
        // The dollar axis is on the start side in both directions (left titles in English,
        // right titles in Arabic): the dates start after it, under the bars.
        Padding(
          padding: const EdgeInsetsDirectional.only(start: _axisWidth),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [for (final a in axis) Text(a, style: axisStyle)],
          ),
        ),
      ],
    );
  }
}

class _UsageTable extends StatelessWidget {
  const _UsageTable({required this.series});

  final UsageSeries series;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final head = ln.text.smallStrong.copyWith(color: c.fgMuted);
    final cell = ln.text.footnote.copyWith(color: c.fg);
    final rows = [
      for (var i = series.points.length - 1; i >= 0; i--)
        if (!series.points[i].figures.future) i,
    ];
    Widget row(String a, String b, String d, TextStyle style) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(flex: 5, child: Text(a, style: style)),
          Expanded(
            flex: 2,
            child: Text(b, textAlign: TextAlign.end, style: style),
          ),
          Expanded(
            flex: 2,
            child: Text(d, textAlign: TextAlign.end, style: style),
          ),
        ],
      ),
    );
    return Column(
      children: [
        row(
          context.t(series.hourly ? 'us_hour' : 'us_day'),
          context.t('us_cost'),
          context.t('us_tokens'),
          head,
        ),
        for (final i in rows)
          row(
            pointLabel(context, series, i),
            ltr(usd(series.points[i].figures.cost)),
            isolate(usageCount(series.points[i].figures.tokens)),
            cell,
          ),
      ],
    );
  }
}

/// Tokens (input/output split), requests, cache share and average cost per request.
class UsageKpis extends StatelessWidget {
  const UsageKpis({super.key, required this.totals});

  final UsageFigures totals;

  @override
  Widget build(BuildContext context) {
    final t = totals;
    final input = t.tokens > 0 ? (t.inputTokens / t.tokens * 100).round() : 0;
    final cached = t.inputTokens > 0
        ? (t.cachedTokens / t.inputTokens * 100).round()
        : 0;
    final perRequest = t.requests > 0 ? (t.tokens / t.requests).round() : 0;
    final priced = t.requests - t.unpricedRequests;
    final tiles = [
      _Kpi(
        label: context.t('us_tokens'),
        value: usageCount(t.tokens),
        note: context.t('us_inputOutput', [
          ltr('$input%'),
          ltr('${100 - input}%'),
        ]),
        split: t.tokens > 0 ? input / 100 : null,
      ),
      _Kpi(
        label: context.t('us_requests'),
        value: usageCount(t.requests),
        note: context.t('us_perRequest', [ltr(usageCount(perRequest))]),
      ),
      _Kpi(
        label: context.t('us_fromCache'),
        value: '$cached%',
        note: context.t('us_tokensReused', [
          isolate(usageCount(t.cachedTokens)),
        ]),
      ),
      _Kpi(
        label: context.t('us_avgCost'),
        value: usd(priced > 0 ? t.cost / priced : 0),
        note: t.unpricedRequests > 0
            ? plural(
                t.unpricedRequests,
                one: context.t('us_unpriced1'),
                two: context.t('us_unpriced2'),
                few: context.t('us_unpricedFew', [t.unpricedRequests]),
                many: context.t('us_unpricedMany', [t.unpricedRequests]),
              )
            : context.t('us_perCompleted'),
      ),
    ];
    return Gutter(
      bottom: LnSpace.md,
      child: Column(
        children: [
          for (var i = 0; i < tiles.length; i += 2)
            Padding(
              padding: EdgeInsets.only(bottom: i == 0 ? LnSpace.tileGap : 0),
              child: IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(child: tiles[i]),
                    const SizedBox(width: LnSpace.tileGap),
                    Expanded(child: tiles[i + 1]),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _Kpi extends StatelessWidget {
  const _Kpi({
    required this.label,
    required this.value,
    required this.note,
    this.split,
  });

  final String label;
  final String value;
  final String note;
  final double? split;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnCardSurface(
      child: Padding(
        padding: const EdgeInsets.all(LnSpace.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: ln.text.footnote.copyWith(color: c.fgMuted)),
            const SizedBox(height: LnSpace.xxs),
            Text(isolate(value), style: ln.text.headline.copyWith(color: c.fg)),
            if (split != null) ...[
              const SizedBox(height: 6),
              ClipRRect(
                borderRadius: const BorderRadius.all(
                  Radius.circular(LnRadius.stadium),
                ),
                child: SizedBox(
                  height: _splitHeight,
                  child: Row(
                    children: [
                      Expanded(
                        flex: (split! * 1000).round().clamp(1, 999),
                        child: ColoredBox(color: c.selection),
                      ),
                      Expanded(
                        flex: ((1 - split!) * 1000).round().clamp(1, 999),
                        child: ColoredBox(color: c.fill4),
                      ),
                    ],
                  ),
                ),
              ),
            ],
            const SizedBox(height: 6),
            Text(note, style: ln.text.small.copyWith(color: c.fgMuted)),
          ],
        ),
      ),
    );
  }
}

/// One ranked row: who or which model, its cost, its share of the total.
typedef UsageRankItem = ({
  String key,
  String name,
  double value,
  Agent? agent,
  VoidCallback? onTap,
});

/// «By agent» / «By model»: the rows by cost, each with its share bar.
class UsageRankCard extends StatelessWidget {
  const UsageRankCard({
    super.key,
    required this.title,
    required this.rows,
    required this.total,
    this.note,
  });

  final String title;
  final String? note;
  final List<UsageRankItem> rows;
  final double total;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return UsageCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Semantics(
                  header: true,
                  child: Text(
                    title,
                    style: ln.text.title.copyWith(color: c.fg),
                  ),
                ),
              ),
              if (note != null)
                Text(note!, style: ln.text.small.copyWith(color: c.fgMuted)),
            ],
          ),
          const SizedBox(height: LnSpace.xs),
          if (rows.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: LnSpace.xs),
              child: Text(
                context.t('us_noUsage'),
                style: ln.text.footnote.copyWith(color: c.fgMuted),
              ),
            ),
          for (final row in rows) _RankRow(row: row, total: total),
        ],
      ),
    );
  }
}

class _RankRow extends StatelessWidget {
  const _RankRow({required this.row, required this.total});

  final UsageRankItem row;
  final double total;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final pct = total > 0 ? row.value / total * 100 : 0.0;
    final pctText = pct > 0 && pct < 1 ? '<1%' : '${pct.round()}%';
    final agent = row.agent;
    final lead = agent != null
        ? LonoraAvatar(
            agentId: agent.id,
            face: agent.avatar,
            color: agent.color,
            tradesOnItsOwn: agent.tradesOnItsOwn,
            size: 32,
            animate: false,
          )
        : Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: c.fill2,
              borderRadius: const BorderRadius.all(
                Radius.circular(LnRadius.iconTile),
              ),
            ),
            child: Icon(FIcons.cpu, size: 18, color: c.fgMuted),
          );
    final content = ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 52),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          children: [
            lead,
            const SizedBox(width: LnSpace.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          row.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: ln.text.captionStrong.copyWith(color: c.fg),
                        ),
                      ),
                      const SizedBox(width: LnSpace.xs),
                      Text(
                        usd(row.value),
                        textDirection: TextDirection.ltr,
                        style: ln.text.caption.copyWith(color: c.fg),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  ClipRRect(
                    borderRadius: const BorderRadius.all(
                      Radius.circular(LnRadius.stadium),
                    ),
                    child: _Meter(
                      height: _splitHeight,
                      fraction: pct.clamp(0.6, 100) / 100,
                      track: c.fill3,
                      fill: c.selection,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: LnSpace.sm),
            SizedBox(
              width: 40,
              child: Text(
                pctText,
                textAlign: TextAlign.end,
                textDirection: TextDirection.ltr,
                style: ln.text.small.copyWith(color: c.fgMuted),
              ),
            ),
            const SizedBox(width: LnSpace.xxs),
            // A row without a chevron keeps its slot, so every row shares one column grid.
            if (row.onTap != null)
              Icon(FIcons.chevronRight, size: 18, color: c.chevron)
            else
              const SizedBox(width: 18),
          ],
        ),
      ),
    );
    return row.onTap == null
        ? content
        : LnTappable(onTap: row.onTap, child: content);
  }
}

/// A count as the Web's `num` prints it, the same in both languages (apps/web UsagePage.tsx):
/// whole with grouping below 10 000, then English compact notation with one decimal below
/// 100 000, none below a million and two from a million («12.3K», «123K», «1.23M»).
String usageCount(int value) {
  if (value < 10000) return NumberFormat.decimalPattern('en').format(value);
  final digits = value >= 1000000
      ? 2
      : value >= 100000
      ? 0
      : 1;
  const units = ['', 'K', 'M', 'B', 'T'];
  var unit = 0;
  var scaled = value.toDouble();
  while (unit < units.length - 1 && scaled >= 1000) {
    scaled /= 1000;
    unit++;
  }
  // A value that rounds up to the next unit reads in that unit (999 999 → «1M»).
  if (unit < units.length - 1 &&
      double.parse(scaled.toStringAsFixed(digits)) >= 1000) {
    scaled /= 1000;
    unit++;
  }
  final format = NumberFormat.decimalPattern('en')
    ..minimumFractionDigits = 0
    ..maximumFractionDigits = digits
    ..turnOffGrouping();
  return '${format.format(scaled)}${units[unit]}';
}

/// A horizontal meter: [fraction] of the track filled from the start side.
class _Meter extends StatelessWidget {
  const _Meter({
    required this.height,
    required this.fraction,
    required this.track,
    required this.fill,
  });

  final double height;
  final double fraction;
  final Color track;
  final Color fill;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: height,
    width: double.infinity,
    child: ColoredBox(
      color: track,
      child: FractionallySizedBox(
        alignment: AlignmentDirectional.centerStart,
        widthFactor: fraction.clamp(0.0, 1.0),
        heightFactor: 1,
        child: ColoredBox(color: fill),
      ),
    ),
  );
}
