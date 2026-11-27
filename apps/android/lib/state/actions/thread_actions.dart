import 'dart:async';

import 'package:uuid/uuid.dart';

import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../app_state.dart';
import '../reply_stream.dart';
import 'base.dart';
import 'shell_actions.dart';

const _uuid = Uuid();
String newNonce() => _uuid.v4().replaceAll('-', '');

const historyPage = 100;

/// Loads a conversation snapshot: thread, newest page (or a page `around` a seq), and runs
/// (seeding live previews from the durable `run.stream`).
class LoadThreadAction extends AppAction {
  LoadThreadAction(this.threadId, {this.around});
  final String threadId;
  final int? around;

  @override
  Future<AppState?> reduce() async {
    if (!signedIn) return null;
    dispatch(
      _ThreadPatch(
        threadId,
        (t) => t.copyWith(loading: true, error: null, focusSeq: around),
      ),
    );
    try {
      final results = await Future.wait<Object?>([
        apiClient.get('/threads/$threadId'),
        apiClient.get(
          '/threads/$threadId/messages',
          query: {'limit': historyPage, 'around': ?around},
        ),
        apiClient
            .get('/runs', query: {'thread_id': threadId})
            .catchError((Object _) => const <Object?>[]),
      ]);
      final thread = Thread.fromJson(asJson(results[0]));
      final page = asJsonList(results[1]).map(Message.fromJson).toList();
      final runs = asJsonList(results[2]).map(Run.fromJson).toList();
      var t = state.thread(threadId);
      // A fresh newest page replaces the cached window unless older pages were already loaded.
      if (around == null &&
          t.messages.isNotEmpty &&
          page.isNotEmpty &&
          t.messages.first.seq >= page.first.seq) {
        t = t.copyWith(messages: const []);
      }
      t = t.mergeMessages(page);
      final runMap = {...t.runs};
      final streams = {...t.streams};
      for (final r in runs) {
        runMap[r.id] = r;
        final seeded = seedStream(streams[r.id], r);
        if (seeded != null) streams[r.id] = seeded;
      }
      t = t.copyWith(
        thread: thread,
        runs: runMap,
        streams: streams,
        loaded: true,
        loading: false,
        hasOlder: around != null ? true : page.length >= historyPage,
      );
      unawaited(_persist(t));
      return state.withThread(t);
    } on ApiError catch (e) {
      return state.withThread(
        state.thread(threadId).copyWith(loading: false, error: e.code),
      );
    } on SessionRequestCancelled {
      return null;
    }
  }

  Future<void> _persist(ThreadState t) async {
    final scope = cacheScope;
    if (scope == null) return;
    final tail = t.messages.length > 60
        ? t.messages.sublist(t.messages.length - 60)
        : t.messages;
    await localStore.write(scope, 'thread_${t.threadId}', {
      'thread': t.thread?.raw,
      'messages': [for (final m in tail) m.raw],
    });
  }
}

/// Shows the cached tail of a conversation before the network answers.
class RestoreThreadCacheAction extends AppAction {
  RestoreThreadCacheAction(this.threadId);
  final String threadId;

  @override
  Future<AppState?> reduce() async {
    final scope = cacheScope;
    if (scope == null || state.thread(threadId).loaded) return null;
    final cached = asJson(await localStore.read(scope, 'thread_$threadId'));
    if (cached.isEmpty || state.thread(threadId).loaded) return null;
    final t = state.thread(threadId);
    final threadJson = asJson(cached['thread']);
    return state.withThread(
      t
          .copyWith(
            thread: threadJson.isEmpty ? t.thread : Thread.fromJson(threadJson),
          )
          .mergeMessages(asJsonList(cached['messages']).map(Message.fromJson)),
    );
  }
}

class LoadOlderAction extends AppAction {
  LoadOlderAction(this.threadId);
  final String threadId;

  /// Why the page did not arrive (the API's code). Null when it arrived, when the session
  /// ended, and when nothing was asked for: a page already loading, no older history, or no
  /// messages yet. Null alone therefore does not mean a page arrived.
  String? errorCode;

  @override
  Future<AppState?> reduce() async {
    final t = state.thread(threadId);
    if (t.loadingOlder || !t.hasOlder || t.messages.isEmpty) return null;
    dispatch(_ThreadPatch(threadId, (t) => t.copyWith(loadingOlder: true)));
    try {
      final page = asJsonList(
        await apiClient.get(
          '/threads/$threadId/messages',
          query: {'limit': historyPage, 'before': t.messages.first.seq},
        ),
      ).map(Message.fromJson).toList();
      return state.withThread(
        state
            .thread(threadId)
            .mergeMessages(page)
            .copyWith(
              loadingOlder: false,
              hasOlder: page.length >= historyPage,
            ),
      );
    } catch (e) {
      if (e is! SessionRequestCancelled) {
        errorCode = e is ApiError ? e.code : 'request_failed';
      }
      return state.withThread(
        state.thread(threadId).copyWith(loadingOlder: false),
      );
    }
  }
}

/// Loads the newest page after landing `around` a seq (closes the gap to live).
class LoadNewestAction extends AppAction {
  LoadNewestAction(this.threadId);
  final String threadId;

  @override
  Future<AppState?> reduce() async {
    try {
      final page = asJsonList(
        await apiClient.get(
          '/threads/$threadId/messages',
          query: {'limit': historyPage},
        ),
      ).map(Message.fromJson);
      return state.withThread(
        state.thread(threadId).mergeMessages(page).copyWith(focusSeq: null),
      );
    } catch (_) {
      return null;
    }
  }
}

class SetOpenThreadAction extends AppAction {
  SetOpenThreadAction(this.threadId);
  final String? threadId;
  @override
  AppState reduce() => state.copyWith(openThreadId: threadId);
}

/// Sends an owner message (`POST /threads/{id}/messages`, 202). The optimistic bubble is the
/// outbox entry keyed by `client_nonce`; a retry reuses the same nonce, so the server dedupes.
class SendMessageAction extends AppAction {
  SendMessageAction(this.threadId, Json body, {String? nonce})
    : nonce = nonce ?? asString(body['client_nonce']) ?? newNonce(),
      body = {...body};
  final String threadId;
  final String nonce;
  final Json body;

  @override
  Future<AppState?> reduce() async {
    body['client_nonce'] = nonce;
    final existing = state.outbox.where((o) => o.nonce == nonce).firstOrNull;
    final entry =
        (existing ??
                OutgoingMessage(
                  nonce: nonce,
                  threadId: threadId,
                  body: body,
                  delivery: Delivery.sending,
                  createdAt: DateTime.now(),
                ))
            .copyWith(delivery: Delivery.sending, errorCode: null);
    dispatch(_OutboxUpsert(entry));
    try {
      final ack = asJson(
        await apiClient.post('/threads/$threadId/messages', body),
      );
      final message = Message.fromJson(asJson(ack['message']));
      final runs = asJsonList(ack['runs']).map(Run.fromJson).toList();
      var t = state.thread(threadId).mergeMessages([message]);
      t = t.copyWith(runs: {...t.runs, for (final r in runs) r.id: r});
      final outbox = state.outbox.where((o) => o.nonce != nonce).toList();
      _persistOutbox(outbox);
      dispatch(
        PatchInboxAction(
          threadId,
          (e) => e.withPrefs({'last_read_seq': message.seq}),
        ),
      );
      return state.withThread(t).copyWith(outbox: outbox);
    } on SessionRequestCancelled {
      return null;
    } on ApiError catch (e) {
      final waits = !e.serverAnswered && entry.isPlain;
      final updated = entry.copyWith(
        delivery: waits ? Delivery.queued : Delivery.failed,
        errorCode: e.code,
      );
      final outbox = [
        for (final o in state.outbox) o.nonce == nonce ? updated : o,
      ];
      _persistOutbox(outbox);
      return state.copyWith(outbox: outbox);
    }
  }

  void _persistOutbox(List<OutgoingMessage> outbox) {
    final scope = cacheScope;
    if (scope == null) return;
    unawaited(
      localStore.write(scope, 'outbox', [for (final o in outbox) o.toJson()]),
    );
  }
}

class _OutboxUpsert extends AppAction {
  _OutboxUpsert(this.entry);
  final OutgoingMessage entry;
  @override
  AppState reduce() {
    final exists = state.outbox.any((o) => o.nonce == entry.nonce);
    return state.copyWith(
      outbox: exists
          ? [for (final o in state.outbox) o.nonce == entry.nonce ? entry : o]
          : [...state.outbox, entry],
    );
  }
}

class RetryOutgoingAction extends AppAction {
  RetryOutgoingAction(this.nonce);
  final String nonce;
  @override
  Future<AppState?> reduce() async {
    final entry = state.outbox.where((o) => o.nonce == nonce).firstOrNull;
    if (entry == null) return null;
    await dispatchAndWait(
      SendMessageAction(entry.threadId, entry.body, nonce: entry.nonce),
    );
    return null;
  }
}

class DiscardOutgoingAction extends AppAction {
  DiscardOutgoingAction(this.nonce);
  final String nonce;
  @override
  AppState reduce() {
    final outbox = state.outbox.where((o) => o.nonce != nonce).toList();
    final scope = cacheScope;
    if (scope != null) {
      unawaited(
        localStore.write(scope, 'outbox', [for (final o in outbox) o.toJson()]),
      );
    }
    return state.copyWith(outbox: outbox);
  }
}

/// Sends every message that waited for the network, oldest first. Returns how many went out.
class FlushOutboxAction extends AppAction {
  static bool _running = false;
  int sent = 0;

  @override
  Future<AppState?> reduce() async {
    if (_running || !signedIn) return null;
    _running = true;
    try {
      final queued =
          state.outbox.where((o) => o.delivery == Delivery.queued).toList()
            ..sort((a, b) => a.createdAt.compareTo(b.createdAt));
      for (final entry in queued) {
        await dispatchAndWait(
          SendMessageAction(entry.threadId, entry.body, nonce: entry.nonce),
        );
        if (!state.outbox.any((o) => o.nonce == entry.nonce)) {
          sent++;
        } else if (state.outbox
                .firstWhere((o) => o.nonce == entry.nonce)
                .delivery ==
            Delivery.queued) {
          break; // still offline
        }
      }
    } finally {
      _running = false;
    }
    return null;
  }
}

/// `POST /threads/{id}/read {seq}` (max-wins).
class MarkReadAction extends AppAction {
  MarkReadAction(this.threadId, this.seq);
  final String threadId;
  final int seq;

  @override
  Future<AppState?> reduce() async {
    final entry = state.shell.entryFor(threadId);
    if (entry != null &&
        entry.lastReadSeq >= seq &&
        entry.unreadCount == 0 &&
        !entry.markedUnread) {
      return null;
    }
    dispatch(
      PatchInboxAction(
        threadId,
        (e) => e.withPrefs({'last_read_seq': seq, 'marked_unread': false}),
      ),
    );
    try {
      final prefs = asJson(
        await apiClient.post('/threads/$threadId/read', {'seq': seq}),
      );
      if (prefs.isNotEmpty) {
        dispatch(PatchInboxAction(threadId, (e) => e.withPrefs(prefs)));
      }
    } catch (_) {}
    return null;
  }
}

/// Get-or-create the agent's direct conversation (`POST /agents/{id}/conversation`).
class EnsureAgentThreadAction extends AppAction {
  EnsureAgentThreadAction(this.agentId);
  final String agentId;
  String? threadId;

  @override
  Future<AppState?> reduce() async {
    for (final e in state.shell.inbox) {
      if (e.agentId == agentId && e.groupId == null) {
        threadId = e.threadId;
        return null;
      }
    }
    final thread = Thread.fromJson(
      asJson(await apiClient.post('/agents/$agentId/conversation')),
    );
    threadId = thread.id;
    return state.withThread(state.thread(thread.id).copyWith(thread: thread));
  }
}

/// Stores a side read (owner actions, approvals, receipts, peer messages, artifacts...).
class SetThreadSideAction extends AppAction {
  SetThreadSideAction(this.threadId, this.key, this.value);
  final String threadId;
  final String key;
  final Object? value;
  @override
  AppState reduce() {
    final t = state.thread(threadId);
    return state.withThread(t.copyWith(side: {...t.side, key: value}));
  }
}

class _ThreadPatch extends AppAction {
  _ThreadPatch(this.threadId, this.patch);
  final String threadId;
  final ThreadState Function(ThreadState) patch;
  @override
  AppState reduce() => state.withThread(patch(state.thread(threadId)));
}

/// Public variant for features that need a local patch.
class PatchThreadAction extends _ThreadPatch {
  PatchThreadAction(super.threadId, super.patch);
}
