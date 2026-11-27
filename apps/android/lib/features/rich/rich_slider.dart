import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../design/design.dart';

/// A card slider in the kit's colours: a 6 dp track, the ink-filled part up to the value,
/// and a 22 dp thumb; follows the reading direction; selection haptic on each step.
class RichSlider extends StatelessWidget {
  const RichSlider({
    super.key,
    required this.value,
    required this.min,
    required this.max,
    required this.step,
    required this.onChanged,
    required this.label,
    required this.valueLabel,
    this.enabled = true,
  });

  final double value;
  final double min;
  final double max;
  final double step;
  final ValueChanged<double> onChanged;
  final String label;
  final String valueLabel;
  final bool enabled;

  double _snap(double next) {
    final snapped = min + ((next - min) / step).round() * step;
    return double.parse(snapped.clamp(min, max).toStringAsFixed(10));
  }

  static String _plain(double v) =>
      v == v.truncateToDouble() ? '${v.toInt()}' : '$v';

  void _set(double next) {
    final clean = _snap(next);
    if (clean == value) return;
    HapticFeedback.selectionClick();
    onChanged(clean);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final fraction = max > min
        ? ((value - min) / (max - min)).clamp(0.0, 1.0)
        : 0.0;
    return Semantics(
      slider: true,
      label: label,
      value: valueLabel,
      increasedValue: _plain(_snap(value + step)),
      decreasedValue: _plain(_snap(value - step)),
      enabled: enabled,
      onIncrease: enabled ? () => _set(value + step) : null,
      onDecrease: enabled ? () => _set(value - step) : null,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final width = constraints.maxWidth;
          void at(double x) {
            final ratio = ((x - 11) / (width - 22)).clamp(0.0, 1.0);
            _set(min + (rtl ? 1 - ratio : ratio) * (max - min));
          }

          return GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapDown: enabled ? (d) => at(d.localPosition.dx) : null,
            onHorizontalDragUpdate: enabled
                ? (d) => at(d.localPosition.dx)
                : null,
            child: Opacity(
              opacity: enabled ? 1 : 0.5,
              child: SizedBox(
                height: 48,
                width: width,
                child: CustomPaint(
                  painter: _SliderPainter(
                    fraction: fraction,
                    rtl: rtl,
                    track: c.fill4,
                    active: c.fg,
                    thumb: c.isDark ? c.fgStrong : c.surface,
                    shadow: c.scrim,
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _SliderPainter extends CustomPainter {
  _SliderPainter({
    required this.fraction,
    required this.rtl,
    required this.track,
    required this.active,
    required this.thumb,
    required this.shadow,
  });
  final double fraction;
  final bool rtl;
  final Color track;
  final Color active;
  final Color thumb;
  final Color shadow;

  @override
  void paint(Canvas canvas, Size size) {
    const r = 11.0;
    final y = size.height / 2;
    const left = r;
    final right = size.width - r;
    final x = rtl
        ? right - fraction * (right - left)
        : left + fraction * (right - left);
    final line = Paint()
      ..strokeWidth = 6
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(Offset(left, y), Offset(right, y), line..color = track);
    canvas.drawLine(
      Offset(rtl ? right : left, y),
      Offset(x, y),
      line..color = active,
    );
    canvas.drawCircle(
      Offset(x, y + 1.5),
      r,
      Paint()
        ..color = shadow
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2.5),
    );
    canvas.drawCircle(Offset(x, y), r, Paint()..color = thumb);
  }

  @override
  bool shouldRepaint(_SliderPainter old) =>
      old.fraction != fraction ||
      old.rtl != rtl ||
      old.active != active ||
      old.track != track ||
      old.thumb != thumb;
}
