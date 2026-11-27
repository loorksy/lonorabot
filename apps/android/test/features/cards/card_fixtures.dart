// Server-shaped records for the card tests. The owner action is the real Mandate card the local
// Lonora server returns for a thread (GET /api/owner-actions?thread_id=, captured read-only);
// approvals and receipts follow packages/contracts/src/trading.ts and D/trade_approvals.py.
import 'dart:convert';

import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';

const threadId = 'a31a5846-d84e-4ea0-b8a3-a78fe4c648a3';
const agentId = 'ecf97259-3681-5cb5-a5be-ce7eb5e0fd95';

/// The trading connection's resource id: what an approval request's `account_id` and an
/// agent's `trading_account_id` name (lonora_tools/trade.py, account_authority.py).
const accountId = '6b1f0c3e-2d4a-4f7e-9c58-1a2b3c4d5e6f';

/// The broker's own account number inside the connection's payload: never a card's key.
const brokerAccountNumber = '20581137';

/// `GET /trading/connections` as the server answers it (`resource_data` rows).
List<Json> connections({String provider = 'simulation'}) => [
  {
    'id': accountId,
    'kind': 'broker_sessions',
    'payload': {
      'provider': provider,
      'account_id': brokerAccountNumber,
      'api_key': 'never-kept',
    },
  },
];

final agent = Agent.fromJson({
  'id': agentId,
  'name': 'Lonora',
  'avatar': 'face-smile',
  'color': 'violet',
  'trading_mode': 'ask',
  'trading_account_id': accountId,
});

Json mandateCard({String status = 'pending', Json? result, String? reason}) => {
  'id': '608be552-0f83-536d-808b-296a7875122f',
  'kind': 'trading_mode',
  'status': status,
  'status_reason': reason,
  'superseded_by': null,
  'source': 'system',
  'agent_id': agentId,
  'thread_id': threadId,
  'run_id': null,
  'timeline_seq': 1,
  'facts': {
    'several_accounts': false,
    'agent': {'exists': true, 'id': agentId, 'name': 'Lonora'},
    'trading_mode': 'ask',
    'active_grant': false,
  },
  'requires_passkey': false,
  'result': result ?? <String, Object?>{},
  'expires_at': '2036-11-24T02:11:09.161728+00:00',
  'decided_at': null,
  'decided_via': null,
  'created_at': '2026-11-27T02:11:09.161728+00:00',
  'updated_at': '2026-11-27T02:11:09.161728+00:00',
};

Json settleCard({String status = 'pending', Json? result}) => {
  'id': 'settle-1',
  'kind': 'settle_operation',
  'status': status,
  'status_reason': null,
  'superseded_by': null,
  'source': 'system',
  'agent_id': agentId,
  'thread_id': threadId,
  'timeline_seq': 4,
  'facts': {
    'several_accounts': false,
    'operation': {
      'action': 'buy',
      'volume': '0.10',
      'symbol': 'XAUUSD',
      'by_agent_name': 'Lonora',
    },
  },
  'requires_passkey': false,
  'result': result ?? <String, Object?>{},
  'created_at': '2026-11-27T09:10:00Z',
  'updated_at': '2026-11-27T09:10:00Z',
};

Json approval({
  String id = 'appr-1',
  String status = 'pending',
  int? timelineSeq = 3,
  String createdAt = '2026-11-27T09:00:00Z',
  List<Json> results = const [],
}) => {
  'id': id,
  'run_id': 'run-1',
  'thread_id': threadId,
  'agent_id': agentId,
  'timeline_seq': timelineSeq,
  'status': status,
  'requests': [
    {
      'account_id': accountId,
      'operation_id': 'op-1',
      'action': 'buy_limit',
      'symbol': 'XAUUSD',
      'volume': '0.10',
      'price': '2346.80',
      'stop_loss': '2330.00',
      'take_profit': '2380.00',
    },
  ],
  'contracts': <Object?>[],
  'results': results,
  'reason': 'الذهب يرتد من دعم يومي واضح.',
  'tolerance': '1.50',
  'reference_price': '2346.80',
  'expires_at': null,
  'created_at': createdAt,
};

Json receipt({String verification = 'verified', int? timelineSeq = 5}) => {
  'operation_id': 'op-1',
  'thread_id': threadId,
  'timeline_seq': timelineSeq,
  'agent_id': agentId,
  'created_at': '2026-11-27T09:05:00Z',
  'kind': 'fill',
  'action': 'buy',
  'symbol': 'XAUUSD',
  'ticket': '50311987',
  'volume': '0.10',
  'price': '2346.75',
  'partial': false,
  'reason': 'Daily support held.',
  'verification': verification,
};

Message message(int seq, {String role = 'assistant', String? created}) =>
    Message.fromJson({
      'id': 'm$seq',
      'thread_id': threadId,
      'role': role,
      'agent_id': role == 'assistant' ? agentId : null,
      'seq': seq,
      'content': 'message $seq',
      'created_at': created ?? '2026-11-27T09:0$seq:30Z',
    });

Json secretCard({String status = 'pending'}) => {
  'id': 'secret-1',
  'kind': 'secret',
  'status': status,
  'status_reason': null,
  'superseded_by': null,
  'source': 'agent',
  'agent_id': agentId,
  'thread_id': threadId,
  'timeline_seq': 2,
  'facts': {
    'several_accounts': false,
    'secret': {
      'label': 'Weather API',
      'agent_name': 'Lonora',
      'fields': [
        {'key': 'WEATHER_KEY', 'secret': true, 'required': true},
      ],
    },
  },
  'requires_passkey': false,
  'result': <String, Object?>{},
  'created_at': '2026-11-27T09:01:00Z',
  'updated_at': '2026-11-27T09:01:00Z',
};

/// Records every request; answers from [routes] (`METHOD path` → value, a Future of one,
/// or ApiError).
class FakeApi extends ApiClient {
  FakeApi(this.routes) : super(userAgent: 'test');

  final Map<String, Object? Function(Object? body)> routes;
  final List<String> calls = [];

  /// A copy of each body as it was sent.
  final List<Object?> bodies = [];

  /// The body objects themselves (a caller that clears its map after sending shows here).
  final List<Object?> sentBodies = [];

  Future<dynamic> _answer(String key, Object? body) async {
    calls.add(key);
    bodies.add(body == null ? null : jsonDecode(jsonEncode(body)));
    sentBodies.add(body);
    final route = routes[key];
    if (route == null) throw ApiError(status: 404, code: 'endpoint_not_found');
    final value = await Future<Object?>.value(route(body));
    if (value is ApiError) throw value;
    return value;
  }

  @override
  Future<dynamic> get(
    String path, {
    Map<String, Object?>? query,
    Duration? timeout,
  }) {
    final q = query == null || query.isEmpty
        ? ''
        : '?${query.entries.map((e) => '${e.key}=${e.value}').join('&')}';
    return _answer('GET $path$q', null);
  }

  @override
  Future<dynamic> post(String path, [Object? body]) =>
      _answer('POST $path', body);
}
