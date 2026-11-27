// Market data of the owner, read-only: broker connections (`GET /trading/connections`), the
// account snapshot (`GET /trading/accounts/{id}`: balances, positions, pending orders), symbols,
// quotes, instruments and candles (`GET /market/*`), watches (`GET /watches`, the owner's brake
// `POST /watches/{id}/control`), the economic calendar (`GET /market/calendar`), opportunities
// (`GET /trading/opportunities`) and the order log (`GET /trading/journal`).
//
// SAFETY (docs/android/analysis/lonora-api-contract.md §11, §19): nothing here places, changes or
// closes an order; there is no call to `/trading/execute` and none may be added.
import 'package:flutter/foundation.dart';

import '../../app/services.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';

/// A broker connection row (`GET /trading/connections`). [raw] feeds the label helper.
@immutable
class MarketConnection {
  const MarketConnection({
    required this.id,
    required this.provider,
    required this.enabled,
    this.raw = const {},
  });

  factory MarketConnection.fromJson(Json j) {
    final payload = asJson(j['payload']);
    return MarketConnection(
      id: asStr(j['id']),
      provider: asStr(payload['provider'], 'metaapi'),
      enabled: asBool(payload['enabled'], true),
      raw: j,
    );
  }

  final String id;
  final String provider;
  final bool enabled;
  final Json raw;

  /// A simulation trades against an imported snapshot (paper): never a broker account.
  bool get isSimulation => provider == 'simulation';
}

@immutable
class MarketQuote {
  const MarketQuote({
    required this.symbol,
    required this.bid,
    required this.ask,
    this.observedAt,
    this.source = '',
  });

  factory MarketQuote.fromJson(Json j) => MarketQuote(
    symbol: asStr(j['symbol']),
    bid: asStr(j['bid'], '${j['bid'] ?? ''}'),
    ask: asStr(j['ask'], '${j['ask'] ?? ''}'),
    observedAt: asDate(j['observed_at']),
    source: asStr(j['source']),
  );

  final String symbol;
  final String bid;
  final String ask;
  final DateTime? observedAt;
  final String source;

  double? get bidValue => double.tryParse(bid);

  /// Whether this quote may replace [shown]: a quote never goes back in time. A read may
  /// repeat the shown observation ([orSame]); a streamed one must be newer (apps/web
  /// hooks/useMarket.ts).
  bool supersedes(MarketQuote? shown, {bool orSame = false}) {
    final mine = observedAt, theirs = shown?.observedAt;
    if (theirs == null) return true;
    if (mine == null) return false;
    return mine.isAfter(theirs) || (orSame && mine == theirs);
  }

  double? get askValue => double.tryParse(ask);

  /// Ask minus bid with the precision of the quote (the Web prints `toPrecision(5)`).
  String get spread {
    final b = bidValue, a = askValue;
    if (b == null || a == null) return '—';
    final decimals = [bid, ask]
        .map((s) => s.contains('.') ? s.length - s.indexOf('.') - 1 : 0)
        .fold(0, (m, d) => d > m ? d : m);
    return (a - b).toStringAsFixed(decimals);
  }
}

@immutable
class MarketCandle {
  const MarketCandle({
    required this.time,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
    this.volume = 0,
  });

  /// Null when a price is missing or not a number (such a candle is dropped).
  static MarketCandle? fromJson(Json j) {
    final time = asDate(j['time']);
    final o = asDouble(j['open']);
    final h = asDouble(j['high']);
    final l = asDouble(j['low']);
    final c = asDouble(j['close']);
    if (time == null || o == null || h == null || l == null || c == null) {
      return null;
    }
    return MarketCandle(
      time: time,
      open: o,
      high: h,
      low: l,
      close: c,
      volume: asDouble(j['volume']) ?? 0,
    );
  }

  final DateTime time;
  final double open;
  final double high;
  final double low;
  final double close;
  final double volume;

  bool get rising => close >= open;
}

List<MarketCandle> candlesFrom(Object? value) => [
  for (final j in asJsonList(value)) ?MarketCandle.fromJson(j),
];

@immutable
class MarketInstrument {
  const MarketInstrument(this.raw);

  final Json raw;

  String get symbol => asStr(raw['symbol']);
  String get description => asStr(raw['description']);
  int? get digits => asInt(raw['digits']);
  String get tickSize => marketField(raw['tick_size']);
  String get volumeMin => marketField(raw['volume_min']);
  String get volumeMax => marketField(raw['volume_max']);
  String get volumeStep => marketField(raw['volume_step']);
}

String marketField(Object? value) => value == null ? '' : '$value';

@immutable
class MarketPosition {
  const MarketPosition(this.raw);

  final Json raw;

  String get id => asStr(raw['id']);
  String get symbol => asStr(raw['symbol']);
  bool get isSell => asStr(raw['side']).startsWith('sell');
  String get volume => marketField(raw['volume']);
  String get openPrice => marketField(raw['open_price']);
  double? get profit => asDouble(raw['profit']);
  String? get stopLoss => asString(raw['stop_loss']);
  String? get takeProfit => asString(raw['take_profit']);
}

@immutable
class MarketOrder {
  const MarketOrder(this.raw);

  final Json raw;

  String get id => asStr(raw['id']);
  String get symbol => asStr(raw['symbol']);
  String get side => asStr(raw['side']);
  bool get isSell => side.startsWith('sell');
  String get volume => marketField(raw['volume']);
  String get price => marketField(raw['price']);
}

/// `GET /trading/accounts/{id}`: the account part, its positions and pending orders.
@immutable
class AccountSnapshot {
  const AccountSnapshot({
    required this.account,
    this.positions = const [],
    this.orders = const [],
  });

  factory AccountSnapshot.fromJson(Json j) => AccountSnapshot(
    account: asJson(j['account']),
    positions: asJsonList(j['positions']).map(MarketPosition.new).toList(),
    orders: asJsonList(j['orders']).map(MarketOrder.new).toList(),
  );

  final Json account;
  final List<MarketPosition> positions;
  final List<MarketOrder> orders;

  String get currency => asStr(account['currency']);
  double? get balance => asDouble(account['balance']);
  double? get equity => asDouble(account['equity']);
  double? get margin => asDouble(account['margin']);
  double? get freeMargin => asDouble(account['free_margin']);
  DateTime? get observedAt => asDate(account['observed_at']);

  /// Open profit across positions (null without positions or numbers).
  double? get openProfit {
    final values = [for (final p in positions) ?p.profit];
    return values.isEmpty ? null : values.fold<double>(0, (s, v) => s + v);
  }
}

/// A watch resource (`GET /watches`) in the shape `watchCondition`/`watchUntil` read.
@immutable
class MarketWatch {
  const MarketWatch(this.raw);

  final Json raw;

  String get id => asStr(raw['id']);
  String? get agentId => asString(raw['agent_id']);
  String? get threadId => asString(raw['thread_id']);
  Json get payload => asJson(raw['payload']);
  String get lifecycle =>
      asString(asJson(raw['state'])['lifecycle']) ?? 'pending';
  bool get enabled => asBool(payload['enabled'], true);
  String? get accountId => asString(payload['account_id']);
  String? get symbol => asString(payload['symbol']);

  String? get code => asString(asJson(raw['state'])['code']);

  /// Cancelled by the owner (`watch_cancelled`): it never watches again.
  bool get cancelled => code == 'watch_cancelled';

  DateTime? get expiresAt => asDate(payload['expires_at']);

  /// Cancelled, expired, or past its expiry before the server marked it (apps/web
  /// shell/domain/SchedulesPages.tsx `listedWatch`): no longer listed, no controls.
  bool get ended {
    final expires = expiresAt;
    return cancelled ||
        lifecycle == 'expired' ||
        (expires != null && !expires.isAfter(DateTime.now()));
  }

  /// Has an expiry the owner can move later («تمديد ساعتين»).
  bool get extendable => !ended && expiresAt != null;

  /// Switched off by a pause (resumable).
  bool get paused => !ended && !enabled;

  /// AgentWatchSummary (apps/web components/market/MarketWatch.tsx `watchSummary`).
  Map<String, Object?> get summary {
    String? text(Object? v) => v == null || v == '' ? null : '$v';
    final kind = text(payload['kind']) ?? 'price';
    return {
      'id': id,
      'kind': kind,
      'account_id': text(payload['account_id']),
      'symbol': text(payload['symbol']),
      'condition': text(payload['condition']),
      'level': text(payload['level']),
      'indicator': kind == 'indicator' ? text(payload['indicator']) : null,
      'timeframe': kind == 'indicator' ? text(payload['timeframe']) : null,
      'metric': kind == 'account' || kind == 'position'
          ? text(payload['metric'])
          : null,
      'expires_at': text(payload['expires_at']),
      'lifecycle': lifecycle,
    };
  }
}

@immutable
class CalendarEvent {
  const CalendarEvent(this.raw);

  final Json raw;

  String get id => asStr(raw['id']);
  String get name => asStr(raw['name']);
  String get currency => asStr(raw['currency']);
  DateTime? get scheduledAt => asDate(raw['scheduled_at']);
  String get impact => asStr(raw['impact']);
  String? get actual => asString(raw['actual']);
  String? get forecast => asString(raw['forecast']);
}

@immutable
class Opportunity {
  const Opportunity(this.raw);

  final Json raw;

  String get id => asStr(raw['id']);
  String? get agentId => asString(raw['agent_id']);
  String? get threadId => asString(raw['thread_id']);
  String get accountId => asStr(raw['account_id']);
  String get symbol => asStr(raw['symbol']);
  String get timeframe => asStr(raw['timeframe']);
  String get status => asStr(raw['status'], 'forming');
  DateTime? get expiresAt => asDate(raw['expires_at']);

  /// Still worth looking at: forming, confirmed or weakened.
  bool get live => const {'forming', 'confirmed', 'degraded'}.contains(status);
}

/// One order-log row (`GET /trading/journal`), read-only.
@immutable
class JournalEntry {
  const JournalEntry(this.raw);

  final Json raw;

  String get operationId => asStr(raw['operation_id']);
  String get accountId => asStr(raw['account_id']);
  String get status => asStr(raw['status']);
  Json get request => asJson(raw['request']);
  String get action => asStr(request['action']);
  String get symbol => asStr(request['symbol']);
  String get volume => marketField(request['volume']);
  DateTime? get updatedAt => asDate(raw['updated_at']);
  String? get agentId => asString(raw['agent_id']);
  String? get threadId => asString(raw['thread_id']);
  int? get timelineSeq => asInt(raw['timeline_seq']);

  /// The details `operationStatusText` reads (verification, send state, resolution).
  Json get details => {
    'verification': {'status': raw['verification_status']},
    'send_state': raw['send_state'],
    'resolution': raw['resolution'],
  };
}

/// A saved chart's market (`GET /charts` row payload), for the watchlist and chart links.
@immutable
class ChartRef {
  const ChartRef({
    required this.id,
    required this.accountId,
    required this.symbol,
    required this.timeframe,
  });

  factory ChartRef.fromJson(Json j) {
    final p = asJson(j['payload']);
    return ChartRef(
      id: asStr(j['id']),
      accountId: asStr(p['account_id']),
      symbol: asStr(p['symbol']),
      timeframe: asStr(p['timeframe']),
    );
  }

  final String id;
  final String accountId;
  final String symbol;
  final String timeframe;
}

/// The markets the owner follows on [accountId], most relevant first: open positions, the
/// fixed markets of its agents, live watches, live opportunities, saved charts. Each symbol
/// once, at most [limit]. Lonora has no separate watchlist: these are its own records.
List<String> followedSymbols({
  required String accountId,
  List<MarketPosition> positions = const [],
  Iterable<Agent> agents = const [],
  List<MarketWatch> watches = const [],
  List<Opportunity> opportunities = const [],
  List<ChartRef> charts = const [],
  int limit = 12,
}) {
  final out = <String>[];
  void add(String? symbol) {
    if (symbol == null || symbol.isEmpty || out.contains(symbol)) return;
    out.add(symbol);
  }

  for (final p in positions) {
    add(p.symbol);
  }
  for (final a in agents) {
    if (a.tradingAccountId == accountId) add(a.tradingSymbol);
  }
  for (final w in watches) {
    if (!w.ended && w.accountId == accountId) add(w.symbol);
  }
  for (final o in opportunities) {
    if (o.live && o.accountId == accountId) add(o.symbol);
  }
  for (final c in charts) {
    if (c.accountId == accountId) add(c.symbol);
  }
  return out.length > limit ? out.sublist(0, limit) : out;
}

/// The change of the last close against the previous candle's close, in percent; null with
/// fewer than two candles.
double? closeChange(List<MarketCandle> candles) {
  if (candles.length < 2) return null;
  final previous = candles[candles.length - 2].close;
  if (previous == 0) return null;
  return (candles.last.close - previous) / previous * 100;
}

/// A part of the Market tab an event makes stale; each one is read again on its own.
enum MarketPart { connections, watches, opportunities, charts, account, quotes }

/// The parts an owner event makes stale. A chart's scene update is that chart's own business
/// (its screen reads it): only a chart that appears, moves or goes changes the markets
/// followed here. Nothing re-reads the economic calendar (the server fetches the owner's
/// feed on each read): first load, pull-to-refresh and retry do.
Set<MarketPart> marketPartsOf(String kind) {
  bool has(String prefix) => kind.startsWith(prefix);
  if (has('market_watches.') || has('watch.')) return {MarketPart.watches};
  if (has('opportunity.')) return {MarketPart.opportunities};
  if (const {
    'cloud_charts.created',
    'cloud_charts.updated',
    'cloud_charts.deleted',
  }.contains(kind)) {
    return {MarketPart.charts};
  }
  if (has('broker_sessions.')) {
    return {MarketPart.connections, MarketPart.account};
  }
  if (has('trading.') ||
      has('broker') ||
      has('operation.') ||
      has('execution_receipt')) {
    return {MarketPart.account};
  }
  if (has('market_data.')) return {MarketPart.quotes};
  return const {};
}

/// The default account: the first enabled connection that agents trade, else the first
/// enabled one, else none.
String? defaultAccount(
  List<MarketConnection> connections,
  Iterable<Agent> agents,
) {
  final enabled = connections.where((c) => c.enabled).toList();
  if (enabled.isEmpty) return null;
  final traded = {for (final a in agents) ?a.tradingAccountId};
  for (final c in enabled) {
    if (traded.contains(c.id)) return c.id;
  }
  return enabled.first.id;
}

// Reads. Each one throws ApiError / SessionRequestCancelled like every api call.

Future<List<MarketConnection>> fetchMarketConnections() async =>
    asJsonList(await api.get('/trading/connections'))
        .map(MarketConnection.fromJson)
        .toList();

Future<AccountSnapshot> fetchAccountSnapshot(String accountId) async =>
    AccountSnapshot.fromJson(
      asJson(
        await api.get('/trading/accounts/${Uri.encodeComponent(accountId)}'),
      ),
    );

Future<List<String>> fetchMarketSymbols(String accountId) async => asStringList(
  await api.get('/market/symbols', query: {'account_id': accountId}),
);

Future<MarketQuote> fetchQuote(String accountId, String symbol) async =>
    MarketQuote.fromJson(
      asJson(
        await api.get(
          '/market/quote',
          query: {'account_id': accountId, 'symbol': symbol},
        ),
      ),
    );

Future<MarketInstrument> fetchInstrument(
  String accountId,
  String symbol,
) async => MarketInstrument(
  asJson(
    await api.get(
      '/market/instrument',
      query: {'account_id': accountId, 'symbol': symbol},
    ),
  ),
);

Future<List<MarketCandle>> fetchCandles(
  String accountId,
  String symbol, {
  String timeframe = '1h',
  int limit = 300,
}) async => candlesFrom(
  await api.get(
    '/market/candles',
    query: {
      'account_id': accountId,
      'symbol': symbol,
      'timeframe': timeframe,
      'limit': limit,
    },
  ),
);

Future<List<MarketWatch>> fetchWatches() async =>
    asJsonList(await api.get('/watches')).map(MarketWatch.new).toList();

/// The owner's brake on a watch: `cancel`, `pause`, `resume`, or `extend` by [hours]
/// (`POST /watches/{id}/control`; resuming a cancelled watch undoes the cancel).
Future<MarketWatch> controlWatch(
  String id,
  String action, {
  int? hours,
}) async => MarketWatch(
  asJson(
    await api.post('/watches/${Uri.encodeComponent(id)}/control', {
      'action': action,
      'hours': ?hours,
    }),
  ),
);

/// The owner's economic calendar feeds (`GET /integrations`, type `economic_calendar`), for
/// a calendar watch: id → name.
Future<Map<String, String>> fetchCalendarFeeds() async => {
  for (final row in asJsonList(await api.get('/integrations')))
    if (asJson(row['payload'])['type'] == 'economic_calendar')
      asStr(row['id']): asStr(asJson(row['payload'])['name'], asStr(row['id'])),
};

Future<List<CalendarEvent>> fetchCalendar() async =>
    asJsonList(await api.get('/market/calendar'))
        .map(CalendarEvent.new)
        .toList();

Future<List<Opportunity>> fetchOpportunities() async =>
    asJsonList(await api.get('/trading/opportunities', query: {'limit': 20}))
        .map(Opportunity.new)
        .toList();

Future<List<JournalEntry>> fetchJournal(String accountId) async => asJsonList(
  await api.get('/trading/journal', query: {'account_id': accountId}),
).map(JournalEntry.new).toList();

Future<List<ChartRef>> fetchChartRefs() async =>
    asJsonList(await api.get('/charts')).map(ChartRef.fromJson).toList();
