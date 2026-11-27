import 'dart:async';

import 'package:async_redux/async_redux.dart';

import '../app/services.dart';
import '../core/api/api_client.dart' show serverAllowed;
import '../core/json.dart';
import '../core/models/models.dart';
import '../core/realtime/event_stream.dart';
import '../core/realtime/lonora_event.dart';
import 'actions/base.dart';
import 'actions/session_actions.dart';
import 'actions/shell_actions.dart';
import 'actions/thread_actions.dart';
import 'app_state.dart';
import 'reply_stream.dart';

late RealtimeController realtime;

/// Owns the owner event feed for the signed-in session and turns events into actions.
/// Feature modules can listen to [events] for kinds they own (e.g. charts, voice calls).
class RealtimeController {
  RealtimeController(this.store) {
    _stream = EventStream(
      onEvent: (event) async {
        store.dispatch(ApplyEventAction(event));
        _events.add(event);
      },
      onReady: () async {
        store.dispatch(RealtimeReadyAction());
      },
      onRejected: () => unawaited(_checkSession()),
    );
    _stream.status.addListener(
      () => store.dispatch(_ConnectionAction(_stream.status.value)),
    );
  }

  final Store<AppState> store;
  late final EventStream _stream;
  final StreamController<LonoraEvent> _events = StreamController.broadcast();

  Stream<LonoraEvent> get events => _events.stream;
  StreamStatus get status => _stream.status.value;

  /// Opens the feed for [server]. A remote plain-http server is never contacted (the bearer
  /// token would travel in clear): https everywhere, plain http only for local hosts.
  void startFor({required String server}) {
    final token = api.token;
    if (token == null || !serverAllowed(server)) return;
    final wsBase = server.replaceFirst(RegExp('^http'), 'ws');
    _stream.start(Uri.parse('$wsBase/api/ws/events'), token);
  }

  void pause() => _stream.pause();
  void resume() {
    if (store.state.session.signedIn) _stream.resume();
  }

  void stop() => _stream.stop();

  Future<void> _checkSession() async {
    try {
      await api.get('/auth/session');
      resume();
    } catch (_) {
      // The 401 handler signs out; other failures retry on the next foreground/network change.
    }
  }
}

class _ConnectionAction extends AppAction {
  _ConnectionAction(this.connection);
  final StreamStatus connection;
  @override
  AppState? reduce() => connection == state.connection
      ? null
      : state.copyWith(connection: connection);
}

/// After every `ready`: refresh snapshots (shell + every loaded conversation), then flush the
/// outbox. This closes the window between connecting and the first event.
class RealtimeReadyAction extends AppAction {
  @override
  AppState? reduce() {
    dispatch(RefreshShellAction());
    for (final t in state.threads.values) {
      if (t.loaded) dispatch(LoadThreadAction(t.threadId));
    }
    if (state.outbox.any((o) => o.delivery == Delivery.queued)) {
      dispatch(FlushOutboxAction());
    }
    return null;
  }
}

Timer? _shellDebounce;
final Map<String, Timer> _threadDebounce = {};

/// Applies one owner event to the state.
class ApplyEventAction extends AppAction {
  ApplyEventAction(this.event);
  final LonoraEvent event;

  @override
  AppState? reduce() {
    final e = event;
    final kind = e.kind;
    var next = state;

    if (kind == 'message.created' || kind == 'message.updated') {
      final message = Message.fromJson(e.payload);
      final threadId = message.threadId.isNotEmpty
          ? message.threadId
          : (e.threadId ?? '');
      if (threadId.isEmpty) return null;
      final t = next.threads[threadId];
      if (t != null) next = next.withThread(t.mergeMessages([message]));
      if (message.clientNonce != null &&
          next.outbox.any((o) => o.nonce == message.clientNonce)) {
        next = next.copyWith(
          outbox: next.outbox
              .where((o) => o.nonce != message.clientNonce)
              .toList(),
        );
      }
      if (kind == 'message.created') next = _bumpInbox(next, threadId, message);
      _scheduleShell();
      return next;
    }

    if (kind == 'message.reaction_updated') {
      final threadId = asString(e.payload['thread_id']) ?? e.threadId;
      final messageId = asString(e.payload['message_id']);
      final t = threadId == null ? null : next.threads[threadId];
      if (t == null || messageId == null) return null;
      final m = t.messages.where((m) => m.id == messageId).firstOrNull;
      if (m == null) return null;
      return next.withThread(
        t.mergeMessages([
          m.withReactions(
            asJsonList(e.payload['reactions']).map(Reaction.fromJson).toList(),
          ),
        ]),
      );
    }

    if (kind == 'thread.updated') {
      final threadId = asString(e.payload['thread_id']) ?? e.threadId;
      final t = threadId == null ? null : next.threads[threadId];
      if (t?.thread == null) return null;
      return next.withThread(
        t!.copyWith(
          thread: t.thread!.copyWith(
            webSearch: asBool(asJson(e.payload['options'])['web_search']),
          ),
        ),
      );
    }

    if (kind == 'thread.read' || kind == 'thread.prefs_updated') {
      final threadId = asString(e.payload['thread_id']) ?? e.threadId;
      if (threadId == null) return null;
      final index = next.shell.inbox.indexWhere((x) => x.threadId == threadId);
      if (index < 0) {
        _scheduleShell();
        return null;
      }
      final inbox = [...next.shell.inbox];
      inbox[index] = inbox[index].withPrefs(e.payload);
      return next.copyWith(shell: next.shell.copyWith(inbox: inbox));
    }

    if (kind.startsWith('run.')) {
      final runId = e.runId;
      final threadId = e.threadId;
      var t = threadId == null ? null : next.threads[threadId];
      // Run projections ride on queued/leased/recovered events.
      final runJson = asJson(e.payload['run']);
      Run? run = runJson.isNotEmpty ? Run.fromJson(runJson) : null;
      // A transition without a snapshot applies to the run already known, in the open
      // conversation or in the owner-wide list (so the chats list's "Working…" follows it).
      final current =
          run ??
          (runId == null
              ? null
              : t?.runs[runId] ??
                    next.shell.runs.where((r) => r.id == runId).firstOrNull);
      if (current != null) {
        final status = switch (kind) {
          'run.running' => 'running',
          'run.waiting_input' => 'waiting_input',
          'run.completed' => 'completed',
          'run.failed' => 'failed',
          'run.cancelled' => 'cancelled',
          _ => current.status,
        };
        run = status == current.status
            ? current
            : current.withStatus(
                status,
                extra: kind == 'run.failed'
                    ? {
                        'error_code': e.payload['code'],
                        'failure': e.payload['failure'],
                      }
                    : null,
              );
      }
      if (t != null && runId != null) {
        final runs = {...t.runs};
        if (run != null) runs[runId] = run;
        final streams = {...t.streams};
        final live = accumulateStream(streams[runId], e);
        if (live != null) streams[runId] = live;
        t = t.copyWith(runs: runs, streams: streams);
        if (live != null && live.gap) _scheduleThread(threadId!);
        next = next.withThread(t);
      }
      // Owner-wide run list (tasks view / avatar activity).
      if (run != null) {
        final list = [...next.shell.runs];
        final i = list.indexWhere((r) => r.id == run!.id);
        if (i >= 0) {
          list[i] = run;
        } else {
          list.insert(0, run);
        }
        next = next.copyWith(shell: next.shell.copyWith(runs: list));
      }
      if (!e.isStreamChunk && threadId != null && kind != 'run.delta') {
        _scheduleThread(threadId, refetchRunsOnly: true);
      }
      return next;
    }

    if (kind.startsWith('tool.')) {
      final threadId = e.threadId;
      final runId = e.runId;
      final t = threadId == null ? null : next.threads[threadId];
      if (t == null || runId == null) return null;
      return next.withThread(
        t.copyWith(
          toolActivity: {
            ...t.toolActivity,
            runId: {...e.payload, 'state': kind.substring(5)},
          },
        ),
      );
    }

    if (kind == 'agent.updated') {
      final agent = Agent.fromJson(e.payload);
      if (agent.id.isEmpty) return null;
      dispatch(UpsertAgentAction(agent));
      return null;
    }

    // Everything else: refetch the affected snapshots (debounced).
    _scheduleShell();
    if (e.threadId != null && next.threads[e.threadId!]?.loaded == true) {
      _scheduleThread(e.threadId!);
    }
    return null;
  }

  AppState _bumpInbox(AppState s, String threadId, Message m) {
    final index = s.shell.inbox.indexWhere((x) => x.threadId == threadId);
    if (index < 0) return s;
    final entry = s.shell.inbox[index];
    final open = s.openThreadId == threadId;
    final raw = {
      ...entry.raw,
      'last_message': {
        'id': m.id,
        'role': m.role,
        'agent_id': m.agentId,
        'content': m.content,
        'preview': m.content.length > 160
            ? m.content.substring(0, 160)
            : m.content,
        'kind': m.attachmentIds.isNotEmpty
            ? 'file'
            : (m.parts.any((p) => p['type'] == 'ui') ? 'card' : 'text'),
        'seq': m.seq,
        'created_at': m.createdAt?.toUtc().toIso8601String(),
        'consumed': m.consumed,
      },
      'last_activity_at': m.createdAt?.toUtc().toIso8601String(),
      'unread_count': m.fromOwner || open
          ? entry.unreadCount
          : entry.unreadCount + 1,
    };
    final inbox = [...s.shell.inbox]..removeAt(index);
    inbox.insert(0, InboxEntry.fromJson(raw));
    return s.copyWith(shell: s.shell.copyWith(inbox: inbox));
  }

  void _scheduleShell() {
    _shellDebounce?.cancel();
    _shellDebounce = Timer(
      const Duration(milliseconds: 600),
      () => dispatch(RefreshShellAction()),
    );
  }

  void _scheduleThread(String threadId, {bool refetchRunsOnly = false}) {
    _threadDebounce[threadId]?.cancel();
    _threadDebounce[threadId] = Timer(const Duration(milliseconds: 150), () {
      _threadDebounce.remove(threadId);
      dispatch(
        refetchRunsOnly
            ? RefreshRunsAction(threadId)
            : LoadThreadAction(threadId),
      );
    });
  }
}

/// Rebases a conversation's runs and previews on the durable snapshot (`GET /runs?thread_id=`).
class RefreshRunsAction extends AppAction {
  RefreshRunsAction(this.threadId);
  final String threadId;

  @override
  Future<AppState?> reduce() async {
    try {
      final runs = asJsonList(
        await apiClient.get('/runs', query: {'thread_id': threadId}),
      ).map(Run.fromJson);
      final t = state.thread(threadId);
      final map = {...t.runs};
      final streams = {...t.streams};
      for (final r in runs) {
        map[r.id] = r;
        final seeded = seedStream(streams[r.id], r);
        if (seeded != null) streams[r.id] = seeded;
      }
      return state.withThread(t.copyWith(runs: map, streams: streams));
    } catch (_) {
      return null;
    }
  }
}

/// Owner session ended by the server (401 anywhere).
void handleUnauthorized(Store<AppState> store) {
  if (store.state.session.signedIn) {
    store.dispatch(SignOutAction(expired: true, revoke: false));
  }
}
