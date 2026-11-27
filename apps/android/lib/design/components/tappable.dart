import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../tokens.dart';

/// forui's [FTappable] with Lonora's press feedback and conveniences: optional selection haptic,
/// semantics hint/selected. Pressing fades the child to [pressOpacity] (120 ms down, 180 ms up)
/// without scaling; [pressScale] adds forui's bounce for elements that should shrink instead.
class LnTappable extends StatelessWidget {
  const LnTappable({
    super.key,
    required this.child,
    this.onTap,
    this.onLongPress,
    this.haptic = false,
    this.pressScale = LnMotion.pressScale,
    this.pressOpacity = LnMotion.pressOpacity,
    this.semanticLabel,
    this.semanticHint,
    this.selected,
    this.enabled = true,
    this.behavior = HitTestBehavior.translucent,
    this.excludeChildSemantics = false,
  });

  final Widget child;
  final VoidCallback? onTap;

  /// Long-press callback. A medium impact fires when [haptic] is true.
  final VoidCallback? onLongPress;

  /// Fires [HapticFeedback.selectionClick] on tap.
  final bool haptic;

  /// Scale while pressed; 1.0 (the default) disables the bounce.
  final double pressScale;

  /// Opacity while pressed; 1.0 disables the fade.
  final double pressOpacity;

  final String? semanticLabel;
  final String? semanticHint;
  final bool? selected;
  final bool enabled;
  final HitTestBehavior behavior;

  /// Drops the child's own semantics: the tappable's node keeps [semanticLabel] and its tap and
  /// focus actions.
  final bool excludeChildSemantics;

  @override
  Widget build(BuildContext context) {
    final tap = enabled && onTap != null
        ? () {
            if (haptic) HapticFeedback.selectionClick();
            onTap!();
          }
        : null;
    final longPress = enabled && onLongPress != null
        ? () {
            if (haptic) HapticFeedback.mediumImpact();
            onLongPress!();
          }
        : null;
    return FTappable(
      style: (s) => s.copyWith(
        pressedEnterDuration: Duration.zero,
        bounceTween: _bounceTween(pressScale),
      ),
      builder: pressOpacity == 1
          ? (_, _, child) => child!
          : (_, states, child) => _PressFade(
              pressed: states.contains(WidgetState.pressed),
              opacity: pressOpacity,
              child: child!,
            ),
      onPress: tap,
      onLongPress: longPress,
      selected: selected ?? false,
      behavior: behavior,
      semanticsLabel: semanticLabel,
      // Not FTappable's excludeSemantics: its Semantics sits above forui's Focus and
      // GestureDetector, so it would drop their tap and focus actions with the child's semantics.
      // The hint sits inside too, so it merges into that node (FTappable sets selected itself).
      child: Semantics(
        hint: semanticHint,
        child: excludeChildSemantics ? ExcludeSemantics(child: child) : child,
      ),
    );
  }
}

/// forui compares tappable styles by value and the tween by identity; a fresh tween on every build
/// would make it recreate its bounce controller (a second ticker) whenever the widget rebuilds.
final Map<double, Tween<double>> _bounceTweens = {};

Tween<double> _bounceTween(double scale) => scale == 1
    ? FTappableStyle.noBounceTween
    : _bounceTweens.putIfAbsent(
        scale,
        () => Tween<double>(begin: 1, end: scale),
      );

class _PressFade extends StatelessWidget {
  const _PressFade({
    required this.pressed,
    required this.opacity,
    required this.child,
  });

  final bool pressed;
  final double opacity;
  final Widget child;

  @override
  Widget build(BuildContext context) => AnimatedOpacity(
    opacity: pressed ? opacity : 1,
    duration: pressed ? LnMotion.pressDown : LnMotion.pressUp,
    curve: pressed ? LnMotion.pressDownCurve : LnMotion.pressUpCurve,
    child: child,
  );
}
