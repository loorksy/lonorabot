import 'package:flutter/foundation.dart' show setEquals;
import 'package:flutter/widgets.dart';

import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../rich/rich_parts.dart';
import 'cards_actions.dart';
import 'execution_receipt_card.dart';
import 'owner_action_card.dart';
import 'peer_card.dart' show peersByMessage;
import 'trade_approval_card.dart';

/// A fixed card placed in the conversation timeline (owner action, trade approval,
/// execution receipt...). Ordered with messages by [seq] (after that message)
/// or by [at] when it has no message anchor.
///
/// [seq] is always set by [threadCards]: the card sits after the newest message whose seq is
/// <= [seq] (and before the next one). Cards with the same [seq] keep the list's order
/// (approval, owner action, receipt; then by time), so a stable sort by [seq] is correct.
class TimelineCard {
  const TimelineCard({
    required this.key,
    required this.at,
    required this.builder,
    this.seq,
  });
  final String key;
  final DateTime at;
  final int? seq;
  final WidgetBuilder builder;
}

/// One fixed card's place in the timeline, before it gets a widget (unit-tested).
class CardAnchor {
  const CardAnchor({
    required this.kind,
    required this.id,
    required this.seq,
    required this.at,
  });

  /// approval, owner_action or receipt.
  final String kind;
  final String id;

  /// The message seq the card follows.
  final int seq;
  final DateTime at;

  String get key => '$kind:$id';
}

const Map<String, int> _kindOrder = {
  'approval': 0,
  'owner_action': 1,
  'receipt': 2,
};

/// The owner-action kind each slot card names (conversation-timeline.ts
/// `SLOT_OWNER_ACTION_KINDS`).
const Map<String, String> slotOwnerActionKinds = {
  'settle': 'settle_operation',
  'mandate': 'trading_mode',
  'secret': 'secret',
};

/// Where each fixed card goes (packages/core/src/conversation-timeline.ts): server sequence
/// anchors (`timeline_seq`, the seq of the message that came next) win over fetch timing;
/// a legacy row without one goes before the first message created at or after it, else after
/// everything. A card a loaded message embeds as a trusted slot has no row of its own (the
/// slot is its place); the row returns when no message embeds it.
List<CardAnchor> cardAnchors({
  required List<Message> messages,
  required List<Json> approvals,
  required List<Json> ownerActions,
  required List<Json> receipts,
  Set<String> slots = const {},
}) {
  final ordered = [...messages]..sort((a, b) => a.seq.compareTo(b.seq));
  final lastSeq = ordered.isEmpty ? 0 : ordered.last.seq;
  int anchor(Json row) {
    final timeline = asInt(row['timeline_seq']);
    if (timeline != null) return timeline - 1;
    final created = asDate(row['created_at']);
    if (created != null) {
      for (final m in ordered) {
        final at = m.createdAt;
        if (at != null && !at.isBefore(created)) return m.seq - 1;
      }
    }
    return lastSeq;
  }

  DateTime when(Json row) =>
      asDate(row['created_at']) ?? DateTime.fromMillisecondsSinceEpoch(0);

  final anchors = <CardAnchor>[];
  final seenApprovals = <String>{};
  for (final row in approvals) {
    final id = asStr(row['id']);
    if (id.isEmpty || !seenApprovals.add(id)) continue;
    if (slots.contains('trade_approval:$id')) continue;
    anchors.add(
      CardAnchor(kind: 'approval', id: id, seq: anchor(row), at: when(row)),
    );
  }
  final seenActions = <String>{};
  for (final row in ownerActions) {
    final id = asStr(row['id']);
    if (id.isEmpty || !seenActions.add(id)) continue;
    final slot = slotOwnerActionKinds.entries
        .where((e) => e.value == row['kind'])
        .firstOrNull
        ?.key;
    if (slot != null && slots.contains('$slot:$id')) continue;
    anchors.add(
      CardAnchor(kind: 'owner_action', id: id, seq: anchor(row), at: when(row)),
    );
  }
  final seenReceipts = <String>{};
  for (final row in receipts) {
    final id = asStr(row['operation_id']);
    if (id.isEmpty || !seenReceipts.add(id)) continue;
    anchors.add(
      CardAnchor(kind: 'receipt', id: id, seq: anchor(row), at: when(row)),
    );
  }
  anchors.sort((a, b) {
    final bySeq = a.seq.compareTo(b.seq);
    if (bySeq != 0) return bySeq;
    final byKind = _kindOrder[a.kind]!.compareTo(_kindOrder[b.kind]!);
    if (byKind != 0) return byKind;
    final byTime = a.at.compareTo(b.at);
    return byTime != 0 ? byTime : a.key.compareTo(b.key);
  });
  return anchors;
}

final Expando<(Set<String>, Set<String>)> _slotCache = Expando('drawn-slots');

/// The messages the conversation draws as another card instead of their rich content: a
/// peer exchange's messages and the messages holding a question with choices. A slot in
/// them is not drawn, so it never hides a fixed card's row (web Conversation.tsx and
/// mobile thread.tsx `undrawn`).
Set<String> undrawnMessages(ThreadState thread) => {
  ...peersByMessage(sideList(thread, SideKeys.peerMessages)).keys,
  for (final run in thread.runs.values)
    for (final request in run.inputRequests)
      if (request.choices.isNotEmpty) ?request.messageId,
};

/// Cards of a conversation, built from `ThreadState.side` reads. Each card reads its live
/// record from the store, so a decision anywhere redraws it in place.
List<TimelineCard> threadCards(BuildContext context, ThreadState thread) {
  final messages = thread.messages;
  final undrawn = undrawnMessages(thread);
  final cached = _slotCache[messages];
  final Set<String> slots;
  if (cached != null && setEquals(cached.$1, undrawn)) {
    slots = cached.$2;
  } else {
    slots = drawnSlots(messages.where((m) => !undrawn.contains(m.id)));
    _slotCache[messages] = (undrawn, slots);
  }
  final anchors = cardAnchors(
    messages: messages,
    approvals: sideList(thread, SideKeys.approvals),
    ownerActions: sideList(thread, SideKeys.ownerActions),
    receipts: sideList(thread, SideKeys.receipts),
    slots: slots,
  );
  final threadId = thread.threadId;
  return [
    for (final a in anchors)
      TimelineCard(
        key: a.key,
        at: a.at,
        seq: a.seq,
        builder: (context) => switch (a.kind) {
          'approval' => TradeApprovalCardView(
            threadId: threadId,
            approvalId: a.id,
          ),
          'owner_action' => OwnerActionCardView(
            threadId: threadId,
            cardId: a.id,
          ),
          _ => ExecutionReceiptCardView(threadId: threadId, operationId: a.id),
        },
      ),
  ];
}

/// Loads the side reads cards need (`/owner-actions?thread_id=`,
/// `/trading/approvals?thread_id=`, `/trading/receipts?thread_id=`,
/// `/peer-messages?thread_id=`) into `ThreadState.side` (keys in [SideKeys]), plus the
/// providers of the accounts approvals name (`/trading/connections`, provider only) so a
/// simulation account is labelled. All reads are GETs; a read that fails keeps what was
/// there, and a late read never takes a decided card back to pending. Dispatched by the
/// conversation when it opens and after events.
class LoadThreadSideAction extends AppAction {
  LoadThreadSideAction(this.threadId);
  final String threadId;

  Future<Object?> _get(String path, [Map<String, Object?>? query]) => apiClient
      .get(path, query: query)
      .then<Object?>((v) => v)
      .catchError((Object _) => null);

  @override
  Future<AppState?> reduce() async {
    if (!signedIn) return null;
    final query = {'thread_id': threadId};
    final results = await Future.wait<Object?>([
      _get('/owner-actions', query),
      _get('/trading/approvals', query),
      _get('/trading/receipts', query),
      _get('/peer-messages', query),
    ]);
    final before = state.thread(threadId);
    final side = <String, Object?>{};
    if (results[0] is List) {
      side[SideKeys.ownerActions] = mergeSideRows(
        sideList(before, SideKeys.ownerActions),
        asJsonList(results[0]),
        merge: mergeOwnerAction,
      );
    }
    if (results[1] is List) {
      side[SideKeys.approvals] = mergeSideRows(
        sideList(before, SideKeys.approvals),
        asJsonList(results[1]),
        merge: mergeApproval,
      );
    }
    if (results[2] is List) side[SideKeys.receipts] = asJsonList(results[2]);
    if (results[3] is List) {
      side[SideKeys.peerMessages] = asJsonList(results[3]);
    }
    // An approval request names its account by the trading connection's id (the same id
    // as an agent's trading_account_id), not by the broker's own account number.
    if (asJsonList(side[SideKeys.approvals]).isNotEmpty) {
      final connections = await _get('/trading/connections');
      if (connections is List) {
        side[SideKeys.accounts] = {
          for (final c in asJsonList(connections))
            ?asString(c['id']): asStr(asJson(c['payload'])['provider']),
        };
      }
    }
    if (side.isEmpty) return null;
    final t = state.thread(threadId);
    return state.withThread(t.copyWith(side: {...t.side, ...side}));
  }
}
