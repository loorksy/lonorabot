// The Execution Receipt (mandate 10.3, 11.2; apps/mobile/components/execution-receipt.tsx), laid
// out like the kit's ScheduleCard: a bordered icon tile, the kicker «إيصال التنفيذ · SYMBOL», the
// action as the title, a hairline divider, the broker's own facts as label / value rows, the
// broker-confirmed status line, and the agent's reason labelled as its words. It never reads as
// verified before the account state was read back. A receipt has no buttons.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../core/json.dart';
import '../../design/design.dart';
import '../../l10n/core/values.dart' show jsString;
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import 'card_parts.dart';
import 'cards_actions.dart';
import 'cards_strings.dart';

class ExecutionReceiptCardView extends StatelessWidget {
  const ExecutionReceiptCardView({
    super.key,
    required this.threadId,
    required this.operationId,
    this.width,
  });

  final String threadId;
  final String operationId;
  final double? width;

  @override
  Widget build(BuildContext context) {
    final row = context.select(
      (AppState s) => sideList(
        s.thread(threadId),
        SideKeys.receipts,
      ).where((r) => asStr(r['operation_id']) == operationId).firstOrNull,
    );
    if (row == null) return const SizedBox.shrink();
    return ExecutionReceiptCard(row: row, width: width);
  }
}

/// A receipt names no account (packages/contracts `ExecutionReceipt`), so it carries no
/// account badge: the agent's current account may not be the one the operation ran on.
class ExecutionReceiptCard extends StatelessWidget {
  const ExecutionReceiptCard({super.key, required this.row, this.width});

  /// The server's `ExecutionReceipt` JSON.
  final Json row;
  final double? width;

  @override
  Widget build(BuildContext context) {
    registerCardsStrings(context.l10n);
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final locale = l10n.lang;
    final kind = asStr(row['kind']);
    final facts = <(String, Object?)>[('receiptTicket', row['ticket'])];
    if (kind == 'fill') {
      facts.addAll([
        ('receiptVolume', row['volume']),
        ('fillPrice', row['price']),
      ]);
    } else if (kind == 'order') {
      facts.addAll([
        ('receiptVolume', row['volume']),
        ('orderPrice', row['price']),
        ('stopLoss', row['stop_loss']),
        ('takeProfit', row['take_profit']),
      ]);
    } else if (kind == 'modify') {
      facts.addAll([
        ('newPrice', row['price']),
        ('newStopLoss', row['stop_loss']),
        ('newTakeProfit', row['take_profit']),
      ]);
    }
    final rows = <FactRow>[
      for (final (label, value) in facts)
        if (value != null && value != '')
          FactRow(l10n.t(label), jsString(value), ltr: true),
      if (row['stop_loss_removed'] == true)
        FactRow(l10n.t('stopLoss'), l10n.t('removedValue')),
      if (row['take_profit_removed'] == true)
        FactRow(l10n.t('takeProfit'), l10n.t('removedValue')),
    ];
    final verification = asString(row['verification']);
    final status = switch (verification) {
      'verified' => l10n.t('accountVerified'),
      'unverified' => l10n.t('accountUnverified'),
      'pending' => l10n.t('accountChecking'),
      _ => null,
    };
    final tone = switch (verification) {
      'unverified' => 'warn',
      'pending' => 'wait',
      _ => 'ok',
    };
    final action = orderLineAction({'action': row['action']}, locale).label;
    final title = [
      action,
      if (row['partial'] == true) l10n.t('partiallyFilled'),
      if (row['agent_id'] == null) ownerActionText(locale).byYou,
    ].join(dotSeparator);
    final symbol = asStr(row['symbol']);
    return SizedBox(
      width: width ?? ActionCard.widthFor(MediaQuery.sizeOf(context).width),
      child: Semantics(
        container: true,
        label: l10n.t('executionReceipt'),
        child: LnCardSurface(
          child: Padding(
            padding: const EdgeInsets.all(LnSpace.cardPadding),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    Container(
                      width: LnSize.iconTile,
                      height: LnSize.iconTile,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: c.surface,
                        borderRadius: const BorderRadius.all(
                          Radius.circular(LnRadius.iconTile),
                        ),
                        border: Border.all(color: c.border),
                      ),
                      child: Icon(
                        FIcons.receiptText,
                        size: LnSize.chromeIcon,
                        color: c.fg,
                      ),
                    ),
                    const SizedBox(width: LnSpace.sm),
                    Expanded(
                      child: Text(
                        symbol.isEmpty
                            ? l10n.t('executionReceipt')
                            // As the approval kicker (cc:C11): the dot never ends or
                            // starts a wrapped line.
                            : '${l10n.t('executionReceipt')}\u00a0·\u00a0${ltr(symbol)}',
                        style: ln.text.footnoteStrong.copyWith(
                          color: c.fgMuted,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Text(title, style: ln.text.title.copyWith(color: c.fg)),
                const SizedBox(height: LnSpace.sm),
                Container(height: 1, color: c.border),
                if (rows.isNotEmpty) ...[
                  const SizedBox(height: LnSpace.sm),
                  FactRows(rows: rows),
                ],
                const SizedBox(height: LnSpace.sm),
                Semantics(
                  liveRegion: true,
                  child: EvidenceLine(
                    tone: tone,
                    icon: toneIcon(tone),
                    child: Text(
                      status == null
                          ? l10n.t('confirmedByBroker')
                          : '${l10n.t('confirmedByBroker')} · $status',
                    ),
                  ),
                ),
                if (asString(row['reason']) case final reason?
                    when reason.isNotEmpty) ...[
                  const SizedBox(height: LnSpace.xs),
                  EvidenceLine(
                    tone: 'plain',
                    icon: FIcons.messageCircle,
                    child: Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(
                            text: '${l10n.t('agentWords')}: ',
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          TextSpan(text: isolate(reason)),
                        ],
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
