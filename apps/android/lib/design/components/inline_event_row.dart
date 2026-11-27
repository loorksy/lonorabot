import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../theme.dart';
import '../tokens.dart';
import 'tappable.dart';

enum InlineEventAlignment { center, start }

/// Inline conversation event ("Memory updated ›", "Call completed ›"): icon slot (20 dp centred, 22 dp
/// start-aligned), 14 dp label, optional muted detail and a chevron. Centred for system events,
/// start-aligned (indented to the bubble text column, label at 58.5 dp from the screen edge) for
/// agent-side events. 8 dp above and below the row; a tappable row is at least [LnSize.minTouch] tall,
/// its content centred.
class InlineEventRow extends StatelessWidget {
  const InlineEventRow({
    super.key,
    required this.icon,
    required this.label,
    this.detail,
    this.alignment = InlineEventAlignment.center,
    this.emphasized = false,
    this.onTap,
    this.showChevron = true,
    this.maxLines = 1,
    this.hug = false,
  });

  /// Usually an `Icon` (sized to 20 through [IconTheme]) or a small illustration.
  final Widget icon;
  final String label;

  /// Muted secondary text after the label ("2 changes").
  final String? detail;
  final InlineEventAlignment alignment;

  /// Near-black label (system events) instead of the muted grey (agent activity).
  final bool emphasized;
  final VoidCallback? onTap;
  final bool showChevron;

  /// Lines of label and detail before an ellipsis (system lines and server reasons can be longer).
  final int maxLines;

  /// Start-aligned only: the row is as wide as its content instead of its line, so a caller can put
  /// an action right after the label (the parent then places the row, e.g. a Row or a start Column).
  final bool hug;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final centered = alignment == InlineEventAlignment.center;
    final slot = centered ? 20.0 : 22.0;
    final style = ln.text.caption.copyWith(
      color: emphasized ? c.fgWarm : c.fgMuted,
    );
    final line =
        MediaQuery.textScalerOf(context).scale(style.fontSize!) * style.height!;
    // Several lines: top-aligned, the icon and chevron centred on the first line, so a label that fits
    // on one line sits exactly as with maxLines 1.
    final firstLine = math.max(slot, line);
    Widget onFirstLine(Widget child) => maxLines == 1
        ? child
        : SizedBox(
            height: firstLine,
            child: Center(child: child),
          );
    final row = Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: maxLines == 1
          ? CrossAxisAlignment.center
          : CrossAxisAlignment.start,
      children: [
        IconTheme.merge(
          data: IconThemeData(
            size: centered ? 18 : 20,
            color: emphasized ? c.fgWarm : c.fgMuted,
          ),
          // Fixed slot so text lines up whatever the icon's ink width (22 dp fits wide phone art).
          child: onFirstLine(
            SizedBox.square(
              dimension: slot,
              child: Center(child: icon),
            ),
          ),
        ),
        SizedBox(width: centered ? 6 : 4.5),
        Flexible(
          child: Padding(
            padding: EdgeInsets.only(
              top: maxLines == 1 ? 0 : (firstLine - line) / 2,
            ),
            child: Text.rich(
              TextSpan(
                text: label,
                children: [
                  if (detail != null)
                    TextSpan(
                      text: '  $detail',
                      style: TextStyle(color: c.fgMuted),
                    ),
                ],
              ),
              maxLines: maxLines,
              overflow: TextOverflow.ellipsis,
              style: style,
            ),
          ),
        ),
        if (showChevron) ...[
          SizedBox(width: centered ? 4 : 1),
          // Lucide chevrons mirror themselves in RTL (matchTextDirection).
          onFirstLine(
            Icon(
              FIcons.chevronRight,
              size: centered ? 16 : 18,
              color: c.chevron,
            ),
          ),
        ],
      ],
    );
    final content = Padding(
      padding: EdgeInsetsDirectional.only(
        start: centered ? 0 : LnSpace.md,
        top: LnSpace.xs,
        bottom: LnSpace.xs,
      ),
      child: centered
          ? Center(child: row)
          : Align(
              alignment: AlignmentDirectional.centerStart,
              widthFactor: hug ? 1 : null,
              child: row,
            ),
    );
    final semantics = detail == null ? label : '$label, $detail';
    if (onTap == null) {
      // Not a button: read as text.
      return Semantics(
        label: semantics,
        excludeSemantics: true,
        child: content,
      );
    }
    return LnTappable(
      onTap: onTap,
      pressScale: 0.97,
      pressOpacity: 1,
      semanticLabel: semantics,
      excludeChildSemantics: true,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: LnSize.minTouch),
        child: content,
      ),
    );
  }
}
