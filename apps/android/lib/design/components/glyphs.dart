import 'package:flutter/widgets.dart';

/// Lonora-drawn glyphs for the few places Lucide has no equivalent (filled tab states, the two-bar
/// sidebar menu, the send arrow). Drawn on a 24-unit canvas with Lucide-like 2-unit
/// strokes so they sit naturally next to Lucide icons.
enum LnGlyphs {
  menu(mirror: true),
  chats,
  chatsFilled,
  me,
  meFilled,
  market,
  marketFilled,
  attention,
  attentionFilled,
  sendArrow,
  stop;

  const LnGlyphs({this.mirror = false});

  /// Whether the glyph flips in right-to-left layouts.
  final bool mirror;
}

/// Paints an [LnGlyphs] glyph at [size], coloured from [color] or the ambient [IconTheme].
class LnGlyph extends StatelessWidget {
  const LnGlyph(
    this.glyph, {
    super.key,
    this.size,
    this.color,
    this.semanticLabel,
  });

  final LnGlyphs glyph;
  final double? size;
  final Color? color;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final theme = IconTheme.of(context);
    final s = size ?? theme.size ?? 24;
    final c = color ?? theme.color ?? const Color(0xFF000000);
    Widget painted = CustomPaint(
      size: Size.square(s),
      painter: _GlyphPainter(glyph, c),
    );
    if (glyph.mirror && Directionality.of(context) == TextDirection.rtl) {
      painted = Transform.flip(flipX: true, child: painted);
    }
    return Semantics(
      label: semanticLabel,
      excludeSemantics: semanticLabel == null,
      child: SizedBox.square(dimension: s, child: painted),
    );
  }
}

class _GlyphPainter extends CustomPainter {
  _GlyphPainter(this.glyph, this.color);

  final LnGlyphs glyph;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 24, size.height / 24);
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..isAntiAlias = true;
    final fill = Paint()
      ..color = color
      ..style = PaintingStyle.fill
      ..isAntiAlias = true;

    switch (glyph) {
      case LnGlyphs.menu:
        canvas.drawLine(const Offset(4, 8.5), const Offset(20, 8.5), stroke);
        canvas.drawLine(const Offset(4, 15.5), const Offset(14, 15.5), stroke);
      case LnGlyphs.chats:
        canvas.drawPath(_bubble(), stroke);
      case LnGlyphs.chatsFilled:
        canvas.drawPath(_bubble(), fill);
        canvas.drawPath(_bubble(), stroke);
      case LnGlyphs.me:
        canvas.drawCircle(const Offset(12, 7.5), 4, stroke);
        canvas.drawPath(_shoulders(), stroke);
      case LnGlyphs.meFilled:
        canvas.drawCircle(const Offset(12, 7.5), 5, fill);
        canvas.drawPath(_shoulders(), fill);
        canvas.drawPath(_shoulders(), stroke);
      case LnGlyphs.market:
        _candles(canvas, stroke, null);
      case LnGlyphs.marketFilled:
        _candles(canvas, stroke, fill);
      case LnGlyphs.attention:
        canvas.drawPath(_bell(), stroke);
        canvas.drawPath(_clapper(), stroke);
      case LnGlyphs.attentionFilled:
        canvas.drawPath(_bell(), fill);
        canvas.drawPath(_bell(), stroke);
        canvas.drawPath(_clapper(), stroke);
      case LnGlyphs.sendArrow:
        final s = stroke..strokeWidth = 2.4;
        canvas.drawLine(const Offset(12, 18.5), const Offset(12, 6), s);
        canvas.drawPath(
          Path()
            ..moveTo(6.5, 11.5)
            ..lineTo(12, 6)
            ..lineTo(17.5, 11.5),
          s,
        );
      case LnGlyphs.stop:
        canvas.drawRRect(
          RRect.fromLTRBR(7, 7, 17, 17, const Radius.circular(2.5)),
          fill,
        );
    }
    canvas.restore();
  }

  /// Round speech bubble with a short tail at the lower start corner.
  static Path _bubble() {
    const c = Offset(12, 11.4);
    const r = 8.9;
    final circle = Path()..addOval(Rect.fromCircle(center: c, radius: r));
    final tail = Path()
      ..moveTo(5.0, 15.6)
      ..lineTo(3.4, 20.9)
      ..quadraticBezierTo(3.25, 21.35, 3.7, 21.2)
      ..lineTo(9.2, 19.4)
      ..close();
    return Path.combine(PathOperation.union, circle, tail);
  }

  /// Two candlesticks (wick + body); bodies are filled when [fill] is given.
  static void _candles(Canvas canvas, Paint stroke, Paint? fill) {
    final left = RRect.fromLTRBR(4.5, 8, 10.5, 16, const Radius.circular(1.5));
    final right = RRect.fromLTRBR(
      13.5,
      5.5,
      19.5,
      12.5,
      const Radius.circular(1.5),
    );
    canvas
      ..drawLine(const Offset(7.5, 3.5), const Offset(7.5, 8), stroke)
      ..drawLine(const Offset(7.5, 16), const Offset(7.5, 20.5), stroke)
      ..drawLine(const Offset(16.5, 2.5), const Offset(16.5, 5.5), stroke)
      ..drawLine(const Offset(16.5, 12.5), const Offset(16.5, 17), stroke);
    if (fill != null) {
      canvas
        ..drawRRect(left, fill)
        ..drawRRect(right, fill);
    }
    canvas
      ..drawRRect(left, stroke)
      ..drawRRect(right, stroke);
  }

  /// Bell body: rounded dome with a flared rim on a flat base.
  static Path _bell() => Path()
    ..moveTo(3.8, 17)
    ..lineTo(20.2, 17)
    ..cubicTo(18.6, 15.3, 18, 13.4, 18, 9.8)
    ..arcToPoint(
      const Offset(6, 9.8),
      radius: const Radius.circular(6),
      clockwise: false,
    )
    ..cubicTo(6, 13.4, 5.4, 15.3, 3.8, 17)
    ..close();

  static Path _clapper() => Path()
    ..moveTo(10, 20.6)
    ..quadraticBezierTo(12, 22.4, 14, 20.6);

  static Path _shoulders() => Path()
    ..moveTo(4.5, 20.5)
    ..cubicTo(4.5, 16.4, 7.4, 14.2, 12, 14.2)
    ..cubicTo(16.6, 14.2, 19.5, 16.4, 19.5, 20.5)
    ..close();

  @override
  bool shouldRepaint(_GlyphPainter old) =>
      old.glyph != glyph || old.color != color;
}
