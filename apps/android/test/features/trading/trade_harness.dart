// Harness of the owner's order tests: the market harness (fonts, catalogs, signed-in store,
// router) with a strict fake API — an unregistered route fails loudly, so an accidental
// execute can never pass for a success — and fixtures of two accounts (a simulation and a
// broker account), positions, a pending order and the order log. No test reaches a server:
// `POST /trading/execute` is only ever answered by a handler a test registers.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FButton;
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/features/trading/trades_data.dart';
import 'package:lonora/state/app_state.dart';

import '../market/wpf_harness.dart';

export '../market/wpf_harness.dart';

/// Unknown routes answer 404 `endpoint_not_found` (after being recorded); the execute's own
/// timeout is recorded.
class StrictApi extends FakeApi {
  final timeouts = <Duration>[];

  Future<dynamic> _strict(
    String method,
    String path,
    Future<dynamic> Function() send,
  ) async {
    final known = handlers.containsKey('$method $path');
    final answer = await send();
    if (!known) throw ApiError(status: 404, code: 'endpoint_not_found');
    return answer;
  }

  @override
  Future<dynamic> get(
    String path, {
    Map<String, Object?>? query,
    Duration? timeout,
  }) => _strict('GET', path, () => super.get(path, query: query));

  @override
  Future<dynamic> post(String path, [Object? body]) =>
      _strict('POST', path, () => super.post(path, body));

  @override
  Future<dynamic> postWithin(String path, Object body, Duration timeout) {
    timeouts.add(timeout);
    return post(path, body);
  }

  /// The bodies sent to the executor, in order.
  List<Json> get executed => [
    for (final c in callsTo('POST', '/trading/execute')) asJson(c.body),
  ];
}

late StrictApi tradeApi;

Future<void> resetTrades() async {
  tradeApi = StrictApi();
  await resetWpf(api: tradeApi);
  OrderDesk.instance.reset();
}

/// The held identities' scope of the test owner on the test server.
final testScope = LocalStore.scope('http://test', 'owner-1');

const simConnection = <String, Object?>{
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
};

Json liveConnection({Json? recovery}) => {
  'id': 'acct-2',
  'kind': 'trading_connections',
  'version': 1,
  'payload': {'provider': 'metaapi', 'account_id': 'uuid', 'enabled': true},
  'state': {
    'broker_identity': {
      'broker': 'Demo Broker',
      'login': '880021',
      'server': 'Live-3',
      'connection_version': 1,
    },
    'broker_recovery': ?recovery,
  },
};

const goldPosition = <String, Object?>{
  'id': 'p-1',
  'symbol': 'XAUUSD',
  'side': 'buy',
  'volume': '0.10',
  'open_price': '2380.50',
  'profit': '212.40',
  'stop_loss': '2365.00',
  'take_profit': null,
};

const eurPosition = <String, Object?>{
  'id': 'p-2',
  'symbol': 'EURUSD',
  'side': 'sell',
  'volume': '0.50',
  'open_price': '1.08420',
  'profit': '36.20',
  'stop_loss': null,
  'take_profit': null,
};

const goldOrder = <String, Object?>{
  'id': 'o-7',
  'symbol': 'XAUUSD',
  'side': 'buy_limit',
  'volume': '0.20',
  'price': '2350.00',
  'stop_loss': '2330.00',
  'take_profit': null,
};

Json accountState({
  String id = 'acct-1',
  List<Json> positions = const [goldPosition, eurPosition],
  List<Json> orders = const [goldOrder],
  bool? tradeAllowed,
  bool? investorMode,
}) => {
  'account': {
    'id': id,
    'currency': 'USD',
    'balance': '10000.00',
    'equity': '10248.60',
    'margin': '412.00',
    'free_margin': '9836.60',
    'observed_at': '2026-11-27T09:58:00Z',
    'trade_allowed': ?tradeAllowed,
    'investor_mode': ?investorMode,
  },
  'positions': positions,
  'orders': orders,
};

Json journalRow(
  String id, {
  required String action,
  required String status,
  String symbol = 'XAUUSD',
  String? agentId = 'a-gold',
  Json extraRequest = const {},
  Json result = const {},
  String? verification,
  String submitted = '2026-11-27T07:12:00Z',
  String? updated,
  Json? resolution,
}) => {
  'operation_id': id,
  'account_id': 'acct-1',
  'status': status,
  'request': {'action': action, 'symbol': symbol, ...extraRequest},
  'result': {'status': status, ...result},
  'submitted_at': submitted,
  'updated_at': updated ?? submitted,
  'agent_id': agentId,
  'thread_id': agentId == null ? null : 't-gold',
  'timeline_seq': 40,
  'verification_status': verification,
  'resolution': resolution,
};

/// The order log of the gold desk: a fill with its price, a placed limit, a rejection, a
/// partial fill, an uncertain close, and the owner's own close (not listed, agent_id null).
final orderLog = <Json>[
  journalRow(
    'op-1',
    action: 'buy',
    status: 'confirmed',
    extraRequest: {'volume': '0.10'},
    result: {
      'details': {'price': '2380.50', 'volume': '0.10'},
    },
    verification: 'verified',
    submitted: '2026-11-27T07:12:00Z',
  ),
  journalRow(
    'op-2',
    action: 'buy_limit',
    status: 'confirmed',
    extraRequest: {'volume': '0.20', 'price': '2350.00'},
    verification: 'verified',
    submitted: '2026-11-27T08:01:00Z',
  ),
  journalRow(
    'op-3',
    action: 'sell',
    status: 'failed',
    extraRequest: {'volume': '0.30'},
    result: {'code': 'broker_order_rejected'},
    submitted: '2026-11-27T08:30:00Z',
  ),
  journalRow(
    'op-4',
    action: 'buy',
    status: 'confirmed',
    extraRequest: {'volume': '0.5'},
    result: {
      'details': {
        'partial_execution': true,
        'volume': '0.2',
        'price': '2379.10',
      },
    },
    submitted: '2026-11-27T09:05:00Z',
  ),
  journalRow(
    'op-5',
    action: 'close_position',
    status: 'ambiguous',
    extraRequest: {'position_id': 'p-9'},
    result: {'code': 'broker_result_ambiguous'},
    submitted: '2026-11-27T09:20:00Z',
  ),
];

/// Scripts the reads of the order screens on [tradeApi].
void scriptTrades({
  List<Json>? connections,
  Json? account,
  Json? liveAccount,
  List<Json>? journal,
}) {
  tradeApi
    ..on(
      'GET /trading/connections',
      (_, _) => connections ?? [simConnection, liveConnection()],
    )
    ..on('GET /trading/accounts/acct-1', (_, _) => account ?? accountState())
    ..on(
      'GET /trading/accounts/acct-2',
      (_, _) =>
          liveAccount ??
          accountState(
            id: 'acct-2',
            positions: [eurPosition],
            orders: const [],
          ),
    )
    ..on('GET /trading/journal', (_, _) => journal ?? orderLog)
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

/// The executor's answer for [body] with [status].
Json executorAnswer(
  Object? body,
  String status, {
  String? code,
  Json details = const {},
}) => {
  'operation_id': asJson(body)['operation_id'],
  'status': status,
  'broker_id': status == 'confirmed' ? 'T-55120' : null,
  'code': code,
  'details': details,
};

/// The agents of the order tests: the gold desk on the simulation, a live desk on the broker
/// account, and one without an account.
final tradeAgents = <Json>[
  ...fixtureAgents,
  {
    'id': 'a-live',
    'name': 'Euro desk',
    'avatar': 'face-focused',
    'color': '#22C55E',
    'role': 'general',
    'scope_mode': 'fixed_market',
    'trading_account_id': 'acct-2',
    'trading_symbol': 'EURUSD',
    'trading_mode': 'ask',
  },
  {
    'id': 'a-none',
    'name': 'Desk without account',
    'avatar': 'face-focused',
    'color': '#22C55E',
    'role': 'general',
    'template': 'trading',
  },
];

Store<AppState> tradeStore({String locale = 'ar'}) =>
    wpfStore(locale: locale, agents: tradeAgents);

/// Finds the button labelled [label] in the topmost sheet or page (the last match).
Finder buttonLabelled(String label) => find.widgetWithText(FButton, label).last;

/// Lets a pending future complete under the test clock.
Future<void> flush(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

/// A completer whose future an execute handler returns: the answer arrives when the test says.
Completer<Object?> pendingAnswer() => Completer<Object?>();
