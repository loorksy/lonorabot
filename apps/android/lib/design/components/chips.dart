// Selectable chips: Lonora's look, built from the kit's stadium and fill tokens, first for the
// Market and Files tabs.
import 'package:flutter/widgets.dart';

import '../theme.dart';
import '../tokens.dart';
import 'tappable.dart';

/// A selectable stadium chip (filters, chart picker): 36 dp tall inside a [LnSize.minTouch] touch
/// target, the ink colour when selected, a light fill otherwise; a selection haptic on tap.
class LnChoiceChip extends StatelessWidget {
  const LnChoiceChip({
    super.key,
    required this.label,
    required this.selected,
    required this.onTap,
    this.icon,
    this.leading,
    this.textDirection,
  });

  /// Height of the visible stadium.
  static const double height = 36;

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final IconData? icon;
  final Widget? leading;

  /// Direction of [label] when it differs from the interface's (a symbol, an account number).
  final TextDirection? textDirection;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final fg = selected ? c.bg : c.fg;
    return LnTappable(
      onTap: onTap,
      haptic: true,
      selected: selected,
      semanticLabel: label,
      excludeChildSemantics: true,
      child: SizedBox(
        height: LnSize.minTouch,
        child: Center(
          widthFactor: 1,
          child: AnimatedContainer(
            duration: LnMotion.fast,
            height: height,
            padding: const EdgeInsetsDirectional.symmetric(horizontal: 14),
            decoration: BoxDecoration(
              color: selected ? c.fg : c.fill2,
              borderRadius: const BorderRadius.all(
                Radius.circular(LnRadius.stadium),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (leading != null) ...[leading!, const SizedBox(width: 6)],
                if (icon != null) ...[
                  Icon(icon, size: 16, color: fg),
                  const SizedBox(width: 6),
                ],
                Text(
                  label,
                  maxLines: 1,
                  textDirection: textDirection,
                  style: ln.text.captionStrong.copyWith(color: fg),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A horizontal strip of [LnChoiceChip]s at the page gutter, [LnSize.minTouch] tall.
class LnChipStrip extends StatelessWidget {
  const LnChipStrip({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: LnSize.minTouch,
    child: ListView.separated(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsetsDirectional.symmetric(
        horizontal: LnSpace.pageGutter,
      ),
      itemCount: children.length,
      separatorBuilder: (_, _) => const SizedBox(width: LnSpace.xs),
      itemBuilder: (_, i) => children[i],
    ),
  );
}
