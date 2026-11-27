import 'dart:async';

import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../app_state.dart';
import 'base.dart';

/// Fetches the owner snapshot the shell needs, in parallel, each endpoint tolerated on its
/// own (apps/mobile/lib/shell-data.tsx): agents, groups, inbox, chat lists, thread settings,
/// recent runs, attention. Called after every realtime `ready`, on foreground, on pull-to-refresh.
class RefreshShellAction extends AppAction {
  RefreshShellAction({this.silent = true});
  final bool silent;

  static Future<void>? _inFlight;

  @override
  Future<AppState?> reduce() async {
    if (!signedIn) return null;
    final running = _inFlight;
    if (running != null) {
      await running;
      return null;
    }
    final completer = Completer<void>();
    _inFlight = completer.future;
    try {
      if (!silent) dispatch(_ShellLoading(true));
      final results = await Future.wait<Object?>([
        _get('/agents'),
        _get('/groups'),
        _get('/threads/inbox'),
        _get('/chat-lists'),
        _get('/threads/settings'),
        _get('/runs'),
        _get('/attention'),
        _get('/attention/view'),
      ]);
      if (!signedIn) return null;
      final failures = results.whereType<ApiError>().toList();
      final allNetwork =
          failures.length == results.length &&
          failures.every((e) => e.isNetwork);
      var shell = state.shell;
      Object? ok(int i) => results[i] is ApiError ? null : results[i];
      final agents = ok(0);
      if (agents is List) {
        final list = asJsonList(agents).map(Agent.fromJson).toList();
        shell = shell.copyWith(
          agents: {for (final a in list) a.id: a},
          agentOrder: [for (final a in list) a.id],
        );
      }
      final groups = ok(1);
      if (groups is List) {
        final list = asJsonList(groups).map(Group.fromJson).toList();
        shell = shell.copyWith(groups: {for (final g in list) g.id: g});
      }
      final inbox = ok(2);
      if (inbox is List) {
        shell = shell.copyWith(
          inbox: asJsonList(inbox).map(InboxEntry.fromJson).toList(),
        );
      }
      final lists = ok(3);
      if (lists is List) {
        shell = shell.copyWith(
          chatLists: asJsonList(lists).map(ChatList.fromJson).toList()
            ..sort((a, b) => a.position.compareTo(b.position)),
        );
      }
      final settings = ok(4);
      if (settings is Map) {
        shell = shell.copyWith(keepArchived: asBool(settings['keep_archived']));
      }
      final runs = ok(5);
      if (runs is List) {
        shell = shell.copyWith(
          runs: asJsonList(runs).map(Run.fromJson).toList(),
        );
      }
      final attention = ok(6);
      if (attention is List) {
        shell = shell.copyWith(attention: asJsonList(attention));
      }
      final view = ok(7);
      if (view is List) {
        final rows = asJsonList(view);
        shell = shell.copyWith(
          attentionView: rows,
          attentionUnseen: rows.where((r) => r['seen'] != true).length,
        );
      }
      shell = shell.copyWith(
        loaded: shell.loaded || failures.length < results.length,
        loading: false,
        offline: allNetwork,
        lastError: failures.isEmpty ? null : failures.first.code,
        inboxError: results[2] is ApiError
            ? (results[2] as ApiError).code
            : null,
        refreshedAt: allNetwork ? shell.refreshedAt : DateTime.now(),
      );
      if (!allNetwork) unawaited(_persist(shell));
      return state.copyWith(shell: shell);
    } finally {
      _inFlight = null;
      completer.complete();
    }
  }

  Future<Object?> _get(String path) async {
    try {
      return await apiClient.get(path);
    } on ApiError catch (e) {
      return e;
    } on SessionRequestCancelled {
      return ApiError.network('cancelled');
    }
  }

  Future<void> _persist(ShellState shell) async {
    final scope = cacheScope;
    if (scope == null) return;
    await localStore.write(scope, 'shell', {
      'agents': [for (final id in shell.agentOrder) shell.agents[id]?.raw],
      'groups': [for (final g in shell.groups.values) g.raw],
      'inbox': [for (final e in shell.inbox) e.raw],
      'chat_lists': [for (final l in shell.chatLists) l.raw],
      'keep_archived': shell.keepArchived,
    });
  }
}

class _ShellLoading extends AppAction {
  _ShellLoading(this.loading);
  final bool loading;
  @override
  AppState reduce() =>
      state.copyWith(shell: state.shell.copyWith(loading: loading));
}

/// Shows the last snapshot of this owner immediately at launch (until the network answers).
class RestoreShellCacheAction extends AppAction {
  @override
  Future<AppState?> reduce() async {
    final scope = cacheScope;
    if (scope == null || state.shell.loaded) return null;
    final cached = asJson(await localStore.read(scope, 'shell'));
    final outboxRaw = await localStore.read(scope, 'outbox');
    final outbox = asJsonList(outboxRaw)
        .map(OutgoingMessage.fromJson)
        .whereType<OutgoingMessage>()
        .toList();
    if (cached.isEmpty && outbox.isEmpty) return null;
    if (state.shell.loaded) {
      return state.copyWith(outbox: outbox.isEmpty ? state.outbox : outbox);
    }
    final agents = asJsonList(cached['agents']).map(Agent.fromJson).toList();
    return state.copyWith(
      outbox: outbox,
      shell: state.shell.copyWith(
        agents: {for (final a in agents) a.id: a},
        agentOrder: [for (final a in agents) a.id],
        groups: {
          for (final g in asJsonList(cached['groups']).map(Group.fromJson))
            g.id: g,
        },
        inbox: asJsonList(cached['inbox']).map(InboxEntry.fromJson).toList(),
        chatLists: asJsonList(cached['chat_lists'])
            .map(ChatList.fromJson)
            .toList(),
        keepArchived: asBool(cached['keep_archived']),
      ),
    );
  }
}

/// Inbox patches that don't need a round trip.
class PatchInboxAction extends AppAction {
  PatchInboxAction(this.threadId, this.patch);
  final String threadId;
  final InboxEntry Function(InboxEntry entry) patch;

  @override
  AppState? reduce() {
    final index = state.shell.inbox.indexWhere((e) => e.threadId == threadId);
    if (index < 0) return null;
    final inbox = [...state.shell.inbox];
    inbox[index] = patch(inbox[index]);
    return state.copyWith(shell: state.shell.copyWith(inbox: inbox));
  }
}

class UpsertAgentAction extends AppAction {
  UpsertAgentAction(this.agent);
  final Agent agent;

  @override
  AppState reduce() {
    final order = state.shell.agentOrder.contains(agent.id)
        ? state.shell.agentOrder
        : [...state.shell.agentOrder, agent.id];
    return state.copyWith(
      shell: state.shell.copyWith(
        agents: {...state.shell.agents, agent.id: agent},
        agentOrder: order,
      ),
    );
  }
}
