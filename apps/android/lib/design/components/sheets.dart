// Sheets, dialogs and menus on forui's own overlays (showFSheet, showFDialog/FDialog, FPopoverMenu)
// and Flutter's CupertinoSheetRoute (the stacked full-height sheet). Lonora's sheet tokens (60 %
// surface over a backdrop blur, 38 dp top radius) are applied on top of forui's behaviour. The blur
// strength is a Lonora choice.
import 'dart:ui' show ImageFilter;

import 'package:flutter/cupertino.dart'
    show CupertinoSheetRoute, CupertinoSheetTransition;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../theme.dart';
import '../tokens.dart';
import 'circle_icon_button.dart';
import 'tappable.dart';

/// Modal bottom sheet via forui [showFSheet]: translucent blurred sheet, 38 dp top radius, drag handle, keyboard
/// aware, capped at [maxHeightFraction] of the screen. Android back, the barrier and a downward drag
/// close it. The caller's [LnTheme] is carried into the sheet. [titleInset] is the title's horizontal
/// inset: the body's 16 dp by default; a body whose rows pad their own content passes that
/// content's inset.
Future<T?> showLnSheet<T>(
  BuildContext context, {
  required WidgetBuilder builder,
  String? title,
  double titleInset = 16,
  double maxHeightFraction = 0.9,
  bool isDismissible = true,
  bool enableDrag = true,
  bool showHandle = true,
  bool useRootNavigator = true,
  EdgeInsetsGeometry padding = const EdgeInsetsDirectional.fromSTEB(
    16,
    0,
    16,
    16,
  ),
}) {
  final ln = context.ln;
  return showFSheet<T>(
    context: context,
    side: FLayout.btt,
    useRootNavigator: useRootNavigator,
    barrierDismissible: isDismissible,
    draggable: enableDrag,
    mainAxisMaxRatio: maxHeightFraction,
    builder: (sheetContext) => LnTheme(
      data: ln,
      child: Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.viewInsetsOf(sheetContext).bottom,
        ),
        child: _SheetMaterial(
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (showHandle) const LnSheetHandle(),
                if (title != null)
                  Padding(
                    padding: EdgeInsetsDirectional.fromSTEB(
                      titleInset,
                      12,
                      titleInset,
                      8,
                    ),
                    child: Semantics(
                      header: true,
                      child: Text(title, style: ln.text.display),
                    ),
                  )
                else
                  const SizedBox(height: 8),
                Flexible(
                  child: Padding(
                    padding: padding,
                    child: Builder(builder: builder),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

/// Sheet fill with its top-rounded clip; a translucent fill sits on a backdrop blur.
class _SheetMaterial extends StatelessWidget {
  const _SheetMaterial({required this.child});

  final Widget child;

  static const _radius = BorderRadius.vertical(
    top: Radius.circular(LnRadius.sheet),
  );

  @override
  Widget build(BuildContext context) {
    final color = context.ln.colors.sheet;
    final body = DecoratedBox(
      decoration: BoxDecoration(color: color, borderRadius: _radius),
      child: child,
    );
    if (color.a == 1) return body;
    return ClipRRect(
      borderRadius: _radius,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30),
        child: body,
      ),
    );
  }
}

/// 36 × 4 drag handle at the top of sheets, [top] dp below the sheet's edge.
class LnSheetHandle extends StatelessWidget {
  const LnSheetHandle({super.key, this.top = 8});

  final double top;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(top: top),
    child: Center(
      heightFactor: 1,
      child: Container(
        width: 36,
        height: 4,
        decoration: BoxDecoration(
          color: context.ln.colors.fgSubtle.withValues(alpha: 0.45),
          borderRadius: const BorderRadius.all(Radius.circular(2)),
        ),
      ),
    ),
  );
}

/// Pushes a stacked full-height sheet ([LnStackedSheetRoute]) and completes with the value it is
/// popped with. The page below scales back to a rounded card over a black backdrop; the sheet
/// stops 8 % of the screen below the top, with 12 dp top corners and the opaque
/// [LnPalette.sheetPage] fill. [showHandle] adds the 36 × 4 handle 5 dp below its top. A
/// downward drag (when [enableDrag]) and Android back close it. Start the content with an
/// [LnSheetHeader]; a scrolling body passes [LnStackedSheet.scrollControllerOf] to its scrollable
/// so a drag at the scroll top closes the sheet. The caller's [LnTheme] is carried into the sheet.
Future<T?> showLnStackedSheet<T>(
  BuildContext context, {
  required WidgetBuilder builder,
  bool showHandle = false,
  bool enableDrag = true,
  bool useRootNavigator = true,
  RouteSettings? settings,
}) => Navigator.of(context, rootNavigator: useRootNavigator).push<T>(
  LnStackedSheetRoute<T>(
    builder: builder,
    showHandle: showHandle,
    enableDrag: enableDrag,
    settings: settings,
    theme: context.ln,
  ),
);

/// The route of [showLnStackedSheet]: Flutter's [CupertinoSheetRoute] (slide-up, drag to dismiss,
/// stacking over another sheet) with Lonora's page treatment. The page it covers scales to
/// [coverScale] about its top centre, moves down 7 % of the screen, rounds to
/// [LnRadius.stackedSheet] and takes a 10 % veil (light grey in dark, black in light), over a
/// black backdrop. Push it on a navigator directly for nested navigation or named routes.
class LnStackedSheetRoute<T> extends CupertinoSheetRoute<T> {
  LnStackedSheetRoute({
    required WidgetBuilder builder,
    bool showHandle = false,
    super.enableDrag,
    super.settings,
    LnThemeData? theme,
  }) : super(
         scrollableBuilder: (context, controller) => _StackedSheetBody(
           controller: controller,
           showHandle: showHandle,
           theme: theme,
           builder: builder,
         ),
       );

  /// Scale of the covered page.
  static const double coverScale = 0.904;

  @override
  DelegatedTransitionBuilder? get delegatedTransition => _coverPage;

  static Widget? _coverPage(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    bool allowSnapshotting,
    Widget? child,
  ) {
    if (child == null) return null;
    // A sheet covering a sheet: Flutter's own lift-and-scale.
    if (CupertinoSheetRoute.hasParentSheet(context)) {
      return CupertinoSheetTransition.delegateTransition(
        context,
        animation,
        secondaryAnimation,
        allowSnapshotting,
        child,
      );
    }
    final linear = Navigator.of(context).userGestureInProgress;
    final curved = CurvedAnimation(
      parent: secondaryAnimation,
      curve: linear ? Curves.linear : Curves.linearToEaseOut,
      reverseCurve: linear ? Curves.linear : Curves.easeInToLinear,
    );
    final scale = curved.drive(Tween<double>(begin: 1, end: coverScale));
    final slide = curved.drive(
      Tween<Offset>(begin: Offset.zero, end: const Offset(0, 0.07)),
    );
    final radius = curved.drive(
      BorderRadiusTween(
        begin: BorderRadius.zero,
        end: const BorderRadius.all(Radius.circular(LnRadius.stackedSheet)),
      ),
    );
    final veil = curved.drive(Tween<double>(begin: 0, end: 0.1));
    curved.dispose();
    return ColoredBox(
      color: const Color(0xFF000000),
      child: Stack(
        children: [
          AnnotatedRegion<SystemUiOverlayStyle>(
            value: SystemUiOverlayStyle.light,
            child: SizedBox(
              height: MediaQuery.sizeOf(context).height * 0.08,
              width: double.infinity,
            ),
          ),
          SlideTransition(
            position: slide,
            child: ScaleTransition(
              scale: scale,
              alignment: Alignment.topCenter,
              filterQuality: FilterQuality.medium,
              child: AnimatedBuilder(
                animation: radius,
                builder: (context, page) => ClipRSuperellipse(
                  borderRadius: radius.value ?? BorderRadius.zero,
                  child: page,
                ),
                child: Stack(
                  children: [
                    child,
                    IgnorePointer(
                      child: FadeTransition(
                        opacity: veil,
                        child: ColoredBox(
                          color: context.ln.isDark
                              ? const Color(0xFFC8C8C8)
                              : const Color(0xFF000000),
                          child: const SizedBox.expand(),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Access to the stacked sheet around a widget.
abstract final class LnStackedSheet {
  /// The sheet's scroll controller: a scrollable that uses it closes the sheet when dragged down
  /// at its top. Null outside a stacked sheet.
  static ScrollController? scrollControllerOf(BuildContext context) => context
      .dependOnInheritedWidgetOfExactType<_StackedSheetScope>()
      ?.controller;
}

class _StackedSheetScope extends InheritedWidget {
  const _StackedSheetScope({required this.controller, required super.child});

  final ScrollController controller;

  @override
  bool updateShouldNotify(_StackedSheetScope old) =>
      controller != old.controller;
}

class _StackedSheetBody extends StatelessWidget {
  const _StackedSheetBody({
    required this.controller,
    required this.showHandle,
    required this.theme,
    required this.builder,
  });

  final ScrollController controller;
  final bool showHandle;
  final LnThemeData? theme;
  final WidgetBuilder builder;

  @override
  Widget build(BuildContext context) {
    final ln = theme ?? context.ln;
    return LnTheme(
      data: ln,
      child: _StackedSheetScope(
        controller: controller,
        child: ColoredBox(
          color: ln.colors.sheetPage,
          child: Stack(
            children: [
              Positioned.fill(child: Builder(builder: builder)),
              if (showHandle)
                const Align(
                  alignment: Alignment.topCenter,
                  child: LnSheetHandle(top: 5),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Header row of a stacked sheet: a ✕ at the start, the centred title (16 dp, warm ink) and an
/// optional [action] at the end, usually a [HeaderPillButton] («إنشاء»). The ✕ is a chrome circle
/// that closes the sheet ([onClose] replaces that); [plainClose] draws a bare 24 dp ✕ in the warm
/// ink instead, for read-only sheets. The circles sit 38 dp below the sheet's top at the 16 dp
/// gutters.
class LnSheetHeader extends StatelessWidget {
  const LnSheetHeader({
    super.key,
    required this.title,
    required this.closeLabel,
    this.onClose,
    this.action,
    this.plainClose = false,
  });

  final String title;

  /// The close button's spoken label («إغلاق»).
  final String closeLabel;
  final VoidCallback? onClose;
  final Widget? action;
  final bool plainClose;

  /// Height from the sheet's top to the row's bottom.
  static const double height = top + 48;

  /// Space above the row's 48 dp touch band.
  static const double top = 14;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final close = onClose ?? () => Navigator.of(context).maybePop();
    final closeButton = plainClose
        ? LnTappable(
            onTap: close,
            semanticLabel: closeLabel,
            excludeChildSemantics: true,
            child: SizedBox.square(
              dimension: LnSize.minTouch,
              child: Icon(FIcons.x, size: LnSize.chromeIcon, color: c.fgWarm),
            ),
          )
        : CircleIconButton(
            icon: const Icon(FIcons.x),
            semanticLabel: closeLabel,
            onTap: close,
          );
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter - 2,
        top,
        LnSpace.pageGutter - 2,
        0,
      ),
      child: SizedBox(
        height: LnSize.minTouch,
        child: NavigationToolbar(
          leading: closeButton,
          middle: Semantics(
            header: true,
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: ln.text.title.copyWith(color: c.fgWarm),
            ),
          ),
          trailing: action,
          middleSpacing: LnSpace.xs,
        ),
      ),
    );
  }
}

/// The primary pill of a sheet header («إنشاء»): a 36 dp stadium hugging its 16 dp label with 16 dp
/// sides, in [LnPalette.selectionFill] with a white label (4.6:1); disabled (null [onPressed]) it is the 4 %
/// fill with the tertiary ink. The touch target is 48 dp tall and 2 dp wider on each side, like a
/// [CircleIconButton], so both align at the same gutter.
class HeaderPillButton extends StatelessWidget {
  const HeaderPillButton({
    super.key,
    required this.label,
    this.onPressed,
    this.semanticLabel,
  });

  final String label;
  final VoidCallback? onPressed;

  /// Spoken instead of [label] when given.
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final enabled = onPressed != null;
    return LnTappable(
      onTap: onPressed,
      haptic: true,
      semanticLabel: semanticLabel ?? label,
      excludeChildSemantics: true,
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          minWidth: LnSize.minTouch,
          minHeight: LnSize.minTouch,
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2),
          child: Center(
            widthFactor: 1,
            child: Container(
              height: LnSize.headerPill,
              padding: const EdgeInsets.symmetric(horizontal: LnSpace.md),
              decoration: ShapeDecoration(
                color: enabled ? c.selectionFill : c.fill1,
                shape: const StadiumBorder(),
              ),
              child: Center(
                widthFactor: 1,
                child: Text(
                  label,
                  maxLines: 1,
                  style: ln.text.body.copyWith(
                    color: enabled ? c.onAccent : c.fgSubtle,
                    height: 1,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// An entry of [showLnActionMenu] and [LnPopoverMenu].
@immutable
class LnMenuAction<T> {
  const LnMenuAction({
    required this.label,
    this.icon,
    this.value,
    this.onSelected,
    this.destructive = false,
    this.enabled = true,
  });

  final String label;
  final IconData? icon;

  /// Returned by [showLnActionMenu] / passed to [LnPopoverMenu.onSelected] when chosen.
  final T? value;

  /// Called after the menu closes.
  final VoidCallback? onSelected;
  final bool destructive;
  final bool enabled;
}

FItem _menuItem(
  BuildContext context,
  LnMenuAction<dynamic> a,
  VoidCallback onPress,
) {
  final c = context.ln.colors;
  final color = a.destructive ? c.error : null;
  return FItem(
    enabled: a.enabled,
    onPress: onPress,
    prefix: a.icon == null ? null : Icon(a.icon, color: color),
    title: Text(a.label, style: color == null ? null : TextStyle(color: color)),
  );
}

/// Bottom-sheet action list built from forui [FItemGroup]/[FItem] (destructive rows in the error
/// colour). Completes with the chosen action's [LnMenuAction.value] (null when dismissed).
Future<T?> showLnActionMenu<T>(
  BuildContext context, {
  required List<LnMenuAction<T>> actions,
  String? title,
}) async {
  LnMenuAction<T>? chosen;
  await showLnSheet<void>(
    context,
    title: title,
    // Level with the rows' icons and labels: the body's 8 dp plus forui's 15 dp item padding.
    titleInset: 23,
    padding: const EdgeInsetsDirectional.fromSTEB(8, 0, 8, 8),
    builder: (context) => FItemGroup(
      children: [
        for (final a in actions)
          _menuItem(context, a, () {
            chosen = a;
            Navigator.of(context).pop();
          }),
      ],
    ),
  );
  chosen?.onSelected?.call();
  return chosen?.value;
}

/// Confirmation dialog via forui [showFDialog]/[FDialog] with cancel (outline) and confirm (primary or
/// destructive) [FButton]s, side by side when both labels fit, else stacked; a label wider than the
/// dialog wraps. Completes with true when confirmed.
Future<bool> showLnConfirm(
  BuildContext context, {
  required String title,
  String? message,
  required String confirmLabel,
  required String cancelLabel,
  bool destructive = false,
}) async {
  final ln = context.ln;
  final result = await showFDialog<bool>(
    context: context,
    useRootNavigator: true,
    builder: (dialogContext, style, animation) => LnTheme(
      data: ln,
      child: FDialog(
        style: (_) => style,
        animation: animation,
        direction: Axis.horizontal,
        title: Text(title),
        body: message == null ? null : Text(message),
        actions: [
          // One row while both labels fit; otherwise stacked, confirm on top, at the end side.
          Flexible(
            child: OverflowBar(
              spacing: style.horizontalStyle.actionSpacing,
              overflowSpacing: style.verticalStyle.actionSpacing,
              overflowAlignment: OverflowBarAlignment.end,
              overflowDirection: VerticalDirection.up,
              children: [
                FButton(
                  style: FButtonStyle.outline(),
                  mainAxisSize: MainAxisSize.min,
                  onPress: () => Navigator.of(dialogContext).pop(false),
                  // Wraps (centred) instead of overflowing forui's content row.
                  child: Flexible(
                    child: Text(cancelLabel, textAlign: TextAlign.center),
                  ),
                ),
                FButton(
                  style: destructive
                      ? FButtonStyle.destructive()
                      : FButtonStyle.primary(),
                  mainAxisSize: MainAxisSize.min,
                  onPress: () => Navigator.of(dialogContext).pop(true),
                  child: Flexible(
                    child: Text(confirmLabel, textAlign: TextAlign.center),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    ),
  );
  return result ?? false;
}

/// Context menu on forui [FPopoverMenu]: a long press on [child] (or a tap when [openOnTap]) opens the
/// menu anchored below it (flipping above when there is no room). [blurBackground] blurs everything behind
/// the menu, including the pressed item (off by default).
class LnPopoverMenu<T> extends StatefulWidget {
  const LnPopoverMenu({
    super.key,
    required this.child,
    required this.actions,
    this.onSelected,
    this.openOnTap = false,
    this.onTap,
    this.semanticLabel,
    this.blurBackground = false,
    this.menuAnchor = AlignmentDirectional.topStart,
    this.childAnchor = AlignmentDirectional.bottomStart,
  });

  final Widget child;
  final List<LnMenuAction<T>> actions;
  final ValueChanged<T?>? onSelected;

  /// Opens on tap instead of calling [onTap] (overflow buttons).
  final bool openOnTap;
  final VoidCallback? onTap;
  final String? semanticLabel;
  final bool blurBackground;
  final AlignmentGeometry menuAnchor;
  final AlignmentGeometry childAnchor;

  @override
  State<LnPopoverMenu<T>> createState() => _LnPopoverMenuState<T>();
}

class _LnPopoverMenuState<T> extends State<LnPopoverMenu<T>>
    with SingleTickerProviderStateMixin {
  late final FPopoverController _controller = FPopoverController(vsync: this);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FPopoverMenu(
    popoverController: _controller,
    menuAnchor: widget.menuAnchor,
    childAnchor: widget.childAnchor,
    style: widget.blurBackground
        ? (s) => s.copyWith(
            barrierFilter: (v) =>
                ImageFilter.blur(sigmaX: 6 * v, sigmaY: 6 * v),
          )
        : null,
    menu: [
      FItemGroup(
        children: [
          for (final a in widget.actions)
            _menuItem(context, a, () {
              _controller.hide();
              a.onSelected?.call();
              widget.onSelected?.call(a.value);
            }),
        ],
      ),
    ],
    builder: (context, controller, child) => Semantics(
      label: widget.semanticLabel,
      child: GestureDetector(
        behavior: HitTestBehavior.translucent,
        onLongPress: widget.openOnTap ? null : controller.toggle,
        onTap: widget.openOnTap ? controller.toggle : widget.onTap,
        child: child,
      ),
    ),
    child: widget.child,
  );
}
