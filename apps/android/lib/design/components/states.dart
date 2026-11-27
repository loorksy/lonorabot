import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:shimmer/shimmer.dart';

import '../theme.dart';
import '../tokens.dart';
import 'block_button.dart';
import 'spinner.dart';

/// Centred empty state: illustration/icon slot, title, body and an optional action.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    this.icon,
    this.illustration,
    required this.title,
    this.body,
    this.actionLabel,
    this.onAction,
  });

  /// Shown in a 64 dp fill1 circle when no [illustration] is given.
  final IconData? icon;
  final Widget? illustration;
  final String title;
  final String? body;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (illustration != null)
              illustration!
            else if (icon != null)
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  color: c.fill1,
                  shape: BoxShape.circle,
                ),
                child: Icon(icon, size: 28, color: c.fgMuted),
              ),
            const SizedBox(height: 16),
            Text(
              title,
              textAlign: TextAlign.center,
              style: ln.text.title.copyWith(color: c.fg),
            ),
            if (body != null) ...[
              const SizedBox(height: 6),
              Text(
                body!,
                textAlign: TextAlign.center,
                style: ln.text.caption.copyWith(color: c.fgMuted),
              ),
            ],
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(height: 20),
              BlockButton(
                label: actionLabel!,
                onPressed: onAction,
                expand: false,
                variant: BlockButtonVariant.secondary,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// [EmptyState] for failures, with a retry button.
class ErrorState extends StatelessWidget {
  const ErrorState({
    super.key,
    required this.title,
    this.body,
    required this.retryLabel,
    this.onRetry,
    this.icon = FIcons.triangleAlert,
  });

  final String title;
  final String? body;
  final String retryLabel;
  final VoidCallback? onRetry;

  /// The warning triangle by default; e.g. `FIcons.wifiOff` when the device is offline.
  final IconData icon;

  @override
  Widget build(BuildContext context) => EmptyState(
    icon: icon,
    title: title,
    body: body,
    actionLabel: retryLabel,
    onAction: onRetry,
  );
}

/// Shimmering placeholders shaped like [ChatListRow]s (66 dp pitch).
class SkeletonRows extends StatelessWidget {
  const SkeletonRows({
    super.key,
    this.count = 6,
    this.animate = true,
    this.semanticLabel = 'Loading',
    this.inset = LnSpace.listInset,
  });

  final int count;

  /// Horizontal inset of each row; a caller whose own padding already sets the row edge passes 0.
  final double inset;

  /// The caller's localized loading label; the English default is for the gallery.
  final String semanticLabel;

  /// Disable for static screenshots.
  final bool animate;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final base = Color.alphaBlend(c.fill3, c.bg);
    final highlight = Color.alphaBlend(c.fill1, c.bg);
    Widget bar(double w, double h) => Container(
      width: w,
      height: h,
      decoration: BoxDecoration(
        color: base,
        borderRadius: BorderRadius.all(Radius.circular(h / 2)),
      ),
    );
    final rows = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < count; i++)
          SizedBox(
            height: LnSize.listRow,
            child: Padding(
              padding: EdgeInsetsDirectional.symmetric(horizontal: inset),
              child: Row(
                children: [
                  Container(
                    width: LnSize.avatarList,
                    height: LnSize.avatarList,
                    decoration: BoxDecoration(
                      color: base,
                      borderRadius: const BorderRadius.all(Radius.circular(14)),
                    ),
                  ),
                  const SizedBox(width: LnSpace.listTextGap),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            bar(96.0 + (i * 37) % 70, 14),
                            const Spacer(),
                            bar(36, 12),
                          ],
                        ),
                        const SizedBox(height: 10),
                        bar(180.0 + (i * 53) % 90, 12),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
    return Semantics(
      label: semanticLabel,
      child: ExcludeSemantics(
        child: animate
            ? Shimmer.fromColors(
                baseColor: base,
                highlightColor: highlight,
                period: const Duration(milliseconds: 1400),
                child: rows,
              )
            : rows,
      ),
    );
  }
}

/// Shimmering placeholders shaped like the Explore layout: a tile strip (a [WideTile] and a small tile,
/// then a row of [ExploreTile]s, scrolling sideways) and [cards] full-width recommendation cards.
class ExploreSkeleton extends StatelessWidget {
  const ExploreSkeleton({
    super.key,
    required this.semanticLabel,
    this.cards = 3,
    this.animate = true,
  });

  /// The localized "Loading" read by screen readers.
  final String semanticLabel;
  final int cards;

  /// Disable for static screenshots.
  final bool animate;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final base = Color.alphaBlend(c.fill3, c.bg);
    final highlight = Color.alphaBlend(c.fill1, c.bg);
    Widget box(double w, double h) => Container(
      width: w,
      height: h,
      decoration: BoxDecoration(
        color: base,
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.tile)),
      ),
    );
    final content = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          physics: const NeverScrollableScrollPhysics(),
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: LnSpace.pageGutter,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  box(LnSize.wideTileWidth, LnSize.wideTileHeight),
                  const SizedBox(width: LnSpace.tileGap),
                  box(LnSize.exploreTile, LnSize.wideTileHeight),
                ],
              ),
              const SizedBox(height: LnSpace.tileGap),
              Row(
                children: [
                  for (var i = 0; i < 3; i++) ...[
                    box(LnSize.exploreTile, LnSize.exploreTile),
                    const SizedBox(width: LnSpace.tileGap),
                  ],
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 40),
        for (var i = 0; i < cards; i++)
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(
              LnSpace.pageGutter,
              0,
              LnSpace.pageGutter,
              LnSpace.tileGap,
            ),
            child: box(double.infinity, 76),
          ),
      ],
    );
    return Semantics(
      label: semanticLabel,
      child: ExcludeSemantics(
        child: animate
            ? Shimmer.fromColors(
                baseColor: base,
                highlightColor: highlight,
                period: const Duration(milliseconds: 1400),
                child: content,
              )
            : content,
      ),
    );
  }
}

enum NetworkStripStatus { hidden, offline, connecting, reconnected }

/// Connectivity banner under the status bar (it paints behind the status bar too). Animates its height
/// between states; hidden collapses to nothing.
class NetworkStrip extends StatelessWidget {
  const NetworkStrip({
    super.key,
    required this.status,
    required this.label,
    this.applyTopInset = true,
  });

  final NetworkStripStatus status;

  /// Localised text ("No connection", "Connecting…", "Back online").
  final String label;
  final bool applyTopInset;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final top = applyTopInset ? MediaQuery.paddingOf(context).top : 0.0;
    final (Color bg, Color fg) = switch (status) {
      NetworkStripStatus.reconnected => (c.success, c.onAccent),
      NetworkStripStatus.offline => (c.inverseSurface, c.onInverse),
      _ => (Color.alphaBlend(c.fill3, c.bg), c.fgMuted),
    };
    return AnimatedSize(
      duration: LnMotion.medium,
      curve: LnMotion.emphasized,
      alignment: Alignment.topCenter,
      child: status == NetworkStripStatus.hidden
          ? const SizedBox(width: double.infinity)
          : AnimatedContainer(
              duration: LnMotion.medium,
              color: bg,
              width: double.infinity,
              padding: EdgeInsets.only(top: top),
              child: Semantics(
                liveRegion: true,
                child: SizedBox(
                  height: 28,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      switch (status) {
                        NetworkStripStatus.connecting => LnSpinner(
                          size: 12,
                          color: fg,
                        ),
                        NetworkStripStatus.reconnected => Icon(
                          FIcons.check,
                          size: 14,
                          color: fg,
                        ),
                        _ => Icon(FIcons.wifiOff, size: 14, color: fg),
                      },
                      const SizedBox(width: 8),
                      Text(
                        label,
                        style: ln.text.smallStrong.copyWith(color: fg),
                      ),
                    ],
                  ),
                ),
              ),
            ),
    );
  }
}
