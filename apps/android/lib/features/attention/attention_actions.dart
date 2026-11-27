// «يحتاج انتباهك» reads and the seen mark (apps/web providers/AttentionProvider.tsx): the view
// rows (`GET /attention/view`) with the items behind them (`GET /attention`, for importance), and
// `POST /attention/seen {notification_id}` when the owner opens an item. Opening decides nothing.
import '../../core/json.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';

int _unseen(List<Json> rows) => rows.where((r) => r['seen'] != true).length;

/// Reads the view and the items into the shell snapshot. When the view cannot be read, [error]
/// says why (the screen shows it) and the snapshot is kept; a failed item read keeps the
/// previous items.
class LoadAttentionAction extends AppAction {
  Object? error;

  @override
  Future<AppState?> reduce() async {
    final List<Object?> results;
    try {
      results = await Future.wait<Object?>([
        apiClient.get('/attention/view'),
        apiClient
            .get('/attention')
            .then<Object?>((v) => v, onError: (_) => null),
      ]);
    } catch (e) {
      error = e;
      return null;
    }
    final rows = asJsonList(results[0]);
    final items = results[1];
    return state.copyWith(
      shell: state.shell.copyWith(
        attentionView: rows,
        attentionUnseen: _unseen(rows),
        attention: items is List ? asJsonList(items) : null,
      ),
    );
  }
}

/// Marks one item seen: an alert then leaves the view, a card or a Task review stays until it
/// is answered (the server decides; the row's dot goes out here at once).
class MarkAttentionSeenAction extends AppAction {
  MarkAttentionSeenAction(this.notificationId);
  final String notificationId;

  /// Why the mark failed (shown as a toast), or null.
  Object? error;

  @override
  Future<AppState?> reduce() async {
    try {
      await apiClient.post('/attention/seen', {
        'notification_id': notificationId,
      });
    } catch (e) {
      error = e;
      return null;
    }
    final rows = [
      for (final r in state.shell.attentionView)
        r['id'] == notificationId ? {...r, 'seen': true} : r,
    ];
    return state.copyWith(
      shell: state.shell.copyWith(
        attentionView: rows,
        attentionUnseen: _unseen(rows),
        attention: [
          for (final i in state.shell.attention)
            if (i['id'] != notificationId) i,
        ],
      ),
    );
  }
}
