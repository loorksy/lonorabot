import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../theme.dart';
import '../tokens.dart';
import 'action_card.dart';
import 'tappable.dart';

/// A label/value pair inside a [ScheduleCard] ("When" / "Every day at 8:00 AM").
@immutable
class ScheduleField {
  const ScheduleField(this.label, this.value);

  final String label;
  final String value;
}

/// Scheduled-task card: 40 dp bordered icon tile with a clock, overflow menu button, title, divider,
/// label/value pairs and a bottom [BlockButton].
class ScheduleCard extends StatelessWidget {
  const ScheduleCard({
    super.key,
    required this.title,
    required this.fields,
    this.icon = FIcons.clock,
    this.onMenu,
    this.menuLabel = 'More options',
    this.action,
    this.width,
  });

  final String title;
  final List<ScheduleField> fields;
  final IconData icon;

  /// Shows the ellipsis button at the top-end when set.
  final VoidCallback? onMenu;
  final String menuLabel;

  /// Bottom button, usually a [BlockButton].
  final Widget? action;
  final double? width;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return SizedBox(
      width: width ?? ActionCard.widthFor(MediaQuery.sizeOf(context).width),
      child: LnCardSurface(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.cardPadding,
                LnSpace.cardPadding,
                LnSpace.cardPadding,
                0,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: LnSize.iconTile,
                    height: LnSize.iconTile,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: c.surface,
                      borderRadius: const BorderRadius.all(
                        Radius.circular(LnRadius.iconTile),
                      ),
                      border: Border.all(color: c.border),
                    ),
                    child: Icon(icon, size: LnSize.chromeIcon, color: c.fg),
                  ),
                  const Spacer(),
                  if (onMenu != null)
                    LnTappable(
                      onTap: onMenu,
                      haptic: true,
                      semanticLabel: menuLabel,
                      excludeChildSemantics: true,
                      child: SizedBox.square(
                        dimension: LnSize.iconTile,
                        child: Icon(
                          FIcons.ellipsis,
                          size: LnSize.chromeIcon,
                          color: c.fg,
                        ),
                      ),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.cardPadding,
                10,
                LnSpace.cardPadding,
                0,
              ),
              child: Text(title, style: ln.text.title.copyWith(color: c.fg)),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.cardPadding,
                LnSpace.sm,
                LnSpace.cardPadding,
                0,
              ),
              child: FDivider(
                style: (s) => s.copyWith(padding: EdgeInsets.zero),
              ),
            ),
            for (var i = 0; i < fields.length; i++)
              Padding(
                padding: EdgeInsetsDirectional.fromSTEB(
                  LnSpace.cardPadding,
                  i == 0 ? 11.5 : 11.5,
                  LnSpace.cardPadding,
                  0,
                ),
                child: MergeSemantics(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        fields[i].label,
                        style: ln.text.body.copyWith(color: c.fgMuted),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        fields[i].value,
                        style: ln.text.body.copyWith(color: c.fg),
                      ),
                    ],
                  ),
                ),
              ),
            if (action != null)
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(
                  LnSpace.cardButtonInset,
                  20,
                  LnSpace.cardButtonInset,
                  LnSpace.cardButtonInset,
                ),
                child: action,
              )
            else
              const SizedBox(height: LnSpace.cardPadding),
          ],
        ),
      ),
    );
  }
}
