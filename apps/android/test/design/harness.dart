// Golden-test harness for the design system: themed app wrapper, viewport setup, and simple
// placeholder art (coloured geometric avatars, a bar-chart illustration) drawn in code, so the
// goldens need no image assets.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/design/design.dart';

/// Android's default family, registered by `loadAppFonts` (the test engine has no system font).
const testFontFamily = 'Roboto';

/// Arabic fallback family registered by `loadAppFonts` (the test engine has no system fallback).
const testFontFallback = ['NotoNaskhArabic'];

/// Golden viewport: 393 × 852 logical px at DPR 2.
const goldenSize = Size(393, 852);

/// Runs [body] with real (blurred) box shadows. flutter_test replaces shadow blur with a hard offset
/// copy by default (`debugDisableShadows`), which would make shadow comparisons meaningless.
Future<void> withRealShadows(Future<void> Function() body) async {
  debugDisableShadows = false;
  try {
    await body();
  } finally {
    debugDisableShadows = true;
  }
}

void setGoldenViewport(
  WidgetTester tester, {
  Size size = goldenSize,
  double dpr = 2,
}) {
  tester.view.physicalSize = size * dpr;
  tester.view.devicePixelRatio = dpr;
  addTearDown(tester.view.reset);
}

LnThemeData testTheme(Brightness b) => LnThemeData.fromPalette(
  b == Brightness.dark ? LnPalette.dark : LnPalette.light,
  fontFamily: testFontFamily,
  fontFamilyFallback: testFontFallback,
);

/// Wraps [child] the way the app does: MaterialApp (Lonora Material theme) → FTheme → LnTheme, with
/// optional RTL and simulated system insets.
Widget lnTestApp({
  required Widget child,
  Brightness brightness = Brightness.light,
  TextDirection direction = TextDirection.ltr,
  EdgeInsets padding = EdgeInsets.zero,
}) {
  final palette = brightness == Brightness.dark
      ? LnPalette.dark
      : LnPalette.light;
  return MaterialApp(
    debugShowCheckedModeBanner: false,
    theme: lnMaterialTheme(
      palette,
      fontFamily: testFontFamily,
      fontFamilyFallback: testFontFallback,
    ),
    builder: (context, app) => MediaQuery(
      data: MediaQuery.of(context)
          .copyWith(padding: padding, viewPadding: padding),
      child: Directionality(
        textDirection: direction,
        child: FTheme(
          data: lnForuiTheme(
            palette,
            fontFamily: testFontFamily,
            fontFamilyFallback: testFontFallback,
          ),
          child: LnTheme(
            data: testTheme(brightness),
            child: FToaster(child: app!),
          ),
        ),
      ),
    ),
    home: Builder(
      builder: (context) =>
          ColoredBox(color: context.ln.colors.bg, child: child),
    ),
  );
}

/// Placeholder avatar shapes (test-only): plain geometric marks, no faces.
enum FakeShape { circle, square, diamond, hexagon }

class FakeAvatar extends StatelessWidget {
  const FakeAvatar(this.shape, this.color, {super.key, this.size});

  final FakeShape shape;
  final Color color;
  final double? size;

  // Shell colours of Lonora's avatar palette (lib/avatar/src/avatar_colors.dart).
  static const violet = Color(0xFF8B5CF6);
  static const green = Color(0xFF10B981);
  static const orange = Color(0xFFF97316);
  static const cyan = Color(0xFF06B6D4);
  static const slate = Color(0xFF64748B);

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, c) {
      final s = size ?? math.min(c.maxWidth, c.maxHeight);
      return Center(
        child: CustomPaint(
          size: Size.square(s),
          painter: _AvatarPainter(shape, color),
        ),
      );
    },
  );
}

class _AvatarPainter extends CustomPainter {
  _AvatarPainter(this.shape, this.color);

  final FakeShape shape;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 24);
    final p = Paint()..color = color;
    switch (shape) {
      case FakeShape.circle:
        canvas.drawCircle(const Offset(12, 12), 11, p);
      case FakeShape.square:
        canvas.drawRRect(
          RRect.fromLTRBR(2, 2, 22, 22, const Radius.circular(5)),
          p,
        );
      case FakeShape.diamond:
        canvas.translate(12, 12);
        canvas.rotate(math.pi / 4);
        canvas.drawRRect(
          RRect.fromLTRBR(-7.8, -7.8, 7.8, 7.8, const Radius.circular(3)),
          p,
        );
      case FakeShape.hexagon:
        final path = Path();
        for (var i = 0; i < 6; i++) {
          final a = -math.pi / 2 + i * math.pi / 3;
          final pt = Offset(12 + 11.5 * math.cos(a), 12 + 11.5 * math.sin(a));
          i == 0 ? path.moveTo(pt.dx, pt.dy) : path.lineTo(pt.dx, pt.dy);
        }
        canvas.drawPath(path..close(), p);
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_AvatarPainter old) =>
      old.shape != shape || old.color != color;
}

/// Placeholder illustration for an action card's header: a small rising bar chart.
class FakeChartIllustration extends StatelessWidget {
  const FakeChartIllustration({super.key});

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    const heights = [18.0, 30.0, 24.0, 42.0, 56.0];
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        for (final (i, h) in heights.indexed) ...[
          if (i > 0) const SizedBox(width: 8),
          Container(
            width: 14,
            height: h,
            decoration: BoxDecoration(
              color: i == heights.length - 1 ? c.positive : c.fgSubtle,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
        ],
      ],
    );
  }
}
