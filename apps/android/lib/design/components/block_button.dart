import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../theme.dart';
import 'spinner.dart';

enum BlockButtonVariant {
  /// forui primary: fgStrong fill, canvas-coloured label.
  primary,

  /// forui secondary: #F0F0F0 neutral fill, fg label.
  secondary,

  /// forui destructive: error fill, white label.
  destructive,

  /// Lonora violet fill, white label (Lonora identity).
  brand,

  /// Consumed/past state (e.g. "Approved"): forui's disabled look as themed by `lnForuiTheme`
  /// (fill #F0F0F0, label #ADADAD). Equivalent to passing a null [BlockButton.onPressed].
  done,
}

/// Full-width 48 dp pill button: forui [FButton] with the Lonora button styles from `lnForuiTheme`.
/// Shows forui's circular progress icon while [loading].
class BlockButton extends StatelessWidget {
  const BlockButton({
    super.key,
    required this.label,
    this.onPressed,
    this.variant = BlockButtonVariant.primary,
    this.loading = false,
    this.icon,
    this.expand = true,
    this.semanticLabel,
  });

  final String label;
  final VoidCallback? onPressed;
  final BlockButtonVariant variant;
  final bool loading;

  /// Optional leading icon.
  final IconData? icon;

  /// Fill the available width (default) or hug the label.
  final bool expand;
  final String? semanticLabel;

  static void _busy() {}

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final style = switch (variant) {
      BlockButtonVariant.primary ||
      BlockButtonVariant.done => FButtonStyle.primary(),
      BlockButtonVariant.secondary => FButtonStyle.secondary(),
      BlockButtonVariant.destructive => FButtonStyle.destructive(),
      BlockButtonVariant.brand => FButtonStyle.primary(
        (s) => s.copyWith(
          decoration: FWidgetStateMap({
            WidgetState.disabled: s.decoration.resolve({WidgetState.disabled}),
            WidgetState.hovered | WidgetState.pressed: s.decoration
                .resolve({})
                .copyWith(
                  color: Color.lerp(c.brand, const Color(0xFF000000), 0.08),
                ),
            WidgetState.any: s.decoration.resolve({}).copyWith(color: c.brand),
          }),
          contentStyle: (cs) => cs.copyWith(
            textStyle: FWidgetStateMap({
              WidgetState.disabled: cs.textStyle.resolve({
                WidgetState.disabled,
              }),
              WidgetState.any: cs.textStyle
                  .resolve({})
                  .copyWith(color: c.onAccent),
            }),
          ),
        ),
      ),
    };
    final onPress = variant == BlockButtonVariant.done
        ? null
        : (loading ? _busy : onPressed);
    return Semantics(
      label: semanticLabel,
      child: FButton(
        style: style,
        onPress: onPress,
        mainAxisSize: expand ? MainAxisSize.max : MainAxisSize.min,
        prefix: loading
            ? const LnSpinner(size: 18)
            : (icon == null ? null : Icon(icon)),
        child: Text(label, maxLines: 1, overflow: TextOverflow.ellipsis),
      ),
    );
  }
}
