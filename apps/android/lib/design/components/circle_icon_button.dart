import 'package:flutter/widgets.dart';

import '../theme.dart';
import '../tokens.dart';
import 'badges.dart';
import 'tappable.dart';

/// Floating circular chrome button: Ø44 in the chrome-circle fill ([LnPalette.chromeCircle], #353535
/// in dark) with a 24 dp icon; light adds a hairline rim and the chrome shadow, dark has no rim.
///
/// The widget occupies `size + 4` square so the touch target is at least 48 dp; the visible circle is
/// centred in it. Place it 2 dp closer to the edge than the visual inset you want (14 for a 16 gutter).
class CircleIconButton extends StatelessWidget {
  const CircleIconButton({
    super.key,
    required this.icon,
    required this.semanticLabel,
    this.onTap,
    this.onLongPress,
    this.size = LnSize.headerCircle,
    this.iconSize = LnSize.chromeIcon,
    this.badge = false,
    this.badgeColor,
    this.iconColor,
    this.fill,
    this.haptic = true,
  });

  /// Usually `Icon(FIcons.search)` or an `LnGlyph`; sized and tinted through [IconTheme].
  final Widget icon;
  final String semanticLabel;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final double size;
  final double iconSize;

  /// Shows a small dot at the top-end of the circle.
  final bool badge;
  final Color? badgeColor;
  final Color? iconColor;

  /// The circle's fill on a tinted surface (e.g. the agent profile gradient); defaults to
  /// [LnPalette.chromeCircle].
  final Color? fill;
  final bool haptic;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final box = size + 4 < 48 ? 48.0 : size + 4;
    return LnTappable(
      onTap: onTap,
      onLongPress: onLongPress,
      haptic: haptic,
      semanticLabel: semanticLabel,
      excludeChildSemantics: true,
      child: SizedBox.square(
        dimension: box,
        child: Center(
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              Container(
                width: size,
                height: size,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: fill ?? c.chromeCircle,
                  shape: BoxShape.circle,
                  border: Border.fromBorderSide(ln.chromeRim),
                  boxShadow: ln.chromeShadow,
                ),
                child: IconTheme.merge(
                  data: IconThemeData(size: iconSize, color: iconColor ?? c.fg),
                  child: icon,
                ),
              ),
              if (badge)
                PositionedDirectional(
                  top: size * 0.12,
                  end: size * 0.12,
                  child: DotBadge(color: badgeColor),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
