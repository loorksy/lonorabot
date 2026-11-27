// Shared pieces of the conversation's fixed cards, composed from the Lonora kit: the
// permission-card header art (agent ••• shield, an illustration band drawn with Lonora's own
// avatar), label/value fact rows, evidence lines, the paper/live account badge and the refusal
// line.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../avatar/avatar.dart';
import '../../core/json.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import 'cards_actions.dart';

/// The flat header band art: the agent's avatar, three fading dots, and the owner's shield.
class CardHeaderArt extends StatelessWidget {
  const CardHeaderArt({
    super.key,
    this.agentId,
    this.icon = FIcons.shieldCheck,
  });

  final String? agentId;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final agent = context.select(
      (AppState s) => agentId == null ? null : s.shell.agents[agentId],
    );
    Widget dot(double alpha) => Container(
      width: 8,
      height: 8,
      margin: const EdgeInsets.symmetric(horizontal: 2),
      decoration: BoxDecoration(
        color: c.fgSubtle.withValues(alpha: alpha),
        shape: BoxShape.circle,
      ),
    );
    return ExcludeSemantics(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (agentId != null)
            LonoraAvatar(
              agentId: agentId!,
              face: agent?.avatar,
              color: agent?.color,
              tradesOnItsOwn: agent?.tradesOnItsOwn ?? false,
              size: 52,
              animate: false,
            )
          else
            _disc(context, FIcons.bot),
          const SizedBox(width: 17.5),
          dot(0.9),
          dot(0.6),
          dot(0.3),
          const SizedBox(width: 17.5),
          _disc(context, icon),
        ],
      ),
    );
  }

  Widget _disc(BuildContext context, IconData glyph) {
    final c = context.ln.colors;
    return Container(
      width: 52,
      height: 52,
      decoration: BoxDecoration(
        color: c.surface,
        shape: BoxShape.circle,
        border: Border.all(color: c.border),
      ),
      child: Icon(glyph, size: 26, color: c.fg),
    );
  }
}

/// A small heading line above a card's title (the card's kind, as the web kicker).
class CardKicker extends StatelessWidget {
  const CardKicker({super.key, required this.text, this.icon, this.trailing});

  final String text;
  final IconData? icon;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Row(
      children: [
        if (icon != null) ...[
          Icon(icon, size: 15, color: c.fgMuted),
          const SizedBox(width: 6),
        ],
        Expanded(
          child: Text(
            text,
            style: ln.text.footnoteStrong.copyWith(color: c.fgMuted),
          ),
        ),
        if (trailing != null) ...[const SizedBox(width: 8), trailing!],
      ],
    );
  }
}

/// One label / value row; a number, ticker or ticket reads left to right inside Arabic.
class FactRow {
  const FactRow(this.label, this.value, {this.ltr = false});
  final String label;
  final String value;
  final bool ltr;
}

class FactRows extends StatelessWidget {
  const FactRows({super.key, required this.rows});
  final List<FactRow> rows;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LayoutBuilder(
      builder: (context, constraints) =>
          _rows(context, ln, c, constraints.maxWidth),
    );
  }

  Widget _rows(
    BuildContext context,
    LnThemeData ln,
    LnPalette c,
    double width,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < rows.length; i++)
          MergeSemantics(
            child: Padding(
              padding: EdgeInsets.only(top: i == 0 ? 0 : 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Text(
                      rows[i].label,
                      style: ln.text.caption.copyWith(color: c.fgMuted),
                    ),
                  ),
                  const SizedBox(width: LnSpace.sm),
                  // The value hugs the row's end and wraps past 60 % of it.
                  ConstrainedBox(
                    constraints: BoxConstraints(maxWidth: width * 0.6),
                    child: Text(
                      rows[i].ltr ? ltr(rows[i].value) : rows[i].value,
                      textAlign: TextAlign.end,
                      style: ln.text.captionStrong.copyWith(color: c.fg),
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

/// ok, wait, warn, bad or plain.
typedef EvidenceTone = String;

/// A status or evidence line: an icon in the tone's colour and the text.
class EvidenceLine extends StatelessWidget {
  const EvidenceLine({
    super.key,
    required this.tone,
    required this.icon,
    required this.child,
  });

  final EvidenceTone tone;
  final IconData icon;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final accent = switch (tone) {
      'ok' => c.success,
      'warn' => c.warning,
      'bad' => c.error,
      _ => c.fgMuted,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: tone == 'plain' || tone == 'wait'
            ? c.fill1
            : accent.withValues(alpha: c.isDark ? 0.16 : 0.1),
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.field)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(icon, size: 16, color: accent),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: DefaultTextStyle.merge(
              style: ln.text.footnote.copyWith(color: c.fg),
              child: child,
            ),
          ),
        ],
      ),
    );
  }
}

IconData toneIcon(EvidenceTone tone) => switch (tone) {
  'ok' => FIcons.check,
  'wait' => FIcons.hourglass,
  'warn' => FIcons.triangleAlert,
  _ => FIcons.x,
};

/// Simulation or broker account, from the provider of the account a card names, in
/// Lonora's own account labels (owner-actions.ts `accountLabel`); nothing when unknown.
class AccountBadge extends StatelessWidget {
  const AccountBadge({super.key, required this.provider});
  final String? provider;

  @override
  Widget build(BuildContext context) {
    final p = provider;
    if (p == null || p.isEmpty) return const SizedBox.shrink();
    final text = ownerActionText(context.l10n.lang);
    final paper = p == 'simulation';
    return StatusChip(
      label: paper ? text.simulation : text.brokerAccount,
      kind: paper ? StatusChipKind.neutral : StatusChipKind.waiting,
    );
  }
}

/// The provider of the trading connection [accountId] in this thread's side reads, else
/// null.
String? accountProvider(ThreadState thread, String? accountId) {
  if (accountId == null) return null;
  final accounts = asJson(thread.side[SideKeys.accounts]);
  return asString(accounts[accountId]);
}

/// The server's refusal, in the owner's words.
class CardError extends StatelessWidget {
  const CardError({super.key, required this.text});
  final String? text;

  @override
  Widget build(BuildContext context) {
    final t = text;
    if (t == null) return const SizedBox.shrink();
    final ln = context.ln;
    return Semantics(
      liveRegion: true,
      child: Padding(
        padding: const EdgeInsets.only(top: LnSpace.xs),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 1),
              child: Icon(FIcons.circleAlert, size: 16, color: ln.colors.error),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                t,
                style: ln.text.footnote.copyWith(color: ln.colors.error),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Two equal-width stadiums side by side (an approval card's Deny / Allow row).
class ButtonPair extends StatelessWidget {
  const ButtonPair({super.key, required this.first, required this.second});
  final Widget first;
  final Widget second;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Expanded(child: first),
      const SizedBox(width: LnSpace.xs),
      Expanded(child: second),
    ],
  );
}
