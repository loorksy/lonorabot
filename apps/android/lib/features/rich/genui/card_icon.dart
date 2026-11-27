import 'package:flutter/widgets.dart';

import 'card_icons.g.dart';

/// One of Lonora's 24-unit stroke icons (packages/ui-tokens/src/icons.ts), as both card
/// renderers draw them: stroke 1.7, round caps and joins. Unknown names draw nothing.
class CardIcon extends StatelessWidget {
  const CardIcon(this.name, {super.key, this.size = 18, this.color});

  final Object? name;
  final double size;
  final Color? color;

  static bool has(Object? name) =>
      name is String && cardIconPaths.containsKey(name);

  @override
  Widget build(BuildContext context) {
    final key = name;
    if (key is! String) return const SizedBox.shrink();
    final path = _paths[key] ??= _parse(cardIconPaths[key]);
    if (path == null) return const SizedBox.shrink();
    final ink = color ?? IconTheme.of(context).color ?? const Color(0xFF000000);
    return ExcludeSemantics(
      child: CustomPaint(
        size: Size.square(size),
        painter: _IconPainter(path, ink),
      ),
    );
  }
}

final Map<String, Path?> _paths = {};

class _IconPainter extends CustomPainter {
  _IconPainter(this.path, this.color);
  final Path path;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 24, size.height / 24);
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.7
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round
        ..isAntiAlias = true,
    );
    canvas.restore();
  }

  @override
  bool shouldRepaint(_IconPainter old) =>
      old.path != path || old.color != color;
}

final RegExp _tokens = RegExp(
  r'[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?',
);

/// A minimal SVG path parser (M L H V C S Q T A Z, absolute and relative).
Path? _parse(String? data) {
  if (data == null) return null;
  final tokens = _tokens.allMatches(data).map((m) => m[0]!).toList();
  final path = Path();
  var i = 0;
  var command = '';
  var x = 0.0, y = 0.0, startX = 0.0, startY = 0.0;
  double? cx, cy; // last control point (for S / T)
  var lastCommand = '';
  bool isCommand(String t) => RegExp(r'^[A-Za-z]$').hasMatch(t);
  double next() => double.parse(tokens[i++]);
  bool flag() {
    // Arc flags may be packed ("011"): read one digit at a time.
    final t = tokens[i];
    if (t.length > 1 && (t.startsWith('0') || t.startsWith('1'))) {
      tokens[i] = t.substring(1);
      return t[0] == '1';
    }
    i++;
    return t == '1';
  }

  while (i < tokens.length) {
    if (isCommand(tokens[i])) {
      command = tokens[i++];
    } else if (command.isEmpty) {
      return null;
    }
    final rel = command == command.toLowerCase();
    final c = command.toUpperCase();
    switch (c) {
      case 'M':
        final nx = next(), ny = next();
        x = rel ? x + nx : nx;
        y = rel ? y + ny : ny;
        path.moveTo(x, y);
        startX = x;
        startY = y;
        // Further pairs after M are line-tos.
        command = rel ? 'l' : 'L';
        cx = cy = null;
      case 'L':
        final nx = next(), ny = next();
        x = rel ? x + nx : nx;
        y = rel ? y + ny : ny;
        path.lineTo(x, y);
        cx = cy = null;
      case 'H':
        final nx = next();
        x = rel ? x + nx : nx;
        path.lineTo(x, y);
        cx = cy = null;
      case 'V':
        final ny = next();
        y = rel ? y + ny : ny;
        path.lineTo(x, y);
        cx = cy = null;
      case 'C':
        var x1 = next(), y1 = next(), x2 = next(), y2 = next();
        var ex = next(), ey = next();
        if (rel) {
          x1 += x;
          y1 += y;
          x2 += x;
          y2 += y;
          ex += x;
          ey += y;
        }
        path.cubicTo(x1, y1, x2, y2, ex, ey);
        cx = x2;
        cy = y2;
        x = ex;
        y = ey;
      case 'S':
        var x2 = next(), y2 = next(), ex = next(), ey = next();
        if (rel) {
          x2 += x;
          y2 += y;
          ex += x;
          ey += y;
        }
        final px = cx, py = cy;
        final smooth = 'CcSs'.contains(lastCommand);
        final x1 = smooth && px != null ? 2 * x - px : x;
        final y1 = smooth && py != null ? 2 * y - py : y;
        path.cubicTo(x1, y1, x2, y2, ex, ey);
        cx = x2;
        cy = y2;
        x = ex;
        y = ey;
      case 'Q':
        var x1 = next(), y1 = next(), ex = next(), ey = next();
        if (rel) {
          x1 += x;
          y1 += y;
          ex += x;
          ey += y;
        }
        path.quadraticBezierTo(x1, y1, ex, ey);
        cx = x1;
        cy = y1;
        x = ex;
        y = ey;
      case 'T':
        var ex = next(), ey = next();
        if (rel) {
          ex += x;
          ey += y;
        }
        final px = cx, py = cy;
        final smooth = 'QqTt'.contains(lastCommand);
        final x1 = smooth && px != null ? 2 * x - px : x;
        final y1 = smooth && py != null ? 2 * y - py : y;
        path.quadraticBezierTo(x1, y1, ex, ey);
        cx = x1;
        cy = y1;
        x = ex;
        y = ey;
      case 'A':
        final rx = next(), ry = next(), rotation = next();
        final large = flag();
        final sweep = flag();
        var ex = next(), ey = next();
        if (rel) {
          ex += x;
          ey += y;
        }
        path.arcToPoint(
          Offset(ex, ey),
          radius: Radius.elliptical(rx, ry),
          rotation: rotation,
          largeArc: large,
          clockwise: sweep,
        );
        x = ex;
        y = ey;
        cx = cy = null;
      case 'Z':
        path.close();
        x = startX;
        y = startY;
        cx = cy = null;
      default:
        return null;
    }
    lastCommand = command;
  }
  return path;
}
