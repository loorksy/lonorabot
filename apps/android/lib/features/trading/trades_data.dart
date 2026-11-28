// The owner's own orders: the ONE place `POST /trading/execute` is called (ARCHITECTURE.md
// «Safety»). [OrderDesk.run] is reached only from the owner's tap on a confirmation sheet
// (lib/features/trading/trade_sheets.dart); never from agents, cards, generated UI, chat
// commands, voice, notifications, deep links, background work, automatic retries or tests (tests
// use the fake API).
//
// Each ticket action keeps one operation_id (UUID v4) with its exact body until its outcome
// settles (port of apps/web components/trading/useTicketAction.ts and lib/held-operation.ts):
// a double tap, a retry after a timeout, a reopened screen or a restarted app sends the same
// identity and the same bytes, which the executor answers from its journal instead of sending
// again. The in-flight guard and the results live here, app-wide, not in a screen's state: an
// execute can take 75 s, longer than the owner stays on a screen.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/storage/held_operations.dart';
import '../../core/storage/local_store.dart';
import '../../state/actions/session_actions.dart' show signOutHooks;
import '../../state/app_state.dart';
import '../market/market_data.dart';
import 'trade_rules.dart';

/// How long an order waits for its answer: the broker relay holds it up to 60 s
/// (lonora_adapters.brokers.relay), and a request abandoned earlier can itself leave an
/// interrupted or uncertain operation behind.
const executeTimeout = Duration(seconds: 75);

/// The held identities' scope of the signed-in owner (the outbox's), or null.
String? orderScope(SessionState session) {
  final owner = session.owner, server = session.server;
  if (owner == null || server == null) return null;
  return LocalStore.scope(server, owner.id);
}

/// What an executor answer or a journal row says about one operation.
@immutable
class TicketOutcome {
  const TicketOutcome({
    required this.status,
    this.details = const {},
    this.code,
    this.brokerId,
  });

  /// An executor answer (`TradeResult`); null when it is not one for [operationId] (a 200
  /// without a known status settles nothing: the identity stays held).
  static TicketOutcome? fromResult(Object? answer, {String? operationId}) {
    final j = asJson(answer);
    final status = asString(j['status']);
    if (status == null || !operationStatuses.contains(status)) return null;
    final id = asString(j['operation_id']);
    if (operationId != null && id != null && id != operationId) return null;
    return TicketOutcome(
      status: status,
      details: asJson(j['details']),
      code: asString(j['code']),
      brokerId: asString(j['broker_id']),
    );
  }

  factory TicketOutcome.fromJournal(JournalEntry e) => TicketOutcome(
    status: e.status,
    details: e.details,
    code: e.code,
    brokerId: e.brokerId,
  );

  final String status;
  final Json details;
  final String? code;
  final String? brokerId;

  bool get settled => operationSettled(status);
}

/// A 200 whose body is not an executor result: nothing is known about the operation.
class TradeAnswerUnknown implements Exception {
  const TradeAnswerUnknown();
}

/// The one `POST /trading/execute`: the held body, as stored.
Future<Object?> _execute(Json body) =>
    api.postWithin('/trading/execute', body, executeTimeout);

/// The owner's order desk: held identities, the in-flight guard, and the last answer and error
/// of each ticket action, shared by every screen that shows them.
class OrderDesk extends ChangeNotifier {
  OrderDesk._();

  static final OrderDesk instance = OrderDesk._();

  /// Mints an operation id (UUID v4).
  static String mint() => const Uuid().v4();

  final _busy = <String>{};
  final _outcomes = <String, TicketOutcome>{};
  final _errors = <String, Object>{};
  final _last = <String, String>{};
  bool _hooked = false;

  HeldOperations get _held => HeldOperations.of(localStore);

  static String _k(String scope, String key) => '$scope\n$key';

  void _hook() {
    if (_hooked) return;
    _hooked = true;
    // Owner-scoped memory goes with the session; an explicit sign-out also deletes the
    // scope's documents, this one included (session_actions `SignOutAction`).
    signOutHooks.add(() async => forget());
  }

  /// Reads [scope]'s held identities (once), then tells the listeners.
  Future<void> load(String scope) async {
    _hook();
    await _held.load(scope);
    notifyListeners();
  }

  /// The identity held for [key] (after [load]).
  HeldOperation? held(String scope, String key) => _held.peek(scope, key);

  /// An order on [key] is being sent now.
  bool busy(String scope, String key) => _busy.contains(_k(scope, key));

  /// Why the last send on [key] got no settled answer (an [ApiError], [TradeAnswerUnknown]).
  Object? error(String scope, String key) => _errors[_k(scope, key)];

  /// The ticket key of the last action the owner took on [card] (a position) this session.
  String? lastOn(String scope, String card) => _last[_k(scope, card)];

  /// The outcome of [key]: its held identity's journal row when the journal has it, else the
  /// last answer this session (useTicketAction.ts `outcome`).
  TicketOutcome? outcome(
    String scope,
    String key,
    List<JournalEntry>? journal,
  ) {
    final op = _held.peek(scope, key);
    if (op != null && journal != null) {
      for (final e in journal) {
        if (e.operationId == op.operationId) {
          return TicketOutcome.fromJournal(e);
        }
      }
    }
    return _outcomes[_k(scope, key)];
  }

  /// Sends the owner's confirmed order on [key]: the held identity's stored body, or a new
  /// identity with [build]'s body, stored before anything is sent. A tap while [key] is in
  /// flight sends nothing (null). [card] records the action as the last one on that card.
  /// [expect] is the held identity the owner's review showed (a check): when [key] no longer
  /// holds it, nothing is sent and no identity is minted (null).
  ///
  /// The identity is released when the answer settles it (confirmed, failed, resolved), or on a
  /// 4xx that proves nothing is journaled under it ([_nothingJournaled]): the form unlocks with
  /// its values kept. Otherwise it stays held, and the next tap asks the executor about the same
  /// operation.
  Future<TicketOutcome?> run({
    required String scope,
    required String key,
    required Json Function() build,
    String? card,
    String? expect,
  }) async {
    _hook();
    final k = _k(scope, key);
    if (!_busy.add(k)) return null;
    if (card != null) _last[_k(scope, card)] = key;
    _errors.remove(k);
    notifyListeners();
    final store = _held;
    try {
      final op = await store.hold(
        scope,
        key,
        mint: mint,
        build: (_) => build(),
        expect: expect,
      );
      if (op == null) return null;
      final sending = await store.attempt(scope, key);
      final started = sending?.sendingSince ?? DateTime.now();
      final Object? answer;
      try {
        answer = await _execute(op.body);
      } on ApiError catch (e) {
        _errors[k] = e;
        if (_definitive(e)) {
          final after = await store.answered(scope, key);
          if (after != null && _nothingJournaled(after, e, started)) {
            await store.release(scope, key, op.operationId);
          }
        } else {
          await store.unanswered(scope, key);
        }
        return null;
      }
      final outcome = TicketOutcome.fromResult(
        answer,
        operationId: op.operationId,
      );
      if (outcome == null) {
        _errors[k] = const TradeAnswerUnknown();
        await store.unanswered(scope, key);
        return null;
      }
      await store.answered(scope, key, journaled: true);
      _outcomes[k] = outcome;
      if (outcome.settled) await store.release(scope, key, op.operationId);
      return outcome;
    } on SessionRequestCancelled {
      // The session changed mid-send: counted, never answered, so it stays held (nothing is
      // written: sign-out may be deleting the scope).
      return null;
    } catch (e) {
      _errors[k] = e;
      return null;
    } finally {
      _busy.remove(k);
      notifyListeners();
    }
  }

  /// Lonora answered with a 4xx: it refused this request before journaling anything under it.
  static bool _definitive(ApiError e) {
    final status = e.status;
    return e.serverAnswered && status != null && status >= 400 && status < 500;
  }

  /// How long after a send that got no answer a refusal proves that send journaled nothing: by
  /// then the API has given it up (the relay waits up to 60 s), so a later request with the same
  /// identity is answered from the journal if it was ever reserved.
  static final staleAfter = executeTimeout * 2;

  /// After the 4xx [e] to the send started at [started], whether nothing can be journaled under
  /// [op]: no send got the executor's result; the refusal came after the executor's identity check
  /// (not a session refusal, which comes first, nor a conflict on the identity itself); and every
  /// send without an answer started at least [staleAfter] before this one.
  static bool _nothingJournaled(
    HeldOperation op,
    ApiError e,
    DateTime started,
  ) {
    if (op.journaled || keepHeldCodes.contains(e.code)) return false;
    if (e.status == 401 || e.status == 403) return false;
    if (!op.unansweredAttempt) return true;
    final since = op.unansweredSince;
    return since != null && started.difference(since) >= staleAfter;
  }

  /// Releases the held identities of [accountId] whose journal row settled (useTicketAction.ts
  /// journal effect); the row's outcome stays shown. The journal lists the newest 200 rows
  /// only: an identity whose row fell out of it settles when the owner checks it again (the
  /// executor answers the same identity from its receipt), or when its ticket is gone
  /// ([dropGone]).
  Future<void> settle(
    String scope,
    String accountId,
    List<JournalEntry> journal,
  ) async {
    _hook();
    final held = await _held.load(scope);
    final rows = {for (final e in journal) e.operationId: e};
    var changed = false;
    for (final MapEntry(:key, value: op) in [...held.entries]) {
      if (asStr(op.body['account_id']) != accountId) continue;
      if (_busy.contains(_k(scope, key))) continue;
      final row = rows[op.operationId];
      if (row == null || !operationSettled(row.status)) continue;
      _outcomes[_k(scope, key)] = TicketOutcome.fromJournal(row);
      await _held.release(scope, key, op.operationId);
      changed = true;
    }
    if (changed) notifyListeners();
  }

  /// Releases held close, edit and cancel identities of [accountId] whose position or order
  /// is gone from a fresh [snapshot], unless the journal still shows the operation unsettled:
  /// nothing can be sent on a ticket that no longer exists.
  Future<void> dropGone(
    String scope,
    String accountId,
    AccountSnapshot snapshot,
    List<JournalEntry> journal,
  ) async {
    _hook();
    final held = await _held.load(scope);
    final rows = {for (final e in journal) e.operationId: e};
    final positions = {for (final p in snapshot.positions) p.id};
    final orders = {for (final o in snapshot.orders) o.id};
    var changed = false;
    for (final MapEntry(:key, value: op) in [...held.entries]) {
      final body = op.body;
      if (asStr(body['account_id']) != accountId) continue;
      if (_busy.contains(_k(scope, key))) continue;
      final gone = switch (asStr(body['action'])) {
        'close_position' ||
        'modify_position' => !positions.contains(body['position_id']),
        'cancel_order' => !orders.contains(body['order_id']),
        _ => false,
      };
      if (!gone) continue;
      final row = rows[op.operationId];
      if (row != null && !operationSettled(row.status)) continue;
      await _held.release(scope, key, op.operationId);
      changed = true;
    }
    if (changed) notifyListeners();
  }

  /// Forgets everything held in memory (sign-out).
  void forget() {
    _outcomes.clear();
    _errors.clear();
    _last.clear();
    if (sl.isRegistered<LocalStore>()) _held.forget();
    notifyListeners();
  }

  @visibleForTesting
  void reset() {
    _busy.clear();
    _outcomes.clear();
    _errors.clear();
    _last.clear();
  }
}
