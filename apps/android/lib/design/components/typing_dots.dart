import 'package:flutter/widgets.dart';

import '../theme.dart';
import '../tokens.dart';

/// Three bouncing dots ("agent is typing"): 1.05 s loop, each dot rises and fades 40 → 100 → 40 %
/// over 0.8 s, staggered 83 ms, in fgWarm.
class TypingDots extends StatefulWidget {
  const TypingDots({
    super.key,
    this.dotSize = 8,
    this.gap = 5,
    this.bounce = 6,
    this.color,
    this.semanticLabel,
  });

  final double dotSize;
  final double gap;
  final double bounce;
  final Color? color;
  final String? semanticLabel;

  @override
  State<TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<TypingDots>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: LnMotion.typingLoop,
  )..repeat();

  static const _active = 48 / 63; // fraction of the loop each dot animates

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  double _phase(double t, int i) {
    final offset =
        i *
        LnMotion.typingStagger.inMicroseconds /
        LnMotion.typingLoop.inMicroseconds;
    final local = (t - offset) % 1.0;
    if (local > _active) return 0;
    final p = local / _active; // 0..1 up then down
    final tri = p < 0.5 ? p * 2 : (1 - p) * 2;
    return Curves.easeInOut.transform(tri);
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? context.ln.colors.fgWarm;
    final reduce = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    return Semantics(
      label: widget.semanticLabel,
      liveRegion: widget.semanticLabel != null,
      child: SizedBox(
        width: widget.dotSize * 3 + widget.gap * 2,
        height: widget.dotSize + widget.bounce,
        child: AnimatedBuilder(
          animation: _c,
          builder: (context, _) => Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (var i = 0; i < 3; i++) ...[
                if (i > 0) SizedBox(width: widget.gap),
                Builder(
                  builder: (context) {
                    final v = reduce ? 0.5 : _phase(_c.value, i);
                    return Transform.translate(
                      offset: Offset(0, -widget.bounce * v),
                      child: Container(
                        width: widget.dotSize,
                        height: widget.dotSize,
                        decoration: BoxDecoration(
                          color: color.withValues(
                            alpha: color.a * (0.4 + 0.6 * v),
                          ),
                          shape: BoxShape.circle,
                        ),
                      ),
                    );
                  },
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// [TypingDots] inside an agent-style bubble (44 dp stadium), start-aligned.
class TypingBubble extends StatelessWidget {
  const TypingBubble({super.key, this.semanticLabel});

  final String? semanticLabel;

  @override
  Widget build(BuildContext context) => Align(
    alignment: AlignmentDirectional.centerStart,
    child: Container(
      height: 44,
      padding: const EdgeInsetsDirectional.fromSTEB(18, 3, 18, 0),
      decoration: ShapeDecoration(
        color: context.ln.colors.agentBubble,
        shape: const StadiumBorder(),
      ),
      child: Center(
        widthFactor: 1,
        child: TypingDots(semanticLabel: semanticLabel),
      ),
    ),
  );
}
