import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../theme.dart';

/// Unread count pill ("3", "99+") on forui's [FBadge]. Min 20 dp, Lonora-violet fill.
/// Lonora-specific.
class UnreadPill extends StatelessWidget {
  const UnreadPill({
    super.key,
    required this.count,
    this.muted = false,
    this.max = 99,
    this.color,
    this.semanticLabel,
  });

  final int count;

  /// The caller's localized "N unread"; English when omitted (the gallery).
  final String? semanticLabel;

  /// Muted chats show a neutral pill.
  final bool muted;
  final int max;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final label = count > max ? '$max+' : '$count';
    final bg = color ?? (muted ? ln.colors.fgSubtle : ln.colors.brand);
    return Semantics(
      label: semanticLabel ?? '$count unread',
      excludeSemantics: true,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minWidth: 20, minHeight: 20),
        child: FBadge(
          style: FBadgeStyle.primary(
            (s) => s.copyWith(
              decoration: BoxDecoration(
                color: bg,
                borderRadius: const BorderRadius.all(Radius.circular(10)),
              ),
              contentStyle: (cs) => cs.copyWith(
                labelTextStyle: ln.text.smallStrong.copyWith(
                  color: ln.colors.onAccent,
                  height: 1,
                ),
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
              ),
            ),
          ),
          child: Text(label, maxLines: 1, textDirection: TextDirection.ltr),
        ),
      ),
    );
  }
}

/// Small dot badge (unread, attention). [ring] draws a canvas-coloured outline so the dot reads on top
/// of icons and avatars.
class DotBadge extends StatelessWidget {
  const DotBadge({
    super.key,
    this.size = 8,
    this.color,
    this.ring = true,
    this.semanticLabel,
  });

  final double size;
  final Color? color;
  final bool ring;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final dot = Container(
      width: size + (ring ? 3 : 0),
      height: size + (ring ? 3 : 0),
      decoration: BoxDecoration(
        color: color ?? ln.colors.attention,
        shape: BoxShape.circle,
        border: ring ? Border.all(color: ln.colors.surface, width: 1.5) : null,
      ),
    );
    return semanticLabel == null
        ? ExcludeSemantics(child: dot)
        : Semantics(label: semanticLabel, child: dot);
  }
}

enum StatusChipKind { neutral, running, waiting, success, error, brand }

/// Compact status label ("Running", "Waiting for you", "Failed") on forui's [FBadge], with a leading
/// dot or icon. Accent colours are the palette's status colours (selection, pending, success,
/// error, brand).
class StatusChip extends StatelessWidget {
  const StatusChip({
    super.key,
    required this.label,
    this.kind = StatusChipKind.neutral,
    this.icon,
  });

  final String label;
  final StatusChipKind kind;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final accent = switch (kind) {
      StatusChipKind.neutral => c.fgMuted,
      StatusChipKind.running => c.selection,
      StatusChipKind.waiting => c.pending,
      StatusChipKind.success => c.success,
      StatusChipKind.error => c.error,
      StatusChipKind.brand => c.brand,
    };
    final bg = kind == StatusChipKind.neutral
        ? c.fill2
        : accent.withValues(alpha: c.isDark ? 0.18 : 0.12);
    // The label mixes toward the ink until it reads ≥ 4.5:1 on its tint, on the page and on a grey
    // tile (the dot keeps the accent).
    final fg = kind == StatusChipKind.neutral
        ? (c.isDark ? c.fgMuted : Color.lerp(c.fgMuted, c.fg, 0.15)!)
        : Color.lerp(accent, c.fg, c.isDark ? 0.25 : 0.55)!;
    return FBadge(
      style: FBadgeStyle.secondary(
        (s) => s.copyWith(
          decoration: BoxDecoration(
            color: bg,
            borderRadius: const BorderRadius.all(Radius.circular(12)),
          ),
          contentStyle: (cs) => cs.copyWith(
            labelTextStyle: ln.text.smallStrong.copyWith(color: fg),
            padding: const EdgeInsetsDirectional.fromSTEB(8, 4, 10, 4),
          ),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null)
            Icon(icon, size: 14, color: accent)
          else
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
            ),
          const SizedBox(width: 6),
          Text(label, maxLines: 1),
        ],
      ),
    );
  }
}
