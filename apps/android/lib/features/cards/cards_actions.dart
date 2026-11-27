// Server reads and owner taps of the conversation's fixed cards. Every write here is one
// explicit owner tap on that specific card, on the same owner-session route the web and Expo
// cards use (docs/android/analysis/lonora-api-contract.md §11). Nothing here executes a trade,
// starts a Run by itself, or calls a webhook; a decision never happens without a tap.
//
// Secret values and the ChatGPT sign-in address never ride on an action (a refused action
// stays reachable from the store): the card posts them itself and dispatches only the row
// the server answers ([PatchOwnerActionAction]).
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../state/actions/base.dart';
import '../../state/actions/shell_actions.dart' show RefreshShellAction;
import '../../state/app_state.dart';

/// `ThreadState.side` keys the cards read.
abstract final class SideKeys {
  static const ownerActions = 'owner_actions';
  static const approvals = 'approvals';
  static const receipts = 'receipts';
  static const peerMessages = 'peer_messages';

  /// trading connection id (what an approval request's `account_id` names) → broker
  /// provider (`simulation` or a broker), from `GET /trading/connections`; only the
  /// provider is kept.
  static const accounts = 'accounts';
}

List<Json> sideList(ThreadState thread, String key) =>
    asJsonList(thread.side[key]);

/// A newer status never goes back to pending when an older read arrives late
/// (packages/core/src/owner-actions.ts `mergeOwnerAction`).
Json mergeOwnerAction(Json previous, Json next) =>
    previous['status'] != 'pending' && next['status'] == 'pending'
    ? previous
    : next;

const Map<String, int> _approvalRank = {
  'pending': 0,
  'approved': 1,
  'rejected': 1,
  'expired': 1,
  'withdrawn': 1,
  'drifted': 1,
  'completed': 2,
  'cancelled': 2,
};

/// A late read never takes an approval back to an earlier state or drops results it
/// already showed (apps/web/src/components/trading/TradeApprovals.tsx `merge`).
Json mergeApproval(Json previous, Json next) {
  final before = _approvalRank[previous['status']];
  final after = _approvalRank[next['status']];
  if (before != null && after != null && before > after) return previous;
  if (previous['status'] == next['status'] &&
      asJsonList(previous['results']).length >
          asJsonList(next['results']).length) {
    return previous;
  }
  return next;
}

List<Json> mergeSideRows(
  List<Json> previous,
  List<Json> next, {
  String id = 'id',
  Json Function(Json, Json)? merge,
}) {
  if (merge == null) return next;
  final old = {for (final row in previous) asStr(row[id]): row};
  return [
    for (final row in next)
      old[asStr(row[id])] == null ? row : merge(old[asStr(row[id])]!, row),
  ];
}

ThreadState _withRow(
  ThreadState t,
  String key,
  Json row, {
  String id = 'id',
  Json Function(Json, Json)? merge,
}) {
  final rows = sideList(t, key);
  final rowId = asStr(row[id]);
  final replaced = rows.any((r) => asStr(r[id]) == rowId);
  return t.copyWith(
    side: {
      ...t.side,
      key: replaced
          ? [
              for (final r in rows)
                asStr(r[id]) != rowId
                    ? r
                    : merge == null
                    ? row
                    : merge(r, row),
            ]
          : [...rows, row],
    },
  );
}

/// Re-reads the thread's owner action cards (after a refusal that means the card changed
/// elsewhere, `owner_action_card_changed`, or a decided-elsewhere conflict): the server's
/// rows as they are now.
class RereadOwnerActionsAction extends AppAction {
  RereadOwnerActionsAction(this.threadId);
  final String threadId;

  @override
  Future<AppState?> reduce() async {
    try {
      final rows = asJsonList(
        await apiClient.get('/owner-actions', query: {'thread_id': threadId}),
      );
      final t = state.thread(threadId);
      return state.withThread(
        t.copyWith(
          side: {
            ...t.side,
            SideKeys.ownerActions: mergeSideRows(
              sideList(t, SideKeys.ownerActions),
              rows,
              merge: (_, next) => next,
            ),
          },
        ),
      );
    } catch (_) {
      return null;
    }
  }
}

/// The owner action row a card's own route answered (never carries what the owner typed).
class PatchOwnerActionAction extends AppAction {
  PatchOwnerActionAction(this.threadId, this.row);
  final String threadId;
  final Json row;

  @override
  AppState? reduce() => row.isEmpty || asStr(row['id']).isEmpty
      ? null
      : state.withThread(
          _withRow(state.thread(threadId), SideKeys.ownerActions, row),
        );
}

/// One tap on an owner action card's button: `POST /owner-actions/{id}/decision`
/// `{decision: confirm|cancel, outcome?, trading_mode?}` (owner-action-card.tsx:112-140).
/// The updated card replaces the row and is kept in [updated]; a refusal is rethrown for the
/// card to show. A Mandate switch the server applied re-reads the agents (their mode) and
/// the thread's approvals (those it withdrew), as web's `refresh()` does.
class OwnerActionDecisionAction extends AppAction {
  OwnerActionDecisionAction({
    required this.threadId,
    required this.cardId,
    required this.decision,
    this.outcome,
    this.tradingMode,
  });

  final String threadId;
  final String cardId;

  /// confirm or cancel.
  final String decision;
  final String? outcome;
  final String? tradingMode;

  /// The card as the server answered it.
  Json? updated;

  Json get body => {
    'decision': decision,
    'trading_mode': ?tradingMode,
    'outcome': ?outcome,
  };

  @override
  Future<AppState?> reduce() async {
    final row = asJson(
      await apiClient.post('/owner-actions/$cardId/decision', body),
    );
    if (row.isEmpty) return null;
    updated = row;
    if (tradingMode != null && asJson(row['result'])['trading_mode'] != null) {
      dispatch(RefreshShellAction());
      dispatch(ReloadApprovalsAction(threadId));
    }
    return state.withThread(
      _withRow(state.thread(threadId), SideKeys.ownerActions, row),
    );
  }
}

/// Continue with ChatGPT (`POST /owner-actions/{id}/chatgpt/start`): the result's
/// `authorization_url` opens in the browser; [account] names a registered account.
class ChatGptStartAction extends AppAction {
  ChatGptStartAction({required this.cardId, this.newAccount = false});
  final String cardId;
  final bool newAccount;

  String? authorizationUrl;
  String? account;

  @override
  Future<AppState?> reduce() async {
    final started = asJson(
      await apiClient.post(
        '/owner-actions/$cardId/chatgpt/start',
        newAccount ? {'new_account': true} : const <String, Object?>{},
      ),
    );
    authorizationUrl = asString(started['authorization_url']);
    account = asString(started['account']);
    return null;
  }
}

/// «طلب جديد» on an expired Settle card (`POST /owner-actions/{id}/renew`).
class OwnerActionRenewAction extends AppAction {
  OwnerActionRenewAction({required this.threadId, required this.cardId});
  final String threadId;
  final String cardId;

  @override
  Future<AppState?> reduce() async {
    final row = asJson(
      await apiClient.post(
        '/owner-actions/$cardId/renew',
        const <String, Object?>{},
      ),
    );
    if (row.isEmpty) return null;
    return state.withThread(
      _withRow(state.thread(threadId), SideKeys.ownerActions, row),
    );
  }
}

/// Re-reads the thread's approvals (`GET /trading/approvals?thread_id=`), merged so a late
/// read never brings a decided card back to pending. A failed read keeps what was there.
class ReloadApprovalsAction extends AppAction {
  ReloadApprovalsAction(this.threadId);
  final String threadId;

  @override
  Future<AppState?> reduce() async {
    try {
      final rows = asJsonList(
        await apiClient.get(
          '/trading/approvals',
          query: {'thread_id': threadId},
        ),
      );
      final t = state.thread(threadId);
      return state.withThread(
        t.copyWith(
          side: {
            ...t.side,
            SideKeys.approvals: mergeSideRows(
              sideList(t, SideKeys.approvals),
              rows,
              merge: mergeApproval,
            ),
          },
        ),
      );
    } catch (_) {
      return null;
    }
  }
}

/// Approve / Reject on a trade approval card: `POST /trading/approvals/{id}/decision
/// {decision: approve|reject}` (trade-approval.tsx:34-58). On a refusal the thread's
/// approvals are read again, so a card decided elsewhere shows as it is now; the refusal
/// is rethrown for the card to show.
class TradeApprovalDecisionAction extends AppAction {
  TradeApprovalDecisionAction({
    required this.threadId,
    required this.approvalId,
    required this.decision,
  }) : assert(decision == 'approve' || decision == 'reject');

  final String threadId;
  final String approvalId;

  /// approve or reject.
  final String decision;

  @override
  Future<AppState?> reduce() async {
    try {
      final row = asJson(
        await apiClient.post('/trading/approvals/$approvalId/decision', {
          'decision': decision,
        }),
      );
      if (row.isEmpty) return null;
      return state.withThread(
        _withRow(
          state.thread(threadId),
          SideKeys.approvals,
          row,
          merge: mergeApproval,
        ),
      );
    } on ApiError {
      await dispatchAndWait(ReloadApprovalsAction(threadId));
      rethrow;
    }
  }
}

/// «طلب جديد» on an expired approval (web `TradeApprovals.tsx`): asks the agent again; it
/// never creates an approvable request by itself (`POST /trading/approvals/{id}/renew`).
class TradeApprovalRenewAction extends AppAction {
  TradeApprovalRenewAction({required this.threadId, required this.approvalId});
  final String threadId;
  final String approvalId;

  @override
  Future<AppState?> reduce() async {
    final data = asJson(
      await apiClient.post(
        '/trading/approvals/$approvalId/renew',
        const <String, Object?>{},
      ),
    );
    if (data.isEmpty || data['id'] == null) return null;
    final run = Run.fromJson(data);
    final t = state.thread(threadId);
    return state.withThread(t.copyWith(runs: {...t.runs, run.id: run}));
  }
}
