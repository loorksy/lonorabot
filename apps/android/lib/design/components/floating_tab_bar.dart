import 'dart:math' as math;
import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart' show MaterialLocalizations;
import 'package:flutter/widgets.dart';

import '../theme.dart';
import '../tokens.dart';
import 'badges.dart';
import 'tappable.dart';

/// One destination of the [FloatingTabBar].
@immutable
class LnTabItem {
  const LnTabItem({
    required this.icon,
    required this.label,
    this.selectedIcon,
    this.badgeCount,
    this.showDot = false,
  });

  /// Outline icon (unselected).
  final Widget icon;

  /// Filled icon shown while selected; falls back to [icon].
  final Widget? selectedIcon;

  /// Accessibility label (the bar shows no text).
  final String label;

  /// Unread count shown as a pill at the icon's top-end corner.
  final int? badgeCount;

  /// Shows a dot instead of a count.
  final bool showDot;
}

/// Floating navigation: a 62 dp stadium with icon-only 54 dp tabs and a sliding highlight 6 dp
/// wider than its tab on each side, plus a detached Ø62 action circle 8 dp away. Gutters are 21 dp;
/// the bottom offset is at least 12 dp. Mirrors in RTL.
///
/// Place it at the bottom of a [Stack] (it applies its own gutters and bottom offset) and pad scrolling
/// content by [FloatingTabBar.totalHeight].
class FloatingTabBar extends StatelessWidget {
  const FloatingTabBar({
    super.key,
    required this.items,
    required this.selectedIndex,
    required this.onSelect,
    this.actionIcon,
    this.actionLabel,
    this.onAction,
    this.actionDot = false,
    this.actionSelected = false,
    this.actionSelectedIcon,
  }) : assert(items.length >= 2);

  final List<LnTabItem> items;
  final int selectedIndex;
  final ValueChanged<int> onSelect;

  /// Icon of the detached action circle (e.g. invite). No circle when null.
  final Widget? actionIcon;
  final String? actionLabel;
  final VoidCallback? onAction;
  final bool actionDot;

  /// Treats the action circle as a selected destination: highlighted inner disc and [actionSelectedIcon].
  /// Pass a [selectedIndex] outside `items` (e.g. -1) so no tab shows the indicator meanwhile.
  final bool actionSelected;

  /// Filled icon shown while [actionSelected]; falls back to [actionIcon].
  final Widget? actionSelectedIcon;

  /// Distance between the bar's bottom edge and the screen's bottom edge: the system navigation inset,
  /// at least 12 dp (`SafeArea.minimum`).
  static double bottomOffset(BuildContext context) =>
      math.max(LnSpace.chromeBottom, MediaQuery.viewPaddingOf(context).bottom);

  /// Vertical space the bar covers from the bottom of the screen, including its offset.
  static double totalHeight(BuildContext context) =>
      LnSize.tabBarHeight + bottomOffset(context);

  /// Vertical space the floating chrome occupies from the screen bottom: bar height plus its bottom
  /// offset, which already accounts for the bottom view padding (see [bottomOffset]). Pad scroll content
  /// by this and place the composer [LnSpace.composerToBar] above it.
  static double occupiedHeight(BuildContext context) => totalHeight(context);

  @override
  Widget build(BuildContext context) {
    final hasAction = actionIcon != null;
    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        LnSpace.tabBarGutter,
        0,
        LnSpace.tabBarGutter,
        bottomOffset(context),
      ),
      child: SizedBox(
        height: LnSize.tabBarHeight,
        child: Row(
          spacing: LnSpace.tabBarSpacing,
          children: [
            Expanded(
              child: _Bar(
                items: items,
                selectedIndex: selectedIndex,
                onSelect: onSelect,
              ),
            ),
            if (hasAction)
              _ActionCircle(
                icon: actionIcon!,
                selectedIcon: actionSelectedIcon,
                selected: actionSelected,
                label: actionLabel ?? '',
                onTap: onAction,
                dot: actionDot,
              ),
          ],
        ),
      ),
    );
  }
}

/// Shared material of the bar and the action circle: bar surface, hairline, chrome shadow. A backdrop
/// blur is added only when the surface is translucent.
class _Glass extends StatelessWidget {
  const _Glass({required this.child, this.circle = false});

  final Widget child;
  final bool circle;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final shape = circle ? const CircleBorder() : const StadiumBorder();
    final surface = ln.colors.barSurface;
    Widget body = DecoratedBox(
      decoration: ShapeDecoration(
        color: surface,
        shape: circle
            ? CircleBorder(side: BorderSide(color: ln.colors.border))
            : StadiumBorder(side: BorderSide(color: ln.colors.border)),
      ),
      child: child,
    );
    if (surface.a < 1) {
      body = ClipPath(
        clipper: ShapeBorderClipper(shape: shape),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
          child: body,
        ),
      );
    }
    return DecoratedBox(
      decoration: ShapeDecoration(shape: shape, shadows: ln.chromeShadow),
      child: body,
    );
  }
}

class _Bar extends StatelessWidget {
  const _Bar({
    required this.items,
    required this.selectedIndex,
    required this.onSelect,
  });

  final List<LnTabItem> items;
  final int selectedIndex;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final shown = selectedIndex >= 0 && selectedIndex < items.length;
    return _Glass(
      child: Padding(
        padding: LnSize.tabBarPadding,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final tabWidth = constraints.maxWidth / items.length;
            const outset = LnSize.tabIndicatorOutset;
            return Stack(
              clipBehavior: Clip.none,
              children: [
                AnimatedPositionedDirectional(
                  duration: LnMotion.tabIndicator,
                  curve: LnMotion.emphasized,
                  start:
                      tabWidth * selectedIndex.clamp(0, items.length - 1) -
                      outset,
                  top: 0,
                  height: LnSize.tabItemHeight,
                  width: tabWidth + 2 * outset,
                  child: AnimatedOpacity(
                    duration: LnMotion.fast,
                    opacity: shown ? 1 : 0,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: ln.colors.tabHighlight,
                        borderRadius: const BorderRadius.all(
                          Radius.circular(LnRadius.tabHighlight),
                        ),
                      ),
                    ),
                  ),
                ),
                Row(
                  children: [
                    for (var i = 0; i < items.length; i++)
                      Expanded(
                        child: SizedBox(
                          height: LnSize.tabItemHeight,
                          child: _TabButton(
                            item: items[i],
                            selected: i == selectedIndex,
                            index: i,
                            count: items.length,
                            onTap: () => onSelect(i),
                          ),
                        ),
                      ),
                  ],
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _TabButton extends StatelessWidget {
  const _TabButton({
    required this.item,
    required this.selected,
    required this.index,
    required this.count,
    required this.onTap,
  });

  final LnTabItem item;
  final bool selected;
  final int index;
  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final icon = selected ? (item.selectedIcon ?? item.icon) : item.icon;
    // One node: the label, the position hint (Material's localized «Tab N of M») and the group flag
    // sit on the tappable's own node, beside its tap and focus actions; the icon and badge are silent.
    return LnTappable(
      onTap: onTap,
      haptic: true,
      semanticLabel: item.label,
      semanticHint: MaterialLocalizations.of(context)
          .tabLabel(tabIndex: index + 1, tabCount: count),
      selected: selected,
      child: Semantics(
        inMutuallyExclusiveGroup: true,
        child: ExcludeSemantics(
          child: Center(
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                IconTheme.merge(
                  data: IconThemeData(
                    size: LnSize.chromeIcon,
                    color: selected ? c.fgStrong : c.fg,
                  ),
                  child: AnimatedSwitcher(
                    duration: LnMotion.fast,
                    switchInCurve: LnMotion.emphasized,
                    child: KeyedSubtree(key: ValueKey(selected), child: icon),
                  ),
                ),
                if (item.badgeCount != null && item.badgeCount! > 0)
                  PositionedDirectional(
                    top: -7,
                    start: 14,
                    child: UnreadPill(count: item.badgeCount!),
                  )
                else if (item.showDot)
                  const PositionedDirectional(
                    top: -2,
                    end: -3,
                    child: DotBadge(),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ActionCircle extends StatelessWidget {
  const _ActionCircle({
    required this.icon,
    required this.selectedIcon,
    required this.selected,
    required this.label,
    required this.onTap,
    required this.dot,
  });

  final Widget icon;
  final Widget? selectedIcon;
  final bool selected;
  final String label;
  final VoidCallback? onTap;
  final bool dot;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    return LnTappable(
      onTap: onTap,
      haptic: true,
      semanticLabel: label,
      selected: selected,
      excludeChildSemantics: true,
      child: SizedBox.square(
        dimension: LnSize.actionCircle,
        child: _Glass(
          circle: true,
          child: Padding(
            padding: const EdgeInsets.all(LnSize.actionCirclePadding),
            child: AnimatedContainer(
              duration: LnMotion.tabIndicator,
              curve: LnMotion.emphasized,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: selected
                    ? c.tabHighlight
                    : c.tabHighlight.withValues(alpha: 0),
              ),
              alignment: Alignment.center,
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  IconTheme.merge(
                    data: IconThemeData(
                      size: LnSize.chromeIcon,
                      color: selected ? c.fgStrong : c.fg,
                    ),
                    child: AnimatedSwitcher(
                      duration: LnMotion.fast,
                      child: KeyedSubtree(
                        key: ValueKey(selected),
                        child: selected ? (selectedIcon ?? icon) : icon,
                      ),
                    ),
                  ),
                  if (dot)
                    const PositionedDirectional(
                      top: -2,
                      end: -3,
                      child: DotBadge(),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Fades scrolling content into the canvas under the bottom chrome (tab bar, composer). Put it in the
/// same [Stack], below the chrome. [height] defaults to the tab bar's total height plus 24 dp.
class BottomChromeFade extends StatelessWidget {
  const BottomChromeFade({super.key, this.height});

  final double? height;

  @override
  Widget build(BuildContext context) {
    final bg = context.ln.colors.bg;
    final h = height ?? FloatingTabBar.totalHeight(context) + LnSpace.xl;
    return IgnorePointer(
      child: SizedBox(
        height: h,
        width: double.infinity,
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [bg.withValues(alpha: 0), bg.withValues(alpha: 0.85), bg],
              stops: const [0, 0.55, 1],
            ),
          ),
        ),
      ),
    );
  }
}
