// Shared pieces of the core settings pages, the Me tab and the auth screens: forui tile groups
// through LnSection / LnListTile, the Ø44 header circle, the kit's empty/error states.
import 'package:flutter/material.dart'
    show RefreshIndicator, RefreshIndicatorTriggerMode, Scaffold;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';
import 'package:shimmer/shimmer.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../auth/auth_strings.dart';
import '../me/me_strings.dart';
import 'settings_core_strings.dart';

/// Registers the labels of this work package (auth, Me, core settings) once per catalog.
void ensureCoreSettingsStrings(BuildContext context) {
  final l10n = context.l10n;
  registerAuthStrings(l10n);
  registerMeStrings(l10n);
  registerSettingsCoreStrings(l10n);
}

/// The owner text for a failed request, or null when the session itself cancelled it (never
/// shown). No HTTP answer at all reads as the `network` text (ARCHITECTURE «Errors»).
String? errorMessage(BuildContext context, Object error) {
  if (error is SessionRequestCancelled) return null;
  final l10n = context.l10n;
  if (error is ApiError) {
    return error.isNetwork ? l10n.errorText(null) : l10n.errorText(error.code);
  }
  return l10n.errorText('request_failed');
}

/// Shows [error] in an error toast unless it is a cancelled request.
void showErrorToast(BuildContext context, Object error) {
  final text = errorMessage(context, error);
  if (text != null) LnToast.show(context, text, kind: LnToastKind.error);
}

/// Back from a pushed settings page; a page opened directly (deep link) goes to [fallback], the
/// page its row lives on (the Me tab unless said otherwise).
void leavePage(BuildContext context, {String fallback = Routes.me}) {
  if (context.canPop()) {
    context.pop();
  } else {
    context.go(fallback);
  }
}

/// A pushed settings page: the Ø44 back circle with the centred page title (16/24 in the ink),
/// then a scrolling column of sections. [onRefresh] adds pull-to-refresh. [body] replaces the
/// list (loading, error and empty states); with [onRefresh] it fills the page and can be pulled
/// too. A page opened directly (deep link) goes back to [fallback].
class SettingsPageScaffold extends StatelessWidget {
  const SettingsPageScaffold({
    super.key,
    required this.title,
    this.children = const [],
    this.body,
    this.onRefresh,
    this.leading,
    this.fallback = Routes.me,
  });

  final String title;
  final List<Widget> children;
  final Widget? body;
  final Future<void> Function()? onRefresh;

  /// Replaces the back circle (a close circle on modal pages).
  final Widget? leading;

  /// Where back goes when there is no page to pop to: the page whose row opens this one.
  final String fallback;

  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    final ln = context.ln;
    Widget content;
    if (body == null) {
      content = ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.only(
          top: LnSpace.xs,
          bottom: LnSpace.xxl + MediaQuery.paddingOf(context).bottom,
        ),
        children: children,
      );
    } else if (onRefresh != null) {
      content = CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [SliverFillRemaining(hasScrollBody: false, child: body)],
      );
    } else {
      content = body!;
    }
    if (onRefresh != null) {
      content = LnRefresh(onRefresh: onRefresh!, child: content);
    }
    return Scaffold(
      backgroundColor: ln.colors.bg,
      body: Column(
        children: [
          ScreenHeader(
            leading:
                leading ??
                CircleIconButton(
                  // Lucide chevrons mirror themselves in RTL (matchTextDirection).
                  icon: const Icon(FIcons.chevronLeft),
                  semanticLabel: context.t('back'),
                  onTap: () => leavePage(context, fallback: fallback),
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
                      style: ln.text.title.copyWith(color: ln.colors.fg),
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: LnSpace.xs),
          Expanded(child: content),
        ],
      ),
    );
  }
}

/// Pull-to-refresh in the app's colours; a medium impact when the pull arms.
class LnRefresh extends StatelessWidget {
  const LnRefresh({super.key, required this.onRefresh, required this.child});

  final Future<void> Function() onRefresh;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    return RefreshIndicator(
      color: c.fg,
      backgroundColor: c.surface,
      triggerMode: RefreshIndicatorTriggerMode.anywhere,
      onRefresh: () {
        HapticFeedback.mediumImpact();
        return onRefresh();
      },
      child: child,
    );
  }
}

/// Failure of a page's first load: the offline variant when no HTTP answer arrived.
class LoadFailure extends StatelessWidget {
  const LoadFailure({super.key, required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final text = errorMessage(context, error) ?? context.t('request_failed');
    final offline = error is ApiError && (error as ApiError).isNetwork;
    return ErrorState(
      icon: offline ? FIcons.wifiOff : FIcons.triangleAlert,
      title: text,
      retryLabel: context.t('retry'),
      onRetry: onRetry,
    );
  }
}

/// Shimmering placeholder shaped like a tile group (first load of a settings page).
class SettingsSkeleton extends StatelessWidget {
  const SettingsSkeleton({
    super.key,
    this.groups = const [3, 2],
    this.animate = true,
  });

  /// Rows per placeholder group.
  final List<int> groups;

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
    final content = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final (g, rows) in groups.indexed)
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(
              LnSpace.pageGutter,
              LnSpace.sm,
              LnSpace.pageGutter,
              LnSpace.sm,
            ),
            child: Container(
              decoration: BoxDecoration(
                border: Border.all(color: c.border),
                borderRadius: const BorderRadius.all(
                  Radius.circular(LnRadius.card),
                ),
              ),
              child: Column(
                children: [
                  for (var i = 0; i < rows; i++)
                    SizedBox(
                      height: 56,
                      child: Padding(
                        padding: const EdgeInsetsDirectional.symmetric(
                          horizontal: LnSpace.md,
                        ),
                        child: Row(
                          children: [
                            bar(24, 24),
                            const SizedBox(width: LnSpace.sm),
                            bar(110.0 + ((g * 3 + i) * 41) % 90, 14),
                            const Spacer(),
                            bar(40, 12),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
      ],
    );
    return Semantics(
      label: context.t('sh_loading'),
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

/// A settings row whose title and hint wrap (forui's item truncates to one line, which would
/// cut Lonora's longer hints): leading icon, up to 2 title lines and 4 hint lines, a trailing
/// widget. Same tile chrome as [LnListTile]; a row without a hint is at least
/// [LnSize.minTouch] tall, as LnListTile's one-line rows.
class WrapTile extends StatelessWidget with FTileMixin {
  const WrapTile({
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
    final titleText = Text(title, maxLines: 2);
    return FTile(
      enabled: enabled,
      onPress: onTap,
      prefix: icon == null ? null : Icon(icon),
      title: subtitle != null ? titleText : MinTouchTileTitle(child: titleText),
      subtitle: subtitle == null ? null : Text(subtitle!, maxLines: 4),
      suffix: trailing,
    );
  }
}

/// One option of a single-choice list (theme, language, reach-me channel, device): a check at
/// the end of the selected row, a selection haptic on tap.
class ChoiceTile extends StatelessWidget with FTileMixin {
  const ChoiceTile({
    super.key,
    required this.title,
    required this.selected,
    required this.onSelect,
    this.subtitle,
    this.icon,
    this.enabled = true,
  });

  final String title;
  final String? subtitle;
  final IconData? icon;
  final bool selected;
  final bool enabled;
  final VoidCallback onSelect;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    // Merged, so the selection sits on the row's own (tappable) node, not on a wrapper.
    return MergeSemantics(
      child: Semantics(
        selected: selected,
        inMutuallyExclusiveGroup: true,
        child: WrapTile(
          title: title,
          subtitle: subtitle,
          icon: icon,
          enabled: enabled,
          // An unselected row keeps the check's box (invisible): every row has the same height.
          trailing: Icon(
            FIcons.check,
            color: selected ? c.selection : const Color(0x00000000),
          ),
          onTap: () {
            HapticFeedback.selectionClick();
            if (!selected) onSelect();
          },
        ),
      ),
    );
  }
}

/// An on/off row: tapping the row or the switch flips it.
class SwitchTile extends StatelessWidget with FTileMixin {
  const SwitchTile({
    super.key,
    required this.title,
    required this.value,
    required this.onChanged,
    this.subtitle,
    this.icon,
  });

  final String title;
  final String? subtitle;
  final IconData? icon;
  final bool value;

  /// Null disables the row (e.g. while saving).
  final ValueChanged<bool>? onChanged;

  // Merged, so the on/off state sits on the row's own (tappable) node, not on a wrapper.
  @override
  Widget build(BuildContext context) => MergeSemantics(
    child: Semantics(
      toggled: value,
      child: WrapTile(
        title: title,
        subtitle: subtitle,
        icon: icon,
        enabled: onChanged != null,
        onTap: onChanged == null
            ? null
            : () {
                HapticFeedback.selectionClick();
                onChanged!(!value);
              },
        trailing: ExcludeSemantics(
          child: LnSwitch(value: value, onChanged: onChanged),
        ),
      ),
    ),
  );
}

/// [text] with a capital first letter: a lowercase phrase that starts a line (English; Arabic has
/// no case).
String sentenceStart(String text) =>
    text.isEmpty ? text : text[0].toUpperCase() + text.substring(1);

/// A muted paragraph between sections, lined up with the rows' text inside the cards (16 dp in from
/// the card edge on both sides).
class SettingsNote extends StatelessWidget {
  const SettingsNote(this.text, {super.key, this.padding});

  final String text;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    // In the section footers' style and inset: the tile group's description.
    final style = FTheme.of(context).tileGroupStyle.descriptionTextStyle;
    return Padding(
      padding:
          padding ??
          const EdgeInsetsDirectional.fromSTEB(
            LnSpace.pageGutter + LnSpace.md,
            0,
            LnSpace.pageGutter + LnSpace.md,
            LnSpace.lg,
          ),
      child: Text(text, style: style.resolve(const {})),
    );
  }
}

/// Vertical gap between sections: [LnSpace.xxl] on pushed pages; the Me tab's cards sit
/// [LnSpace.md] apart.
class SectionGap extends StatelessWidget {
  const SectionGap({super.key, this.height = LnSpace.xxl});

  final double height;

  @override
  Widget build(BuildContext context) => SizedBox(height: height);
}

/// A choice made in place from a settings row (a [LnListTile] with `picker: true` whose key is
/// [row]): the popover menu of [actions] opens at the row's end edge, under its value and ⇕ glyph
/// (above it when there is no room below), with a check on the [selected] one. Completes with the
/// chosen value, or null when dismissed.
Future<T?> showRowPicker<T>(
  BuildContext context, {
  required GlobalKey row,
  required String label,
  required T selected,
  required List<LnMenuAction<T>> actions,
}) {
  final box = row.currentContext!.findRenderObject()! as RenderBox;
  final rect = box.localToGlobal(Offset.zero) & box.size;
  final endX = Directionality.of(context) == TextDirection.rtl
      ? rect.left
      : rect.right - 1;
  return showLnPopoverMenu<T>(
    context,
    actions: actions,
    // A one-dp slice of the row's end edge: the menu lines up with that edge.
    anchorRect: Rect.fromLTWH(endX, rect.top, 1, rect.height),
    selected: selected,
    semanticLabel: label,
  );
}

/// Opens [url] outside the app (browser); an error toast when nothing can open it.
Future<void> openExternalUrl(BuildContext context, Uri url) async {
  bool opened;
  try {
    opened = await launchUrl(url, mode: LaunchMode.externalApplication);
  } catch (_) {
    opened = false;
  }
  if (!opened && context.mounted) {
    LnToast.show(context, context.t('set_linkFailed'), kind: LnToastKind.error);
  }
}
