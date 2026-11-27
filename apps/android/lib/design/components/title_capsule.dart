import 'package:flutter/widgets.dart';

import '../theme.dart';
import '../tokens.dart';
import 'tappable.dart';

/// Chat-header identity: a 48 dp avatar centred above a 31 dp name pill with a narrow trailing
/// chevron 8 dp after the name. The avatar is painted over the pill's top edge. The pill is the
/// chrome-circle fill (no rim in dark); the name is the 16 dp title style in the ink.
class TitleCapsule extends StatelessWidget {
  const TitleCapsule({
    super.key,
    required this.avatar,
    required this.title,
    this.onTap,
    this.semanticHint,
    this.showChevron = true,
  });

  /// Avatar widget, laid out in a 48 × 48 box.
  final Widget avatar;
  final String title;
  final VoidCallback? onTap;
  final String? semanticHint;
  final bool showChevron;

  /// Vertical distance from the avatar box top to the pill top.
  static const double pillOffset = 39.5;

  /// Total height of the widget (avatar top to pill bottom).
  static const double height = pillOffset + LnSize.namePill;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: onTap,
      haptic: true,
      semanticLabel: title,
      semanticHint: semanticHint,
      excludeChildSemantics: true,
      child: SizedBox(
        height: height,
        child: Stack(
          alignment: AlignmentDirectional.topCenter,
          clipBehavior: Clip.none,
          children: [
            Positioned(
              top: pillOffset,
              child: Container(
                height: LnSize.namePill,
                constraints: const BoxConstraints(maxWidth: 240),
                padding: EdgeInsetsDirectional.only(
                  start: 12,
                  end: showChevron ? 10 : 12,
                ),
                decoration: ShapeDecoration(
                  color: c.chromeCircle,
                  shape: StadiumBorder(side: ln.chromeRim),
                  shadows: ln.chromeShadow,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Flexible(
                      child: Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        // White in dark; light keeps the warm ink.
                        style: ln.text.title.copyWith(
                          color: c.isDark ? c.fg : c.fgWarm,
                        ),
                      ),
                    ),
                    if (showChevron) ...[
                      const SizedBox(width: 8),
                      NarrowChevron(color: c.chevron, height: 10),
                    ],
                  ],
                ),
              ),
            ),
            SizedBox.square(dimension: LnSize.avatarHeader, child: avatar),
          ],
        ),
      ),
    );
  }
}

/// The compact, tall "›" used in the name pill (5 × 12 dp by default, 1.6 dp stroke). Mirrors in
/// RTL.
class NarrowChevron extends StatelessWidget {
  const NarrowChevron({
    super.key,
    required this.color,
    this.width = 5,
    this.height = 12,
  });

  final Color color;
  final double width;
  final double height;

  @override
  Widget build(BuildContext context) {
    final rtl = Directionality.of(context) == TextDirection.rtl;
    return CustomPaint(
      size: Size(width, height),
      painter: _ChevronPainter(color, rtl),
    );
  }
}

class _ChevronPainter extends CustomPainter {
  _ChevronPainter(this.color, this.rtl);

  final Color color;
  final bool rtl;

  @override
  void paint(Canvas canvas, Size size) {
    const inset = 0.8;
    final x0 = rtl ? size.width - inset : inset;
    final x1 = rtl ? inset : size.width - inset;
    final path = Path()
      ..moveTo(x0, inset)
      ..quadraticBezierTo(x1, size.height / 2 - 1.2, x1, size.height / 2)
      ..quadraticBezierTo(x1, size.height / 2 + 1.2, x0, size.height - inset);
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.6
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );
  }

  @override
  bool shouldRepaint(_ChevronPainter old) =>
      old.color != color || old.rtl != rtl;
}
