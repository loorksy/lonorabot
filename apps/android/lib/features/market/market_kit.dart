// Shared pieces of the market, charts, attention and files screens (work package F): the
// strings registration, a pushed page with the Ø44 header circles and a centred title (the same
// chrome as the settings pages), footnotes and number helpers. Composed from the kit; nothing
// here restyles Material defaults.
import 'package:flutter/material.dart' show Scaffold;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart' show NumberFormat;

import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../attention/attention_strings.dart';
import '../charts/charts_strings.dart';
import '../files/files_strings.dart';
import '../settings/settings_common.dart' show ensureCoreSettingsStrings;
import 'market_strings.dart';

L10n? _registered;

/// Registers the labels of the market, charts, attention and files screens (once per catalog).
void ensureWpfStrings(BuildContext context) {
  final l10n = context.l10n;
  if (identical(l10n, _registered)) return;
  ensureCoreSettingsStrings(context);
  registerMarketStrings(l10n);
  registerChartsStrings(l10n);
  registerAttentionStrings(l10n);
  registerFilesStrings(l10n);
  _registered = l10n;
}

/// Back from a pushed page; a page opened directly (deep link) goes to [fallback].
void leaveTo(BuildContext context, String fallback) {
  if (context.canPop()) {
    context.pop();
  } else {
    context.go(fallback);
  }
}

/// A pushed page: the back circle, a centred title (with an optional muted subtitle) and up to
/// two trailing circles, over [body]. Content scrolls under nothing: the header is its own row.
class PushedPage extends StatelessWidget {
  const PushedPage({
    super.key,
    required this.title,
    required this.body,
    required this.fallback,
    this.subtitle,
    this.trailing = const [],
    this.titleDirection,
    this.titleWidget,
  });

  /// The page's name; [titleWidget] draws it instead when given.
  final String title;
  final String? subtitle;
  final Widget body;

  /// Where back goes when nothing is below this page.
  final String fallback;
  final List<Widget> trailing;

  /// Forces the title's direction (file names and tickers read in their own direction).
  final TextDirection? titleDirection;

  /// Drawn in place of the title text, under the same header semantics. It sets its own insets
  /// from the header circles (a file name that keeps its extension uses the free width).
  final Widget? titleWidget;

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    final ln = context.ln;
    final c = ln.colors;
    final side = 56.0 * (trailing.length > 1 ? 2 : 1);
    return Scaffold(
      backgroundColor: c.bg,
      body: Column(
        children: [
          ScreenHeader(
            leading: CircleIconButton(
              // Lucide chevrons mirror themselves in RTL (matchTextDirection).
              icon: const Icon(FIcons.chevronLeft),
              semanticLabel: context.t('back'),
              onTap: () => leaveTo(context, fallback),
            ),
            center: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: titleWidget == null ? side : 0,
              ),
              child: SizedBox(
                height: LnSize.headerCircle,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Semantics(
                      header: true,
                      child:
                          titleWidget ??
                          Text(
                            title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            textDirection: titleDirection,
                            textAlign: TextAlign.center,
                            style: ln.text.headline.copyWith(color: c.fg),
                          ),
                    ),
                    if (subtitle != null)
                      Padding(
                        padding: EdgeInsets.symmetric(
                          horizontal: titleWidget == null ? 0 : side,
                        ),
                        child: Text(
                          subtitle!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          textAlign: TextAlign.center,
                          style: ln.text.small.copyWith(color: c.fgMuted),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            trailing: trailing.isEmpty
                ? null
                : Row(mainAxisSize: MainAxisSize.min, children: trailing),
          ),
          const SizedBox(height: LnSpace.xs),
          Expanded(child: body),
        ],
      ),
    );
  }
}

/// A muted footnote at the page gutter (notes under sections).
class Footnote extends StatelessWidget {
  const Footnote(this.text, {super.key, this.icon, this.underHeader = false});

  final String text;
  final IconData? icon;

  /// Stands in for a section's rows (an empty or failed section): starts at the 32 dp inset of
  /// the [SectionHeader] above it.
  final bool underHeader;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        underHeader ? 32 : LnSpace.pageGutter + 4,
        LnSpace.xs,
        LnSpace.pageGutter + 4,
        LnSpace.xs,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (icon != null) ...[
            Padding(
              padding: const EdgeInsets.only(top: 1),
              child: Icon(icon, size: 15, color: c.fgMuted),
            ),
            const SizedBox(width: 6),
          ],
          Expanded(
            child: Text(
              text,
              style: ln.text.footnote.copyWith(color: c.fgMuted),
            ),
          ),
        ],
      ),
    );
  }
}

/// MetaApi's display name, on the broker pages and as a quote source.
const metaApiName = 'MetaApi (MetaTrader)';

/// A quote's source by name: the simulation in the interface language, MetaApi as the broker
/// pages name it, any other provider id as the server sends it.
String quoteSource(BuildContext context, String source) => switch (source) {
  'simulation' => context.t('simulation'),
  'metaapi' => metaApiName,
  _ => source,
};

/// A market number as the broker writes it: the server's decimal string, trailing zeros kept.
/// Null or empty reads «—».
String marketNumber(Object? value) {
  if (value == null) return '—';
  final text = '$value'.trim();
  return text.isEmpty ? '—' : text;
}

final NumberFormat _money = NumberFormat('#,##0.00', 'en');

/// An amount with grouping and two decimals in Latin digits (account values, profit).
String money(double value) => _money.format(value);

/// [money] with an explicit sign (+12.40, -3.00).
String signedMoney(double value) => value > 0
    ? '+${money(value)}'
    : (value < 0 ? '-${money(-value)}' : money(0));

/// A percentage with an explicit sign and two decimals (+0.42%).
String signedPercent(double value) {
  final text = value.abs().toStringAsFixed(2);
  return value > 0 ? '+$text%' : (value < 0 ? '-$text%' : '$text%');
}
