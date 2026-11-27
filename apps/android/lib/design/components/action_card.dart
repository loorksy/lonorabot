import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../theme.dart';
import '../tokens.dart';

/// Bordered conversation card used for approvals and permissions, on forui's [FCard.raw]: width min(315, 80 % of the screen),
/// radius 24, hairline border, soft card shadow. Optional flat illustration header (fill2, 109 dp),
/// body with 16 dp padding, and an actions area whose [BlockButton]s are inset 12 dp.
class ActionCard extends StatelessWidget {
  const ActionCard({
    super.key,
    this.header,
    this.headerHeight = LnSize.illustrationHeader,
    this.body,
    this.actions = const [],
    this.width,
    this.semanticLabel,
  });

  /// Illustration shown centred on a flat fill2 band. No band when null.
  final Widget? header;
  final double headerHeight;

  /// Body content; plain [Text] inherits the 16/21.25 body style.
  final Widget? body;

  /// Usually one or two [BlockButton]s, stacked with 8 dp gaps.
  final List<Widget> actions;

  /// Overrides the default width.
  final double? width;
  final String? semanticLabel;

  /// min(315, 80 % of [screenWidth]).
  static double widthFor(double screenWidth) =>
      math.min(LnSize.cardMaxWidth, screenWidth * LnSize.bubbleMaxFraction);

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final content = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (header != null)
          Container(
            height: headerHeight,
            color: c.fill2,
            alignment: Alignment.center,
            child: header,
          ),
        if (body != null)
          Padding(
            padding: EdgeInsetsDirectional.fromSTEB(
              LnSpace.cardPadding,
              header != null ? LnSpace.sm : LnSpace.cardPadding,
              LnSpace.cardPadding,
              LnSpace.cardPadding,
            ),
            child: DefaultTextStyle(
              style: ln.text.body.copyWith(color: c.fg),
              child: body!,
            ),
          ),
        if (actions.isNotEmpty)
          Padding(
            padding: EdgeInsetsDirectional.fromSTEB(
              LnSpace.cardButtonInset,
              body == null ? LnSpace.cardButtonInset : 0,
              LnSpace.cardButtonInset,
              LnSpace.cardButtonInset,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (var i = 0; i < actions.length; i++) ...[
                  if (i > 0) const SizedBox(height: LnSpace.xs),
                  actions[i],
                ],
              ],
            ),
          ),
      ],
    );
    return Semantics(
      container: true,
      label: semanticLabel,
      child: SizedBox(
        width: width ?? widthFor(MediaQuery.sizeOf(context).width),
        child: LnCardSurface(child: content),
      ),
    );
  }
}

/// The bordered card surface shared by [ActionCard] and `ScheduleCard`: forui [FCard.raw] with the
/// card radius (24), canvas fill and soft card shadow; the hairline border is painted on top so
/// header fills reach the rounded edge.
class LnCardSurface extends StatelessWidget {
  const LnCardSurface({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    const radius = BorderRadius.all(Radius.circular(LnRadius.card));
    return FCard.raw(
      style: (s) => s.copyWith(
        decoration: BoxDecoration(
          color: ln.colors.surface,
          borderRadius: radius,
          boxShadow: ln.cardShadow,
        ),
      ),
      child: Container(
        foregroundDecoration: BoxDecoration(
          borderRadius: radius,
          border: Border.all(color: ln.colors.border),
        ),
        child: ClipRRect(borderRadius: radius, child: child),
      ),
    );
  }
}
