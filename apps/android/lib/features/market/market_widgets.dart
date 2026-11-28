// Pieces of the Market tab, composed from the kit's explore components
// (design/components/explore.dart: tile strips of a 296 × 128 wide card and 144 dp tiles, "… ›"
// section headers, full-width recommendation cards) and filled with Lonora's own market records.
// Colours are palette tokens; numbers read left to right in both languages.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../design/design.dart';
import '../../l10n/l10n.dart';
import 'market_data.dart';
import 'market_kit.dart';

/// The wide account card at the head of the tile strip (WideTile geometry): the account's
/// label and kind (simulation or broker), its equity, balance and open profit.
class AccountTile extends StatelessWidget {
  const AccountTile({
    super.key,
    required this.label,
    required this.simulation,
    this.snapshot,
    this.error,
    this.onTap,
  });

  final String label;
  final bool simulation;
  final AccountSnapshot? snapshot;

  /// Shown instead of the amounts when the account could not be read.
  final String? error;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    const white = LnPalette.inkWhite;
    final s = snapshot;
    final kind = context.t(simulation ? 'simulation' : 'brokerAccount');
    final equity = s?.equity;
    final profit = s?.openProfit;
    final balance = s?.balance;
    final currency = s?.currency ?? '';
    return WideTile(
      onTap: onTap,
      label: [
        label,
        kind,
        if (equity != null)
          '${context.t('mk_equity')} ${money(equity)} $currency',
        ?error,
      ].join('. '),
      color: simulation ? c.brand : c.selection,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(FIcons.wallet, size: 20, color: white),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: ln.text.footnoteStrong.copyWith(color: white),
                ),
              ),
              const SizedBox(width: 8),
              _Pill(text: kind),
            ],
          ),
          const Spacer(),
          if (error != null)
            Text(
              error!,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: ln.text.caption.copyWith(color: white),
            )
          else ...[
            Text(
              equity == null ? '—' : '${money(equity)} $currency',
              maxLines: 1,
              textDirection: TextDirection.ltr,
              style: ln.text.largeTitle.copyWith(color: white, height: 1.2),
            ),
            const SizedBox(height: 2),
            Text(
              [
                if (balance != null)
                  '${context.t('mk_balance')} ${ltr(money(balance))}',
                if (profit != null)
                  '${context.t('mk_profit')} ${ltr(signedMoney(profit))}',
              ].join(dotSeparator),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: ln.text.footnote.copyWith(color: white),
            ),
          ],
        ],
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    // The tile's own foreground (white on a saturated tile, as ExploreTile draws it), on a
    // darkened pill: white on a lighter one would fall under 3:1 on the lavender tile.
    const white = LnPalette.inkWhite;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0x40000000),
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.stadium)),
      ),
      child: Text(
        text,
        maxLines: 1,
        style: context.ln.text.smallStrong.copyWith(color: white),
      ),
    );
  }
}

/// A followed market (144 dp tile): ticker, bid, and the day's change in the market colours.
class SymbolTile extends StatelessWidget {
  const SymbolTile({
    super.key,
    required this.symbol,
    this.quote,
    this.change,
    this.onTap,
  });

  final String symbol;
  final MarketQuote? quote;

  /// Percent change of the last daily close.
  final double? change;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final ch = change;
    final tone = ch == null ? c.fgMuted : (ch >= 0 ? c.positive : c.negative);
    return LnTappable(
      onTap: onTap,
      haptic: true,
      semanticLabel: [
        symbol,
        if (quote != null) '${context.t('bid')} ${quote!.bid}',
        if (ch != null) '${context.t('mk_dayChange')} ${signedPercent(ch)}',
      ].join('. '),
      excludeChildSemantics: true,
      child: Container(
        width: LnSize.exploreTile,
        height: LnSize.exploreTile,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: ln.opaque(c.fill2),
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.tile)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              ch == null
                  ? FIcons.chartLine
                  : (ch >= 0 ? FIcons.trendingUp : FIcons.trendingDown),
              size: 22,
              color: tone,
            ),
            const Spacer(),
            Text(
              symbol,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textDirection: TextDirection.ltr,
              style: ln.text.title.copyWith(color: c.fg),
            ),
            Text(
              quote == null ? '—' : marketNumber(quote!.bid),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textDirection: TextDirection.ltr,
              style: ln.text.headline.copyWith(color: c.fg),
            ),
            const SizedBox(height: 2),
            Text(
              ch == null ? ' ' : signedPercent(ch),
              maxLines: 1,
              textDirection: TextDirection.ltr,
              style: ln.text.footnoteStrong.copyWith(
                color: ch != null && ch >= 0 ? c.positiveText : tone,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A navigation tile of the strip (ExploreTile at 144 × 128, a palette colour, a Lucide icon).
class LinkTile extends StatelessWidget {
  const LinkTile({
    super.key,
    required this.label,
    required this.icon,
    required this.color,
    this.onTap,
  });

  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => ExploreTile(
    label: label,
    leading: Icon(icon),
    color: color,
    width: LnSize.exploreTile,
    height: LnSize.wideTileHeight,
    onTap: onTap,
  );
}

/// A Lucide icon in the 32 dp illustration slot of a [RecommendationCard], tinted.
class CardIcon extends StatelessWidget {
  const CardIcon(this.icon, {super.key, this.color});

  final IconData icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final tint = color ?? c.fgMuted;
    return Container(
      width: LnSize.recIllustration,
      height: LnSize.recIllustration,
      decoration: BoxDecoration(
        color: tint.withValues(alpha: 0.14),
        borderRadius: const BorderRadius.all(
          Radius.circular(LnRadius.iconTile),
        ),
      ),
      child: Icon(icon, size: 18, color: tint),
    );
  }
}

/// One label · value line of a facts list (quote, instrument, an order's review), the value left
/// to right; one semantics node per line.
class FactRow extends StatelessWidget {
  const FactRow({super.key, required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Semantics(
      container: true,
      label: '$label: $value',
      excludeSemantics: true,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        // The value's box ends at the card's end edge (the label's unused room goes between).
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Flexible(
              child: Text(
                label,
                style: ln.text.caption.copyWith(color: c.fgMuted),
              ),
            ),
            const SizedBox(width: 12),
            // The value hugs that edge whatever its own direction.
            Expanded(
              child: Align(
                alignment: AlignmentDirectional.centerEnd,
                child: Text(
                  value,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  textDirection: readingDirection(value) ?? TextDirection.ltr,
                  style: ln.text.captionStrong.copyWith(color: c.fg),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A grouped block of [FactRow]s on the light fill (24 dp radius).
class FactsCard extends StatelessWidget {
  const FactsCard({super.key, required this.children, this.title});

  final String? title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Container(
      padding: const EdgeInsetsDirectional.fromSTEB(16, 10, 16, 10),
      decoration: BoxDecoration(
        color: c.fill1,
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.card)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (title != null)
            Padding(
              padding: const EdgeInsets.only(top: 4, bottom: 4),
              child: Text(
                title!,
                style: ln.text.footnoteStrong.copyWith(color: c.fgMuted),
              ),
            ),
          ...children,
        ],
      ),
    );
  }
}

/// The calendar event line: time, currency, event, actual or forecast; the impact as a dot.
class CalendarRow extends StatelessWidget {
  const CalendarRow({super.key, required this.event, required this.time});

  final CalendarEvent event;
  final String time;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final impact = event.impact.toLowerCase();
    final dot = impact.startsWith('high')
        ? c.negative
        : impact.startsWith('med')
        ? c.warning
        : c.fgSubtle;
    final value = event.actual ?? event.forecast ?? '—';
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(24, 8, 24, 8),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
          ),
          const SizedBox(width: 12),
          // The time sits at the start of its column (beside the dot) in both directions.
          SizedBox(
            width: 92,
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: Text(
                time,
                maxLines: 1,
                textDirection: TextDirection.ltr,
                style: ln.text.footnote.copyWith(color: c.fgMuted),
              ),
            ),
          ),
          Text(
            event.currency,
            textDirection: TextDirection.ltr,
            style: ln.text.footnoteStrong.copyWith(color: c.fg),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              event.name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textDirection: readingDirection(event.name),
              // Beside the currency in both directions: the name reads in its own direction
              // but sits at the row's start.
              textAlign: Directionality.of(context) == TextDirection.rtl
                  ? TextAlign.right
                  : TextAlign.left,
              style: ln.text.caption.copyWith(color: c.fg),
            ),
          ),
          const SizedBox(width: 8),
          Text(
            value,
            textDirection: TextDirection.ltr,
            style: ln.text.footnoteStrong.copyWith(color: c.fg),
          ),
        ],
      ),
    );
  }
}
