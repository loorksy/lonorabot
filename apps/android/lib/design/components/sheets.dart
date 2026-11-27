// Sheets, dialogs and menus on forui's own overlays (showFSheet, showFDialog/FDialog, FPopoverMenu).
// Lonora's sheet tokens (60 % surface over a backdrop blur, 38 dp top radius) are applied on top of
// forui's behaviour. The blur strength is a Lonora choice.
import 'dart:ui' show ImageFilter;

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../theme.dart';
import '../tokens.dart';

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

/// 36 × 4 drag handle at the top of sheets.
class LnSheetHandle extends StatelessWidget {
  const LnSheetHandle({super.key});

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: Center(
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
