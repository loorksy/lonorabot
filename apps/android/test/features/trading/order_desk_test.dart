// The order desk and the held identities (useTicketAction.ts / held-operation.ts, with the
// critic's corrections): one identity per ticket action, stored with its exact body before
// anything is sent, resent byte for byte, released only when the outcome settles or when a 4xx
// proves nothing under it was journaled; app-wide in-flight guard; one document that survives
// «مسح ذاكرة التخزين المؤقت» and goes with an explicit sign-out. Every execute is answered by
// the fake API.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/storage/held_operations.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/features/market/market_data.dart';
import 'package:lonora/features/me/me_actions.dart';
import 'package:lonora/features/trading/trade_rules.dart';
import 'package:lonora/features/trading/trades_data.dart';
import 'package:lonora/state/actions/session_actions.dart';
import 'package:lonora/state/realtime.dart';

import 'trade_harness.dart';

final _uuidV4 = RegExp(
  r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
);

const _gold = MarketPosition(goldPosition);
final _close = heldKey('close_position', 'acct-1', 'p-1');
Json _closeBody() => closeRequest(accountId: 'acct-1', p: _gold);

OrderDesk get desk => OrderDesk.instance;

Future<TicketOutcome?> _runClose() =>
    desk.run(scope: testScope, key: _close, build: _closeBody);

void main() {
  setUpAll(setUpWpf);
  setUp(resetTrades);

  test('the identity is stored with its exact body before the send', () async {
    Object? stored;
    tradeApi.on('POST /trading/execute', (body, _) async {
      stored = await localStore.read(testScope, HeldOperations.document);
      return executorAnswer(body, 'submitted');
    });
    final outcome = await _runClose();
    expect(outcome!.status, 'submitted');
    final sent = tradeApi.executed.single;
    final id = sent['operation_id'] as String;
    expect(id, matches(_uuidV4));
    expect(sent, {..._closeBody(), 'operation_id': id});
    expect(asJson(asJson(stored)[_close])['operation_id'], id);
    expect(asJson(asJson(stored)[_close])['body'], sent);
    expect(tradeApi.timeouts.single, const Duration(seconds: 75));
  });

  test('no answer: kept, and the retry sends the same id and bytes; settled releases it', () async {
    var n = 0;
    tradeApi.on('POST /trading/execute', (body, _) {
      if (++n == 1) throw ApiError.network('timeout');
      return executorAnswer(body, 'confirmed');
    });
    expect(await _runClose(), isNull);
    expect(desk.error(testScope, _close), isA<ApiError>());
    final held = desk.held(testScope, _close)!;
    expect(held.unansweredAttempt, isTrue);
    final outcome = await _runClose();
    expect(outcome!.status, 'confirmed');
    expect(tradeApi.executed, hasLength(2));
    expect(jsonEncode(tradeApi.executed[1]), jsonEncode(tradeApi.executed[0]));
    expect(tradeApi.executed[0]['operation_id'], held.operationId);
    expect(desk.held(testScope, _close), isNull);
    expect(desk.error(testScope, _close), isNull);
    // The next tap is a new operation.
    await _runClose();
    expect(tradeApi.executed[2]['operation_id'], isNot(held.operationId));
  });

  test('reserved, submitted and ambiguous keep the identity held', () async {
    final answers = ['reserved', 'submitted', 'ambiguous'];
    tradeApi.on(
      'POST /trading/execute',
      (body, _) => executorAnswer(body, answers.removeAt(0)),
    );
    for (var i = 0; i < 3; i++) {
      final o = await _runClose();
      expect(operationUnsettled(o!.status), isTrue);
      expect(desk.held(testScope, _close), isNotNull);
    }
    expect(
      tradeApi.executed.map((b) => b['operation_id']).toSet(),
      hasLength(1),
    );
  });

  test(
    'a 4xx with every send answered releases it; the values stay the owner\'s',
    () async {
      tradeApi.on(
        'POST /trading/execute',
        (_, _) => throw ApiError(status: 400, code: 'volume_step_mismatch'),
      );
      final key = openKey('acct-1');
      Json order() => {
        'account_id': 'acct-1',
        'action': 'buy',
        'symbol': 'XAUUSD',
        'volume': '0.015',
      };
      expect(await desk.run(scope: testScope, key: key, build: order), isNull);
      expect(desk.held(testScope, key), isNull);
      expect(
        (desk.error(testScope, key)! as ApiError).code,
        'volume_step_mismatch',
      );
      await desk.run(scope: testScope, key: key, build: order);
      expect(
        tradeApi.executed[1]['operation_id'],
        isNot(tradeApi.executed[0]['operation_id']),
      );
    },
  );

  test('a 4xx after a send that got no answer keeps it (that send may still journal)', () async {
    var n = 0;
    tradeApi.on('POST /trading/execute', (_, _) {
      if (++n == 1) {
        throw ApiError(status: 504, code: 'broker_gateway_no_answer');
      }
      throw ApiError(status: 409, code: 'broker_observation_unavailable');
    });
    await _runClose();
    await _runClose();
    final held = desk.held(testScope, _close)!;
    expect(held.attempts, 2);
    expect(held.answered, 1);
    expect(
      tradeApi.executed[1]['operation_id'],
      tradeApi.executed[0]['operation_id'],
    );
  });

  test('an executor result journals the identity: no later 4xx releases it, a 401 included', () async {
    var n = 0;
    tradeApi.on('POST /trading/execute', (body, _) {
      n++;
      if (n == 1) return executorAnswer(body, 'ambiguous');
      if (n == 2) throw ApiError(status: 401, code: 'unauthorized');
      throw ApiError(status: 409, code: 'broker_observation_unavailable');
    });
    await _runClose();
    final id = desk.held(testScope, _close)!.operationId;
    expect(desk.held(testScope, _close)!.journaled, isTrue);
    expect(desk.held(testScope, _close)!.unansweredAttempt, isFalse);
    await _runClose();
    expect(desk.held(testScope, _close)?.operationId, id);
    await _runClose();
    expect(desk.held(testScope, _close)?.operationId, id);
    expect(tradeApi.executed.map((b) => b['operation_id']).toSet(), {id});
  });

  test(
    'a session refusal (401) keeps the identity even with every send answered',
    () async {
      tradeApi.on(
        'POST /trading/execute',
        (_, _) => throw ApiError(status: 401, code: 'unauthorized'),
      );
      await _runClose();
      final held = desk.held(testScope, _close)!;
      expect(held.unansweredAttempt, isFalse);
      expect(held.journaled, isFalse);
    },
  );

  test('offline, then refusals: held while the unanswered send could still arrive, then released', () async {
    var n = 0;
    tradeApi.on('POST /trading/execute', (body, _) {
      if (++n == 1) throw ApiError.network();
      throw ApiError(status: 409, code: 'broker_trading_not_allowed');
    });
    final key = openKey('acct-1');
    Json order() => {
      'account_id': 'acct-1',
      'action': 'buy',
      'symbol': 'XAUUSD',
      'volume': '0.1',
    };
    await desk.run(scope: testScope, key: key, build: order);
    for (var i = 0; i < 3; i++) {
      await desk.run(scope: testScope, key: key, build: order);
    }
    final held = desk.held(testScope, key)!;
    expect(held.attempts, 4);
    expect(held.answered, 3);
    expect(held.unansweredSince, isNotNull);
    // Neither the journal nor the account has anything that would release it.
    await desk.settle(testScope, 'acct-1', const []);
    await desk.dropGone(
      testScope,
      'acct-1',
      AccountSnapshot.fromJson(accountState()),
      const [],
    );
    expect(desk.held(testScope, key), isNotNull);
    // Read again later (the unanswered send started 151 s before): the same refusal now
    // proves nothing was journaled, and the form is free.
    final doc = asJson(
      await localStore.read(testScope, HeldOperations.document),
    );
    await localStore.write(testScope, HeldOperations.document, {
      ...doc,
      key: {
        ...asJson(doc[key]),
        'unanswered_since': DateTime.now()
            .subtract(const Duration(seconds: 151))
            .toUtc()
            .toIso8601String(),
      },
    });
    desk.forget();
    await desk.load(testScope);
    await desk.run(scope: testScope, key: key, build: order);
    expect(desk.held(testScope, key), isNull);
    expect(
      (desk.error(testScope, key)! as ApiError).code,
      'broker_trading_not_allowed',
    );
    expect(
      tradeApi.executed.map((b) => b['operation_id']).toSet(),
      hasLength(1),
    );
  });

  for (final (age, released) in [(10, false), (200, true)]) {
    test(
      'a send the app never saw end (${age}s ago) counts as unanswered from when it started',
      () async {
        tradeApi.on(
          'POST /trading/execute',
          (_, _) => throw ApiError(status: 409, code: 'market_quote_stale'),
        );
        final started = DateTime.now().subtract(Duration(seconds: age));
        final body = {..._closeBody(), 'operation_id': 'op-dangling'};
        await localStore.write(testScope, HeldOperations.document, {
          _close: {
            'operation_id': 'op-dangling',
            'body': body,
            'created_at': started.toUtc().toIso8601String(),
            'attempts': 1,
            'answered': 0,
            'sending_since': started.toUtc().toIso8601String(),
          },
        });
        await desk.load(testScope);
        await _runClose();
        expect(tradeApi.executed.single, body);
        final held = desk.held(testScope, _close);
        if (released) {
          expect(held, isNull);
        } else {
          expect(held!.unansweredSince!.toUtc(), started.toUtc());
          expect(held.sendingSince, isNull);
        }
      },
    );
  }

  test(
    'a check never mints: once the reviewed identity is gone, nothing is sent',
    () async {
      tradeApi.on(
        'POST /trading/execute',
        (body, _) => executorAnswer(body, 'submitted'),
      );
      await _runClose();
      final id = desk.held(testScope, _close)!.operationId;
      await desk.settle(testScope, 'acct-1', [
        JournalEntry(
          journalRow(
            id,
            action: 'close_position',
            status: 'confirmed',
            extraRequest: {'position_id': 'p-1'},
          ),
        ),
      ]);
      expect(desk.held(testScope, _close), isNull);
      final outcome = await desk.run(
        scope: testScope,
        key: _close,
        build: _closeBody,
        expect: id,
      );
      expect(outcome, isNull);
      expect(tradeApi.executed, hasLength(1));
      expect(desk.held(testScope, _close), isNull);
      expect(desk.outcome(testScope, _close, null)!.status, 'confirmed');
    },
  );

  test(
    'a conflict on the identity keeps it; so does a server failure',
    () async {
      var code = 'idempotency_conflict';
      var status = 409;
      tradeApi.on(
        'POST /trading/execute',
        (_, _) => throw ApiError(status: status, code: code),
      );
      await _runClose();
      expect(desk.held(testScope, _close), isNotNull);
      status = 500;
      code = 'request_failed';
      await _runClose();
      expect(desk.held(testScope, _close)!.unansweredAttempt, isTrue);
    },
  );

  test('a 200 that is not an executor result settles nothing', () async {
    tradeApi.on('POST /trading/execute', (_, _) => <String, Object?>{});
    expect(await _runClose(), isNull);
    expect(desk.error(testScope, _close), isA<TradeAnswerUnknown>());
    expect(desk.held(testScope, _close)!.unansweredAttempt, isTrue);
    tradeApi.on(
      'POST /trading/execute',
      (body, _) => {...executorAnswer(body, 'confirmed'), 'operation_id': 'x'},
    );
    expect(await _runClose(), isNull);
    expect(desk.held(testScope, _close), isNotNull);
  });

  test('a second tap while one is in flight sends nothing', () async {
    final answer = pendingAnswer();
    tradeApi.on('POST /trading/execute', (_, _) => answer.future);
    final first = _runClose();
    final second = await _runClose();
    expect(second, isNull);
    await Future<void>.delayed(Duration.zero);
    expect(desk.busy(testScope, _close), isTrue);
    answer.complete(executorAnswer(tradeApi.executed.single, 'confirmed'));
    expect((await first)!.status, 'confirmed');
    expect(tradeApi.executed, hasLength(1));
    expect(desk.busy(testScope, _close), isFalse);
  });

  test(
    'the journal settles a held identity; an unsettled row keeps it',
    () async {
      tradeApi.on(
        'POST /trading/execute',
        (body, _) => executorAnswer(body, 'ambiguous'),
      );
      await _runClose();
      final id = desk.held(testScope, _close)!.operationId;
      JournalEntry row(String status) => JournalEntry(
        journalRow(
          id,
          action: 'close_position',
          status: status,
          extraRequest: {'position_id': 'p-1'},
          resolution: status == 'resolved'
              ? {'source': 'owner', 'outcome': 'not_executed'}
              : null,
        ),
      );
      expect(
        desk.outcome(testScope, _close, [row('ambiguous')])!.status,
        'ambiguous',
      );
      await desk.settle(testScope, 'acct-1', [row('ambiguous')]);
      expect(desk.held(testScope, _close), isNotNull);
      await desk.settle(testScope, 'acct-2', [row('resolved')]);
      expect(desk.held(testScope, _close), isNotNull);
      await desk.settle(testScope, 'acct-1', [row('resolved')]);
      expect(desk.held(testScope, _close), isNull);
      expect(desk.outcome(testScope, _close, const [])!.status, 'resolved');
    },
  );

  test('a ticket gone from the account releases its identity unless still unsettled', () async {
    tradeApi.on('POST /trading/execute', (_, _) => throw ApiError.network());
    await _runClose();
    final open = openKey('acct-1');
    await desk.run(
      scope: testScope,
      key: open,
      build: () => {
        'account_id': 'acct-1',
        'action': 'buy',
        'symbol': 'XAUUSD',
        'volume': '0.1',
      },
    );
    final id = desk.held(testScope, _close)!.operationId;
    final present = AccountSnapshot.fromJson(accountState());
    final gone = AccountSnapshot.fromJson(accountState(positions: const []));
    await desk.dropGone(testScope, 'acct-1', present, const []);
    expect(desk.held(testScope, _close), isNotNull);
    final unsettled = JournalEntry(
      journalRow(id, action: 'close_position', status: 'submitted'),
    );
    await desk.dropGone(testScope, 'acct-1', gone, [unsettled]);
    expect(desk.held(testScope, _close), isNotNull);
    await desk.dropGone(testScope, 'acct-1', gone, const []);
    expect(desk.held(testScope, _close), isNull);
    expect(desk.held(testScope, open), isNotNull);
  });

  test(
    'one document keyed by the raw key, read back by a new process',
    () async {
      final dir = Directory.systemTemp.createTempSync('held');
      addTearDown(() => dir.deleteSync(recursive: true));
      final first = HeldOperations.of(LocalStore.at(dir));
      const keys = [
        'close_position:acc:pos',
        'close_position_acc_pos',
        'modify_position:acc:p|1|2||',
      ];
      for (final (i, k) in keys.indexed) {
        await first.hold(
          'scope',
          k,
          mint: () => 'id-$i',
          build: (id) => {'action': 'close_position', 'n': i},
        );
      }
      await first.attempt('scope', keys[2]);
      expect(
        Directory('${dir.path}/scope')
            .listSync()
            .map((f) => f.path.split('/').last),
        ['held_operations.json'],
      );
      final again = HeldOperations.of(LocalStore.at(dir));
      final held = await again.load('scope');
      expect(held.keys, keys);
      expect(held[keys[1]]!.operationId, 'id-1');
      expect(held[keys[2]]!.body, {
        'action': 'close_position',
        'n': 2,
        'operation_id': 'id-2',
      });
      // A send the old process never saw answered stays unanswered.
      expect(held[keys[2]]!.unansweredAttempt, isTrue);
    },
  );

  testWidgets(
    '«مسح ذاكرة التخزين المؤقت» keeps the held identity; sign-out drops it',
    (tester) async {
      final store = tradeStore();
      realtime = FakeRealtime(store);
      tradeApi.on('POST /trading/execute', (_, _) => throw ApiError.network());
      await tester.runAsync(() async {
        await _runClose();
        final id = desk.held(testScope, _close)!.operationId;
        await localStore.write(testScope, 'shell', {'cached': true});
        await store.dispatchAndWait(ClearLocalCacheAction());
        expect(await localStore.read(testScope, 'shell'), isNull);
        final kept = asJson(
          await localStore.read(testScope, HeldOperations.document),
        );
        expect(asJson(kept[_close])['operation_id'], id);
        // A fresh read (another process) still finds it.
        desk.forget();
        await desk.load(testScope);
        expect(desk.held(testScope, _close)!.operationId, id);

        await store.dispatchAndWait(SignOutAction());
        expect(
          await localStore.read(testScope, HeldOperations.document),
          isNull,
        );
        expect(desk.held(testScope, _close), isNull);
        await desk.load(testScope);
        expect(desk.held(testScope, _close), isNull);
      });
    },
  );
}
