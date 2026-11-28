import 'package:flutter/foundation.dart';

import '../json.dart';
import 'local_store.dart';

/// One owner order identity kept for one ticket action until its outcome settles (port of
/// apps/web/src/lib/held-operation.ts). [body] is the exact request sent with
/// [operationId]: a retry resends it byte for byte, so the executor answers from its journal
/// instead of sending again.
@immutable
class HeldOperation {
  const HeldOperation({
    required this.operationId,
    required this.body,
    required this.createdAt,
    this.attempts = 0,
    this.answered = 0,
    this.journaled = false,
    this.sendingSince,
    this.unansweredSince,
  });

  static HeldOperation? fromJson(Object? value) {
    final j = asJson(value);
    final id = asString(j['operation_id']);
    final body = asJson(j['body']);
    if (id == null || id.isEmpty || body['operation_id'] != id) return null;
    return HeldOperation(
      operationId: id,
      body: body,
      createdAt: asDate(j['created_at']) ?? DateTime.now(),
      attempts: asInt(j['attempts']) ?? 0,
      answered: asInt(j['answered']) ?? 0,
      journaled: j['journaled'] == true,
      sendingSince: asDate(j['sending_since']),
      unansweredSince: asDate(j['unanswered_since']),
    );
  }

  final String operationId;
  final Json body;
  final DateTime createdAt;

  /// Sends started with this identity (counted before each send).
  final int attempts;

  /// Sends that Lonora answered with a 2xx or 4xx status.
  final int answered;

  /// Some send got the executor's own result: the journal has a row for this identity, so only a
  /// settled answer or journal row releases it (never a 4xx).
  final bool journaled;

  /// When the send under way started; still set when a later process reads it, that send ended
  /// without an answer (the app stopped meanwhile).
  final DateTime? sendingSince;

  /// When the latest send that ended without Lonora's answer started.
  final DateTime? unansweredSince;

  /// Some send with this identity ended without Lonora's answer (offline, timeout, a gateway
  /// that may still execute it, the app stopped meanwhile): it may yet be journaled.
  bool get unansweredAttempt => attempts > answered;

  HeldOperation copyWith({
    int? attempts,
    int? answered,
    bool? journaled,
    DateTime? Function()? sendingSince,
    DateTime? Function()? unansweredSince,
  }) => HeldOperation(
    operationId: operationId,
    body: body,
    createdAt: createdAt,
    attempts: attempts ?? this.attempts,
    answered: answered ?? this.answered,
    journaled: journaled ?? this.journaled,
    sendingSince: sendingSince == null ? this.sendingSince : sendingSince(),
    unansweredSince: unansweredSince == null
        ? this.unansweredSince
        : unansweredSince(),
  );

  Json toJson() => {
    'operation_id': operationId,
    'body': body,
    'created_at': createdAt.toUtc().toIso8601String(),
    'attempts': attempts,
    'answered': answered,
    if (journaled) 'journaled': true,
    if (sendingSince case final at?)
      'sending_since': at.toUtc().toIso8601String(),
    if (unansweredSince case final at?)
      'unanswered_since': at.toUtc().toIso8601String(),
  };
}

/// The owner's held order identities: ONE LocalStore document ([document]) per server and
/// owner, a JSON map keyed by the raw ticket key ("close_position:acc-1:p-7", a modify's
/// "position|stop|target|…" ticket included), so no key is ever folded into a file name.
/// One instance per [LocalStore] ([of]) keeps what it read in memory.
///
/// «مسح ذاكرة التخزين المؤقت» empties the scope and writes this document back from memory
/// (lib/features/me/me_actions.dart), like the outbox. Signing out with revocation deletes the
/// scope and with it this document: the server's journal stays the system of record.
final class HeldOperations {
  HeldOperations._(this._store);

  static final _instances = Expando<HeldOperations>('HeldOperations');

  /// The held identities kept in [store].
  static HeldOperations of(LocalStore store) =>
      _instances[store] ??= HeldOperations._(store);

  static const document = 'held_operations';

  final LocalStore _store;
  final Map<String, Map<String, HeldOperation>> _memory = {};
  final Map<String, Future<Map<String, HeldOperation>>> _loading = {};

  /// Every held identity of [scope], read once.
  Future<Map<String, HeldOperation>> load(String scope) {
    final cached = _memory[scope];
    if (cached != null) return Future.value(cached);
    return _loading[scope] ??= () async {
      final raw = asJson(await _store.read(scope, document));
      final held = <String, HeldOperation>{
        for (final MapEntry(:key, :value) in raw.entries)
          key: ?HeldOperation.fromJson(value),
      };
      _memory[scope] = held;
      _loading.remove(scope);
      return held;
    }();
  }

  /// The identity held for [key], once [load] has read [scope].
  HeldOperation? peek(String scope, String key) => _memory[scope]?[key];

  /// The held identities of [scope] already read ({} before [load]).
  Map<String, HeldOperation> all(String scope) =>
      Map.unmodifiable(_memory[scope] ?? const {});

  /// The identity held for [key], or a new one ([mint] gives its id, [build] its body with
  /// that id) stored before it is returned, so nothing is sent under an identity that is not
  /// kept. With [expect] (a check of the identity the owner reviewed) nothing is minted: null
  /// unless [key] still holds [expect].
  Future<HeldOperation?> hold(
    String scope,
    String key, {
    required String Function() mint,
    required Json Function(String operationId) build,
    String? expect,
  }) async {
    final held = await load(scope);
    final existing = held[key];
    if (expect != null) {
      return existing?.operationId == expect ? existing : null;
    }
    if (existing != null) return existing;
    final id = mint();
    final op = HeldOperation(
      operationId: id,
      body: {...build(id), 'operation_id': id},
      createdAt: DateTime.now(),
    );
    held[key] = op;
    await _persist(scope);
    return op;
  }

  /// Counts a send about to start now (persisted first: a send the app never saw answered stays
  /// unanswered). A send still under way from before ended without an answer.
  Future<HeldOperation?> attempt(String scope, String key) => _update(
    scope,
    key,
    (op) => op.copyWith(
      attempts: op.attempts + 1,
      unansweredSince: () => op.sendingSince ?? op.unansweredSince,
      sendingSince: DateTime.now,
    ),
  );

  /// Counts the send under way as answered by Lonora with a 2xx or 4xx status; [journaled] when
  /// the answer is the executor's result.
  Future<HeldOperation?> answered(
    String scope,
    String key, {
    bool journaled = false,
  }) => _update(
    scope,
    key,
    (op) => op.copyWith(
      answered: op.answered + 1,
      journaled: op.journaled || journaled,
      sendingSince: () => null,
    ),
  );

  /// Ends the send under way without an answer.
  Future<HeldOperation?> unanswered(String scope, String key) => _update(
    scope,
    key,
    (op) => op.copyWith(
      unansweredSince: () => op.sendingSince ?? op.unansweredSince,
      sendingSince: () => null,
    ),
  );

  /// Drops the identity held for [key] when it is still [operationId].
  Future<void> release(String scope, String key, String operationId) async {
    final held = await load(scope);
    if (held[key]?.operationId != operationId) return;
    held.remove(key);
    await _persist(scope);
  }

  /// Writes [scope]'s document from memory (after «مسح ذاكرة التخزين المؤقت» emptied the
  /// scope); nothing when it holds no identity.
  Future<void> persist(String scope) async {
    final held = _memory[scope];
    if (held == null || held.isEmpty) return;
    await _persist(scope);
  }

  /// Forgets what memory holds (sign-out); the document is read again when needed.
  void forget() {
    _memory.clear();
    _loading.clear();
  }

  Future<HeldOperation?> _update(
    String scope,
    String key,
    HeldOperation Function(HeldOperation) change,
  ) async {
    final held = await load(scope);
    final op = held[key];
    if (op == null) return null;
    final next = held[key] = change(op);
    await _persist(scope);
    return next;
  }

  Future<void> _persist(String scope) {
    final held = _memory[scope] ?? const <String, HeldOperation>{};
    return _store.write(
      scope,
      document,
      held.isEmpty
          ? null
          : {
              for (final MapEntry(:key, :value) in held.entries)
                key: value.toJson(),
            },
    );
  }
}
