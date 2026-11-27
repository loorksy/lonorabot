// The live fixed card a lonora-ui v2 trusted Slot names (docs/genui.md §4a): the same record
// and the same owner-session buttons as its own timeline row, drawn inside the slot's trust
// frame. A record that is not in this conversation (or of another kind) draws nothing.
import 'package:flutter/widgets.dart';

import '../../core/json.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import 'cards_actions.dart';
import 'owner_action_card.dart';
import 'thread_cards.dart';
import 'trade_approval_card.dart';

/// The card for a slot `{card, record}`; «هذه البطاقة غير متاحة هنا» when this conversation
/// has no such record.
Widget buildSlotCard(
  BuildContext context, {
  required String threadId,
  required String card,
  required String record,
}) => _SlotCard(threadId: threadId, card: card, record: record);

class _SlotCard extends StatelessWidget {
  const _SlotCard({
    required this.threadId,
    required this.card,
    required this.record,
  });

  final String threadId;
  final String card;
  final String record;

  @override
  Widget build(BuildContext context) {
    final present = context.select((AppState s) {
      final t = s.thread(threadId);
      if (card == 'trade_approval') {
        return sideList(t, SideKeys.approvals).any(
          (r) =>
              asStr(r['id']) == record &&
              asStr(r['thread_id'], threadId) == threadId,
        );
      }
      final kind = slotOwnerActionKinds[card];
      return kind != null &&
          sideList(t, SideKeys.ownerActions).any(
            (r) =>
                asStr(r['id']) == record &&
                r['kind'] == kind &&
                asStr(r['thread_id'], threadId) == threadId,
          );
    });
    if (!present) {
      final ln = context.ln;
      return Padding(
        padding: const EdgeInsets.all(4),
        child: Text(
          context.t('uiSlotGone'),
          style: ln.text.footnote.copyWith(color: ln.colors.fgMuted),
        ),
      );
    }
    return LayoutBuilder(
      builder: (context, constraints) => card == 'trade_approval'
          ? TradeApprovalCardView(
              threadId: threadId,
              approvalId: record,
              width: constraints.maxWidth,
            )
          : OwnerActionCardView(
              threadId: threadId,
              cardId: record,
              width: constraints.maxWidth,
            ),
    );
  }
}
