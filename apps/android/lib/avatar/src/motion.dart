// Pure motion and geometry maths of the Lonora avatar.
//
// Faithful Dart port of packages/core/src/trading-avatar-motion.js (the DOM-free part:
// geometry, faces, facial tokens, the twenty states, expressions, personality, morph
// planning, sampling, reactions, idle pose, turn and face transform). The SVG markup,
// pointer binding and browser controller (js:1426-1936) are replaced by the Flutter widget.
// Function structure and constants follow the source; JS line ranges are cited per block.
// Naming: the JS segment field `L` (centre-line length) is `len` here.
import 'dart:math' as math;

import 'avatar_state.dart';

const double _tau = math.pi * 2; // js:19
const double _deg = math.pi / 180; // js:20

/* ───────────────────────── geometry (400-unit space), js:22-36 ───────────────────────── */

/// Fixed avatar geometry in the 400-unit SVG space (`GEOMETRY`, js:23-31).
abstract final class AvatarGeometry {
  /// `viewBox="22 22 356 356"`.
  static const double viewBoxX = 22, viewBoxY = 22, viewBoxSize = 356;
  static const double shellCx = 200, shellCy = 200, shellR = 177;
  static const double faceX = 78,
      faceY = 123,
      faceWidth = 244,
      faceHeight = 155,
      faceRx = 77.5;
  static const double barWidth = 26;
  static const List<double> barX = [140, 180, 220, 260];
  static const double centerY = 200.5;
  static const double floorY = 241;
  static const List<double> restHeights = [39, 60, 81, 49];
}

const double _w = AvatarGeometry.barWidth; // js:32-36
const List<double> _xs = AvatarGeometry.barX;
const double _cy = AvatarGeometry.centerY;
const double _floor = AvatarGeometry.floorY;
const List<double> _rest = AvatarGeometry.restHeights;

/* ───────────────────────────── faces, js:62-86 ───────────────────────────── */

/// Face ids in catalogue order (`AVATAR_FACES`, js:62-81).
const List<String> avatarFaceIds = [
  'orb',
  'face-smile',
  'face-thoughtful',
  'face-happy',
  'face-wink',
  'face-sleepy',
  'face-surprised',
  'face-angry',
  'face-playful',
  'face-excited',
  'face-skeptical',
  'face-dreamy',
  'face-focused',
  'face-worried',
  'face-laugh',
  'face-determined',
];

/// Existing shell identifiers retain the legacy signal face (js:83-86): unknown → `orb`.
String resolveAvatarFace(String? value) =>
    avatarFaceIds.contains(value) ? value! : 'orb';

const double _baseSeconds = 2.8; // js:88
const double _morphSeconds = 0.95; // js:89 shape → shape travel time
const double _morphDelay = 0.07; // js:90 stagger between signals

/// `MORPH` (js:1291).
abstract final class AvatarMorph {
  static const double seconds = _morphSeconds;
  static const double delay = _morphDelay;
}

/* ───────────────────────────── math helpers, js:92-123 ───────────────────────────── */

double _clamp(double x, [double a = 0, double b = 1]) =>
    x < a ? a : (x > b ? b : x);
double _lerp(double a, double b, double t) => a + (b - a) * t;
double _wrap(double x) => x - x.floorToDouble();
double _wrapSigned(double x) {
  x = _wrap(x);
  return x > 0.5 ? x - 1 : x;
}

double _smooth(double x) {
  x = _clamp(x);
  return x * x * (3 - 2 * x);
}

double _inOut(double x) {
  x = _clamp(x);
  return x < 0.5 ? 4 * x * x * x : 1 - math.pow(-2 * x + 2, 3).toDouble() / 2;
}

double _outCubic(double x) => 1 - math.pow(1 - _clamp(x), 3).toDouble();
double _inCubic(double x) {
  x = _clamp(x);
  return x * x * x;
}

double _spring(double x, [double z = 0.7, double w = 7.3]) {
  x = _clamp(x);
  final wd = w * math.sqrt(1 - z * z), k = (z * w) / wd;
  double raw(double t) =>
      1 - math.exp(-z * w * t) * (math.cos(wd * t) + k * math.sin(wd * t));
  return raw(x) + (1 - raw(1)) * x * x * x;
}

double _bump(double d, double r) {
  d = d.abs();
  return d >= r ? 0 : 0.5 * (1 + math.cos((math.pi * d) / r));
}

double _seg(double u, double a, double b) => _clamp((u - a) / (b - a));

/// JS `%` is a truncating remainder; Dart's `remainder` matches it exactly.
double _lerpAng(double a, double b, double t) =>
    a + ((((b - a + 540).remainder(360)) + 360).remainder(360) - 180) * t;

/// V8's `Math.hypot` (max-scaled Kahan sum), so morph costs tie-break as on web.
double _hypot(double x, double y) {
  final ax = x.abs(), ay = y.abs();
  final max = ax > ay ? ax : ay;
  if (max == 0) return 0;
  // V8 normalises by the largest magnitude and Kahan-sums the squares; for two terms the
  // compensation after the first is always zero, so this is the same arithmetic.
  final a = ax / max, b = ay / max;
  return math.sqrt(a * a + b * b) * max;
}

/// How large the glyph is drawn inside the visor (`GLYPH_SCALE`, js:125).
const double glyphScale = 1.1;
const int _n = 8; // js:126 particles that make up the one liquid mass

/// Number of glyph particles (`PARTICLES`, js:1289).
const int avatarParticles = _n;

/* ─────────────── facial coordinate system, FACE_TOKENS / FACIAL_GEOMETRY, js:128-242 ─────────────── */

const double _facialUnit = AvatarGeometry.barWidth;
const double _eyeHalfSpacing = (260 - 140) * 0.35;
const double _eyeLine = -AvatarGeometry.faceHeight * 0.055;
const double _primaryStroke = _facialUnit * 0.68,
    _secondaryStroke = _facialUnit * 0.44;
const double _browStroke = _facialUnit * 0.32,
    _accentStroke = _facialUnit * 0.29;
const double _eyeHeight = 39, _eyeArcRadius = _primaryStroke * 0.72;
const double _eyeArcSpan = 140, _mouthArcSpan = 110;
const double _mouthWidth = _facialUnit * 1.6;
final double _eyeArcCorrection =
    (_eyeArcRadius * (1 + math.cos((_eyeArcSpan * _deg) / 2))) / 2;
final double _mouthRadius =
    (_mouthWidth - _secondaryStroke) /
    (2 * math.sin((_mouthArcSpan * _deg) / 2));
final double _mouthCorrection =
    (_mouthRadius * (1 + math.cos((_mouthArcSpan * _deg) / 2))) / 2;
const double _minimumSeparation = _facialUnit * 0.2;
const double _browLine =
    _eyeLine - _eyeHeight / 2 - _minimumSeparation - _browStroke;
const double _mouthLine = AvatarGeometry.faceHeight * 0.185;
const double _expressionHalfWidth =
    (AvatarGeometry.faceWidth * 0.35) / glyphScale;
const double _expressionHalfHeight =
    (AvatarGeometry.faceHeight * 0.41) / glyphScale;

/// Canonical facial design tokens (`FACE_TOKENS`, js:152-207).
abstract final class FaceTokens {
  // stroke
  static const double strokePrimary = _primaryStroke;
  static const double strokeCurvedEye = _primaryStroke * 0.8;
  static const double strokeSecondary = _secondaryStroke;
  static const double strokeEyebrow = _browStroke;
  static const double strokeAccent = _accentStroke;
  static const double strokeIndicator = _accentStroke * 1.08;
  // shape
  static const double eyeWidth = _primaryStroke;
  static const double eyeHeight = _eyeHeight;
  static const double eyeArcRadius = _eyeArcRadius;
  static const double eyeArcSpan = _eyeArcSpan;
  static const double eyebrowLength = _facialUnit * 1.08;
  static const double eyebrowRise = _browStroke;
  static const double mouthWidth = _mouthWidth;
  static final double mouthRadius = _mouthRadius;
  static const double mouthArcSpan = _mouthArcSpan;
  static const double laughingMouthScale = 1.12;
  static const double roundMouthRadius = _secondaryStroke * 0.88;
  static const double tongueWidth = _primaryStroke * 0.75;
  static const double tongueLength = _secondaryStroke * 0.25;
  static const double winkHalfWidth = _primaryStroke * 0.4;
  static const double winkHalfHeight = _eyeHeight * 0.3;
  static const double closedEyeLength = _eyeHeight - _primaryStroke;
  static const double accentLength = _facialUnit * 0.42;
  static const double accentRadius = _facialUnit * 0.36;
  static const double questionRadius = _facialUnit * 0.34;
  static const double cornerRadius = _secondaryStroke / 2;
  // spacing
  static const double eyeHalfSpacing = _eyeHalfSpacing;
  static const double eyeLine = _eyeLine;
  static const double browLine = _browLine;
  static const double mouthLine = _mouthLine;
  static const double minimumSeparation = _minimumSeparation;
  static const double accentPitch = _facialUnit * 0.72;
  static const double accentLine = -_facialUnit * 1.52;
  static const double sideAccentX = _eyeHalfSpacing + _facialUnit * 0.7;
  static const double tongueLine = _mouthLine + _secondaryStroke * 0.9;
  static const double sideAccentLine = -_facialUnit * 1.05;
  // optical
  static final double eyeArcCorrection = _eyeArcCorrection;
  static final double mouthCorrection = _mouthCorrection;
  static const double openMouthOffset = _secondaryStroke * 0.34;
  static const double thoughtfulEyeOffset = _facialUnit * 0.035;
  static const double focusedMouthOffset = _facialUnit * 0.16;
  // motion
  static const double breathAmplitude = _facialUnit * 0.025;
  static const double blinkPhase = 0.82;
  static const double blinkHalfDuration = 0.035;
  static const double blinkStrokeRatio = 0.65;
  // render
  static const double gooBlur = 0.5;
  static const double glowBlur = 2;
  static const double glowOpacity = 0.16;
}

/// Shared facial anchors (`FACIAL_GEOMETRY`, js:208-242), in the unscaled glyph space.
abstract final class FacialGeometry {
  static const double horizontalCenter = AvatarGeometry.shellCx;
  static const double verticalCenter = AvatarGeometry.centerY;
  static const (double, double) leftEye = (
    200 - _eyeHalfSpacing,
    _cy + _eyeLine,
  );
  static const (double, double) rightEye = (
    200 + _eyeHalfSpacing,
    _cy + _eyeLine,
  );
  static const (double, double) leftEyebrow = (
    200 - _eyeHalfSpacing,
    _cy + _browLine,
  );
  static const (double, double) rightEyebrow = (
    200 + _eyeHalfSpacing,
    _cy + _browLine,
  );
  static const (double, double) mouth = (200, _cy + _mouthLine);
  static const double boundsHalfWidth = _expressionHalfWidth;
  static const double boundsHalfHeight = _expressionHalfHeight;

  /// Rendered facial safe area `(x, y, width, height)` = (114.6, 136.95, 170.8, 127.1).
  static const (double, double, double, double) safeArea = (
    200 - _expressionHalfWidth * glyphScale,
    _cy - _expressionHalfHeight * glyphScale,
    _expressionHalfWidth * glyphScale * 2,
    _expressionHalfHeight * glyphScale * 2,
  );
}

/* ───────────────────────────── segment model, js:243-302 ───────────────────────────── */

/// One signal: a stroked arc with centre ([cx], [cy]), centre-line length [len], heading
/// [th]° at the middle (0 = right, 90 = down), curvature [k] (1/radius), stroke width [w],
/// opacity [o], accent tint [c] and optional accent colour [ar]. Pose samples also carry
/// the resolved stroke colour [r], [g], [b] (`BarPose`).
class AvatarBar {
  AvatarBar({
    this.i = 0,
    this.cx = 200,
    this.cy = _cy,
    this.len = 0.01,
    this.th = 90,
    this.k = 0,
    this.w = 0.01,
    this.o = 1,
    this.c = 0,
    this.ar,
    this.r = 248,
    this.g = 248,
    this.b = 251,
  });

  int i;
  double cx, cy, len, th, k, w, o, c;
  List<double>? ar;
  double r, g, b;

  AvatarBar copy() => AvatarBar(
    i: i,
    cx: cx,
    cy: cy,
    len: len,
    th: th,
    k: k,
    w: w,
    o: o,
    c: c,
    ar: ar,
    r: r,
    g: g,
    b: b,
  );

  @override
  String toString() =>
      'AvatarBar(cx: $cx, cy: $cy, len: $len, th: $th, k: $k, w: $w, o: $o, rgb: $r,$g,$b)';
}

typedef _T = FaceTokens;
typedef _Shape = (double x, double y, double len, double th, double k);
typedef _Put = void Function(
  AvatarBar b,
  double x,
  double y,
  double len,
  double th,
  double k,
  double w,
  double o,
  double c,
);

// js:251 hidden particle (zero width)
void _h(AvatarBar b, [double x = 0, double y = 0]) =>
    _g(b, x, y, 0.01, 0, 0, 0.01, 1, 0);
// js:252-262
void _g(
  AvatarBar b,
  double x,
  double y,
  double len,
  double th, [
  double k = 0,
  double w = 16,
  double o = 1,
  double c = 0,
]) {
  b.cx = 200 + x;
  b.cy = _cy + y;
  b.len = math.max(len, 0.01);
  b.th = th;
  b.k = k;
  b.w = w;
  b.o = o;
  b.c = c;
  b.ar = null;
}

void _gs(AvatarBar b, _Shape s, double w, double o, double c) =>
    _g(b, s.$1, s.$2, s.$3, s.$4, s.$5, w, o, c);
void _ps(_Put f, AvatarBar b, _Shape s, double w, double o, double c) =>
    f(b, s.$1, s.$2, s.$3, s.$4, s.$5, w, o, c);

// js:264-266 legacy "vertical capsule" pose: h = outer height, y = centre offset, dx, rot°
double _sit(double h) => _floor - _cy - h / 2;
void _p(
  AvatarBar b,
  double h,
  double y, [
  double o = 1,
  double c = 0,
  double dx = 0,
  double rot = 0,
  double w = _w,
]) =>
    _g(b, _xs[b.i] - 200 + dx, y, math.max(h - w, 0.01), 90 + rot, 0, w, o, c);

// js:268-281 shape builders → [x, y, L, th, k]
_Shape _arc(double ccx, double ccy, double r, double alpha, double span) => (
  ccx + r * math.cos(alpha * _deg),
  ccy + r * math.sin(alpha * _deg),
  r * span * _deg,
  alpha + 90,
  1 / r,
);
_Shape _line(double x0, double y0, double x1, double y1) => (
  (x0 + x1) / 2,
  (y0 + y1) / 2,
  _hypot(x1 - x0, y1 - y0),
  math.atan2(y1 - y0, x1 - x0) / _deg,
  0,
);

// js:283-288 glyph-level transform: offset, rotation, scale
_Put _x([double ox = 0, double oy = 0, double psi = 0, double s = 1]) {
  final c = math.cos(psi * _deg), n = math.sin(psi * _deg);
  return (b, x, y, len, th, k, w, o, col) => _g(
    b,
    (x * c - y * n) * s + ox,
    (x * n + y * c) * s + oy,
    len * s,
    th + psi,
    k / s,
    w * s,
    o,
    col,
  );
}

/* 🕯 candle = body + wick, js:290-321 */
const List<double> _green = [52, 225, 150], _red = [251, 113, 133];
const double _oy = 12;
void _candle(
  List<AvatarBar> bars,
  int i,
  double o,
  double c,
  double hi,
  double lo, [
  double op = 1,
  double tintAmt = 1,
  double rot = 0,
  double dx = 0,
  double w = 22,
]) {
  final x = _xs[i] - 200 + dx,
      top = math.min(o, c) + _oy,
      bot = math.max(o, c) + _oy,
      my = (top + bot) / 2,
      wk = (hi + lo) / 2 + _oy;
  final up = _smooth((o - c) / 8 + 0.5),
      col = [
        _lerp(_red[0], _green[0], up),
        _lerp(_red[1], _green[1], up),
        _lerp(_red[2], _green[2], up),
      ];
  final r = rot * _deg;
  void put(AvatarBar b, double d, double len, double ww) {
    _g(
      b,
      x - d * math.sin(r),
      d * math.cos(r),
      len,
      90 + rot,
      0,
      ww,
      op,
      tintAmt,
    );
    b.ar = col;
  }

  put(bars[2 * i], my, math.max(bot - top - w, 0.01), w);
  // JS Math.round rounds halves up; operands here are positive so .round() agrees.
  final ww = math.max(8, (w * 0.45).round()).toDouble();
  put(bars[2 * i + 1], wk, math.max(lo - hi - ww, 0.01), ww);
}

const List<double> _co = [-20, 28, 12, -4],
    _cc = [24, -12, -32, -54]; // js:318-321
const List<double> _chi = [-29, -21, -41, -63], _clo = [33, 37, 21, 5];

const List<List<double>> _celebrate = [
  [255, 209, 102],
  [102, 244, 178],
  [125, 211, 252],
  [255, 158, 192],
]; // js:323-328

/* ───────────────────────────── the 20 states, js:330-806 ───────────────────────────── */

double _sendX(double u) => u < 0.34
    ? 56 * _inCubic(u / 0.34)
    : u < 0.5
    ? 56 + 120 * _seg(u, 0.34, 0.5)
    : u < 0.56
    ? -130
    : -130 + 130 * _outCubic(_seg(u, 0.56, 0.88)); // js:331-338

class _StateDef {
  const _StateDef({
    required this.k,
    this.fluid,
    required this.poster,
    this.gaze,
    this.accent,
    required this.fn,
  });

  /// Loop length factor: loop seconds = 2.8 × k.
  final double k;
  final double? fluid;

  /// Phase shown when motion is reduced.
  final double poster;
  final (double, double) Function(double u)? gaze;
  final String? accent;
  final void Function(double u, List<AvatarBar> b) fn;
}

final Map<LonoraAvatarState, _StateDef> _states = {
  /* Four smooth, bottom-aligned capsules are the idle identity; no price wicks. js:341-353 */
  LonoraAvatarState.waiting: _StateDef(
    k: 0.72,
    fluid: 0.15,
    poster: 0,
    fn: (u, b) {
      for (var i = 0; i < 4; i++) {
        final h = _rest[i] + (i == 2 ? 4 : 2) * math.sin(_tau * u);
        _p(b[i], h, _sit(h), 1, i == 2 ? 1 : 0);
        if (i == 2) b[i].ar = [31, 212, 179];
      }
    },
  ),
  // js:354-367
  LonoraAvatarState.sleeping: _StateDef(
    k: 2.6,
    fluid: 0.15,
    poster: 0.3,
    gaze: (_) => (0, 0.4),
    fn: (u, b) {
      for (var i = 0; i < 4; i++) {
        final s = 0.5 + 0.5 * math.sin(_tau * (u - i * 0.1)), e = 10 + 6 * s;
        _candle(b, i, -2, 2, -e, e, 1, 0.12, 0, 0, 16);
        for (final bar in [b[2 * i], b[2 * i + 1]]) {
          bar.o = 0.35 + 0.25 * s;
        }
      }
    },
  ),
  // js:368-379
  LonoraAvatarState.thinking: _StateDef(
    k: 0.62,
    poster: 0.12,
    gaze: (_) => (0.5, -0.5),
    fn: (u, b) {
      for (var i = 0; i < 4; i++) {
        final p = _wrap(u - i * 0.13),
            a = p < 0.55 ? math.sin((math.pi * p) / 0.55) : 0.0;
        _g(
          b[i],
          _xs[i] - 200,
          12 - 40 * a,
          0.01 + 14 * a,
          90,
          0,
          28 - 4 * a,
          1,
          0.3 + 0.5 * a,
        );
      }
    },
  ),
  // js:380-397
  LonoraAvatarState.analyzing: _StateDef(
    k: 1.3,
    fluid: 0.15,
    poster: 0.32,
    fn: (u, b) {
      const m = <double>[10, 4, -2, -8],
          aa = <double>[10, 12, 10, 14],
          bm = <double>[26, 28, 30, 34],
          a = <double>[0, 0.31, 0.62, 0.17],
          bb = <double>[0.45, 0.1, 0.75, 0.33];
      for (var i = 0; i < 4; i++) {
        final o = m[i] + aa[i] * math.sin(_tau * (u + a[i])),
            c =
                m[i] +
                bm[i] * math.sin(_tau * (2 * u + bb[i])) -
                6 * math.sin(_tau * (u + a[i] + 0.2));
        final hi =
                math.min(o, c) -
                7 -
                5 * (0.5 + 0.5 * math.sin(_tau * (3 * u + a[i]))),
            lo =
                math.max(o, c) +
                7 +
                5 * (0.5 + 0.5 * math.sin(_tau * (3 * u + bb[i])));
        _candle(b, i, o, c, hi, lo, 1, 1);
      }
    },
  ),
  // js:398-411
  LonoraAvatarState.inspecting: _StateDef(
    k: 1.5,
    fluid: 0.15,
    poster: 0.5,
    gaze: (u) =>
        ((((0.5 - 0.5 * math.cos(_tau * u)) * 3 - 1.5) / 1.5) * 0.85, 0),
    fn: (u, b) {
      final pos = (0.5 - 0.5 * math.cos(_tau * u)) * 3;
      for (var i = 0; i < 4; i++) {
        final g = _bump(i - pos, 1.3), cc = _lerp(_co[i], _cc[i], 1 + 0.35 * g);
        _candle(
          b,
          i,
          _co[i],
          cc,
          _chi[i] - 8 * g,
          _clo[i] + 8 * g,
          1,
          0.3 + 0.7 * g,
        );
      }
    },
  ),
  // js:412-425
  LonoraAvatarState.reviewing: _StateDef(
    k: 1.8,
    fluid: 0.15,
    poster: 0.72,
    fn: (u, b) {
      final fade = _smooth(_seg(u, 0.88, 0.99)), all = _bump(u - 0.8, 0.07);
      for (var i = 0; i < 4; i++) {
        final a =
                _spring(_seg(u, 0.06 + 0.17 * i, 0.06 + 0.17 * i + 0.1)) *
                (1 - fade),
            cc = _lerp(_co[i], _cc[i], 1 + 0.2 * a + 0.15 * all);
        _candle(
          b,
          i,
          _co[i],
          cc,
          _chi[i] - 6 * a,
          _clo[i] + 6 * a,
          1,
          0.3 + 0.7 * _clamp(a),
        );
      }
    },
  ),
  // js:426-443
  LonoraAvatarState.listening: _StateDef(
    k: 1.0,
    fluid: 0.15,
    poster: 0.3,
    fn: (u, b) {
      const ph1 = <double>[0, 0.27, 0.55, 0.8],
          ph2 = <double>[0.1, 0.5, 0.2, 0.7];
      for (var i = 0; i < 4; i++) {
        final s1 = 0.5 + 0.5 * math.sin(_tau * (u + ph1[i])),
            s2 = 0.5 + 0.5 * math.sin(_tau * (2 * u + ph2[i])),
            e = s1 * (0.35 + 0.65 * s2),
            r = 12 + 34 * e;
        _candle(
          b,
          i,
          -4 * (1 - e),
          4 * (1 - e),
          -r,
          r,
          1,
          0.4 + 0.5 * e,
          0,
          0,
          18,
        );
        b[2 * i].ar = null;
        b[2 * i + 1].ar = null;
      }
    },
  ),
  // js:444-466
  LonoraAvatarState.learning: _StateDef(
    k: 2.2,
    fluid: 0.15,
    poster: 0.7,
    fn: (u, b) {
      const inc = <double>[12, 17, 22, 28];
      final reset = _inOut(_seg(u, 0.88, 1)),
          level = <double>[0, 0, 0, 0],
          flash = <double>[0, 0, 0, 0];
      for (var k = 0; k < 12; k++) {
        final t = 0.04 + 0.065 * k, i = k % 4;
        level[i] += _spring(_seg(u, t, t + 0.05), 0.62, 7);
        if (u >= t) {
          flash[i] = math.max(flash[i], 1 - _smooth(_seg(u, t, t + 0.12)));
        }
      }
      for (var i = 0; i < 4; i++) {
        final lv = level[i] * (1 - reset),
            o = 22.0,
            c = o - (22 + (inc[i] * lv) / 2.4);
        _candle(
          b,
          i,
          o,
          c,
          c - 8 - 3 * lv,
          o + 8,
          1,
          0.55 + 0.45 * math.max(flash[i], lv / 3),
        );
      }
    },
  ),
  // js:467-484
  LonoraAvatarState.angry: _StateDef(
    k: 0.5,
    fluid: 0.15,
    poster: 0.2,
    accent: '#fb7185',
    gaze: (_) => (0, 0),
    fn: (u, b) {
      const r = <double>[-15, -9, 9, 15];
      final pulse = 0.5 + 0.5 * math.sin(_tau * 3 * u);
      for (var i = 0; i < 4; i++) {
        final o = -22 - 3 * pulse, c = 22 + 3 * pulse;
        _candle(
          b,
          i,
          o,
          c,
          o - 12,
          c + 12,
          1,
          1,
          r[i],
          1.6 * math.sin(_tau * 11 * u + i * 1.7),
          22,
        );
        b[2 * i].ar = _red;
        b[2 * i + 1].ar = _red;
      }
    },
  ),

  /* ── glyph family: ONE liquid mass takes the shape of the job's icon ── */
  /* 🔍 a ring and a handle; the lens looks around. js:488-511 */
  LonoraAvatarState.searching: _StateDef(
    k: 2.0,
    poster: 0.15,
    gaze: (u) =>
        (0.6 * math.sin(_tau * u), 0.25 * math.sin(_tau * 2 * u + 0.6)),
    fn: (u, b) {
      final f = _x(
        12 * math.sin(_tau * u),
        7 * math.sin(_tau * 2 * u + 0.6),
        6 * math.sin(_tau * u + 0.8),
        1.0 + 0.04 * math.sin(_tau * 2 * u),
      );
      const r = 30.0, cx = -8.0, cy = -8.0, d = 0.7071;
      for (var j = 0; j < 4; j++) {
        _ps(f, b[j], _arc(cx, cy, r, 45 + 90.0 * j, 90), 17, 1, 0.55);
      }
      _ps(
        f,
        b[4],
        _line(
          cx + (r + 6) * d,
          cy + (r + 6) * d,
          cx + (r + 32) * d,
          cy + (r + 32) * d,
        ),
        23,
        1,
        0.1,
      );
    },
  ),
  /* ✏ a pencil that draws a line and erases it. js:513-529 */
  LonoraAvatarState.writing: _StateDef(
    k: 1.0,
    poster: 0.62,
    gaze: (_) => (-0.2, 0.3),
    fn: (u, b) {
      final g = _inOut(_seg(u, 0.05, 0.78)) * (1 - _inOut(_seg(u, 0.88, 1))),
          tx = -40 + 74 * g;
      final wig =
              3 *
              math.sin(_tau * 12 * u) *
              _smooth(g * 12) *
              _smooth((1 - g) * 12),
          ty = 30 + wig;
      const ux = 0.7071, uy = -0.7071;
      _g(b[0], (-44 + tx) / 2, 40, tx + 44, 0, 0, 10, 1, 0.55);
      _g(b[1], tx, ty, 0.01, 0, 0, 8, 1, 0.9);
      _g(b[2], tx + ux * 13, ty + uy * 13, 10, -45, 0, 16, 1, 0.9);
      _g(b[3], tx + ux * 47, ty + uy * 47, 38, -45, 0, 27, 1, 0);
    },
  ),
  /* ⟳ a spinning ring around a pulsing core. js:531-548 */
  LonoraAvatarState.working: _StateDef(
    k: 0.8,
    poster: 0.2,
    gaze: (_) => (0, 0),
    fn: (u, b) {
      final rot = 360 * u + 24 * math.sin(_tau * 2 * u);
      for (var j = 0; j < 4; j++) {
        _gs(
          b[j],
          _arc(
            0,
            0,
            38,
            rot + 90 * j,
            54 + 24 * math.sin(_tau * (2 * u - j * 0.25)),
          ),
          16,
          1,
          0.3 + 0.6 * _bump(_wrapSigned(u - j / 4), 0.28),
        );
      }
      _g(b[4], 0, 0, 0.01, 0, 0, 14 + 5 * math.sin(_tau * 2 * u), 1, 0.5);
    },
  ),
  /* ⚡ a bolt that charges and fires in two beats. js:550-566 */
  LonoraAvatarState.executing: _StateDef(
    k: 0.78,
    poster: 0.27,
    gaze: (_) => (0, 0),
    fn: (u, b) {
      final f1 = _bump(u - 0.25, 0.09),
          f2 = _bump(u - 0.55, 0.07),
          hit = math.max(f1, f2);
      final f = _x(
            2 * (f1 + f2) * math.sin(_tau * 14 * u),
            0,
            0,
            1.0 + 0.08 * f1 + 0.1 * f2,
          ),
          c = 0.6 + 0.4 * hit;
      _ps(f, b[0], _line(14, -42, -12, 2), 22, 1, c);
      _ps(f, b[1], _line(-12, 2, 12, 2), 22, 1, c);
      _ps(f, b[2], _line(12, 2, -14, 44), 22, 1, c);
      f(b[3], 42, -30, 0.01, 0, 0, 7 + 8 * hit, 1, 1);
      f(b[4], -40, 32, 0.01, 0, 0, 6 + 7 * math.max(f2, 0.3 * f1), 1, 1);
    },
  ),
  /* ➜ an arrow that thrusts out through the visor edge and returns. js:568-583 */
  LonoraAvatarState.sending: _StateDef(
    k: 1.1,
    poster: 0.08,
    gaze: (u) => (_clamp(_sendX(u) / 80, -1, 1) * 0.7, 0),
    fn: (u, b) {
      final st = u < 0.5
          ? _smooth(_seg(u, 0.1, 0.34))
          : 1 - _smooth(_seg(u, 0.56, 0.8));
      final f = _x(14 + _sendX(u), 0, 0, 1.12),
          x0 = -34 - 30 * st,
          tl = 10 + 18 * st;
      f(b[0], (x0 + 24) / 2, 0, 24 - x0, 0, 0, 20, 1, 0.35);
      _ps(f, b[1], _line(24, 0, 2, -22), 20, 1, 0.9);
      _ps(f, b[2], _line(24, 0, 2, 22), 20, 1, 0.9);
      f(b[3], x0 - 14 - tl / 2, 0, tl, 0, 0, 12, 1, 0.3);
    },
  ),
  /* •))) a speaker: a dot and three waves pulsing with the syllables. js:585-605 */
  LonoraAvatarState.speaking: _StateDef(
    k: 0.85,
    poster: 0.2,
    gaze: (_) => (0.2, 0),
    fn: (u, b) {
      final env =
              0.3 +
              0.7 *
                  math
                      .pow(0.5 + 0.5 * math.sin(_tau * 4 * u - 1), 1.4)
                      .toDouble(),
          f = _x(16, 0, 0, 1.12);
      const r = <double>[28, 48, 68];
      f(b[0], -46, 0, 0.01, 0, 0, 22 + 10 * env, 1, 0.3 + 0.3 * env);
      for (var j = 0; j < 3; j++) {
        final wv = _bump(_wrapSigned(u * 4 - j * 0.2), 0.3);
        _ps(
          f,
          b[j + 1],
          _arc(-46, 0, r[j] * (1 + 0.05 * wv), 0, 80),
          14,
          1,
          0.2 + 0.6 * math.max(wv, env * 0.4),
        );
      }
    },
  ),
  /* Wi‑Fi: a dot and three arcs light up one by one. js:607-629 */
  LonoraAvatarState.connecting: _StateDef(
    k: 1.3,
    poster: 0.7,
    gaze: (_) => (0, -0.2),
    fn: (u, b) {
      final f = _x(0, 0, 0, 1.12), fade = _inOut(_seg(u, 0.8, 0.95));
      double lit(double a) =>
          _spring(_seg(u, a, a + 0.12), 0.6, 6.6) * (1 - fade);
      const r = <double>[24, 44, 64];
      final l0 = lit(0.06);
      f(
        b[0],
        0,
        28,
        0.01,
        0,
        0,
        14 + 10 * _clamp(l0),
        1,
        0.2 + 0.75 * _clamp(l0),
      );
      for (var j = 0; j < 3; j++) {
        final l = lit(0.18 + 0.14 * j);
        _ps(
          f,
          b[j + 1],
          _arc(0, 28, r[j] * (0.92 + 0.08 * l), -90, 90),
          6 + 8 * _clamp(l),
          1,
          0.2 + 0.75 * _clamp(l),
        );
      }
    },
  ),
  /* ✓ a bold check mark with two sparkles. js:631-645 */
  LonoraAvatarState.success: _StateDef(
    k: 1.6,
    poster: 0.4,
    accent: '#66f4b2',
    gaze: (_) => (0, -0.1),
    fn: (u, b) {
      final f = _x(
            2,
            -2,
            0,
            1.0 + 0.08 * _bump(u - 0.12, 0.1) + 0.04 * _bump(u - 0.6, 0.12),
          ),
          t1 = 0.5 + 0.5 * math.sin(_tau * 2 * u),
          t2 = 0.5 + 0.5 * math.sin(_tau * 2 * u + 3.1);
      _ps(f, b[0], _line(-34, 6, -12, 28), 26, 1, 1);
      _ps(f, b[1], _line(-12, 28, 40, -28), 26, 1, 1);
      f(b[2], 50, -40, 0.01, 0, 0, 5 + 9 * t1, 1, 1);
      f(b[3], -48, -28, 0.01, 0, 0, 4 + 8 * t2, 1, 1);
    },
  ),
  /* ✕ a bold cross with one damped shake. js:647-660 */
  LonoraAvatarState.error: _StateDef(
    k: 1.4,
    poster: 0.4,
    accent: '#fb7185',
    gaze: (_) => (0, 0.35),
    fn: (u, b) {
      final t = u - 0.04,
          shake = t > 0 && t < 0.46
              ? 5 * math.sin(_tau * 7 * t) * math.exp(-10 * t)
              : 0.0,
          pl = 1 + 0.06 * math.sin(_tau * 2 * u + 1),
          r = 31 * pl;
      _g(b[0], shake, 0, 2 * r * 1.414 - 24, 45, 0, 25, 1, 1);
      _g(b[1], shake, 0, 2 * r * 1.414 - 24, -45, 0, 25, 1, 1);
    },
  ),
  /* ⚠ a hazard triangle with an exclamation mark. js:662-677 */
  LonoraAvatarState.warning: _StateDef(
    k: 1.2,
    poster: 0.1,
    accent: '#f9bf67',
    gaze: (_) => (0, 0),
    fn: (u, b) {
      final a = 0.5 + 0.5 * _tanh(2.2 * math.sin(_tau * 2 * u)),
          f = _x(0, 0, 0, 1.1 + 0.05 * a),
          c = 0.6 + 0.4 * a;
      _ps(f, b[0], _line(0, -38, -46, 38), 15, 1, c);
      _ps(f, b[1], _line(0, -38, 46, 38), 15, 1, c);
      _ps(f, b[2], _line(-46, 38, 46, 38), 15, 1, c);
      f(b[3], 0, -4 - 2 * a, 10, 90, 0, 13, 1, 0);
      f(b[4], 0, 18, 0.01, 0, 0, 13, 1, 0);
    },
  ),
  /* ✦ a star-burst that sways and shifts through warm colours. js:679-713 */
  LonoraAvatarState.celebrating: _StateDef(
    k: 0.9,
    poster: 0.3,
    gaze: (_) => (0, -0.2),
    fn: (u, b) {
      final sw = 25 * math.sin(_tau * u),
          lift = -6 * math.sin(_tau * 2 * u).abs();
      for (var j = 0; j < 4; j++) {
        final a = 90 * j + sw,
            r1 = 34 + 14 * math.sin(_tau * 2 * u - j * 0.4).abs();
        _g(
          b[j],
          (math.cos(a * _deg) * r1) / 2,
          (math.sin(a * _deg) * r1) / 2 + lift,
          r1,
          a,
          0,
          15,
          1,
          0.9,
        );
      }
      _g(b[4], 0, lift, 0.01, 0, 0, 24 + 5 * math.sin(_tau * 2 * u), 1, 0.9);
      for (var j = 0; j < 5; j++) {
        final q = _wrap(u + j * 0.2) * 4,
            k0 = q.floor() % 4,
            ff = _smooth(q - q.floorToDouble()),
            a = _celebrate[k0],
            bc = _celebrate[(k0 + 1) % 4];
        b[j].ar = [
          _lerp(a[0], bc[0], ff),
          _lerp(a[1], bc[1], ff),
          _lerp(a[2], bc[2], ff),
        ];
      }
    },
  ),
};

double _tanh(double x) {
  if (x > 20) return 1;
  if (x < -20) return -1;
  final e = math.exp(2 * x);
  return (e - 1) / (e + 1);
}

/// Loop phase a reduced-motion poster shows for [state] (`STATES[id].poster`).
double posterPhase(LonoraAvatarState state) => _states[state]!.poster;

/// The state's own gaze target at loop phase [u], or null (`STATES[id].gaze`, web only).
(double, double)? stateGaze(LonoraAvatarState state, double u) =>
    _states[state]!.gaze?.call(u);

/* ───────────────────────────── colour helpers, js:808-834 ───────────────────────────── */

const List<double> _eye = [248, 248, 251];
const String _defaultAccent = '#6cf4c4';

/// Hex `#rgb` / `#rrggbb` → [r, g, b]; anything else → [fallback] (js:811-831, hex branch).
List<double>? parseHexColor(String? input, [List<double>? fallback]) {
  if (input == null || input.isEmpty) return fallback;
  final m = RegExp(
    r'^#([0-9a-f]{3}|[0-9a-f]{6})$',
    caseSensitive: false,
  ).firstMatch(input.trim());
  if (m == null) return fallback;
  var h = m.group(1)!;
  if (h.length == 3) h = h.split('').map((c) => c + c).join();
  return [
    int.parse(h.substring(0, 2), radix: 16).toDouble(),
    int.parse(h.substring(2, 4), radix: 16).toDouble(),
    int.parse(h.substring(4, 6), radix: 16).toDouble(),
  ];
}

final Map<LonoraAvatarState, List<double>> _semantic = {
  for (final e in _states.entries)
    if (e.value.accent != null) e.key: parseHexColor(e.value.accent)!,
}; // js:832-834

/* ───────────────────────────── segments, js:836-863 ───────────────────────────── */

List<AvatarBar> _newSegs() => List.generate(_n, (i) => AvatarBar(i: i));

void _runState(
  LonoraAvatarState state,
  double u,
  List<AvatarBar> bars, [
  String identity = '',
  String face = 'orb',
  double reactionProgress = 1,
]) {
  for (final b in bars) {
    _h(b);
  }
  if (state == LonoraAvatarState.waiting && resolveAvatarFace(face) != 'orb') {
    _facialExpression(
      face,
      u,
      bars,
      avatarPersonality(identity),
      reactionProgress,
    );
  } else if (state == LonoraAvatarState.waiting && identity.isNotEmpty) {
    _personalizedWaiting(u, bars, avatarPersonality(identity));
  } else {
    _states[state]!.fn(u, bars);
  }
}

/// Idle-only expressions keep the four capsules while changing their rhythm (js:866-893).
void _personalizedWaiting(
  double u,
  List<AvatarBar> b,
  AvatarPersonality profile,
) {
  final time = _wrap(u + profile.phase), direction = profile.direction;
  final sway = 1.5 * math.sin(_tau * time);
  for (var i = 0; i < 4; i++) {
    final wave = math.sin(_tau * (time - i * 0.17 * direction));
    var height = _rest[i], lift = 0.0, dx = 0.0;
    if (profile.pattern == 0) {
      height += 3.5 * wave;
    } else if (profile.pattern == 1) {
      height *= 0.96 + 0.04 * math.sin(_tau * time);
      lift = 1.5 * (1 + math.sin(_tau * (time + i * 0.2 * direction)));
    } else if (profile.pattern == 2) {
      height += 2 * wave;
      dx = sway + 0.75 * math.sin(_tau * (time - i * 0.1));
      lift = 1.25 * math.sin(_tau * (time + i * 0.15 * direction));
    } else {
      final bounce = math.max(
        0.0,
        math.sin(_tau * (time - i * 0.16 * direction)),
      );
      height += 2.5 * bounce;
      lift = 3.5 * bounce;
      dx = sway * 0.5;
    }
    height = _clamp(height, 30, 94);
    _p(b[i], height, _sit(height) - lift, 1, i == 2 ? 1 : 0, dx);
    if (i == 2) b[i].ar = [31, 212, 179];
  }
}

/// All presets share anchors, optical corrections and stroke hierarchy; only expression
/// topology varies (js:894-1120).
void _facialExpression(
  String face,
  double u,
  List<AvatarBar> b,
  AvatarPersonality profile, [
  double reactionProgress = 1,
]) {
  final phase = _wrap(u + profile.phase),
      breath = math.sin(_tau * phase) * _T.breathAmplitude;
  final reaction = faceReaction(reactionProgress, face);
  final blink = math.max(
    _bump(phase - _T.blinkPhase, _T.blinkHalfDuration),
    reaction.blink,
  );
  const teal = <double>[31, 212, 179];
  void segment(
    int slot,
    _Shape geometry, [
    double width = _T.strokeSecondary,
    bool accent = false,
  ]) {
    _gs(b[slot], geometry, width, 1, accent ? 1 : 0);
    if (accent) b[slot].ar = teal;
  }

  void stroke(
    int slot,
    double x0,
    double y0,
    double x1,
    double y1, [
    double width = _T.strokeSecondary,
    bool accent = false,
  ]) => segment(slot, _line(x0, y0, x1, y1), width, accent);
  void curve(
    int slot,
    double x,
    double y,
    double radius,
    double alpha,
    double span, [
    double width = _T.strokeSecondary,
    bool accent = false,
  ]) => segment(slot, _arc(x, y, radius, alpha, span), width, accent);
  void dot(int slot, double x, double y, [bool accent = true]) =>
      segment(slot, (x, y, 0.01, 0, 0), _T.strokeIndicator, accent);
  void eye(int slot, double x) => segment(slot, (
    x,
    _T.eyeLine,
    (_T.eyeHeight - _T.strokePrimary) * (1 - blink),
    90,
    0,
  ), _T.strokePrimary * (1 - (1 - _T.blinkStrokeRatio) * blink));
  void curvedEye(
    int slot,
    double x, [
    bool sleepy = false,
    bool thoughtful = false,
  ]) {
    final gentleBlink = 1 - reaction.blink * 0.12;
    final correction =
        _T.eyeArcCorrection * gentleBlink +
        (thoughtful ? _T.thoughtfulEyeOffset : 0);
    curve(
      slot,
      x,
      _T.eyeLine + (sleepy ? -correction : correction),
      _T.eyeArcRadius * gentleBlink,
      sleepy ? 90 : 270,
      _T.eyeArcSpan,
      _T.strokeCurvedEye,
    );
  }

  void smile(int slot, [bool laugh = false]) {
    final radius =
        (laugh
            ? (_T.mouthWidth * _T.laughingMouthScale - _T.strokeSecondary) /
                  (2 * math.sin((_T.mouthArcSpan * _deg) / 2))
            : _T.mouthRadius) *
        (1 + reaction.mouth * 0.035);
    final correction =
        (radius * (1 + math.cos((_T.mouthArcSpan * _deg) / 2))) / 2;
    curve(
      slot,
      0,
      _T.mouthLine - correction + breath,
      radius,
      90,
      _T.mouthArcSpan,
    );
  }

  void flatMouth(int slot, [double offset = 0]) {
    final half =
        ((_T.mouthWidth * 0.72 - _T.strokeSecondary) / 2) *
        (1 + reaction.mouth * 0.04);
    stroke(
      slot,
      -half + offset,
      _T.mouthLine + breath,
      half + offset,
      _T.mouthLine + breath,
    );
  }

  void wink(int slot) {
    const x = _T.eyeHalfSpacing, y = _T.eyeLine;
    stroke(
      slot,
      x + _T.winkHalfWidth,
      y - _T.winkHalfHeight,
      x - _T.winkHalfWidth,
      y,
      _T.strokeCurvedEye,
    );
    stroke(
      slot + 1,
      x - _T.winkHalfWidth,
      y,
      x + _T.winkHalfWidth,
      y + _T.winkHalfHeight,
      _T.strokeCurvedEye,
    );
  }

  void brows(int slot, [bool worried = false]) {
    for (var side = -1; side <= 1; side += 2) {
      final x = side * _T.eyeHalfSpacing,
          y = _T.browLine,
          rise = _T.eyebrowRise * (worried ? 1 : -1);
      stroke(
        slot + (side == 1 ? 1 : 0),
        x - _T.eyebrowLength / 2,
        y - (side * rise) / 2,
        x + _T.eyebrowLength / 2,
        y + (side * rise) / 2,
        _T.strokeEyebrow,
      );
    }
  }

  void cheekMarks(int slot, int side) {
    final x = side * _T.sideAccentX;
    const y = _T.sideAccentLine, reach = _T.accentLength;
    stroke(
      slot,
      x,
      y,
      x + side * reach * 0.45,
      y - reach,
      _T.strokeAccent,
      true,
    );
    stroke(
      slot + 1,
      x - side * _T.minimumSeparation,
      y - _T.minimumSeparation,
      x - side * _T.minimumSeparation,
      y - _T.minimumSeparation - reach,
      _T.strokeAccent,
      true,
    );
  }

  const x = _T.eyeHalfSpacing;
  switch (face) {
    case 'face-thoughtful':
      curvedEye(0, -x, true, true);
      curvedEye(1, x, true, true);
      flatMouth(2);
      dot(3, -_T.accentPitch, _T.accentLine);
      dot(4, 0, _T.accentLine);
      dot(5, _T.accentPitch, _T.accentLine);
    case 'face-happy':
      curvedEye(0, -x);
      curvedEye(1, x);
      smile(2);
    case 'face-wink':
      eye(0, -x);
      wink(1);
      smile(3);
    case 'face-sleepy':
      curvedEye(0, -x, true);
      curvedEye(1, x, true);
      flatMouth(2);
      const cx = _T.sideAccentX, cy = _T.accentLine, half = _T.accentRadius;
      stroke(
        3,
        cx - half,
        cy - half,
        cx + half,
        cy - half,
        _T.strokeAccent,
        true,
      );
      stroke(
        4,
        cx + half,
        cy - half,
        cx - half,
        cy + half,
        _T.strokeAccent,
        true,
      );
      stroke(
        5,
        cx - half,
        cy + half,
        cx + half,
        cy + half,
        _T.strokeAccent,
        true,
      );
    case 'face-surprised':
      eye(0, -x);
      eye(1, x);
      curve(
        2,
        0,
        _T.mouthLine + _T.openMouthOffset + breath,
        _T.roundMouthRadius,
        0,
        360,
      );
      for (var i = -1; i <= 1; i++) {
        stroke(
          4 + i,
          i * _T.accentPitch,
          _T.accentLine,
          i * (_T.accentPitch + _T.minimumSeparation),
          _T.accentLine - _T.accentLength,
          _T.strokeAccent,
          true,
        );
      }
    case 'face-angry':
      eye(0, -x);
      eye(1, x);
      brows(2);
      flatMouth(4);
    case 'face-playful':
      curvedEye(0, -x);
      curvedEye(1, x);
      smile(2);
      stroke(
        3,
        0,
        _T.tongueLine - _T.tongueLength / 2,
        0,
        _T.tongueLine + _T.tongueLength / 2,
        _T.tongueWidth,
        true,
      );
    case 'face-excited':
      eye(0, -x);
      wink(1);
      smile(3, true);
      cheekMarks(4, 1);
    case 'face-skeptical':
      eye(0, -x);
      curvedEye(1, x);
      dot(2, 0, _T.mouthLine, false);
      const cx = 0.0, cy = _T.accentLine, r = _T.questionRadius;
      curve(3, cx, cy, r, 285, 245, _T.strokeAccent, true);
      stroke(
        4,
        cx + r * 0.25,
        cy + r * 0.85,
        cx - r * 0.25,
        cy + r * 1.5,
        _T.strokeAccent,
        true,
      );
      dot(
        5,
        cx - r * 0.25,
        cy +
            r * 1.5 +
            _T.strokeAccent +
            _T.minimumSeparation +
            (_T.strokeIndicator - _T.strokeAccent) / 2,
      );
    case 'face-dreamy':
      curvedEye(0, -x, true);
      curvedEye(1, x, true);
      smile(2);
      const cx = _T.sideAccentX, cy = _T.accentLine, r = _T.accentRadius;
      stroke(3, cx, cy - r, cx, cy + r, _T.strokeAccent, true);
      stroke(4, cx - r, cy, cx + r, cy, _T.strokeAccent, true);
    case 'face-focused':
      eye(0, -x);
      stroke(
        1,
        x - _T.closedEyeLength / 2,
        _T.eyeLine,
        x + _T.closedEyeLength / 2,
        _T.eyeLine,
        _T.strokeCurvedEye,
      );
      flatMouth(2, -_T.focusedMouthOffset);
    case 'face-worried':
      eye(0, -x);
      eye(1, x);
      brows(2, true);
      curve(
        4,
        0,
        _T.mouthLine + _T.mouthCorrection + breath,
        _T.mouthRadius,
        270,
        _T.mouthArcSpan,
      );
    case 'face-laugh':
      curvedEye(0, -x);
      curvedEye(1, x);
      smile(2, true);
      cheekMarks(3, -1);
      cheekMarks(5, 1);
    case 'face-determined':
      const half = _T.closedEyeLength / 2, rise = _T.eyebrowRise / 2;
      stroke(
        0,
        -x - half,
        _T.eyeLine - rise,
        -x + half,
        _T.eyeLine + rise,
        _T.strokePrimary,
      );
      stroke(
        1,
        x - half,
        _T.eyeLine + rise,
        x + half,
        _T.eyeLine - rise,
        _T.strokePrimary,
      );
      flatMouth(2);
    default:
      eye(0, -x);
      eye(1, x);
      smile(2);
  }
}

/* ───────────────────────── points, morph planning, sampling, js:1122-1292 ───────────────────────── */

(double, double) _pointAt(double cx, double cy, double th, double k, double s) {
  final t = th * _deg;
  if (k.abs() < 1e-5) return (cx + s * math.cos(t), cy + s * math.sin(t));
  return (
    cx + (math.sin(t + k * s) - math.sin(t)) / k,
    cy - (math.cos(t + k * s) - math.cos(t)) / k,
  );
} // js:1122-1129

/// Points along a segment's centre-line (js:1130-1135).
List<(double, double)> segmentPoints(
  double cx,
  double cy,
  double len,
  double th,
  double k, [
  int n = 24,
]) => [
  for (var j = 0; j <= n; j++)
    _pointAt(cx, cy, th, k, -len / 2 + (len * j) / n),
];

/// The polyline a renderer strokes for [bar]: the centre-line scaled by [glyphScale] around
/// the visor centre, with as many points as `avatarBarPath` (avatar-motion.ts:108-122).
List<(double, double)> avatarBarPoints(AvatarBar bar) => segmentPoints(
  200 + (bar.cx - 200) * glyphScale,
  _cy + (bar.cy - _cy) * glyphScale,
  bar.len * glyphScale,
  bar.th,
  bar.k / glyphScale,
  math.min(32, ((bar.k * bar.len).abs() * 9).ceil() + 1),
);

/// Assignment of particles on screen to particles of the new shape (`planMorph` result).
class MorphPlan {
  MorphPlan({
    required this.perm,
    required this.flip,
    required this.rank,
    required this.bow,
  });

  /// Identity plan (js:1136-1141).
  factory MorphPlan.identity() => MorphPlan(
    perm: List.generate(_n, (i) => i),
    flip: List.filled(_n, false),
    rank: List.generate(_n, (i) => i),
    bow: List.filled(_n, 1),
  );

  final List<int> perm;
  final List<bool> flip;
  final List<int> rank;
  final List<int> bow;
}

(double, double, double, double) _ends(AvatarBar s) {
  final a = _pointAt(s.cx, s.cy, s.th, s.k, -s.len / 2),
      b = _pointAt(s.cx, s.cy, s.th, s.k, s.len / 2);
  return (a.$1, a.$2, b.$1, b.$2);
} // js:1180-1185

/// Best one-to-one assignment (and direction flips) from the shapes on screen to the new
/// shapes (js:1186-1250): exact DP over subsets, then rank by x and bow toward the centre.
MorphPlan planMorph(List<AvatarBar> from, List<AvatarBar> to) {
  final e = from.map(_ends).toList(), f = to.map(_ends).toList();
  final cost = List.generate(_n, (_) => List.filled(_n, 0.0));
  final flipM = List.generate(_n, (_) => List.filled(_n, false));
  for (var i = 0; i < _n; i++) {
    for (var j = 0; j < _n; j++) {
      final a = e[i], b = f[j];
      final d1 =
          _hypot(a.$1 - b.$1, a.$2 - b.$2) + _hypot(a.$3 - b.$3, a.$4 - b.$4);
      final d2 =
          _hypot(a.$1 - b.$3, a.$2 - b.$4) + _hypot(a.$3 - b.$1, a.$4 - b.$2);
      cost[i][j] = math.min(d1, d2);
      flipM[i][j] = d2 < d1;
    }
  }
  const full = (1 << _n) - 1;
  final dp = List.filled(full + 1, double.infinity),
      pick = List.filled(full + 1, -1);
  dp[0] = 0;
  for (var m = 0; m < full; m++) {
    if (dp[m] == double.infinity) continue;
    var i = 0;
    for (var x = m; x != 0; x &= x - 1) {
      i++;
    }
    for (var j = 0; j < _n; j++) {
      if (m & (1 << j) == 0) {
        final nm = m | (1 << j), v = dp[m] + cost[i][j];
        if (v < dp[nm]) {
          dp[nm] = v;
          pick[nm] = j;
        }
      }
    }
  }
  final perm = List.filled(_n, 0);
  var m = full;
  for (var i = _n - 1; i >= 0; i--) {
    final j = pick[m];
    perm[i] = j;
    m &= ~(1 << j);
  }
  final flip = [for (var i = 0; i < _n; i++) flipM[i][perm[i]]];
  // JS Array.prototype.sort is stable; break cx ties by index to match it.
  final order = List.generate(_n, (i) => i)
    ..sort((i, j) {
      final d = from[i].cx.compareTo(from[j].cx);
      return d != 0 ? d : i.compareTo(j);
    });
  final rank = List.filled(_n, 0);
  for (var r = 0; r < _n; r++) {
    rank[order[r]] = r;
  }
  final bow = [
    for (var i = 0; i < _n; i++)
      () {
        // bend each path toward the face centre
        final s = from[i], t = to[perm[i]], dx = t.cx - s.cx, dy = t.cy - s.cy;
        var d = _hypot(dx, dy);
        if (d == 0) d = 1;
        final px = -dy / d,
            py = dx / d,
            mx = (s.cx + t.cx) / 2,
            my = (s.cy + t.cy) / 2;
        return px * (200 - mx) + py * (_cy - my) >= 0 ? 1 : -1;
      }(),
  ];
  return MorphPlan(perm: perm, flip: flip, rank: rank, bow: bow);
}

/// Shape of signal [i] [t] seconds into a morph (null [from] = already arrived), written to
/// [out]; returns the eased progress (js:1251-1287).
double morphSegment(
  AvatarBar? from,
  List<AvatarBar> tgt,
  MorphPlan plan,
  int i,
  double t,
  AvatarBar out,
) {
  final s = tgt[plan.perm[i]];
  var th = s.th, k = s.k;
  if (plan.flip[i]) {
    th += 180;
    k = -k;
  }
  final p = from != null
      ? _clamp(
          (t - plan.rank[i] * _morphDelay * 0.5) /
              (_morphSeconds - 7 * _morphDelay * 0.5),
        )
      : 1.0;
  if (p >= 1) {
    out
      ..cx = s.cx
      ..cy = s.cy
      ..len = s.len
      ..th = th
      ..k = k
      ..w = s.w
      ..o = s.o;
    return 1;
  }
  final e = _inOut(p),
      dx = s.cx - from!.cx,
      dy = s.cy - from.cy,
      d = _hypot(dx, dy);
  final bow = d > 1
      ? (plan.bow[i] * d * 0.09 * math.sin(math.pi * e)) / d
      : 0.0;
  out
    ..cx = _lerp(from.cx, s.cx, e) - dy * bow
    ..cy = _lerp(from.cy, s.cy, e) + dx * bow
    ..len = _lerp(from.len, s.len, e)
    ..th = _lerpAng(from.th, th, e)
    ..k = _lerp(from.k, k, e)
    ..w = _lerp(from.w, s.w, e)
    ..o = _lerp(from.o, s.o, e);
  return e;
}

List<double> _tint(AvatarBar s, List<double> acc) {
  final a = s.ar ?? acc;
  return [
    _lerp(_eye[0], a[0], s.c),
    _lerp(_eye[1], a[1], s.c),
    _lerp(_eye[2], a[2], s.c),
  ];
} // js:1288-1291

/// Pure sampler: the [avatarParticles] shapes of [state] at loop phase [u] (js:1294-1327).
List<AvatarBar> poseAt(
  LonoraAvatarState state,
  double u, {
  String accent = _defaultAccent,
  String identity = '',
  String face = 'orb',
  double reactionProgress = 1,
}) {
  final b = _newSegs();
  _runState(state, _wrap(u), b, identity, face, reactionProgress);
  final acc =
      _semantic[state] ?? parseHexColor(accent, parseHexColor(_defaultAccent))!;
  return [
    for (final s in b)
      () {
        final c = _tint(s, acc);
        return AvatarBar(
          i: s.i,
          cx: s.cx,
          cy: s.cy,
          len: s.len,
          th: s.th,
          k: s.k,
          w: s.w,
          o: s.o,
          r: c[0],
          g: c[1],
          b: c[2],
        );
      }(),
  ];
}

/// Seconds per loop of [state] (js:1290).
double loopSeconds(LonoraAvatarState state, [double speed = 1]) =>
    (_baseSeconds * _states[state]!.k) / speed;

/* ───────────────────────────── personality, js:1293-1330 ───────────────────────────── */

/// Stable visual personality from the agent's ID, independent of its name or colour.
class AvatarPersonality {
  const AvatarPersonality({
    required this.phase,
    required this.direction,
    required this.tempo,
    required this.cycleSeconds,
    required this.spinSeconds,
    required this.pattern,
    required this.gazeXFrequency,
    required this.gazeYFrequency,
    required this.gazeXAmplitude,
    required this.gazeYAmplitude,
  });

  final double phase;
  final int direction;
  final double tempo;
  final double cycleSeconds;
  final double spinSeconds;
  final int pattern;
  final double gazeXFrequency;
  final double gazeYFrequency;
  final double gazeXAmplitude;
  final double gazeYAmplitude;
}

/// `Math.imul`, as an unsigned 32-bit result (inputs taken modulo 2^32).
int imul32(int a, int b) {
  a &= 0xFFFFFFFF;
  b &= 0xFFFFFFFF;
  final lo = (a & 0xFFFF) * (b & 0xFFFF);
  final mid =
      (((a >> 16) * (b & 0xFFFF) + (a & 0xFFFF) * (b >> 16)) & 0xFFFF) << 16;
  return (lo + mid) & 0xFFFFFFFF;
}

final Map<String, AvatarPersonality> _personalities = {};

/// Port of `avatarPersonality` (js:1293-1330): FNV-1a over UTF-16 code units, then a
/// mulberry32-style sampler. Memoised; the same id gives the same personality as web/Expo.
AvatarPersonality avatarPersonality([String identity = '']) {
  final cached = _personalities[identity];
  if (cached != null) return cached;
  if (_personalities.length > 512) _personalities.clear();
  return _personalities[identity] = _computePersonality(identity);
}

AvatarPersonality _computePersonality(String identity) {
  if (identity.isEmpty) {
    return const AvatarPersonality(
      phase: 0,
      direction: 1,
      tempo: 0.5,
      cycleSeconds: 24,
      spinSeconds: 2.7,
      pattern: 0,
      gazeXFrequency: 0.16,
      gazeYFrequency: 0.11,
      gazeXAmplitude: 0.42,
      gazeYAmplitude: 0.12,
    );
  }
  var hash = 2166136261;
  for (var i = 0; i < identity.length; i++) {
    hash = imul32(hash ^ identity.codeUnitAt(i), 16777619);
  }
  final direction = hash & 1 != 0 ? -1 : 1, pattern = (hash >> 8) % 4;
  var seed = hash;
  double sample() {
    seed = (seed + 0x6d2b79f5) & 0xFFFFFFFF;
    var value = imul32(seed ^ (seed >> 15), seed | 1);
    value ^= (value + imul32(value ^ (value >> 7), value | 61)) & 0xFFFFFFFF;
    return (value ^ (value >> 14)) / 4294967296;
  }

  return AvatarPersonality(
    phase: sample(),
    direction: direction,
    tempo: 0.42 + sample() * 0.22,
    cycleSeconds: 18 + sample() * 12,
    spinSeconds: 2.4 + sample() * 0.6,
    pattern: pattern,
    gazeXFrequency: 0.12 + sample() * 0.12,
    gazeYFrequency: 0.08 + sample() * 0.09,
    gazeXAmplitude: 0.28 + sample() * 0.2,
    gazeYAmplitude: 0.08 + sample() * 0.08,
  );
}

/* ───────────────────────── reactions, idle pose, turn, js:1332-1442 ───────────────────────── */

/// Face temperament: rate, amplitude, vertical bias, reaction gaze X/Y, tilt, lift, scale,
/// blink, mouth (js:1332-1349).
const Map<String, List<double>> _faceBehavior = {
  'face-smile': [1, 0.8, 0, 0.1, 0, 2, 0, 0.01, 0.8, 0.3],
  'face-thoughtful': [0.65, 0.7, -0.08, -0.22, -0.22, -1, 0, -0.01, 0.35, -0.2],
  'face-happy': [1.05, 0.8, -0.02, 0.08, -0.12, 3, -1, 0.02, 0.2, 0.6],
  'face-wink': [0.9, 0.75, 0, 0.24, 0.03, -3, 0, 0.01, 0.9, 0.2],
  'face-sleepy': [0.25, 0.3, 0.12, 0, 0.18, 1, 1, -0.02, 1, -0.4],
  'face-surprised': [0.7, 0.6, -0.02, 0, -0.2, 0, -0.7, -0.025, 0.05, 0.9],
  'face-angry': [0.6, 0.55, 0.02, -0.16, 0.05, -2, 0, -0.01, 0.7, -0.6],
  'face-playful': [1.1, 0.9, 0, 0.3, -0.06, 4, -0.8, 0.025, 0.5, 0.8],
  'face-excited': [1.15, 0.85, -0.03, -0.12, -0.16, -4, -1.2, 0.03, 0.3, 1],
  'face-skeptical': [0.6, 0.8, -0.03, -0.3, -0.03, -2.5, 0, -0.005, 0.6, -0.3],
  'face-dreamy': [0.35, 0.45, -0.06, 0.12, -0.14, 2.5, -0.7, 0.008, 0.95, 0.1],
  'face-focused': [0.35, 0.35, 0, 0.02, -0.08, 0, 0.4, -0.008, 0.45, -0.1],
  'face-worried': [0.85, 0.6, 0.02, 0.2, 0.12, 1.5, 0.2, -0.015, 0.65, -0.8],
  'face-laugh': [1, 0.8, -0.01, -0.06, -0.1, 3.5, -0.9, 0.022, 0.4, 0.95],
  'face-determined': [
    0.45,
    0.45,
    0,
    -0.08,
    0.08,
    -1.5,
    0.7,
    -0.012,
    0.55,
    -0.5,
  ],
};

/// Tap reaction sample (`faceReaction` result).
class FaceReaction {
  const FaceReaction({
    this.gazeX = 0,
    this.gazeY = 0,
    this.yaw = 0,
    this.scale = 1,
    this.offsetY = 0,
    this.tilt = 0,
    this.blink = 0,
    this.mouth = 0,
  });

  final double gazeX, gazeY, yaw, scale, offsetY, tilt, blink, mouth;
}

/// Shared calm reaction, applied to facial content only; endpoints are visually neutral
/// (js:1351-1381). The signal face (`orb`) turns a full circle instead.
FaceReaction faceReaction(
  double progress, [
  String face = 'orb',
  String identity = '',
]) {
  final p = _clamp(progress.isFinite ? progress : 1),
      profile = avatarPersonality(identity);
  final active = p > 0 && p < 1;
  final pulse = active ? math.pow(math.sin(math.pi * p), 2).toDouble() : 0.0;
  final values = _faceBehavior[resolveAvatarFace(face)];
  if (values == null) {
    return FaceReaction(yaw: _tau * _inOut(p) * profile.direction);
  }
  return FaceReaction(
    gazeX: values[3] * pulse * profile.direction,
    gazeY: values[4] * pulse,
    yaw: 0,
    tilt: values[5] * pulse * profile.direction,
    offsetY: values[6] * pulse,
    scale: 1 + values[7] * pulse,
    blink: values[8] * pulse,
    mouth: values[9] * pulse,
  );
}

/// Idle gaze and occasional spin (`idleAvatarPose`, js:1383-1411).
({double gazeX, double gazeY, double yaw}) idleAvatarPose(
  double seconds, [
  String identity = '',
  String face = 'orb',
]) {
  final time = seconds.isFinite ? math.max(0.0, seconds) : 0.0;
  final profile = avatarPersonality(identity),
      values = _faceBehavior[resolveAvatarFace(face)];
  final rate = values != null ? values[0] : 1.0,
      amplitude = values != null ? values[1] : 1.0;
  final cycle = time.remainder(profile.cycleSeconds);
  final start = profile.cycleSeconds - profile.spinSeconds,
      spin = _clamp((cycle - start) / profile.spinSeconds);
  final focus = values != null ? 1.0 : 1 - math.sin(math.pi * spin),
      phase = profile.phase * _tau;
  return (
    gazeX:
        math.sin(time * _tau * profile.gazeXFrequency * rate + phase) *
        profile.gazeXAmplitude *
        focus *
        profile.direction *
        amplitude,
    gazeY:
        math.sin(time * _tau * profile.gazeYFrequency * rate + phase * 0.7) *
            profile.gazeYAmplitude *
            focus *
            amplitude +
        (values != null ? values[2] : 0),
    yaw: values != null || cycle < start
        ? 0.0
        : _tau * _inOut(spin) * profile.direction,
  );
}

/// Spherical visor projection; the back stays hidden rather than showing mirrored eyes
/// (`avatarTurn`, js:1413-1421).
({double tx, double scaleX, double opacity}) avatarTurn(double yaw) {
  final angle = yaw.isFinite ? yaw : 0.0, facing = math.cos(angle);
  return (
    tx: 125 * math.sin(angle),
    scaleX: math.max(0.001, facing),
    opacity: _smooth(_clamp((facing - 0.02) / 0.12)),
  );
}

/// 3D face transform for gaze and poke (`faceTransform`, js:1424-1434): applied as
/// translate(200+tx, 200.5+ty) rotate(rot°) skewY(skew°) scale(sx, sy) translate(-200, -200.5).
({double tx, double ty, double rot, double skew, double sx, double sy})
faceTransform([double gx = 0, double gy = 0, double poke = 0]) {
  final s = 1 - 0.07 * poke;
  return (
    tx: gx * 26,
    ty: gy * 15 + 3 * poke,
    rot: -gx * 5,
    skew: -gx * 4,
    sx: (1 - 0.1 * gx.abs()) * s,
    sy: (1 - 0.06 * gy.abs()) * s,
  );
}
