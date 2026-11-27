import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../theme.dart';
import '../tokens.dart';
import 'badges.dart';
import 'tappable.dart';

/// Ø36 circle with a 20 dp arrow-down in the warm ink that appears when the conversation is scrolled
/// away from the latest message: the menu fill in dark (#262626, no rim, no shadow); the chrome
/// surface with a hairline and the chrome shadow in light. Scales and fades in/out with [visible]; shows an unread count above the circle.
/// [semanticLabel] is spoken as given: the caller composes it in its own language, with the unread
/// count while there is one (e.g. «الانتقال إلى الأحدث، 3 غير مقروءة»).
class JumpToLatestButton extends StatelessWidget {
  const JumpToLatestButton({
    super.key,
    required this.visible,
    required this.onTap,
    this.unreadCount = 0,
    this.semanticLabel = 'Jump to latest',
    this.unreadSemanticLabel,
  });

  final bool visible;
  final VoidCallback onTap;
  final int unreadCount;

  /// The whole spoken label, unread count included; the English default is for the gallery only.
  final String semanticLabel;

  /// Joined to [semanticLabel] with ", " while [unreadCount] > 0.
  @Deprecated(
    'Pass the whole localized label, unread count included, in semanticLabel.',
  )
  final String? unreadSemanticLabel;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return IgnorePointer(
      ignoring: !visible,
      child: AnimatedOpacity(
        opacity: visible ? 1 : 0,
        duration: LnMotion.fast,
        child: AnimatedScale(
          scale: visible ? 1 : 0.6,
          duration: LnMotion.medium,
          curve: visible ? Curves.easeOutBack : Curves.easeIn,
          child: LnTappable(
            onTap: onTap,
            haptic: true,
            semanticLabel: unreadCount > 0 && unreadSemanticLabel != null
                ? '$semanticLabel, $unreadSemanticLabel'
                : semanticLabel,
            excludeChildSemantics: true,
            child: SizedBox.square(
              dimension: 48,
              child: Stack(
                clipBehavior: Clip.none,
                alignment: Alignment.center,
                children: [
                  Container(
                    width: LnSize.jumpButton,
                    height: LnSize.jumpButton,
                    decoration: BoxDecoration(
                      color: c.isDark ? c.menuSurface : c.surface,
                      shape: BoxShape.circle,
                      border: Border.fromBorderSide(ln.chromeRim),
                      boxShadow: c.isDark ? null : ln.chromeShadow,
                    ),
                    child: Icon(FIcons.arrowDown, size: 20, color: c.fgWarm),
                  ),
                  if (unreadCount > 0)
                    Positioned(top: -6, child: UnreadPill(count: unreadCount)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
