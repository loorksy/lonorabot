// CustomPainter that draws one avatar frame exactly as the native SVG renderer composes it
// (apps/mobile/components/bot-avatar.tsx:229-300): shell + radial shade, visor clipped to
// the sphere and moved by turn/gaze/poke, glyph strokes with round caps (goo filter at
// ≥ 48 px), then the gloss highlight. All drawing happens in the SVG's 400-unit space.
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';

import 'motion.dart';

const double _deg = math.pi / 180;
const Offset _center = Offset(AvatarGeometry.shellCx, AvatarGeometry.shellCy);
const double _cy = AvatarGeometry.centerY;
const Color _visorColor = Color(0xFF0D0D11);
final Rect _faceRect = Rect.fromLTWH(
  AvatarGeometry.faceX,
  AvatarGeometry.faceY,
  AvatarGeometry.faceWidth,
  AvatarGeometry.faceHeight,
);
final RRect _visor = RRect.fromRectXY(
  _faceRect,
  AvatarGeometry.faceRx,
  AvatarGeometry.faceRx,
);
final Path _sphere = Path()
  ..addOval(Rect.fromCircle(center: _center, radius: AvatarGeometry.shellR));

// <radialGradient cx=".34" cy=".27" r=".95"> on the shell's bounding box (23..377).
final Paint _shade = Paint()
  ..shader = ui.Gradient.radial(
    const Offset(23 + 0.34 * 354, 23 + 0.27 * 354),
    0.95 * 354,
    const [
      Color.fromRGBO(255, 255, 255, 0.4),
      Color.fromRGBO(255, 255, 255, 0),
      Color.fromRGBO(0, 0, 0, 0),
      Color.fromRGBO(0, 0, 0, 0.42),
    ],
    const [0, 0.38, 0.6, 1],
  );

// Gloss ellipse: white .5 → 0, group opacity .55, drawn as a unit circle under scale.
final Paint _gloss = Paint()
  ..shader = ui.Gradient.radial(Offset.zero, 1, const [
    Color.fromRGBO(255, 255, 255, 0.5 * 0.55),
    Color.fromRGBO(255, 255, 255, 0),
  ]);

/// SVG goo: feGaussianBlur → feColorMatrix alpha × 20 − 9.5 (a soft threshold).
ui.ImageFilter _goo(double sigma) => ui.ImageFilter.compose(
  outer: const ColorFilter.matrix(<double>[
    1, 0, 0, 0, 0, //
    0, 1, 0, 0, 0, //
    0, 0, 1, 0, 0, //
    0, 0, 0, 20, -9.5 * 255,
  ]),
  inner: ui.ImageFilter.blur(
    sigmaX: sigma,
    sigmaY: sigma,
    tileMode: TileMode.decal,
  ),
);

/// Everything one frame needs; the widget mutates it and calls [notify] to repaint.
class AvatarScene extends ChangeNotifier {
  AvatarScene({required this.bars, required this.shell});

  List<AvatarBar> bars;
  Color shell;

  /// Gaze (−1…1), poke squash (0…0.8) and turn yaw (radians).
  double gazeX = 0, gazeY = 0, poke = 0, yaw = 0;

  /// Tap-reaction transform of the glyph group; skipped when [moving] is false.
  double barScale = 1, barOffsetY = 0, barTilt = 0;
  bool moving = false;

  /// Resting face (not the signal bars): lighter goo and glow.
  bool facial = false;

  /// Goo filter on (the native renderer enables it from 48 px).
  bool goo = false;

  void notify() => notifyListeners();
}

class AvatarPainter extends CustomPainter {
  AvatarPainter(this.scene) : super(repaint: scene);

  final AvatarScene scene;

  @override
  void paint(Canvas canvas, Size size) {
    final s = math.min(size.width, size.height) / AvatarGeometry.viewBoxSize;
    canvas.save();
    canvas.translate(
      (size.width - AvatarGeometry.viewBoxSize * s) / 2,
      (size.height - AvatarGeometry.viewBoxSize * s) / 2,
    );
    canvas.scale(s);
    canvas.translate(-AvatarGeometry.viewBoxX, -AvatarGeometry.viewBoxY);

    canvas.drawCircle(
      _center,
      AvatarGeometry.shellR,
      Paint()..color = scene.shell,
    );
    canvas.drawCircle(_center, AvatarGeometry.shellR, _shade);

    final turn = avatarTurn(scene.yaw);
    if (turn.opacity > 0) {
      canvas.save();
      canvas.clipPath(_sphere);
      if (turn.opacity < 1) {
        canvas.saveLayer(
          _sphere.getBounds(),
          Paint()..color = Color.fromRGBO(0, 0, 0, turn.opacity),
        );
      }
      // translate(200+tx 200.5) scale(scaleX 1) translate(-200 -200.5)
      canvas.translate(200 + turn.tx, _cy);
      canvas.scale(turn.scaleX, 1);
      canvas.translate(-200, -_cy);
      // translate rotate skewY scale translate (faceTransform)
      final look = faceTransform(scene.gazeX, scene.gazeY, scene.poke);
      canvas.translate(200 + look.tx, _cy + look.ty);
      canvas.rotate(look.rot * _deg);
      canvas.skew(0, math.tan(look.skew * _deg));
      canvas.scale(look.sx, look.sy);
      canvas.translate(-200, -_cy);

      canvas.drawRRect(_visor, Paint()..color = _visorColor);
      canvas.clipRRect(_visor);
      if (scene.moving) {
        canvas.translate(200, _cy + scene.barOffsetY);
        canvas.rotate(scene.barTilt * _deg);
        canvas.scale(scene.barScale);
        canvas.translate(-200, -_cy);
      }
      if (scene.goo) {
        final gooSigma = scene.facial ? FaceTokens.gooBlur : 1.65;
        final glowSigma = scene.facial ? FaceTokens.glowBlur : 5.0;
        final glowOpacity = scene.facial ? FaceTokens.glowOpacity : 1.0;
        canvas.saveLayer(
          _faceRect,
          Paint()
            ..color = Color.fromRGBO(0, 0, 0, glowOpacity)
            ..imageFilter = ui.ImageFilter.compose(
              outer: ui.ImageFilter.blur(
                sigmaX: glowSigma,
                sigmaY: glowSigma,
                tileMode: TileMode.decal,
              ),
              inner: _goo(gooSigma),
            ),
        );
        _drawBars(canvas);
        canvas.restore();
        canvas.saveLayer(_faceRect, Paint()..imageFilter = _goo(gooSigma));
        _drawBars(canvas);
        canvas.restore();
      } else {
        _drawBars(canvas);
      }
      if (turn.opacity < 1) canvas.restore();
      canvas.restore();
    }

    // <ellipse cx=150 cy=82 rx=86 ry=38 transform="rotate(-24 150 82)">
    canvas.save();
    canvas.translate(150, 82);
    canvas.rotate(-24 * _deg);
    canvas.scale(86, 38);
    canvas.drawCircle(Offset.zero, 1, _gloss);
    canvas.restore();
    canvas.restore();
  }

  void _drawBars(Canvas canvas) {
    for (final bar in scene.bars) {
      final width = math.max(bar.w * glyphScale, 0.01);
      if (width < 0.05 || bar.o <= 0) continue;
      final color = Color.fromRGBO(
        bar.r.round().clamp(0, 255),
        bar.g.round().clamp(0, 255),
        bar.b.round().clamp(0, 255),
        bar.o.clamp(0.0, 1.0),
      );
      if (bar.len * glyphScale < 0.05) {
        // A zero-length round-capped stroke is a dot; draw it explicitly.
        canvas.drawCircle(
          Offset(
            200 + (bar.cx - 200) * glyphScale,
            _cy + (bar.cy - _cy) * glyphScale,
          ),
          width / 2,
          Paint()..color = color,
        );
        continue;
      }
      final points = avatarBarPoints(bar);
      final path = Path()..moveTo(points.first.$1, points.first.$2);
      for (var i = 1; i < points.length; i++) {
        path.lineTo(points[i].$1, points[i].$2);
      }
      canvas.drawPath(
        path,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = width
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round,
      );
    }
  }

  @override
  bool shouldRepaint(AvatarPainter oldDelegate) => oldDelegate.scene != scene;
}

/// Gold "trades on its own" ring: 2 px stroke whose outer edge sits 3 px outside the
/// avatar (bot-avatar.tsx:306-312). Paint it over a box inflated by 3 px.
class AvatarRingPainter extends CustomPainter {
  const AvatarRingPainter();

  static const Color gold = Color(0xFFF0C866);

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawCircle(
      size.center(Offset.zero),
      size.shortestSide / 2 - 1,
      Paint()
        ..color = gold
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2,
    );
  }

  @override
  bool shouldRepaint(AvatarRingPainter oldDelegate) => false;
}

/// Crown badge, 20-unit viewBox: a disc in the page background and the gold crown
/// `M4 7 7 9 10 4 13 9 16 7 14 14H6Z` (bot-avatar.tsx:313-322).
class AvatarCrownPainter extends CustomPainter {
  const AvatarCrownPainter(this.background);

  final Color background;

  static final Path _crown = Path()
    ..moveTo(4, 7)
    ..lineTo(7, 9)
    ..lineTo(10, 4)
    ..lineTo(13, 9)
    ..lineTo(16, 7)
    ..lineTo(14, 14)
    ..lineTo(6, 14)
    ..close();

  @override
  void paint(Canvas canvas, Size size) {
    canvas.scale(size.shortestSide / 20);
    canvas.drawCircle(const Offset(10, 10), 10, Paint()..color = background);
    canvas.drawPath(_crown, Paint()..color = AvatarRingPainter.gold);
  }

  @override
  bool shouldRepaint(AvatarCrownPainter oldDelegate) =>
      oldDelegate.background != background;
}
