// A file name as a pushed page's header title: centred while it fits between equal insets,
// otherwise moved into the free width beside the header's circles and, still too long, shortened
// in the middle so its extension stays visible («statement-o….pdf»). Screen readers hear the
// whole name.
import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../../l10n/l10n.dart';

class FileNameTitle extends StatelessWidget {
  const FileNameTitle({
    super.key,
    required this.name,
    required this.style,
    required this.start,
    required this.end,
  });

  final String name;
  final TextStyle style;

  /// The width the header's circles take at the start and at the end.
  final double start;
  final double end;

  @override
  Widget build(BuildContext context) {
    final direction = textDirectionFor(name, Directionality.of(context));
    final scaler = MediaQuery.textScalerOf(context);
    double widthOf(String text) {
      final painter = TextPainter(
        text: TextSpan(text: text, style: style),
        textDirection: direction,
        textScaler: scaler,
        maxLines: 1,
      )..layout();
      final width = painter.width;
      painter.dispose();
      return width;
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final side = math.max(start, end);
        final centred = widthOf(name) <= constraints.maxWidth - 2 * side;
        return Padding(
          padding: centred
              ? EdgeInsets.symmetric(horizontal: side)
              : EdgeInsetsDirectional.only(start: start, end: end),
          child: Text(
            centred
                ? name
                : middleEllipsis(
                    name,
                    constraints.maxWidth - start - end,
                    widthOf,
                  ),
            semanticsLabel: name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textDirection: direction,
            textAlign: TextAlign.center,
            style: style,
          ),
        );
      },
    );
  }
}

/// [name] shortened in the middle to fit [room] as measured by [widthOf], keeping its extension
/// (up to 8 characters after the last dot).
String middleEllipsis(
  String name,
  double room,
  double Function(String text) widthOf,
) {
  if (widthOf(name) <= room) return name;
  final dot = name.lastIndexOf('.');
  final ext = dot > 0 && name.length - dot <= 8 ? name.substring(dot) : '';
  final base = name.substring(0, name.length - ext.length).characters;
  String cut(int n) => '${base.take(n)}…$ext';
  var lo = 0, hi = base.length;
  while (lo < hi) {
    final mid = (lo + hi + 1) ~/ 2;
    if (widthOf(cut(mid)) <= room) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return cut(lo);
}
