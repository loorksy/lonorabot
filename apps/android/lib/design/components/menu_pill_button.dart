import 'package:flutter/widgets.dart';

import '../theme.dart';
import '../tokens.dart';
import 'badges.dart';
import 'glyphs.dart';
import 'tappable.dart';

/// The conversation header's ☰ button that opens the chat drawer: a Ø44 [LnPalette.chromeCircle]
/// with [LnGlyphs.menu], no rim in dark (light keeps the hairline), chrome shadow. With
/// [unreadCount] > 0 it widens into a 44 dp stadium: the glyph stays at its start and a Ø20 count
/// disc in [LnPalette.selectionFill] (white Latin digits at 4.6:1, "99+") follows at its end, 4 dp away, centred in the
/// stadium's end cap.
///
/// The touch target is 48 dp tall (2 dp around the visual): place it 2 dp closer to the edge than
/// the visual inset, as a [CircleIconButton].
class MenuPillButton extends StatelessWidget {
  const MenuPillButton({
    super.key,
    required this.semanticLabel,
    this.unreadCount = 0,
    this.unreadLabel,
    this.onTap,
  });

  /// What the button opens ("Chats").
  final String semanticLabel;

  /// Unread messages in the other chats; 0 shows the plain circle.
  final int unreadCount;

  /// The caller's localized count ("3 unread"), read after [semanticLabel]; English when omitted.
  final String? unreadLabel;
  final VoidCallback? onTap;

  /// Glyph-side inset (the circle's own (44 − 24) / 2) and the disc's end cap ((44 − 20) / 2).
  static const double _glyphInset = 10;
  static const double _discInset = 12;
  static const double _discGap = 4;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final counted = unreadCount > 0;
    final label = counted
        ? '$semanticLabel, ${unreadLabel ?? '$unreadCount unread'}'
        : semanticLabel;
    final glyph = LnGlyph(LnGlyphs.menu, size: LnSize.chromeIcon, color: c.fg);
    return LnTappable(
      onTap: onTap,
      haptic: true,
      semanticLabel: label,
      excludeChildSemantics: true,
      child: Padding(
        padding: const EdgeInsets.all(
          (LnSize.minTouch - LnSize.headerCircle) / 2,
        ),
        child: DecoratedBox(
          decoration: ShapeDecoration(
            color: c.chromeCircle,
            shape: StadiumBorder(
              side: c.isDark
                  ? BorderSide.none
                  : BorderSide(
                      color: c.border,
                      strokeAlign: BorderSide.strokeAlignInside,
                    ),
            ),
            shadows: ln.chromeShadow,
          ),
          child: _maybeAnimatedSize(
            animate: !MediaQuery.disableAnimationsOf(context),
            child: SizedBox(
              height: LnSize.headerCircle,
              child: counted
                  ? Padding(
                      padding: const EdgeInsetsDirectional.fromSTEB(
                        _glyphInset,
                        0,
                        _discInset,
                        0,
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        spacing: _discGap,
                        children: [
                          glyph,
                          UnreadPill(
                            count: unreadCount,
                            color: c.selectionFill,
                          ),
                        ],
                      ),
                    )
                  : SizedBox.square(
                      dimension: LnSize.headerCircle,
                      child: Center(child: glyph),
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The pill grows with [LnMotion.medium]; with animations off it just takes its new width
/// (AnimatedSize asserts on a zero duration in some layouts).
Widget _maybeAnimatedSize({required bool animate, required Widget child}) =>
    animate
    ? AnimatedSize(
        duration: LnMotion.medium,
        curve: LnMotion.emphasized,
        alignment: AlignmentDirectional.centerStart,
        child: child,
      )
    : child;
