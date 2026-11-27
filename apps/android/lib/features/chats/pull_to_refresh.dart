import 'package:flutter/material.dart'
    show RefreshIndicator, RefreshIndicatorStatus, RefreshIndicatorTriggerMode;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../design/design.dart';
import '../../l10n/l10n.dart';

/// Pull-to-refresh with the kit's spinner: Material's gesture logic without its look
/// ([RefreshIndicator.noSpinner]), a medium haptic when the pull arms, and an [LnSpinner]
/// [spinnerTop] dp from the top while [onRefresh] runs.
class LnPullToRefresh extends StatefulWidget {
  const LnPullToRefresh({
    super.key,
    required this.onRefresh,
    required this.child,
    this.spinnerTop,
  });

  final Future<void> Function() onRefresh;

  /// The scroll view.
  final Widget child;

  /// Defaults to just under the header circles.
  final double? spinnerTop;

  @override
  State<LnPullToRefresh> createState() => _LnPullToRefreshState();
}

class _LnPullToRefreshState extends State<LnPullToRefresh> {
  bool _busy = false;

  Future<void> _run() async {
    setState(() => _busy = true);
    try {
      await widget.onRefresh();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Stack(
    children: [
      Positioned.fill(
        child: RefreshIndicator.noSpinner(
          onRefresh: _run,
          triggerMode: RefreshIndicatorTriggerMode.anywhere,
          onStatusChange: (status) {
            if (status == RefreshIndicatorStatus.armed) {
              HapticFeedback.mediumImpact();
            }
          },
          child: widget.child,
        ),
      ),
      if (_busy)
        Positioned(
          top: widget.spinnerTop ?? ScreenHeader.heightOf(context) + 8,
          left: 0,
          right: 0,
          child: Center(
            child: LnSpinner(semanticLabel: context.t('sh_loading')),
          ),
        ),
    ],
  );
}
