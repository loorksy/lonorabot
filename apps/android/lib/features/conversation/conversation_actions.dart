// Conversation-only actions. Writes record the server's refusal in [errorCode] instead of
// throwing, so a screen can show `context.l10n.errorText(code)` after `dispatchAndWait`.
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';

/// Side-read key of the conversation's files (`GET /artifacts?thread_id=`).
const artifactsSideKey = 'artifacts';

abstract class ConversationWriteAction extends AppAction {
  /// The API error code when the server (or the network) refused; null on success.
  String? errorCode;

  /// The server's Retry-After, when it gave one.
  Duration? retryAfter;

  void fail(ApiError e) {
    errorCode = e.code;
    retryAfter = e.retryAfter;
  }
}

/// The conversation's files (attachments and agent files), for inline images and file cards.
class LoadThreadArtifactsAction extends AppAction {
  LoadThreadArtifactsAction(this.threadId);
  final String threadId;

  @override
  Future<AppState?> reduce() async {
    if (!signedIn) return null;
    try {
      final rows = asJsonList(
        await apiClient.get('/artifacts', query: {'thread_id': threadId}),
      );
      final t = state.thread(threadId);
      return state.withThread(
        t.copyWith(side: {...t.side, artifactsSideKey: rows}),
      );
    } on ApiError {
      return null;
    } on SessionRequestCancelled {
      return null;
    }
  }
}

/// A file this device just uploaded joins the conversation's files at once.
class AddThreadArtifactAction extends AppAction {
  AddThreadArtifactAction(this.threadId, this.artifact);
  final String threadId;
  final Json artifact;

  @override
  AppState? reduce() {
    final id = asString(artifact['id']);
    if (id == null) return null;
    final t = state.thread(threadId);
    final rows = asJsonList(t.side[artifactsSideKey]);
    if (rows.any((r) => r['id'] == id)) return null;
    return state.withThread(
      t.copyWith(
        side: {
          ...t.side,
          artifactsSideKey: [artifact, ...rows],
        },
      ),
    );
  }
}

/// `POST /runs/{id}/cancel|resume|retry` for one run.
class ConversationRunControlAction extends ConversationWriteAction {
  ConversationRunControlAction(this.runId, this.control);
  final String runId;

  /// cancel | resume | retry
  final String control;

  @override
  Future<AppState?> reduce() async {
    try {
      final data = asJson(await apiClient.post('/runs/$runId/$control', {}));
      if (data.isEmpty) return null;
      final run = Run.fromJson(data);
      final t = state.thread(run.threadId);
      return state.withThread(t.copyWith(runs: {...t.runs, run.id: run}));
    } on ApiError catch (e) {
      fail(e);
      return null;
    } on SessionRequestCancelled {
      return null;
    }
  }
}

/// The composer's Stop: cancels every cancellable run of the conversation (a queued card
/// submit included), as Lonora's clients do.
class StopConversationRunsAction extends ConversationWriteAction {
  StopConversationRunsAction(this.runIds);
  final List<String> runIds;

  @override
  Future<AppState?> reduce() async {
    for (final id in runIds) {
      final action = ConversationRunControlAction(id, 'cancel');
      await dispatchAndWait(action);
      errorCode ??= action.errorCode;
    }
    return null;
  }
}

/// «تحويل إلى مهمة»: `POST /tasks?agent_id=&thread_id=` with the message as the task.
class CreateTaskFromMessageAction extends ConversationWriteAction {
  CreateTaskFromMessageAction({
    required this.threadId,
    required this.agentId,
    required this.message,
  });
  final String threadId;
  final String agentId;
  final Message message;

  @override
  Future<AppState?> reduce() async {
    final content = message.content;
    try {
      await apiClient.post(
        '/tasks?agent_id=${Uri.encodeQueryComponent(agentId)}'
        '&thread_id=${Uri.encodeQueryComponent(threadId)}',
        {
          'title': content.length > 160 ? content.substring(0, 160) : content,
          'description': content,
        },
      );
    } on ApiError catch (e) {
      fail(e);
    } on SessionRequestCancelled {
      // Signed out meanwhile: nothing to report.
    }
    return null;
  }
}

/// The owner's quick reaction (`PUT …/messages/{id}/reactions/{emoji}`, `DELETE …/reactions`
/// to remove it), shown at once. A refusal puts the message's reactions back, unless a newer
/// toggle of the same message followed (that one owns the chips), and records [errorCode], as
/// apps/mobile does (`reactionTurns`).
class ConversationReactionAction extends ConversationWriteAction {
  ConversationReactionAction({
    required this.threadId,
    required this.messageId,
    this.emoji,
  });
  final String threadId;
  final String messageId;

  /// null removes the owner's reaction.
  final String? emoji;

  static final Map<String, int> _turns = {};

  Message? _message(AppState s) =>
      s.thread(threadId).messages.where((m) => m.id == messageId).firstOrNull;

  @override
  Future<AppState?> reduce() async {
    final before = _message(state);
    if (before == null) return null;
    final key = '$threadId/$messageId';
    final turn = (_turns[key] ?? 0) + 1;
    _turns[key] = turn;
    dispatch(
      _MergeMessageAction(
        threadId,
        before.withReactions([
          ...before.reactions.where((r) => r.reactor != 'owner'),
          if (emoji != null)
            Reaction(
              reactor: 'owner',
              emoji: emoji!,
              createdAt: DateTime.now(),
            ),
        ]),
      ),
    );
    List<Reaction> reactions;
    try {
      final path = '/threads/$threadId/messages/$messageId/reactions';
      final data = asJson(
        emoji == null
            ? await apiClient.delete(path)
            : await apiClient.put('$path/${Uri.encodeComponent(emoji!)}'),
      );
      reactions = asJsonList(data['reactions']).map(Reaction.fromJson).toList();
    } on ApiError catch (e) {
      fail(e);
      reactions = before.reactions;
    } on SessionRequestCancelled {
      return null;
    }
    if (_turns[key] != turn) return null;
    final latest = _message(state);
    if (latest == null) return null;
    return state.withThread(
      state.thread(threadId).mergeMessages([latest.withReactions(reactions)]),
    );
  }
}

class _MergeMessageAction extends AppAction {
  _MergeMessageAction(this.threadId, this.message);
  final String threadId;
  final Message message;

  @override
  AppState reduce() =>
      state.withThread(state.thread(threadId).mergeMessages([message]));
}

/// The conversation's web search (`PUT /threads/{id}/options`).
class ToggleWebSearchAction extends ConversationWriteAction {
  ToggleWebSearchAction(this.threadId, this.enabled);
  final String threadId;
  final bool enabled;

  @override
  Future<AppState?> reduce() async {
    try {
      final thread = Thread.fromJson(
        asJson(
          await apiClient.put('/threads/$threadId/options', {
            'web_search': enabled,
          }),
        ),
      );
      return state.withThread(state.thread(threadId).copyWith(thread: thread));
    } on ApiError catch (e) {
      fail(e);
      return null;
    } on SessionRequestCancelled {
      return null;
    }
  }
}
