// Anchored popover menus: the menu card and row shared with showLnAnchoredMenu, and
// showLnPopoverMenu (the «+» menus, the attach menu, in-place pickers).
import 'dart:math' as math;

import 'package:flutter/material.dart' show MaterialLocalizations;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../theme.dart';
import '../tokens.dart';
import 'sheets.dart' show LnMenuAction, LnPopoverMenu;
import 'tappable.dart';

/// The card of an anchored menu: [LnPalette.menuSurface], a one-pixel [LnPalette.menuBorder]
/// hairline, [LnRadius.menu], [LnSpace.menuInset] above the first and below the last row,
/// [LnShadow.menu] in light, an optional [header] line (12/16 in [LnPalette.fgMuted], e.g. the
/// message time). Rows scroll when the card is given less height than they need. forui's popover
/// menus ([LnPopoverMenu]) draw the same card from the theme.
class LnMenuCard extends StatelessWidget {
  const LnMenuCard({
    super.key,
    required this.children,
    this.header,
    this.width,
  });

  /// Usually [LnMenuRow]s.
  final List<Widget> children;
  final String? header;
  final double? width;

  static const double radius = LnRadius.menu;
  static const double verticalPadding = LnSpace.menuInset;

  /// The header's line box sits 8 dp under the top padding and 6 dp above the first row.
  static const double headerTop = 8;
  static const double headerBottom = 6;
  static const double inset = LnSpace.md;

  /// Height of the [header] block at [scaler] (0 without a header).
  static double headerExtent(TextScaler scaler) =>
      headerTop + scaler.scale(16) + headerBottom;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final hairline = 1 / MediaQuery.devicePixelRatioOf(context);
    final shape = RoundedRectangleBorder(
      borderRadius: const BorderRadius.all(Radius.circular(radius)),
      side: BorderSide(color: c.menuBorder, width: hairline),
    );
    // A DecoratedBox, not a Container: the rows keep their insets from the outer edge, the
    // hairline paints over them.
    return SizedBox(
      width: width,
      child: DecoratedBox(
        decoration: ShapeDecoration(
          color: c.menuSurface,
          shape: shape.copyWith(side: BorderSide.none),
          shadows: c.isDark ? null : LnShadow.menu,
        ),
        child: DecoratedBox(
          decoration: ShapeDecoration(shape: shape),
          position: DecorationPosition.foreground,
          child: ClipPath(
            clipper: ShapeBorderClipper(shape: shape),
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(vertical: verticalPadding),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (header != null)
                    Padding(
                      padding: const EdgeInsetsDirectional.fromSTEB(
                        inset,
                        headerTop,
                        inset,
                        headerBottom,
                      ),
                      child: Text(
                        header!,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: ln.text.small.copyWith(color: c.fgMuted),
                      ),
                    ),
                  ...children,
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A row of an anchored menu: [LnSize.menuRow] (48 dp) tall, a [LnSize.menuIcon] (24 dp) icon
/// 16 dp from the start, the 16 dp label 12 dp after it, an optional check at the end. Destructive
/// rows draw in the error colour; disabled rows are faded and inert.
class LnMenuRow extends StatelessWidget {
  const LnMenuRow({
    super.key,
    required this.label,
    this.icon,
    this.onTap,
    this.destructive = false,
    this.enabled = true,
    this.checked,
    this.indent = false,
    this.height = LnSize.menuRow,
    this.color,
  });

  final String label;
  final IconData? icon;
  final VoidCallback? onTap;
  final bool destructive;
  final bool enabled;

  /// True draws the check (and sets the selected flag); null rows are not checkable.
  final bool? checked;

  /// Keeps the icon's room when [icon] is null, so the label lines up with its siblings'.
  final bool indent;

  /// Row height; values under [LnSize.minTouch] are raised to it (the touch target).
  final double height;

  /// Label and icon colour; [LnPalette.fg] when null.
  final Color? color;

  static const double iconSize = LnSize.menuIcon;
  static const double iconGap = LnSpace.sm;

  /// The row's height at [scaler]: [height] (at least 48 dp), or the label's line box plus 8 dp
  /// above and below when larger text needs more.
  static double extent(double height, TextScaler scaler) =>
      math.max(math.max(height, LnSize.minTouch), scaler.scale(24) + 16);

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final ink = destructive ? c.error : (color ?? c.fg);
    return LnTappable(
      onTap: enabled ? onTap : null,
      enabled: enabled,
      haptic: true,
      selected: checked,
      semanticLabel: label,
      excludeChildSemantics: true,
      child: Opacity(
        opacity: enabled ? 1 : LnPalette.disabledOpacity,
        child: SizedBox(
          height: extent(height, MediaQuery.textScalerOf(context)),
          child: Padding(
            padding: const EdgeInsetsDirectional.symmetric(
              horizontal: LnMenuCard.inset,
            ),
            child: Row(
              children: [
                if (icon != null) ...[
                  Icon(icon, size: iconSize, color: ink),
                  const SizedBox(width: iconGap),
                ] else if (indent)
                  const SizedBox(width: iconSize + iconGap),
                Expanded(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: ln.text.body.copyWith(color: ink),
                  ),
                ),
                if (checked ?? false) ...[
                  const SizedBox(width: LnSpace.xs),
                  Icon(FIcons.check, size: 20, color: c.brand),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The rect of [key]'s render box, or the global [rect], in [navigator]'s overlay.
Rect lnAnchorRect(NavigatorState navigator, {GlobalKey? key, Rect? rect}) {
  assert((key == null) != (rect == null), 'Pass exactly one of key and rect.');
  final overlay = navigator.overlay!.context.findRenderObject()! as RenderBox;
  if (key != null) {
    final box = key.currentContext!.findRenderObject()! as RenderBox;
    return MatrixUtils.transformRect(
      box.getTransformTo(overlay),
      Offset.zero & box.size,
    );
  }
  return overlay.globalToLocal(rect!.topLeft) & rect.size;
}

/// The part of the overlay a menu may use: the system padding and keyboard, plus [margin].
Rect lnMenuArea(BuildContext context, Size size, {double margin = 8}) {
  final media = MediaQuery.of(context);
  final insets = media.padding + media.viewInsets;
  return Rect.fromLTRB(
    insets.left + margin,
    insets.top + margin,
    size.width - insets.right - margin,
    size.height - insets.bottom - margin,
  );
}

/// The horizontal place of a [width]-wide menu edge-aligned to [anchor]: the anchor's edge nearer
/// the screen edge (its start edge when both are as near), kept inside [area].
double lnMenuLeft(
  Rect anchor,
  Rect area,
  double width,
  TextDirection direction,
) {
  final toLeft = anchor.left - area.left;
  final toRight = area.right - anchor.right;
  final bool alignLeft;
  if ((toLeft - toRight).abs() < 1) {
    alignLeft = direction == TextDirection.ltr;
  } else {
    alignLeft = toLeft < toRight;
  }
  final left = alignLeft ? anchor.left : anchor.right - width;
  return left.clamp(area.left, math.max(area.left, area.right - width));
}

/// Where [showLnPopoverMenu] puts a menu of [height] next to [anchor]: below it when it fits, else
/// above it when it fits there, else on the roomier side with the height cut to that room (the
/// rows scroll).
Rect lnPopoverRect({
  required Rect anchor,
  required Rect area,
  required double width,
  required double height,
  required double gap,
  required TextDirection direction,
}) {
  final w = math.min(width, area.width);
  final left = lnMenuLeft(anchor, area, w, direction);
  final below = area.bottom - (anchor.bottom + gap);
  final above = (anchor.top - gap) - area.top;
  if (height <= below || (height > above && below >= above)) {
    return Rect.fromLTWH(
      left,
      anchor.bottom + gap,
      w,
      math.max(0, math.min(height, below)),
    );
  }
  final h = math.max(0.0, math.min(height, above));
  return Rect.fromLTWH(left, anchor.top - gap - h, w, h);
}

/// Opens a menu anchored to a widget ([anchorKey]) or a global [anchorRect], without a scrim: the
/// [LnMenuCard] of [actions] ([width] dp, rows [rowHeight] tall, at least 48), [gap] dp below the
/// anchor or above it when there is no room below (a negative [gap] overlaps the anchor),
/// edge-aligned to the anchor (see [lnMenuLeft]).
/// The row whose value equals [selected] shows a check (a picker); with [selected] null no row is
/// checkable. Rows draw in [LnPalette.fgWarm]. A tap outside and Android back dismiss it.
///
/// Completes with the chosen action's [LnMenuAction.value] (null when dismissed) and then calls its
/// [LnMenuAction.onSelected].
Future<T?> showLnPopoverMenu<T>(
  BuildContext context, {
  required List<LnMenuAction<T>> actions,
  GlobalKey? anchorKey,
  Rect? anchorRect,
  T? selected,
  double width = 240,
  double rowHeight = LnSize.menuRow,
  double gap = 4,
  String? semanticLabel,
  bool useRootNavigator = true,
}) async {
  final navigator = Navigator.of(context, rootNavigator: useRootNavigator);
  final anchor = lnAnchorRect(navigator, key: anchorKey, rect: anchorRect);
  final reduced = MediaQuery.disableAnimationsOf(context);
  final chosen = await navigator.push(
    _PopoverRoute<LnMenuAction<T>>(
      theme: context.ln,
      direction: Directionality.of(context),
      barrierLabel: MaterialLocalizations.of(context).modalBarrierDismissLabel,
      duration: reduced ? Duration.zero : LnMotion.fast,
      builder: (context, animation) {
        final scaler = MediaQuery.textScalerOf(context);
        final rows = LnMenuRow.extent(rowHeight, scaler);
        final indent = actions.any((a) => a.icon != null);
        return LayoutBuilder(
          builder: (context, box) {
            final area = lnMenuArea(context, box.biggest);
            final rect = lnPopoverRect(
              anchor: anchor,
              area: area,
              width: width,
              height: actions.length * rows + 2 * LnMenuCard.verticalPadding,
              gap: gap,
              direction: Directionality.of(context),
            );
            // By position, not by edges: a negative gap overlaps the anchor.
            final above = rect.center.dy < anchor.center.dy;
            return Stack(
              children: [
                Positioned.fromRect(
                  rect: rect,
                  child: FadeTransition(
                    opacity: animation,
                    child: ScaleTransition(
                      scale: Tween<double>(
                        begin: 0.95,
                        end: 1,
                      ).animate(animation),
                      alignment: above
                          ? Alignment.bottomCenter
                          : Alignment.topCenter,
                      child: Semantics(
                        scopesRoute: true,
                        namesRoute: true,
                        explicitChildNodes: true,
                        label:
                            semanticLabel ??
                            MaterialLocalizations.of(context).popupMenuLabel,
                        child: LnMenuCard(
                          children: [
                            for (final a in actions)
                              LnMenuRow(
                                label: a.label,
                                icon: a.icon,
                                indent: indent,
                                destructive: a.destructive,
                                enabled: a.enabled,
                                height: rowHeight,
                                color: context.ln.colors.fgWarm,
                                checked: selected == null
                                    ? null
                                    : a.value == selected,
                                onTap: () => Navigator.of(context).pop(a),
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            );
          },
        );
      },
    ),
  );
  chosen?.onSelected?.call();
  return chosen?.value;
}

/// A menu route without a scrim: the barrier only catches the outside tap (and names the dismiss
/// action for screen readers). The caller's [LnTheme] and direction are carried in.
class _PopoverRoute<R> extends PopupRoute<R> {
  _PopoverRoute({
    required this.theme,
    required this.direction,
    required this.barrierLabel,
    required this.duration,
    required this.builder,
  });

  final LnThemeData theme;
  final TextDirection direction;
  final Duration duration;
  final Widget Function(BuildContext context, Animation<double> animation)
  builder;

  @override
  final String barrierLabel;

  @override
  Color? get barrierColor => null;

  @override
  bool get barrierDismissible => true;

  @override
  Duration get transitionDuration => duration;

  late final CurvedAnimation _curved = CurvedAnimation(
    parent: animation!,
    curve: LnMotion.emphasized,
    reverseCurve: Curves.easeIn,
  );

  @override
  Widget buildPage(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
  ) => LnTheme(
    data: theme,
    child: Directionality(
      textDirection: direction,
      child: builder(context, _curved),
    ),
  );

  @override
  void dispose() {
    _curved.dispose();
    super.dispose();
  }
}
