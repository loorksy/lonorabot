// Asks before a group form with unsaved edits is left (Lonora Web's «مغادرة التعديلات؟»,
// apps/web/src/shell/navigation.tsx:95-135): the system back, the predictive back and the
// header's back or ✕ circle (which pop through `maybePop`) all go through it.
import 'package:flutter/widgets.dart';

import '../../design/design.dart';
import '../../l10n/l10n.dart';

/// «مغادرة التعديلات؟» · «تجاهل» / «متابعة التعديل»; true when the owner discards the edits.
Future<bool> confirmLeaveEdits(BuildContext context) {
  final l10n = context.l10n;
  return showLnConfirm(
    context,
    title: l10n.t('groups_leaveQ'),
    message: l10n.t('groups_leaveBody'),
    confirmLabel: l10n.t('groups_discard'),
    cancelLabel: l10n.t('groups_keepEditing'),
    destructive: true,
  );
}

class LeaveGuard extends StatelessWidget {
  const LeaveGuard({super.key, required this.dirty, required this.child});

  final bool dirty;
  final Widget child;

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !dirty,
    onPopInvokedWithResult: (didPop, _) async {
      if (didPop) return;
      if (await confirmLeaveEdits(context) && context.mounted) {
        Navigator.of(context).pop();
      }
    },
    child: child,
  );
}
