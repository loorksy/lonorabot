// Pieces of the owner's order screens, composed from the kit: a tinted notice (why an order
// is paused, the live-money warning, a broker outage), an operation's status line and its
// alert, the side badge, the position and pending-order cards with their actions
// (apps/web shell/agent/TradesPage.tsx `PositionCard`, components/trading/Orders.tsx), and the
// order log's row with its state chip (TradesPage.tsx, order-state.ts).
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../market/market_data.dart';
import '../market/market_kit.dart';
import '../market/market_widgets.dart';
import 'trade_flows.dart';
import 'trade_rules.dart';
import 'trade_text.dart';
import 'trades_data.dart';

enum NoticeTone { warning, error, info }

/// A tinted note with a leading icon: why an order is paused, the live-money warning, an
/// outage. [onTap] makes the whole note a link (a trailing chevron shows it).
class TradeNotice extends StatelessWidget {
  const TradeNotice({
    super.key,
    required this.text,
    this.tone = NoticeTone.warning,
    this.icon,
    this.title,
    this.onTap,
    this.linkLabel,
  });

  final String text;
  final String? title;
  final NoticeTone tone;
  final IconData? icon;
  final VoidCallback? onTap;

  /// Spoken after the text when [onTap] is set («التعطل والاستعادة»).
  final String? linkLabel;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final accent = switch (tone) {
      NoticeTone.warning => c.warning,
      NoticeTone.error => c.error,
      NoticeTone.info => c.selection,
    };
    final glyph =
        icon ??
        switch (tone) {
          NoticeTone.warning => FIcons.triangleAlert,
          NoticeTone.error => FIcons.circleAlert,
          NoticeTone.info => FIcons.info,
        };
    final body = Container(
      constraints: const BoxConstraints(minHeight: LnSize.minTouch),
      padding: const EdgeInsetsDirectional.fromSTEB(14, 12, 12, 12),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: c.isDark ? 0.18 : 0.12),
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.field)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: Icon(glyph, size: 18, color: accent),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (title != null)
                  Text(
                    title!,
                    style: ln.text.captionStrong.copyWith(color: c.fg),
                  ),
                Text(text, style: ln.text.caption.copyWith(color: c.fg)),
                if (onTap != null && linkLabel != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      linkLabel!,
                      style: ln.text.captionStrong.copyWith(color: c.link),
                    ),
                  ),
              ],
            ),
          ),
          if (onTap != null) ...[
            const SizedBox(width: 8),
            Icon(FIcons.chevronRight, size: 18, color: c.chevron),
          ],
        ],
      ),
    );
    final label = [?title, text, ?linkLabel].join('. ');
    if (onTap == null) {
      return Semantics(label: label, excludeSemantics: true, child: body);
    }
    return LnTappable(
      onTap: onTap,
      semanticLabel: label,
      excludeChildSemantics: true,
      child: body,
    );
  }
}

/// Why the owner's orders on this account are paused, or null: the broker refuses trading on it
/// (every order), or its state cannot be verified (new risk only; exits stay).
TradeNotice? pausedNotice(
  BuildContext context,
  TradeAccount account, {
  VoidCallback? onRecovery,
}) {
  if (account.notAllowed) {
    return TradeNotice(
      text: context.t('broker_trading_not_allowed'),
      tone: NoticeTone.error,
      icon: FIcons.ban,
    );
  }
  if (account.down) {
    return TradeNotice(
      text: context.t('tr_pausedDown'),
      icon: FIcons.unplug,
      onTap: onRecovery,
      linkLabel: onRecovery == null ? null : context.t('rc_title'),
    );
  }
  return null;
}

/// An operation's status line (a polite live region) and the alert of a send without a settled
/// answer (assertive), as TradesPage.tsx `role="status"` / `role="alert"`.
class OutcomeView extends StatelessWidget {
  const OutcomeView({super.key, this.outcome, this.error});

  final TicketOutcome? outcome;
  final Object? error;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final o = outcome;
    final e = error;
    if (o == null && e == null) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (o != null)
          Semantics(
            liveRegion: true,
            container: true,
            child: Padding(
              padding: const EdgeInsets.only(top: LnSpace.xs),
              child: Text.rich(
                TextSpan(
                  children: [
                    for (final (i, line) in outcomeLines(l10n, o).indexed)
                      TextSpan(
                        text: i == 0 ? line : '\n$line',
                        style: i == 0
                            ? ln.text.captionStrong.copyWith(color: c.fg)
                            : null,
                      ),
                  ],
                ),
                style: ln.text.caption.copyWith(color: c.fgMuted),
              ),
            ),
          ),
        if (e != null)
          Semantics(
            liveRegion: true,
            container: true,
            child: Padding(
              padding: const EdgeInsets.only(top: LnSpace.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Icon(FIcons.circleAlert, size: 15, color: c.error),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      tradeErrorText(l10n, e),
                      style: ln.text.caption.copyWith(color: c.fg),
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

/// «شراء» / «بيع» with its direction icon: never colour alone.
class SideBadge extends StatelessWidget {
  const SideBadge({super.key, required this.side});

  final String side;

  @override
  Widget build(BuildContext context) {
    final sell = sideOf(side) == 'sell';
    return StatusChip(
      label: sideWord(context.l10n, side),
      kind: sell ? StatusChipKind.error : StatusChipKind.success,
      icon: sell ? FIcons.trendingDown : FIcons.trendingUp,
    );
  }
}

/// A card of the order screens: the light fill, the card radius.
class TradeCard extends StatelessWidget {
  const TradeCard({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(LnSpace.cardPadding),
    decoration: BoxDecoration(
      color: context.ln.colors.fill1,
      borderRadius: const BorderRadius.all(Radius.circular(LnRadius.card)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: children,
    ),
  );
}

/// The card's head: the account's label (muted), then the symbol (left to right) and a badge.
class _CardHead extends StatelessWidget {
  const _CardHead({
    required this.account,
    required this.symbol,
    required this.badge,
  });

  final String account;
  final String symbol;
  final Widget badge;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          isolate(account),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: ln.text.footnote.copyWith(color: c.fgMuted),
        ),
        const SizedBox(height: 2),
        Row(
          children: [
            Flexible(
              child: Semantics(
                header: true,
                child: Text(
                  symbol,
                  textDirection: TextDirection.ltr,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: ln.text.headline.copyWith(color: c.fg),
                ),
              ),
            ),
            const SizedBox(width: LnSpace.xs),
            badge,
          ],
        ),
      ],
    );
  }
}

/// One open position with the owner's «تعديل الوقف والهدف» and «إغلاق الصفقة» (or «تحقق من
/// نتيجة الإغلاق» while a close is held), its last outcome and alert (TradesPage.tsx
/// `PositionCard`). [onChanged] reads the account and the journal again after an order. While
/// the broker refuses trading, only a held close or edit can still be checked.
class PositionCard extends StatelessWidget {
  const PositionCard({
    super.key,
    required this.account,
    required this.position,
    this.onChanged,
  });

  final TradeAccount account;
  final MarketPosition position;
  final VoidCallback? onChanged;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final p = position;
    return ListenableBuilder(
      listenable: OrderDesk.instance,
      builder: (context, _) {
        final state = positionState(account, p);
        String value(String? v) => v == null || v.isEmpty ? '—' : ltr(v);
        return TradeCard(
          children: [
            _CardHead(
              account: account.label,
              symbol: p.symbol,
              badge: SideBadge(side: p.side),
            ),
            const SizedBox(height: LnSpace.xs),
            FactRow(label: l10n.t('receiptVolume'), value: value(p.volume)),
            FactRow(label: l10n.t('tr_entryPrice'), value: value(p.openPrice)),
            FactRow(label: l10n.t('stopLoss'), value: value(p.stopLoss)),
            FactRow(label: l10n.t('takeProfit'), value: value(p.takeProfit)),
            const SizedBox(height: LnSpace.sm),
            BlockButton(
              label: l10n.t('tr_editStopTarget'),
              icon: FIcons.shieldCheck,
              variant: BlockButtonVariant.secondary,
              onPressed: state.busy || (account.notAllowed && !state.editHeld)
                  ? null
                  : () =>
                        editStopTarget(context, account, p, onDone: onChanged),
            ),
            const SizedBox(height: LnSpace.xs),
            BlockButton(
              label: l10n.t(
                state.closeHeld ? 'tr_checkCloseResult' : 'tr_closeTrade',
              ),
              icon: FIcons.circleX,
              variant: BlockButtonVariant.destructive,
              loading: state.closeBusy,
              onPressed: state.busy || (account.notAllowed && !state.closeHeld)
                  ? null
                  : () => confirmClose(context, account, p, onDone: onChanged),
            ),
            OutcomeView(outcome: state.outcome, error: state.error),
          ],
        );
      },
    );
  }
}

/// One pending order with the owner's «إلغاء الأمر» (or «تحقق من نتيجة الإلغاء» while held)
/// and its outcome (components/trading/Orders.tsx, with the close's confirmation).
class PendingOrderCard extends StatelessWidget {
  const PendingOrderCard({
    super.key,
    required this.account,
    required this.order,
    this.onChanged,
  });

  final TradeAccount account;
  final MarketOrder order;
  final VoidCallback? onChanged;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final o = order;
    return ListenableBuilder(
      listenable: OrderDesk.instance,
      builder: (context, _) {
        final state = orderCardState(account, o);
        String value(String? v) => v == null || v.isEmpty ? '—' : ltr(v);
        return TradeCard(
          children: [
            _CardHead(
              account: account.label,
              symbol: o.symbol,
              badge: SideBadge(side: o.side),
            ),
            const SizedBox(height: LnSpace.xs),
            FactRow(
              label: l10n.t('tr_type'),
              value: orderKindWord(l10n, o.side),
            ),
            FactRow(label: l10n.t('receiptVolume'), value: value(o.volume)),
            FactRow(label: l10n.t('orderPrice'), value: value(o.price)),
            FactRow(label: l10n.t('stopLoss'), value: value(o.stopLoss)),
            FactRow(label: l10n.t('takeProfit'), value: value(o.takeProfit)),
            const SizedBox(height: LnSpace.sm),
            BlockButton(
              label: l10n.t(
                state.held ? 'tr_checkCancelResult' : 'tr_cancelOrder',
              ),
              icon: FIcons.circleX,
              variant: BlockButtonVariant.destructive,
              loading: state.busy,
              onPressed: state.blocked
                  ? null
                  : () => confirmCancel(context, account, o, onDone: onChanged),
            ),
            if (state.protective && account.down && !state.held)
              Padding(
                padding: const EdgeInsets.only(top: LnSpace.xs),
                child: Footnote(
                  l10n.t('tr_protectiveOrder'),
                  icon: FIcons.shieldCheck,
                ),
              ),
            OutcomeView(outcome: state.outcome, error: state.error),
          ],
        );
      },
    );
  }
}

/// An order state's chip: its icon and name in its tone (never colour alone).
class OrderStateChip extends StatelessWidget {
  const OrderStateChip({super.key, required this.state});

  final OrderState state;

  @override
  Widget build(BuildContext context) {
    final (kind, icon) = switch (orderTone(state)) {
      OrderTone.wait => (StatusChipKind.waiting, FIcons.hourglass),
      OrderTone.ok => (StatusChipKind.success, FIcons.check),
      OrderTone.bad => (StatusChipKind.error, FIcons.x),
      OrderTone.off => (StatusChipKind.neutral, FIcons.minus),
      OrderTone.warn => (StatusChipKind.waiting, FIcons.triangleAlert),
    };
    return StatusChip(
      label: orderStateName(context.l10n, state),
      kind: kind,
      icon: icon,
    );
  }
}

/// One «سجل الأوامر» row: what was asked (and the executed size of a partial fill), the time
/// and kind, a price only with the broker's evidence, and the state (TradesPage.tsx).
class OrderLogRow extends StatelessWidget {
  const OrderLogRow({super.key, required this.entry});

  final JournalEntry entry;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final e = entry;
    final state = orderState(e);
    final wording = orderWording(l10n, e.action);
    final fill = orderFill(e);
    final asked = e.request['volume'] == null ? null : '${e.request['volume']}';
    final size = state == OrderState.partial
        ? (fill.volume != null && asked != null
              ? ltr('${fill.volume} / $asked')
              : null)
        : (asked == null ? null : ltr(asked));
    final title = [wording.title, ?size, isolate(e.symbol)].join(' ');
    final subtitle = [
      ltr(orderTime(l10n, e)),
      if (wording.kind.isNotEmpty) wording.kind,
      if (fill.price != null && state != OrderState.uncertain) ltr(fill.price!),
    ].join(dotSeparator);
    final sell = e.action.startsWith('sell');
    return MergeSemantics(
      child: Container(
        constraints: const BoxConstraints(minHeight: 64),
        padding: const EdgeInsetsDirectional.fromSTEB(16, 12, 12, 12),
        child: Row(
          children: [
            CardIcon(
              sell ? FIcons.trendingDown : FIcons.trendingUp,
              color: sell ? c.negative : c.positive,
            ),
            const SizedBox(width: LnSpace.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: ln.text.captionStrong.copyWith(color: c.fg),
                  ),
                  Text(
                    subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: ln.text.footnote.copyWith(color: c.fgMuted),
                  ),
                ],
              ),
            ),
            const SizedBox(width: LnSpace.xs),
            OrderStateChip(state: state),
          ],
        ),
      ),
    );
  }
}
