// Page chrome shared by the agent, skills, routines, tasks and knowledge pages, composed from the
// kit: the Ø44 back circle and an optional trailing circle in the header row, the centred page
// title, then the page body.
import 'package:flutter/material.dart' show Scaffold, SelectionArea;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons, FTheme, FTile, FTileMixin;
import 'package:go_router/go_router.dart';

import '../../../app/routes.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';

/// Back from a pushed page; a page opened directly (deep link) goes to [fallback].
void leaveTo(BuildContext context, String fallback) {
  if (context.canPop()) {
    context.pop();
  } else {
    context.go(fallback);
  }
}

/// A pushed page: back circle (or [leading]), centred [title], optional [trailing] circle,
/// then [body] filling the rest.
class AgentPage extends StatelessWidget {
  const AgentPage({
    super.key,
    required this.title,
    required this.body,
    this.trailing,
    this.leading,
    this.fallback = Routes.agents,
    this.onBack,
    this.background,
  });

  final String title;
  final Widget body;
  final Widget? trailing;
  final Widget? leading;

  /// Where back goes when nothing is under this page.
  final String fallback;

  /// Replaces the default back behaviour (e.g. a discard-changes check).
  final VoidCallback? onBack;

  /// The page fill; the canvas by default. The agent's own sub-pages (instructions, memory) use
  /// [LnPalette.sheetPage].
  final Color? background;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    return Scaffold(
      backgroundColor: background ?? ln.colors.bg,
      body: Column(
        children: [
          ScreenHeader(
            leading:
                leading ??
                CircleIconButton(
                  // Lucide chevrons mirror themselves in RTL (matchTextDirection).
                  icon: const Icon(FIcons.chevronLeft),
                  semanticLabel: context.t('back'),
                  onTap: onBack ?? () => leaveTo(context, fallback),
                ),
            center: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 56),
              child: SizedBox(
                height: LnSize.headerCircle,
                child: Center(
                  child: Semantics(
                    header: true,
                    child: Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: ln.text.headline.copyWith(color: ln.colors.fg),
                    ),
                  ),
                ),
              ),
            ),
            trailing: trailing,
          ),
          const SizedBox(height: LnSpace.xs),
          Expanded(child: body),
        ],
      ),
    );
  }
}

/// The ✓ circle of an editor's header (the instructions, the avatar): Ø44 in a 48 dp touch box.
/// Enabled, it is the action blue ([LnPalette.selectionFill]) with a white check (4.6:1);
/// disabled (null [onTap]), the chrome circle with a tertiary check; [busy] shows a spinner.
class ConfirmCircle extends StatelessWidget {
  const ConfirmCircle({
    super.key,
    required this.semanticLabel,
    this.onTap,
    this.busy = false,
  });

  final String semanticLabel;
  final VoidCallback? onTap;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final enabled = onTap != null && !busy;
    return LnTappable(
      onTap: enabled ? onTap : null,
      haptic: true,
      semanticLabel: semanticLabel,
      excludeChildSemantics: true,
      child: SizedBox.square(
        dimension: LnSize.minTouch,
        child: Center(
          child: AnimatedContainer(
            duration: LnMotion.fast,
            width: LnSize.headerCircle,
            height: LnSize.headerCircle,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: enabled ? c.selectionFill : c.chromeCircle,
              shape: BoxShape.circle,
              border: enabled ? null : Border.fromBorderSide(ln.chromeRim),
              boxShadow: ln.chromeShadow,
            ),
            child: busy
                ? const LnSpinner(size: 18)
                : Icon(
                    FIcons.check,
                    size: LnSize.chromeIcon,
                    color: enabled ? c.onAccent : c.fgSubtle,
                  ),
          ),
        ),
      ),
    );
  }
}

/// A tile's trailing chevron. Lucide's chevron follows the text direction by itself.
class TileChevron extends StatelessWidget {
  const TileChevron({super.key});

  @override
  Widget build(BuildContext context) =>
      Icon(FIcons.chevronRight, color: context.ln.colors.chevron);
}

/// Bottom padding of a scrolling page (system inset plus a gap).
double pageBottomPadding(BuildContext context) =>
    LnSpace.xxl + MediaQuery.paddingOf(context).bottom;

/// A section title at the page gutter (above content that is not a tile group), in the same
/// style as tile-group and field labels.
class PageSectionTitle extends StatelessWidget {
  const PageSectionTitle(
    this.text, {
    super.key,
    this.trailing,
    this.padding = const EdgeInsetsDirectional.fromSTEB(
      LnSpace.pageGutter,
      LnSpace.xs,
      LnSpace.pageGutter,
      0,
    ),
  });

  final String text;
  final Widget? trailing;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final style = FTheme.of(context).textFieldStyle;
    return Padding(
      padding: padding,
      child: Row(
        children: [
          Expanded(
            child: Semantics(
              header: true,
              child: Text(text, style: style.labelTextStyle.resolve({})),
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

/// A labelled text field whose text reads in its own direction (an English instruction in the
/// Arabic interface reads left to right, as Lonora's text does) while its label and notes follow
/// the interface. Built on [LnTextField].
class ContentField extends StatelessWidget {
  const ContentField({
    super.key,
    required this.controller,
    this.label,
    this.hint,
    this.helper,
    this.error,
    this.enabled = true,
    this.autofocus = false,
    this.minLines,
    this.maxLines = 1,
    this.maxLength,
    this.keyboardType,
    this.inputFormatters = const [],
    this.ltrOnly = false,
    this.onChanged,
    this.padding = const EdgeInsetsDirectional.fromSTEB(
      LnSpace.pageGutter,
      LnSpace.sm,
      LnSpace.pageGutter,
      0,
    ),
  });

  final TextEditingController controller;
  final String? label;
  final String? hint;
  final String? helper;
  final String? error;
  final bool enabled;
  final bool autofocus;
  final int? minLines;
  final int? maxLines;
  final int? maxLength;
  final TextInputType? keyboardType;
  final List<TextInputFormatter> inputFormatters;

  /// Identifiers, versions, cron expressions and links always read left to right.
  final bool ltrOnly;
  final ValueChanged<String>? onChanged;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final style = FTheme.of(context).textFieldStyle;
    final states = <WidgetState>{if (!enabled) WidgetState.disabled};
    final ambient = Directionality.of(context);
    final multiline = maxLines != 1;
    return Padding(
      padding: padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (label != null)
            Padding(
              padding: style.labelPadding,
              child: Text(label!, style: style.labelTextStyle.resolve(states)),
            ),
          ValueListenableBuilder<TextEditingValue>(
            valueListenable: controller,
            builder: (context, value, _) => LnTextField(
              controller: controller,
              hint: hint,
              enabled: enabled,
              autofocus: autofocus,
              minLines: minLines,
              maxLines: maxLines,
              keyboardType:
                  keyboardType ??
                  (multiline ? TextInputType.multiline : TextInputType.text),
              textCapitalization: ltrOnly
                  ? TextCapitalization.none
                  : TextCapitalization.sentences,
              // Identifiers, versions, cron and links are typed as they are.
              autocorrect: !ltrOnly,
              enableSuggestions: !ltrOnly,
              textDirection: ltrOnly
                  ? TextDirection.ltr
                  : textDirectionFor(value.text, ambient),
              maxLength: maxLength,
              inputFormatters: inputFormatters,
              onChanged: onChanged,
            ),
          ),
          if (error != null)
            Padding(
              padding: style.errorPadding,
              child: Text(error!, style: style.errorTextStyle),
            )
          else if (helper != null)
            Padding(
              padding: style.descriptionPadding,
              child: Text(
                helper!,
                style: style.descriptionTextStyle.resolve(states),
              ),
            ),
        ],
      ),
    );
  }
}

/// Agent- or owner-written text, each line in its own reading direction (an English line of an
/// Arabic memory reads left to right), selectable.
class ContentText extends StatelessWidget {
  const ContentText(this.text, {super.key, this.style});

  final String text;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final ambient = Directionality.of(context);
    return SelectionArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final line in text.split('\n'))
            Text(
              line,
              textDirection: textDirectionFor(line, ambient),
              style: style,
            ),
        ],
      ),
    );
  }
}

/// A tile whose title and subtitle are shown whole (agent- or owner-written lines that must not
/// be cut); otherwise the same chrome as the settings rows, a one-line row [LnSize.minTouch] tall
/// as [LnListTile]'s.
class FullTile extends StatelessWidget with FTileMixin {
  const FullTile({
    super.key,
    required this.title,
    this.subtitle,
    this.icon,
    this.trailing,
    this.onTap,
    this.enabled = true,
  });

  final String title;
  final String? subtitle;
  final IconData? icon;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final titleText = Text(title, maxLines: 40, overflow: TextOverflow.visible);
    return FTile(
      enabled: enabled,
      onPress: onTap,
      prefix: icon == null ? null : Icon(icon),
      title: subtitle != null ? titleText : MinTouchTileTitle(child: titleText),
      subtitle: subtitle == null
          ? null
          : Text(subtitle!, maxLines: 40, overflow: TextOverflow.visible),
      suffix: trailing,
    );
  }
}
