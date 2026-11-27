import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../state/actions/base.dart';
import '../../state/actions/thread_actions.dart';
import '../../state/app_state.dart';

/// A lonora-ui v2 card send (docs/genui.md §7, apps/mobile/app/thread.tsx `submit`): posts only
/// `MessageCreate.ui_submit {source_message_id, part, path, values}` with a fresh
/// `client_nonce`, at once and never through the offline outbox (a retry is the owner's tap).
/// The server writes the owner's bubble and queues the card's own Run; both merge into the
/// conversation. Throws the [ApiError] for the card to show.
class SubmitCardAction extends AppAction {
  SubmitCardAction({
    required this.threadId,
    required this.messageId,
    required this.part,
    required this.path,
    required this.values,
    String? nonce,
  }) : nonce = nonce ?? newNonce();

  final String threadId;
  final String messageId;
  final int part;
  final String path;
  final Json values;
  final String nonce;

  Json get body => {
    'content': '',
    'client_nonce': nonce,
    'ui_submit': {
      'source_message_id': messageId,
      'part': part,
      'path': path,
      'values': values,
    },
  };

  @override
  Future<AppState?> reduce() async {
    final ack = asJson(
      await apiClient.post('/threads/$threadId/messages', body),
    );
    final message = Message.fromJson(asJson(ack['message']));
    final runs = asJsonList(ack['runs']).map(Run.fromJson).toList();
    var t = state.thread(threadId);
    if (message.id.isNotEmpty) t = t.mergeMessages([message]);
    final merged = {...t.runs};
    for (final run in runs) {
      // A Run event that arrived before this response is newer: keep it.
      final prior = merged[run.id];
      if (prior == null ||
          prior.updatedAt == null ||
          run.updatedAt == null ||
          !run.updatedAt!.isBefore(prior.updatedAt!)) {
        merged[run.id] = run;
      }
    }
    return state.withThread(t.copyWith(runs: merged));
  }
}

/// «تعديل» on a locked card part (`POST /threads/{t}/messages/{m}/ui-state/{part}/unlock`),
/// then reads that one message again for its new card state.
class UnlockCardAction extends AppAction {
  UnlockCardAction({
    required this.threadId,
    required this.message,
    required this.part,
  });

  final String threadId;
  final Message message;
  final int part;

  @override
  Future<AppState?> reduce() async {
    await apiClient.post(
      '/threads/$threadId/messages/${message.id}/ui-state/$part/unlock',
      const <String, Object?>{},
    );
    try {
      final rows = asJsonList(
        await apiClient.get(
          '/threads/$threadId/messages',
          query: {'around': message.seq, 'limit': 1},
        ),
      ).map(Message.fromJson).where((m) => m.id == message.id).toList();
      if (rows.isEmpty) return null;
      return state.withThread(state.thread(threadId).mergeMessages(rows));
    } catch (_) {
      // The next snapshot reads it.
      return null;
    }
  }
}
