import 'package:flutter/material.dart';

import '../core/json.dart';
import '../core/models/models.dart';
import '../core/realtime/lonora_event.dart';
import 'reply_stream.dart';

enum SessionStatus { unknown, signedOut, signedIn }

@immutable
class SessionState {
  const SessionState({
    this.status = SessionStatus.unknown,
    this.server,
    this.owner,
    this.lastServer,
    this.lastEmail,
    this.expired = false,
    this.pendingSetupToken,
  });

  final SessionStatus status;
  final String? server;
  final Owner? owner;
  final String? lastServer;
  final String? lastEmail;

  /// The last sign-out was the server ending the session (401), not the owner.
  final bool expired;

  /// Setup token from a `lonora://connect` link, held in memory for that server only.
  final ({String server, String token})? pendingSetupToken;

  bool get signedIn =>
      status == SessionStatus.signedIn && owner != null && server != null;

  SessionState copyWith({
    SessionStatus? status,
    Object? server = _k,
    Object? owner = _k,
    Object? lastServer = _k,
    Object? lastEmail = _k,
    bool? expired,
    Object? pendingSetupToken = _k,
  }) => SessionState(
    status: status ?? this.status,
    server: identical(server, _k) ? this.server : server as String?,
    owner: identical(owner, _k) ? this.owner : owner as Owner?,
    lastServer: identical(lastServer, _k)
        ? this.lastServer
        : lastServer as String?,
    lastEmail: identical(lastEmail, _k) ? this.lastEmail : lastEmail as String?,
    expired: expired ?? this.expired,
    pendingSetupToken: identical(pendingSetupToken, _k)
        ? this.pendingSetupToken
        : pendingSetupToken as ({String server, String token})?,
  );
}

const _k = Object();

/// Inbox-level data: everything the chat list, tabs and pickers need. Refreshed as a whole
/// snapshot after every realtime `ready` and on foreground; patched by events in between.
@immutable
class ShellState {
  const ShellState({
    this.agents = const {},
    this.agentOrder = const [],
    this.groups = const {},
    this.inbox = const [],
    this.chatLists = const [],
    this.keepArchived = false,
    this.runs = const [],
    this.attention = const [],
    this.attentionView = const [],
    this.attentionUnseen = 0,
    this.loaded = false,
    this.loading = false,
    this.offline = false,
    this.lastError,
    this.inboxError,
    this.refreshedAt,
  });

  final Map<String, Agent> agents;
  final List<String> agentOrder;
  final Map<String, Group> groups;
  final List<InboxEntry> inbox;
  final List<ChatList> chatLists;
  final bool keepArchived;

  /// Latest 100 runs owner-wide (`GET /runs`), for activity and the tasks view.
  final List<Run> runs;
  final List<Json> attention;
  final List<Json> attentionView;
  final int attentionUnseen;
  final bool loaded;
  final bool loading;
  final bool offline;
  final String? lastError;

  /// Why `GET /threads/inbox` failed in the last refresh; null when it answered.
  final String? inboxError;
  final DateTime? refreshedAt;

  List<Agent> get orderedAgents => [for (final id in agentOrder) ?agents[id]];

  InboxEntry? entryFor(String threadId) {
    for (final e in inbox) {
      if (e.threadId == threadId) return e;
    }
    return null;
  }

  int get unreadTotal => inbox
      .where((e) => !e.archived && !e.muted)
      .fold(
        0,
        (sum, e) =>
            sum +
            e.unreadCount +
            (e.markedUnread && e.unreadCount == 0 ? 1 : 0),
      );

  ShellState copyWith({
    Map<String, Agent>? agents,
    List<String>? agentOrder,
    Map<String, Group>? groups,
    List<InboxEntry>? inbox,
    List<ChatList>? chatLists,
    bool? keepArchived,
    List<Run>? runs,
    List<Json>? attention,
    List<Json>? attentionView,
    int? attentionUnseen,
    bool? loaded,
    bool? loading,
    bool? offline,
    Object? lastError = _k,
    Object? inboxError = _k,
    DateTime? refreshedAt,
  }) => ShellState(
    agents: agents ?? this.agents,
    agentOrder: agentOrder ?? this.agentOrder,
    groups: groups ?? this.groups,
    inbox: inbox ?? this.inbox,
    chatLists: chatLists ?? this.chatLists,
    keepArchived: keepArchived ?? this.keepArchived,
    runs: runs ?? this.runs,
    attention: attention ?? this.attention,
    attentionView: attentionView ?? this.attentionView,
    attentionUnseen: attentionUnseen ?? this.attentionUnseen,
    loaded: loaded ?? this.loaded,
    loading: loading ?? this.loading,
    offline: offline ?? this.offline,
    lastError: identical(lastError, _k) ? this.lastError : lastError as String?,
    inboxError: identical(inboxError, _k)
        ? this.inboxError
        : inboxError as String?,
    refreshedAt: refreshedAt ?? this.refreshedAt,
  );
}

enum Delivery { sending, queued, failed }

/// An owner send that has not been acknowledged by the server yet (Q6 outbox).
@immutable
class OutgoingMessage {
  const OutgoingMessage({
    required this.nonce,
    required this.threadId,
    required this.body,
    required this.delivery,
    required this.createdAt,
    this.errorCode,
  });

  final String nonce;
  final String threadId;

  /// The exact `MessageCreate` body (retries reuse it with the same `client_nonce`).
  final Json body;
  final Delivery delivery;
  final DateTime createdAt;
  final String? errorCode;

  String get content => asStr(body['content']);
  String? get replyTo => asString(body['reply_to']);
  List<String> get attachmentIds => asStringList(body['attachment_ids']);

  /// Only plain owner text waits for the network; answers, edits, card submits and voice notes never do.
  bool get isPlain =>
      body['input_answer'] == null &&
      body['ui_submit'] == null &&
      body['voice'] == null &&
      body['edited_from'] == null;

  OutgoingMessage copyWith({Delivery? delivery, Object? errorCode = _k}) =>
      OutgoingMessage(
        nonce: nonce,
        threadId: threadId,
        body: body,
        delivery: delivery ?? this.delivery,
        createdAt: createdAt,
        errorCode: identical(errorCode, _k)
            ? this.errorCode
            : errorCode as String?,
      );

  Json toJson() => {
    'nonce': nonce,
    'thread_id': threadId,
    'body': body,
    'delivery': delivery.name,
    'created_at': createdAt.toUtc().toIso8601String(),
    'error_code': errorCode,
  };

  static OutgoingMessage? fromJson(Json j) {
    final nonce = asString(j['nonce']);
    final thread = asString(j['thread_id']);
    final body = asJson(j['body']);
    if (nonce == null || thread == null || body.isEmpty) return null;
    final delivery = Delivery.values.firstWhere(
      (d) => d.name == j['delivery'],
      orElse: () => Delivery.failed,
    );
    // A send that was in flight when the app died never got its answer: it waits for the network.
    return OutgoingMessage(
      nonce: nonce,
      threadId: thread,
      body: body,
      delivery: delivery == Delivery.sending ? Delivery.queued : delivery,
      createdAt: asDate(j['created_at']) ?? DateTime.now(),
      errorCode: asString(j['error_code']),
    );
  }
}

/// One conversation as the client knows it: canonical server messages (ascending seq), the
/// thread's runs, live reply previews, tool activity, and side reads used by cards.
@immutable
class ThreadState {
  const ThreadState({
    required this.threadId,
    this.thread,
    this.messages = const [],
    this.runs = const {},
    this.streams = const {},
    this.toolActivity = const {},
    this.hasOlder = false,
    this.loadingOlder = false,
    this.loaded = false,
    this.loading = false,
    this.focusSeq,
    this.side = const {},
    this.error,
    this.version = 0,
  });

  final String threadId;
  final Thread? thread;
  final List<Message> messages;
  final Map<String, Run> runs;
  final Map<String, LiveReplyStream> streams;

  /// Latest tool event per run: `{name, call_id, effect, state}`.
  final Map<String, Json> toolActivity;
  final bool hasOlder;
  final bool loadingOlder;
  final bool loaded;
  final bool loading;

  /// When opened `around` a seq (search/push landing), the seq to centre and flash.
  final int? focusSeq;

  /// Side reads keyed by name (`owner_actions`, `approvals`, `receipts`, `peer_messages`,
  /// `artifacts`, `collaboration`): raw server lists owned by the conversation feature.
  final Map<String, Object?> side;
  final String? error;

  /// Bumped on every change, cheap equality for selectors.
  final int version;

  List<Run> get activeRuns => runs.values.where((r) => !r.isTerminal).toList();

  ThreadState copyWith({
    Object? thread = _k,
    List<Message>? messages,
    Map<String, Run>? runs,
    Map<String, LiveReplyStream>? streams,
    Map<String, Json>? toolActivity,
    bool? hasOlder,
    bool? loadingOlder,
    bool? loaded,
    bool? loading,
    Object? focusSeq = _k,
    Map<String, Object?>? side,
    Object? error = _k,
  }) => ThreadState(
    threadId: threadId,
    thread: identical(thread, _k) ? this.thread : thread as Thread?,
    messages: messages ?? this.messages,
    runs: runs ?? this.runs,
    streams: streams ?? this.streams,
    toolActivity: toolActivity ?? this.toolActivity,
    hasOlder: hasOlder ?? this.hasOlder,
    loadingOlder: loadingOlder ?? this.loadingOlder,
    loaded: loaded ?? this.loaded,
    loading: loading ?? this.loading,
    focusSeq: identical(focusSeq, _k) ? this.focusSeq : focusSeq as int?,
    side: side ?? this.side,
    error: identical(error, _k) ? this.error : error as String?,
    version: version + 1,
  );

  /// Merges server messages by id (keeps ascending seq; replaces existing).
  ThreadState mergeMessages(Iterable<Message> incoming) {
    final byId = {for (final m in messages) m.id: m};
    for (final m in incoming) {
      if (m.threadId == threadId || m.threadId.isEmpty) byId[m.id] = m;
    }
    final list = byId.values.toList()..sort((a, b) => a.seq.compareTo(b.seq));
    return copyWith(messages: list);
  }
}

enum AppThemeMode { system, light, dark }

@immutable
class PrefsState {
  const PrefsState({
    this.themeMode = AppThemeMode.system,
    this.locale = 'ar',
    this.chatPrefs = const ChatPrefs(),
    this.notify = const NotifyPrefs(),
  });

  final AppThemeMode themeMode;
  final String locale;
  final ChatPrefs chatPrefs;
  final NotifyPrefs notify;

  ThemeMode get materialThemeMode => switch (themeMode) {
    AppThemeMode.system => ThemeMode.system,
    AppThemeMode.light => ThemeMode.light,
    AppThemeMode.dark => ThemeMode.dark,
  };

  PrefsState copyWith({
    AppThemeMode? themeMode,
    String? locale,
    ChatPrefs? chatPrefs,
    NotifyPrefs? notify,
  }) => PrefsState(
    themeMode: themeMode ?? this.themeMode,
    locale: locale ?? this.locale,
    chatPrefs: chatPrefs ?? this.chatPrefs,
    notify: notify ?? this.notify,
  );
}

/// This phone's notification preferences (apps/web device-prefs.ts `NotifyPrefs`), surviving
/// sign-out: [inApp] the heads-up banner for replies (urgent items show regardless), [preview]
/// the message's words in banners and notifications.
@immutable
class NotifyPrefs {
  const NotifyPrefs({this.inApp = true, this.preview = true});

  final bool inApp;
  final bool preview;

  NotifyPrefs copyWith({bool? inApp, bool? preview}) =>
      NotifyPrefs(inApp: inApp ?? this.inApp, preview: preview ?? this.preview);
}

/// Per-device conversation preferences (apps/mobile/lib/chat-prefs.ts), surviving sign-out.
@immutable
class ChatPrefs {
  const ChatPrefs({
    this.steps = true,
    this.stepsOpen = false,
    this.detailedStatus = false,
    this.assist = true,
  });

  final bool steps;
  final bool stepsOpen;
  final bool detailedStatus;
  final bool assist;

  ChatPrefs copyWith({
    bool? steps,
    bool? stepsOpen,
    bool? detailedStatus,
    bool? assist,
  }) => ChatPrefs(
    steps: steps ?? this.steps,
    stepsOpen: stepsOpen ?? this.stepsOpen,
    detailedStatus: detailedStatus ?? this.detailedStatus,
    assist: assist ?? this.assist,
  );

  Json toJson() => {
    'steps': steps,
    'steps_open': stepsOpen,
    'detailed_status': detailedStatus,
    'assist': assist,
  };

  static ChatPrefs fromJson(Json j) => ChatPrefs(
    steps: asBool(j['steps'], true),
    stepsOpen: asBool(j['steps_open']),
    detailedStatus: asBool(j['detailed_status']),
    assist: asBool(j['assist'], true),
  );
}

@immutable
class AppState {
  const AppState({
    this.session = const SessionState(),
    this.shell = const ShellState(),
    this.threads = const {},
    this.outbox = const [],
    this.connection = StreamStatus.idle,
    this.prefs = const PrefsState(),
    this.openThreadId,
  });

  final SessionState session;
  final ShellState shell;
  final Map<String, ThreadState> threads;
  final List<OutgoingMessage> outbox;
  final StreamStatus connection;
  final PrefsState prefs;

  /// The conversation currently on screen (heads-up banners skip it; read marks go to it).
  final String? openThreadId;

  ThreadState thread(String id) => threads[id] ?? ThreadState(threadId: id);

  List<OutgoingMessage> outboxFor(String threadId) =>
      outbox.where((o) => o.threadId == threadId).toList(growable: false);

  AppState copyWith({
    SessionState? session,
    ShellState? shell,
    Map<String, ThreadState>? threads,
    List<OutgoingMessage>? outbox,
    StreamStatus? connection,
    PrefsState? prefs,
    Object? openThreadId = _k,
  }) => AppState(
    session: session ?? this.session,
    shell: shell ?? this.shell,
    threads: threads ?? this.threads,
    outbox: outbox ?? this.outbox,
    connection: connection ?? this.connection,
    prefs: prefs ?? this.prefs,
    openThreadId: identical(openThreadId, _k)
        ? this.openThreadId
        : openThreadId as String?,
  );

  AppState withThread(ThreadState value) =>
      copyWith(threads: {...threads, value.threadId: value});

  /// Everything owner-scoped is dropped on sign-out; device prefs stay.
  AppState signedOut({required SessionState session}) =>
      AppState(session: session, prefs: prefs);
}
