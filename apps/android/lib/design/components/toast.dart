import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../theme.dart';

enum LnToastKind { normal, notice, positive, error }

/// Transient toast on forui's toaster ([showFToast]); requires an [FToaster] (or [FScaffold]) above the
/// calling context. `lnForuiTheme` places toasts at the top with an inverse surface. The previous toast
/// is dismissed so only one shows at a time; forui keeps it while it is pressed and allows swiping it
/// away.
abstract final class LnToast {
  static const defaultDuration = Duration(milliseconds: 2400);

  static FToasterEntry? _current;

  /// Shows [text]. [action] is a `(label, callback)` pair rendered as a trailing text button.
  static FToasterEntry show(
    BuildContext context,
    String text, {
    LnToastKind kind = LnToastKind.normal,
    (String, VoidCallback)? action,
    Duration duration = defaultDuration,
  }) {
    dismiss();
    final c = context.ln.colors;
    final (Color? accent, IconData? icon) = switch (kind) {
      LnToastKind.normal => (null, null),
      LnToastKind.notice => (c.warning, FIcons.info),
      LnToastKind.positive => (c.success, FIcons.check),
      LnToastKind.error => (c.error, FIcons.x),
    };
    final direction = Directionality.maybeOf(context) ?? TextDirection.ltr;
    SemanticsService.sendAnnouncement(View.of(context), text, direction);
    late final FToasterEntry entry;
    entry = showFToast(
      context: context,
      duration: duration,
      icon: icon == null
          ? null
          : Container(
              width: 20,
              height: 20,
              decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
              child: Icon(icon, size: 13, color: c.onAccent),
            ),
      title: Text(text, maxLines: 3, overflow: TextOverflow.ellipsis),
      suffixBuilder: action == null
          ? null
          : (context, entry) => GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () {
                action.$2();
                entry.dismiss();
              },
              child: Semantics(
                button: true,
                child: Padding(
                  padding: const EdgeInsetsDirectional.only(start: 12),
                  child: Text(
                    action.$1,
                    style: context.ln.text.captionStrong.copyWith(
                      color: c.toastAction,
                    ),
                  ),
                ),
              ),
            ),
      // An older toast finishing its exit must not forget the newer one.
      onDismiss: () {
        if (identical(_current, entry)) _current = null;
      },
    );
    _current = entry;
    return entry;
  }

  /// Dismisses the current toast.
  static void dismiss() {
    final current = _current;
    _current = null;
    if (current == null) return;
    try {
      current.dismiss();
    } on FlutterError {
      // Its toaster was disposed with the tree that showed it; nothing is left to dismiss.
    }
  }
}
