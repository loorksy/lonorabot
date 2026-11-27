// The usage dashboard's data (lonora-api-contract §13; packages/contracts usage.ts) and its
// number rules (apps/web UsagePage.tsx `usd`, `nice`, `tick`). A view of what requests cost at
// list price, never a cap: nothing here limits or blocks a request.
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import '../../../app/services.dart';
import '../../../core/json.dart';

/// `day` (24 hours of today), `week` (7 days) or `month` (30 days).
enum UsagePeriod { day, week, month }

/// The figures of a window, a bucket or a ranked row. A bucket of today that has not started
/// has every figure null.
@immutable
class UsageFigures {
  const UsageFigures({
    this.costUsd,
    this.inputTokens = 0,
    this.outputTokens = 0,
    this.cachedTokens = 0,
    this.tokens = 0,
    this.requests = 0,
    this.unpricedRequests = 0,
    this.future = false,
  });

  factory UsageFigures.fromJson(Json j) => UsageFigures(
    costUsd: asDouble(j['cost_usd']),
    inputTokens: asInt(j['input_tokens']) ?? 0,
    outputTokens: asInt(j['output_tokens']) ?? 0,
    cachedTokens: asInt(j['cached_tokens']) ?? 0,
    tokens:
        asInt(j['tokens']) ??
        (asInt(j['input_tokens']) ?? 0) + (asInt(j['output_tokens']) ?? 0),
    requests: asInt(j['requests']) ?? 0,
    unpricedRequests: asInt(j['unpriced_requests']) ?? 0,
    future:
        j['cost_usd'] == null && j['tokens'] == null && j['requests'] == null,
  );

  /// USD at list price; null for a model without a list price or a future bucket.
  final double? costUsd;
  final int inputTokens;
  final int outputTokens;
  final int cachedTokens;
  final int tokens;
  final int requests;
  final int unpricedRequests;

  /// A bucket of today that has not started yet.
  final bool future;

  double get cost => costUsd ?? 0;
}

/// One hour or day: its start in the owner's zone (wall clock) and its figures.
@immutable
class UsagePoint {
  const UsagePoint({required this.start, required this.figures});

  final DateTime start;
  final UsageFigures figures;
}

@immutable
class UsageMonth {
  const UsageMonth({
    required this.start,
    required this.spentUsd,
    required this.projectedUsd,
    required this.daysInMonth,
    required this.dayOfMonth,
  });

  final DateTime start;
  final double spentUsd;
  final double projectedUsd;
  final int daysInMonth;
  final int dayOfMonth;

  /// The month's last day (wall clock).
  DateTime get end => DateTime.utc(start.year, start.month, daysInMonth);
}

/// `GET /usage/series`.
@immutable
class UsageSeries {
  const UsageSeries({
    required this.period,
    required this.hourly,
    required this.timezone,
    required this.points,
    required this.totals,
    required this.previous,
    required this.month,
  });

  factory UsageSeries.fromJson(Json j) {
    final month = asJson(j['month']);
    return UsageSeries(
      period: UsagePeriod.values.firstWhere(
        (p) => p.name == j['period'],
        orElse: () => UsagePeriod.month,
      ),
      hourly: j['bucket'] == 'hour',
      timezone: asStr(j['timezone'], 'UTC'),
      points: [
        for (final p in asJsonList(j['points']))
          UsagePoint(
            start: wallClock(asStr(p['start'])) ?? DateTime.utc(1970),
            figures: UsageFigures.fromJson(p),
          ),
      ],
      totals: UsageFigures.fromJson(asJson(j['totals'])),
      previous: UsageFigures.fromJson(asJson(j['previous'])),
      month: UsageMonth(
        start: wallClock(asStr(month['start'])) ?? DateTime.utc(1970),
        spentUsd: asDouble(month['spent_usd']) ?? 0,
        projectedUsd: asDouble(month['projected_usd']) ?? 0,
        daysInMonth: asInt(month['days_in_month']) ?? 30,
        dayOfMonth: asInt(month['day_of_month']) ?? 1,
      ),
    );
  }

  final UsagePeriod period;

  /// Hour buckets (today) rather than day buckets.
  final bool hourly;
  final String timezone;
  final List<UsagePoint> points;
  final UsageFigures totals;

  /// The equal preceding window, cut at the same elapsed point.
  final UsageFigures previous;
  final UsageMonth month;

  /// The last bucket that has started (the chart's default reading).
  int get lastStarted {
    var last = 0;
    for (var i = 0; i < points.length; i++) {
      if (!points[i].figures.future) last = i;
    }
    return last;
  }
}

/// One ranked agent or model.
@immutable
class UsageRankRow {
  const UsageRankRow({
    required this.figures,
    this.agentId,
    this.agentName,
    this.provider,
    this.model,
  });

  final UsageFigures figures;
  final String? agentId;
  final String? agentName;
  final String? provider;
  final String? model;
}

/// `GET /usage/rank`: totals, agents and models, largest cost first.
@immutable
class UsageRank {
  const UsageRank({
    required this.totals,
    required this.agents,
    required this.models,
  });

  factory UsageRank.fromJson(Json j) => UsageRank(
    totals: UsageFigures.fromJson(asJson(j['totals'])),
    agents: [
      for (final a in asJsonList(j['agents']))
        UsageRankRow(
          figures: UsageFigures.fromJson(a),
          agentId: asString(a['agent_id']),
          agentName: asString(a['agent_name']),
        ),
    ],
    models: [
      for (final m in asJsonList(j['models']))
        UsageRankRow(
          figures: UsageFigures.fromJson(m),
          provider: asString(m['provider']),
          model: asString(m['model']),
        ),
    ],
  );

  final UsageFigures totals;
  final List<UsageRankRow> agents;
  final List<UsageRankRow> models;
}

/// The wall-clock time an ISO-8601 instant names in its own offset («2026-11-27T00:00:00+03:00»
/// → 27 Nov 00:00), as a UTC DateTime so nothing shifts it to the phone's zone. The series are
/// cut in the owner's zone and say so in their offsets.
DateTime? wallClock(String iso) {
  final m = RegExp(r'^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?')
      .firstMatch(iso);
  if (m == null) return null;
  int part(int i) => int.parse(m[i] ?? '0');
  return DateTime.utc(part(1), part(2), part(3), part(4), part(5));
}

/// The query of every usage read. No `tz`, as on the Web: the server cuts the hours, «today»
/// and the month in the owner's own stored zone, whatever zone the phone is in.
Map<String, Object?> _query(UsagePeriod period, String? agentId) => {
  'period': period.name,
  'agent_id': ?agentId,
};

Future<UsageSeries> fetchSeries(UsagePeriod period, {String? agentId}) async =>
    UsageSeries.fromJson(
      asJson(await api.get('/usage/series', query: _query(period, agentId))),
    );

Future<UsageRank> fetchRank(UsagePeriod period, {String? agentId}) async =>
    UsageRank.fromJson(
      asJson(await api.get('/usage/rank', query: _query(period, agentId))),
    );

/// `GET /usage/summary`: every token since the start.
Future<({int input, int output, int cached})> fetchUsageSummary() async {
  final j = asJson(await api.get('/usage/summary'));
  return (
    input: asInt(j['input_tokens']) ?? 0,
    output: asInt(j['output_tokens']) ?? 0,
    cached: asInt(j['cached_tokens']) ?? 0,
  );
}

/// Downloads `GET /usage/export.csv` to [savePath] (UTF-8 with BOM, as the server writes it).
Future<void> downloadUsageCsv(
  String savePath,
  UsagePeriod period, {
  String? agentId,
}) => api.downloadTo(
  '/usage/export.csv',
  savePath,
  query: _query(period, agentId),
);

/// A cost in dollars as the Web prints it: whole dollars from 100, cents from 0.10, then
/// three or four decimals so a tiny cost never reads as $0.00 (apps/web UsagePage.tsx `usd`).
/// Latin digits and a leading «$» in both languages.
String usd(num? value) {
  final v = (value ?? 0).toDouble();
  String body;
  if (v >= 1000) {
    final whole = v.round().toString();
    body = whole.replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => ',');
  } else if (v >= 100) {
    body = v.toStringAsFixed(0);
  } else if (v >= 0.1 || v == 0) {
    body = v.toStringAsFixed(2);
  } else if (v >= 0.01) {
    body = v.toStringAsFixed(3);
  } else {
    body = math.max(v, 1e-4).toStringAsFixed(4);
  }
  return '\$$body';
}

/// A round axis top at or above [v] (apps/web UsagePage.tsx `nice`).
double niceCeiling(double v) {
  if (!(v > 0)) return 1;
  final p = math.pow(10, (math.log(v) / math.ln10).floor()).toDouble();
  final f = v / p;
  const steps = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
  final step = steps.firstWhere((n) => f <= n + 1e-9, orElse: () => 10);
  return step * p;
}

/// The chart's top: twice the nice half of 108 % of the largest bucket.
double chartTop(Iterable<double> values) {
  final most = values.fold<double>(0, math.max);
  return 2 * niceCeiling(most * 1.08 / 2);
}

/// An axis label in dollars with just the decimals it needs (apps/web UsagePage.tsx `tick`).
String axisTick(double v) {
  if (v == 0) return r'$0';
  var d = 0;
  while (d < 6 &&
      (double.parse(v.toStringAsFixed(d)) - v).abs() > v.abs() * 1e-6) {
    d++;
  }
  if (d == 1) d = 2;
  return '\$${v.toStringAsFixed(d)}';
}

/// The change against the previous window, rounded to a whole percent; null when there is
/// nothing to compare with.
int? percentChange(double current, double previous) {
  if (!(previous > 0)) return null;
  return ((current - previous) / previous * 100).round();
}
