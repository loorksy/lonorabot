import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../theme.dart';
import '../tokens.dart';
import 'tappable.dart';

/// Section title with a trailing chevron ("Recommendation ›"), 16/500 muted. Indented 32 dp so the text
/// lines up with the content of full-width cards below it.
class SectionHeader extends StatelessWidget {
  const SectionHeader({
    super.key,
    required this.title,
    this.onTap,
    this.padding,
  });

  final String title;
  final VoidCallback? onTap;

  /// Defaults to 32 dp start/end, 27 dp top, 16 dp bottom.
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final row = Row(
      children: [
        Expanded(
          child: Semantics(
            header: true,
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: ln.text.title.copyWith(color: c.fgMuted),
            ),
          ),
        ),
        // Lucide chevrons mirror themselves in RTL (matchTextDirection).
        if (onTap != null)
          Icon(FIcons.chevronRight, size: 20, color: c.fgMuted),
      ],
    );
    return Padding(
      padding: padding ?? const EdgeInsetsDirectional.fromSTEB(32, 0, 30, 0),
      child: onTap == null
          ? row
          : LnTappable(
              onTap: onTap,
              semanticLabel: title,
              excludeChildSemantics: true,
              child: SizedBox(height: 44, child: row),
            ),
    );
  }
}

/// Square explore tile (144², radius 22): solid colour or gradient, an icon/emoji at the top-start and
/// a 16/500 label at the bottom-start, or a caller's [body].
class ExploreTile extends StatelessWidget {
  const ExploreTile({
    super.key,
    required this.label,
    this.leading,
    this.color,
    this.gradient,
    this.foreground = LnPalette.inkWhite,
    this.onTap,
    this.width = LnSize.exploreTile,
    this.height = LnSize.exploreTile,
    this.labelStyle,
    this.body,
  });

  /// [ExploreTile] spanning two columns (296 × 128).
  const ExploreTile.wide({
    super.key,
    required this.label,
    this.leading,
    this.color,
    this.gradient,
    this.foreground = LnPalette.inkWhite,
    this.onTap,
    this.labelStyle,
    this.body,
  }) : width = LnSize.wideTileWidth,
       height = LnSize.wideTileHeight;

  /// The tile's text; only its accessibility label when [body] is given.
  final String label;

  /// 32 dp icon, emoji or illustration.
  final Widget? leading;
  final Color? color;
  final Gradient? gradient;

  /// Label/icon colour: white on saturated tiles, `fg` on light gradients.
  final Color foreground;
  final VoidCallback? onTap;
  final double width;
  final double height;
  final TextStyle? labelStyle;

  /// Custom content inside the tile's 16 dp padding (an account card's name and amounts), in place of
  /// [leading] and the label; text and icons default to [foreground].
  final Widget? body;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final custom = body == null
        ? null
        : IconTheme.merge(
            data: IconThemeData(color: foreground),
            child: DefaultTextStyle.merge(
              style: TextStyle(color: foreground),
              child: body!,
            ),
          );
    return LnTappable(
      onTap: onTap,
      haptic: true,
      semanticLabel: label,
      excludeChildSemantics: true,
      child: Container(
        width: width,
        height: height,
        padding: const EdgeInsetsDirectional.fromSTEB(16, 16, 16, 16),
        decoration: BoxDecoration(
          color: gradient == null ? (color ?? ln.colors.fill1) : null,
          gradient: gradient,
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.tile)),
        ),
        child:
            custom ??
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (leading != null)
                  IconTheme.merge(
                    data: IconThemeData(
                      size: LnSize.recIllustration,
                      color: foreground,
                    ),
                    child: SizedBox.square(
                      dimension: LnSize.recIllustration,
                      child: leading,
                    ),
                  ),
                const Spacer(),
                Text(
                  label,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style:
                      labelStyle ??
                      ln.text.title.copyWith(
                        color: foreground,
                        height: 21.7 / 16,
                      ),
                ),
              ],
            ),
      ),
    );
  }
}

/// Wide explore tile (296 × 128). Same as [ExploreTile.wide].
class WideTile extends ExploreTile {
  const WideTile({
    super.key,
    required super.label,
    super.leading,
    super.color,
    super.gradient,
    super.foreground,
    super.onTap,
    super.labelStyle,
    super.body,
  }) : super(width: LnSize.wideTileWidth, height: LnSize.wideTileHeight);
}

/// Full-width recommendation card: fill1, radius 22, 32 dp illustration at a 20 dp inset, title 16/500
/// and up to two lines of 14 dp muted subtitle.
class RecommendationCard extends StatelessWidget {
  const RecommendationCard({
    super.key,
    required this.title,
    this.subtitle,
    this.leading,
    this.onTap,
  });

  final String title;
  final String? subtitle;

  /// 32 dp icon or illustration.
  final Widget? leading;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: onTap,
      pressScale: 0.98,
      pressOpacity: 1,
      semanticLabel: subtitle == null ? title : '$title. $subtitle',
      excludeChildSemantics: true,
      child: Container(
        constraints: const BoxConstraints(minHeight: 72),
        padding: const EdgeInsetsDirectional.fromSTEB(20, 14, 16, 14),
        decoration: BoxDecoration(
          color: c.fill1,
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.tile)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: IconTheme.merge(
                data: IconThemeData(size: LnSize.recIllustration, color: c.fg),
                child: SizedBox.square(
                  dimension: LnSize.recIllustration,
                  child: leading,
                ),
              ),
            ),
            const SizedBox(width: 15),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: ln.text.title.copyWith(color: c.fg),
                  ),
                  if (subtitle != null)
                    Text(
                      subtitle!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: ln.text.caption.copyWith(color: c.fgMuted),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
