import 'package:flutter/widgets.dart';

import '../theme.dart';
import '../tokens.dart';

/// Top chrome row: leading circle button, centre slot, trailing circle button. Sits [topGap] below the
/// status bar and keeps buttons at the 16 dp page gutter. Transparent: content scrolls underneath.
///
/// Pass [CircleIconButton]s (they include a 2 dp touch margin, accounted for here).
class ScreenHeader extends StatelessWidget {
  const ScreenHeader({
    super.key,
    this.leading,
    this.center,
    this.trailing,
    this.topGap = topGapDefault,
    this.applyTopInset = true,
  });

  final Widget? leading;
  final Widget? center;
  final Widget? trailing;
  final double topGap;
  final bool applyTopInset;

  static const double topGapDefault = 10;

  /// Height of the button row (circle + touch margin).
  static const double rowHeight = 48;

  /// Total height from the screen top, for padding content that scrolls beneath.
  static double heightOf(
    BuildContext context, {
    double topGap = topGapDefault,
    double extra = 0,
  }) => MediaQuery.paddingOf(context).top + topGap - 2 + rowHeight + extra;

  @override
  Widget build(BuildContext context) {
    final top =
        (applyTopInset ? MediaQuery.paddingOf(context).top : 0.0) + topGap - 2;
    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter - 2,
        top,
        LnSpace.pageGutter - 2,
        0,
      ),
      child: Stack(
        alignment: AlignmentDirectional.topCenter,
        children: [
          if (center != null)
            Padding(padding: const EdgeInsets.only(top: 2), child: center),
          SizedBox(
            height: rowHeight,
            child: Row(children: [?leading, const Spacer(), ?trailing]),
          ),
        ],
      ),
    );
  }
}

/// Tab-root header: large title ("Explore", 20/700) at the gutter, optional trailing text or widget on
/// the same baseline, optional trailing circle buttons.
class LargeTitleHeader extends StatelessWidget {
  const LargeTitleHeader({
    super.key,
    required this.title,
    this.trailing,
    this.topGap = 14,
    this.color,
  });

  final String title;
  final Widget? trailing;
  final double topGap;

  /// Title colour; defaults to `fg` (use white over dark header art).
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter,
        MediaQuery.paddingOf(context).top + topGap,
        LnSpace.pageGutter,
        0,
      ),
      child: SizedBox(
        height: 44,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: Semantics(
                header: true,
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: ln.text.display.copyWith(color: color ?? ln.colors.fg),
                ),
              ),
            ),
            if (trailing != null)
              DefaultTextStyle.merge(
                style: ln.text.body.copyWith(color: color ?? ln.colors.fg),
                child: trailing!,
              ),
          ],
        ),
      ),
    );
  }
}
