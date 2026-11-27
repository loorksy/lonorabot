// Realistic market fixtures (shapes verified against the local Lonora server's simulation
// adapter: decimal strings, ISO times).
import 'package:lonora/core/json.dart';

import 'wpf_harness.dart';

final connectionsFixture = <Json>[
  {
    'id': 'acct-1',
    'kind': 'trading_connections',
    'version': 2,
    'payload': {
      'provider': 'simulation',
      'account_id': 'acct-1',
      'enabled': true,
    },
    'state': {
      'broker_identity': {
        'broker': 'Lonora Sim',
        'login': '5021',
        'server': 'Paper-1',
        'connection_version': 2,
      },
    },
  },
  {
    'id': 'acct-2',
    'kind': 'trading_connections',
    'version': 1,
    'payload': {'provider': 'metaapi', 'account_id': 'uuid', 'enabled': true},
    'state': {},
  },
];

final accountFixture = <String, Object?>{
  'account': {
    'id': 'acct-1',
    'currency': 'USD',
    'balance': '10000.00',
    'equity': '10248.60',
    'margin': '412.00',
    'free_margin': '9836.60',
    'observed_at': '2026-11-27T09:58:00Z',
  },
  'positions': [
    {
      'id': 'p-1',
      'symbol': 'XAUUSD',
      'side': 'buy',
      'volume': '0.10',
      'open_price': '2380.50',
      'profit': '212.40',
      'stop_loss': '2365.00',
      'take_profit': null,
    },
    {
      'id': 'p-2',
      'symbol': 'EURUSD',
      'side': 'sell',
      'volume': '0.50',
      'open_price': '1.08420',
      'profit': '36.20',
      'stop_loss': null,
      'take_profit': null,
    },
  ],
  'orders': [
    {
      'id': 'o-1',
      'symbol': 'GBPUSD',
      'side': 'buy_limit',
      'volume': '0.20',
      'price': '1.26100',
    },
  ],
};

Json quoteFor(String symbol) => switch (symbol) {
  'XAUUSD' => {
    'symbol': 'XAUUSD',
    'bid': '2401.74',
    'ask': '2402.06',
    'observed_at': '2026-11-27T09:59:30Z',
    'source': 'simulation',
  },
  'EURUSD' => {
    'symbol': 'EURUSD',
    'bid': '1.08055',
    'ask': '1.08061',
    'observed_at': '2026-11-27T09:59:30Z',
    'source': 'simulation',
  },
  _ => {
    'symbol': symbol,
    'bid': '1.26340',
    'ask': '1.26352',
    'observed_at': '2026-11-27T09:59:30Z',
    'source': 'simulation',
  },
};

List<Json> dailyFor(String symbol) => switch (symbol) {
  'XAUUSD' => [
    candle(symbol, '2026-11-26T00:00:00Z', 2380, 2392, 2371, 2386.2, tf: '1d'),
    candle(symbol, '2026-11-27T00:00:00Z', 2386, 2405, 2384, 2401.7, tf: '1d'),
  ],
  'EURUSD' => [
    candle(
      symbol,
      '2026-11-26T00:00:00Z',
      1.083,
      1.085,
      1.081,
      1.0832,
      tf: '1d',
    ),
    candle(
      symbol,
      '2026-11-27T00:00:00Z',
      1.0832,
      1.0838,
      1.0801,
      1.0806,
      tf: '1d',
    ),
  ],
  _ => [],
};

Json candle(
  String symbol,
  String time,
  double o,
  double h,
  double l,
  double c, {
  String tf = '1h',
}) => {
  'symbol': symbol,
  'timeframe': tf,
  'time': time,
  'open': '$o',
  'high': '$h',
  'low': '$l',
  'close': '$c',
  'volume': '120',
};

/// [n] hourly candles of a gentle uptrend with a pullback, deterministic.
List<Json> hourlyCandles(String symbol, int n, {double start = 2360}) {
  final out = <Json>[];
  var price = start;
  final t0 = DateTime.utc(2026, 11, 25, 0);
  for (var i = 0; i < n; i++) {
    final wave = ((i * 37) % 11 - 5) * 0.9;
    final drift = i < n * 0.6 ? 0.55 : -0.35;
    final open = price;
    final close = price + drift + wave * 0.5;
    final high = (open > close ? open : close) + 1.2 + (i % 3);
    final low = (open < close ? open : close) - 1.1 - (i % 4) * 0.5;
    out.add(
      candle(
        symbol,
        t0.add(Duration(hours: i)).toIso8601String(),
        double.parse(open.toStringAsFixed(2)),
        double.parse(high.toStringAsFixed(2)),
        double.parse(low.toStringAsFixed(2)),
        double.parse(close.toStringAsFixed(2)),
      ),
    );
    price = close;
  }
  return out;
}

final watchesFixture = <Json>[
  {
    'id': 'w-1',
    'agent_id': 'a-gold',
    'thread_id': 't-gold',
    'version': 3,
    'payload': {
      'kind': 'price',
      'account_id': 'acct-1',
      'symbol': 'XAUUSD',
      'condition': 'cross_above',
      'level': '2410',
      'enabled': true,
      'expires_at': null,
    },
    'state': {'lifecycle': 'pending'},
  },
  {
    'id': 'w-2',
    'agent_id': 'a-research',
    'thread_id': 't-research',
    'version': 2,
    'payload': {
      'kind': 'indicator',
      'account_id': 'acct-1',
      'symbol': 'EURUSD',
      'indicator': 'rsi',
      'timeframe': '1h',
      'condition': 'below',
      'level': '30',
      'enabled': false,
    },
    'state': {'lifecycle': 'pending', 'code': 'watch_paused'},
  },
  {
    'id': 'w-3',
    'agent_id': 'a-gold',
    'thread_id': 't-gold',
    'version': 5,
    'payload': {
      'kind': 'price',
      'account_id': 'acct-1',
      'symbol': 'XAUUSD',
      'condition': 'below',
      'level': '2300',
      'enabled': false,
    },
    'state': {'lifecycle': 'pending', 'code': 'watch_cancelled'},
  },
];

final calendarFixture = <Json>[
  {
    'id': 'e-1',
    'name': 'Non-Farm Payrolls',
    'currency': 'USD',
    'observed_at': '2026-11-27T08:00:00Z',
    'scheduled_at': '2099-12-04T13:30:00Z',
    'impact': 'high',
    'actual': null,
    'forecast': '185K',
    'source': 'feed',
  },
  {
    'id': 'e-2',
    'name': 'ECB Press Conference',
    'currency': 'EUR',
    'observed_at': '2026-11-27T08:00:00Z',
    'scheduled_at': '2099-12-05T13:45:00Z',
    'impact': 'medium',
    'actual': null,
    'forecast': null,
    'source': 'feed',
  },
];

final opportunitiesFixture = <Json>[
  {
    'id': 'op-1',
    'agent_id': 'a-gold',
    'thread_id': 't-gold',
    'account_id': 'acct-1',
    'symbol': 'XAUUSD',
    'timeframe': '4h',
    'setup_key': 'breakout',
    'status': 'confirmed',
    'expires_at': '2099-12-01T00:00:00Z',
  },
  {
    'id': 'op-2',
    'agent_id': 'a-gold',
    'thread_id': 't-gold',
    'account_id': 'acct-1',
    'symbol': 'XAUUSD',
    'timeframe': '1h',
    'setup_key': 'pullback',
    'status': 'expired',
    'expires_at': '2026-11-20T00:00:00Z',
  },
];

final journalFixture = <Json>[
  {
    'operation_id': 'op-a',
    'account_id': 'acct-1',
    'status': 'confirmed',
    'request': {'action': 'buy', 'symbol': 'XAUUSD', 'volume': '0.10'},
    'result': {},
    'submitted_at': '2026-11-27T07:12:00Z',
    'updated_at': '2026-11-27T07:12:03Z',
    'agent_id': 'a-gold',
    'thread_id': 't-gold',
    'timeline_seq': 42,
    'verification_status': 'verified',
  },
];

final chartsFixture = <Json>[
  {
    'id': 'c-1',
    'agent_id': 'a-gold',
    'thread_id': 't-gold',
    'version': 4,
    'payload': {
      'account_id': 'acct-1',
      'symbol': 'XAUUSD',
      'timeframe': '1h',
      'indicators': [
        {'name': 'ema', 'period': 20},
      ],
      'annotations': [],
    },
    'state': {},
    'updated_at': '2026-11-27T09:40:00Z',
  },
];

/// Scripts the whole Market tab on [fakeApi].
void scriptMarket({bool noAccounts = false}) {
  fakeApi
    ..on(
      'GET /trading/connections',
      (_, _) => noAccounts ? [] : connectionsFixture,
    )
    ..on('GET /trading/accounts/acct-1', (_, _) => accountFixture)
    ..on('GET /watches', (_, _) => watchesFixture)
    ..on('GET /market/calendar', (_, _) => calendarFixture)
    ..on('GET /trading/opportunities', (_, _) => opportunitiesFixture)
    ..on('GET /trading/journal', (_, _) => journalFixture)
    ..on('GET /charts', (_, _) => chartsFixture)
    ..on('GET /market/quote', (_, q) => quoteFor('${q?['symbol']}'))
    ..on(
      'GET /market/candles',
      (_, q) => q?['timeframe'] == '1d'
          ? dailyFor('${q?['symbol']}')
          : hourlyCandles('${q?['symbol']}', 48),
    )
    ..on(
      'GET /market/symbols',
      (_, _) => ['XAUUSD', 'XAGUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'US30'],
    )
    ..on(
      'GET /market/instrument',
      (_, q) => {
        'symbol': q?['symbol'],
        'description': 'Gold vs US Dollar',
        'digits': 2,
        'tick_size': '0.01',
        'volume_min': '0.01',
        'volume_max': '50',
        'volume_step': '0.01',
      },
    );
}
