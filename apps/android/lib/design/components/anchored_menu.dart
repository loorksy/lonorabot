// The long-press menu of a message: everything behind it blurred and lightly dimmed, the message
// redrawn sharp at its own place, a reaction pill above it and the menu card below it.
import 'dart:math' as math;
import 'dart:ui' show ImageFilter, lerpDouble;

import 'package:flutter/material.dart' show MaterialLocalizations;
import 'package:flutter/widgets.dart';

import '../theme.dart';
import '../tokens.dart';
import 'popover_menu.dart';
import 'sheets.dart' show LnMenuAction;
import 'tappable.dart';

/// One slot of [showLnAnchoredMenu]'s reaction pill.
@immutable
class LnReactionOption<T> {
  const LnReactionOption({
    required this.value,
    required this.child,
    required this.semanticLabel,
    this.selected = false,
  });

  /// Returned by [showLnAnchoredMenu] when the slot is tapped.
  final T value;

  /// Usually the emoji as a [Text] (drawn at 26 dp); an [Icon] for the "more" slot (24 dp, muted).
  final Widget child;
  final String semanticLabel;

  /// The owner's own reaction: drawn on a tinted disc and flagged selected.
  final bool selected;
}

/// Backdrop of the anchored menu: a heavy blur and a light dim (black 30 % in dark, 12 % in light).
/// Lonora-specific values; the dims are candidates for palette tokens.
const double _blurSigma = 24;
const _dimDark = Color(0x4D000000);
const _dimLight = Color(0x1F000000);

/// Pill → message and message → menu (dp).
const double _gap = 6;

/// A message taller than the room left keeps at least this much (dp), the menu scrolls below it.
const double _minTarget = 96;

/// The reaction pill: 48 dp slots (the touch target) in a 52 dp stadium with 4 dp end padding;
/// the selected disc is 44 dp.
const double _slot = LnSize.minTouch;
const double _pillHeight = 52;
const double _pillPadding = 4;
const double _selectedDisc = 44;

/// Opens the long-press menu of [target], the widget at [targetKey] (or at the global
/// [targetRect]): a modal overlay that blurs (σ 24) and lightly dims everything behind it, redraws
/// [target] sharp at its own rect (shifted only as much as needed to fit the safe area), shows the
/// [reactions] pill 6 dp above it (with [moreReaction] as its last slot) and the [actions] card
/// ([menuWidth] dp, optional [header] such as the message time) 6 dp below it. Pill and card align
/// with the side of the screen the target is nearer to.
///
/// When the column is taller than the safe area, the target is cut (at least 96 dp of it stays) so
/// the pill and the card stay visible; the card's rows scroll if even that is not enough. The cut
/// keeps the target's top, unless the target starts above the safe area (a message scrolled partly
/// out of view): then it keeps the part that was on screen, where the long press landed.
/// [target] must lay out at the target's size (pass the same bubble).
///
/// A tap outside the pill and card, or Android back, dismisses it with null. Completes with the
/// tapped reaction's or action's value; an action's [LnMenuAction.onSelected] runs after the menu
/// has closed.
Future<T?> showLnAnchoredMenu<T>(
  BuildContext context, {
  required Widget target,
  GlobalKey? targetKey,
  Rect? targetRect,
  List<LnMenuAction<T>> actions = const [],
  List<LnReactionOption<T>> reactions = const [],
  LnReactionOption<T>? moreReaction,
  String? header,
  String? reactionsLabel,
  String? menuLabel,
  double menuWidth = 250,
  bool useRootNavigator = true,
}) async {
  final navigator = Navigator.of(context, rootNavigator: useRootNavigator);
  final anchor = lnAnchorRect(navigator, key: targetKey, rect: targetRect);
  final reduced = MediaQuery.disableAnimationsOf(context);
  final picked = await navigator.push(
    _AnchoredMenuRoute<_Picked<T>>(
      theme: context.ln,
      direction: Directionality.of(context),
      barrierLabel: MaterialLocalizations.of(context).modalBarrierDismissLabel,
      duration: reduced ? Duration.zero : LnMotion.medium,
      builder: (context, animation) => _AnchoredMenu<T>(
        animation: animation,
        anchor: anchor,
        target: target,
        actions: actions,
        reactions: [...reactions, ?moreReaction],
        header: header,
        reactionsLabel: reactionsLabel,
        menuLabel: menuLabel,
        menuWidth: menuWidth,
      ),
    ),
  );
  picked?.action?.onSelected?.call();
  return picked?.value;
}

class _Picked<T> {
  const _Picked(this.value, [this.action]);

  final T? value;
  final LnMenuAction<T>? action;
}

/// The rects of the anchored menu's parts in the overlay.
@immutable
class _Placement {
  const _Placement({
    required this.pill,
    required this.target,
    required this.targetOffset,
    required this.menu,
  });

  final Rect pill;

  /// The target's shown rect: its own width, its height cut when there is no room.
  final Rect target;

  /// How far down the target the shown rect starts: 0 unless the cut keeps a lower part.
  final double targetOffset;
  final Rect menu;

  /// The column [pill], target, [menu] inside [area], shifted from [anchor] only as far as needed.
  static _Placement compute({
    required Rect anchor,
    required Rect area,
    required double pillWidth,
    required double menuWidth,
    required double menuHeight,
    required TextDirection direction,
  }) {
    final hasPill = pillWidth > 0;
    final hasMenu = menuHeight > 0;
    final pillBlock = hasPill ? _pillHeight + _gap : 0.0;
    var menuH = menuHeight;
    var targetH = anchor.height;
    double menuBlock() => hasMenu ? menuH + _gap : 0.0;
    if (pillBlock + targetH + menuBlock() > area.height) {
      targetH = math.max(
        math.min(anchor.height, _minTarget),
        area.height - pillBlock - menuBlock(),
      );
      if (hasMenu && pillBlock + targetH + menuBlock() > area.height) {
        menuH = math.max(0, area.height - pillBlock - targetH - _gap);
      }
    }
    final total = pillBlock + targetH + menuBlock();
    final top = (anchor.top - pillBlock)
        .clamp(area.top, math.max(area.top, area.bottom - total))
        .toDouble();
    final targetTop = top + pillBlock;
    // A cut target shows the part that was on screen: the window starts no lower than the visible
    // top and as high as it can while still reaching the visible bottom.
    final visibleTop = math.max(0.0, area.top - anchor.top);
    final visibleBottom = math.min(anchor.height, area.bottom - anchor.top);
    final targetOffset = math
        .min(visibleTop, math.max(0.0, visibleBottom - targetH))
        .clamp(0.0, anchor.height - targetH)
        .toDouble();
    final pillW = math.min(pillWidth, area.width);
    final menuW = math.min(menuWidth, area.width);
    return _Placement(
      pill: Rect.fromLTWH(
        lnMenuLeft(anchor, area, pillW, direction),
        top,
        hasPill ? pillW : 0,
        hasPill ? _pillHeight : 0,
      ),
      target: Rect.fromLTWH(anchor.left, targetTop, anchor.width, targetH),
      targetOffset: targetOffset,
      menu: Rect.fromLTWH(
        lnMenuLeft(anchor, area, menuW, direction),
        targetTop + targetH + _gap,
        hasMenu ? menuW : 0,
        menuH,
      ),
    );
  }
}

class _AnchoredMenu<T> extends StatelessWidget {
  const _AnchoredMenu({
    required this.animation,
    required this.anchor,
    required this.target,
    required this.actions,
    required this.reactions,
    required this.header,
    required this.reactionsLabel,
    required this.menuLabel,
    required this.menuWidth,
  });

  final Animation<double> animation;
  final Rect anchor;
  final Widget target;
  final List<LnMenuAction<T>> actions;
  final List<LnReactionOption<T>> reactions;
  final String? header;
  final String? reactionsLabel;
  final String? menuLabel;
  final double menuWidth;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final direction = Directionality.of(context);
    final scaler = MediaQuery.textScalerOf(context);
    final rowExtent = LnMenuRow.extent(LnSize.menuRow, scaler);
    final menuHeight = actions.isEmpty
        ? 0.0
        : actions.length * rowExtent +
              2 * LnMenuCard.verticalPadding +
              (header == null ? 0 : LnMenuCard.headerExtent(scaler));
    final pillWidth = reactions.isEmpty
        ? 0.0
        : reactions.length * _slot + 2 * _pillPadding;
    final indent = actions.any((a) => a.icon != null);
    final dim = c.isDark ? _dimDark : _dimLight;

    final pill = reactions.isEmpty
        ? null
        : _ReactionPill<T>(reactions: reactions, label: reactionsLabel);
    final menu = actions.isEmpty
        ? null
        : LnMenuCard(
            header: header,
            children: [
              for (final a in actions)
                LnMenuRow(
                  label: a.label,
                  icon: a.icon,
                  indent: indent,
                  destructive: a.destructive,
                  enabled: a.enabled,
                  onTap: () =>
                      Navigator.of(context).pop(_Picked<T>(a.value, a)),
                ),
            ],
          );

    // One named scope for the pill, the message and the card: announced when it opens.
    return Semantics(
      scopesRoute: true,
      namesRoute: true,
      explicitChildNodes: true,
      label: menuLabel ?? MaterialLocalizations.of(context).popupMenuLabel,
      child: LayoutBuilder(
        builder: (context, box) {
          final place = _Placement.compute(
            anchor: anchor,
            area: lnMenuArea(context, box.biggest),
            pillWidth: pillWidth,
            menuWidth: menuWidth,
            menuHeight: menuHeight,
            direction: direction,
          );
          return AnimatedBuilder(
            animation: animation,
            builder: (context, _) {
              final t = animation.value;
              // The column rides on the target as it moves from its own place to the shown one.
              final dy = lerpDouble(0, place.target.top - anchor.top, t)!;
              final shownHeight = lerpDouble(
                anchor.height,
                place.target.height,
                t,
              )!;
              // The shown window slides down the target to the part that stays.
              final offset = lerpDouble(0, place.targetOffset, t)!;
              final appear = t.clamp(0.0, 1.0);
              final scale = 0.92 + 0.08 * appear;
              return Stack(
                children: [
                  Positioned.fill(
                    child: IgnorePointer(
                      child: BackdropFilter(
                        filter: ImageFilter.blur(
                          sigmaX: _blurSigma * appear,
                          sigmaY: _blurSigma * appear,
                          tileMode: TileMode.clamp,
                        ),
                        child: ColoredBox(
                          color: dim.withValues(alpha: dim.a * appear),
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    left: anchor.left,
                    top: anchor.top + dy,
                    width: anchor.width,
                    height: shownHeight,
                    child: IgnorePointer(
                      child: ClipRect(
                        child: OverflowBox(
                          alignment: Alignment.topCenter,
                          minWidth: anchor.width,
                          maxWidth: anchor.width,
                          minHeight: anchor.height,
                          maxHeight: anchor.height,
                          child: Transform.translate(
                            offset: Offset(0, -offset),
                            child: target,
                          ),
                        ),
                      ),
                    ),
                  ),
                  if (pill != null)
                    Positioned.fromRect(
                      rect: place.pill.shift(
                        Offset(0, dy - (place.target.top - anchor.top)),
                      ),
                      child: Opacity(
                        opacity: appear,
                        child: Transform.scale(
                          scale: scale,
                          alignment: Alignment.bottomCenter,
                          child: pill,
                        ),
                      ),
                    ),
                  if (menu != null)
                    Positioned(
                      left: place.menu.left,
                      top: anchor.top + dy + shownHeight + _gap,
                      width: place.menu.width,
                      height: place.menu.height,
                      child: Opacity(
                        opacity: appear,
                        child: Transform.scale(
                          scale: scale,
                          alignment: Alignment.topCenter,
                          child: menu,
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
  }
}

class _ReactionPill<T> extends StatelessWidget {
  const _ReactionPill({required this.reactions, required this.label});

  final List<LnReactionOption<T>> reactions;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final hairline = 1 / MediaQuery.devicePixelRatioOf(context);
    return Semantics(
      container: true,
      explicitChildNodes: true,
      label: label,
      child: DecoratedBox(
        decoration: ShapeDecoration(
          color: c.menuSurface,
          shape: StadiumBorder(
            side: BorderSide(color: c.menuBorder, width: hairline),
          ),
        ),
        child: ClipPath(
          clipper: const ShapeBorderClipper(shape: StadiumBorder()),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: _pillPadding),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final r in reactions)
                  LnTappable(
                    onTap: () => Navigator.of(context).pop(_Picked<T>(r.value)),
                    haptic: true,
                    selected: r.selected,
                    semanticLabel: r.semanticLabel,
                    excludeChildSemantics: true,
                    child: SizedBox(
                      width: _slot,
                      height: _pillHeight,
                      child: Center(
                        child: Container(
                          width: _selectedDisc,
                          height: _selectedDisc,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: r.selected ? c.reactionSelected : null,
                          ),
                          child: MediaQuery.withNoTextScaling(
                            child: DefaultTextStyle.merge(
                              style: const TextStyle(
                                fontSize: LnSize.reactionPickerEmoji,
                                height: 1,
                              ),
                              child: IconTheme.merge(
                                data: IconThemeData(
                                  size: LnSize.chromeIcon,
                                  color: c.fgMuted,
                                ),
                                child: r.child,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A modal route whose barrier only catches the outside tap; the page draws its own animated blur.
class _AnchoredMenuRoute<R> extends PopupRoute<R> {
  _AnchoredMenuRoute({
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
