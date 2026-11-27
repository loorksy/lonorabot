// The Me tab: entry cards 16 dp apart, every one a Lonora capability: the owner (account), token
// usage, the owner's agents and their work, the server-side services, and Settings (its own
// page). No visible title: the owner's card leads.
import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../settings/settings_common.dart';
import 'me_data.dart';

class MeScreen extends StatefulWidget {
  const MeScreen({super.key});

  @override
  State<MeScreen> createState() => _MeScreenState();
}

class _MeScreenState extends State<MeScreen> {
  OwnerProfileData? _profile;
  UsageSummary? _usage;
  Object? _usageError;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    await Future.wait([_loadProfile(), _loadUsage()]);
  }

  Future<void> _loadProfile() async {
    try {
      final profile = await fetchOwnerProfile();
      if (mounted) setState(() => _profile = profile);
    } catch (_) {
      // The card falls back to the email; the account page shows the error.
    }
  }

  Future<void> _loadUsage() async {
    if (_usageError != null) setState(() => _usageError = null);
    try {
      final usage = await fetchUsageSummary();
      if (mounted) {
        setState(() {
          _usage = usage;
          _usageError = null;
        });
      }
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted) setState(() => _usageError = e);
    }
  }

  /// The account page edits the name and form of address the card shows: read them again.
  Future<void> _openAccount() async {
    await context.push(Routes.account);
    if (mounted) await _loadProfile();
  }

  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    final ln = context.ln;
    final owner = context.select((AppState s) => s.session.owner);
    void open(String route) => context.push(route);
    const gap = SectionGap(height: LnSpace.md);

    return ColoredBox(
      color: ln.colors.bg,
      child: LnRefresh(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(
            bottom: FloatingTabBar.occupiedHeight(context) + LnSpace.xl,
          ),
          children: [
            // No visible title: the owner's card leads, 30 dp under the status bar. The tab's
            // name stays the screen's first heading for screen readers.
            Semantics(
              header: true,
              label: context.t('android_me'),
              child: SizedBox(height: MediaQuery.paddingOf(context).top + 30),
            ),
            if (owner != null) ...[
              _OwnerCard(owner: owner, profile: _profile, onTap: _openAccount),
              gap,
            ],
            _UsageCard(
              usage: _usage,
              error: _usage == null ? _usageError : null,
              onTap: () => open(Routes.usage),
              onRetry: _loadUsage,
            ),
            gap,
            LnSection(
              children: [
                LnListTile(
                  icon: FIcons.bot,
                  title: context.t('agents'),
                  onTap: () => open(Routes.agents),
                ),
                LnListTile(
                  icon: FIcons.calendarClock,
                  title: context.t('routines'),
                  onTap: () => open(Routes.routines()),
                ),
                LnListTile(
                  icon: LnIcons.listChecks,
                  title: context.t('sh_tasks'),
                  onTap: () => open(Routes.tasks),
                ),
                LnListTile(
                  icon: FIcons.folder,
                  title: context.t('sh_sFiles'),
                  onTap: () => open(Routes.artifacts()),
                ),
                LnListTile(
                  icon: FIcons.chartCandlestick,
                  title: context.t('charts'),
                  onTap: () => open(Routes.charts()),
                ),
                LnListTile(
                  icon: FIcons.brain,
                  title: context.t('whatIKnow'),
                  onTap: () => open(Routes.ownerKnowledge),
                ),
              ],
            ),
            gap,
            LnSection(
              children: [
                LnListTile(
                  icon: FIcons.blocks,
                  title: context.t('integrations'),
                  onTap: () => open(Routes.integrations),
                ),
                LnListTile(
                  icon: FIcons.cpu,
                  title: context.t('models'),
                  onTap: () => open(Routes.models),
                ),
                LnListTile(
                  icon: FIcons.activity,
                  title: context.t('running_title'),
                  onTap: () => open(Routes.running),
                ),
              ],
            ),
            gap,
            // The phone's preferences, notifications and About live on their own page.
            LnSection(
              children: [
                LnListTile(
                  icon: FIcons.settings,
                  title: context.t('settings'),
                  onTap: () => open(Routes.settings),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// The sign-out confirmation (Web wording, apps/web SettingsRoot.tsx `confirmSignOut`).
Future<bool> confirmSignOut(BuildContext context) => showLnConfirm(
  context,
  title: context.t('me_signOutQ'),
  message: context.t('me_signOutBody'),
  confirmLabel: context.t('logout'),
  cancelLabel: context.t('sh_cancel'),
  destructive: true,
);

/// The owner's card at the top of Me: initial, name (20/24 bold), email; opens the account page.
/// Lonora has no owner picture, so the avatar is the name's first letter (as the Web's settings
/// root). 16 dp around the 48 dp avatar: an 80 dp card.
class _OwnerCard extends StatelessWidget {
  const _OwnerCard({
    required this.owner,
    required this.profile,
    required this.onTap,
  });

  final Owner owner;
  final OwnerProfileData? profile;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final name = ownerDisplayName(profile, owner);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
      // One node: «name, email», then what a tap does.
      child: MergeSemantics(
        child: Semantics(
          hint: context.t('me_openAccount'),
          child: FTileGroup(
            children: [
              FTile(
                style: (s) => s.copyWith(
                  contentStyle: (cs) => cs.copyWith(
                    padding: const EdgeInsetsDirectional.all(LnSpace.md),
                  ),
                ),
                semanticsLabel: '$name, ${owner.email}',
                onPress: () {
                  HapticFeedback.selectionClick();
                  onTap();
                },
                prefix: OwnerInitialAvatar(name: name),
                // Full 24 and 20 dp lines in every script (forui trims a tile's outer
                // line edges): with the 48 dp avatar, a card of 16 + 48 + 16.
                title: Text(
                  name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: ln.text.display.copyWith(color: c.fg),
                  strutStyle: _line(20, 24),
                  textHeightBehavior: _fullLines,
                ),
                subtitle: Text(
                  ltr(owner.email),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: ln.text.caption.copyWith(color: c.fgMuted),
                  strutStyle: _line(14, 20),
                  textHeightBehavior: _fullLines,
                ),
                suffix: const Icon(FIcons.chevronRight),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

const _fullLines = TextHeightBehavior(
  leadingDistribution: TextLeadingDistribution.even,
);

/// Lines of exactly [height] dp for [size] dp text, whichever fonts the words fall back to.
StrutStyle _line(double size, double height) => StrutStyle(
  fontSize: size,
  height: height / size,
  leadingDistribution: TextLeadingDistribution.even,
  forceStrutHeight: true,
);

/// A round letter avatar for the owner.
class OwnerInitialAvatar extends StatelessWidget {
  const OwnerInitialAvatar({super.key, required this.name, this.size = 48});

  final String name;
  final double size;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    return ExcludeSemantics(
      child: Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: ln.colors.brand,
          shape: BoxShape.circle,
        ),
        child: Text(
          ownerInitial(name),
          style: ln.text.headline.copyWith(
            color: ln.colors.onAccent,
            fontSize: size * 0.42,
            height: 1,
          ),
        ),
      ),
    );
  }
}

/// Token usage, under the owner's card: `GET /usage/summary`, which is three totals; the usage
/// page has the breakdown. A grouped card: a header on the list rows' grid (their padding, 20 dp
/// icon, title style and chevron), a hairline, then the totals.
class _UsageCard extends StatelessWidget {
  const _UsageCard({
    required this.usage,
    required this.error,
    required this.onTap,
    required this.onRetry,
  });

  /// Null while the first read is in flight (placeholder bars).
  final UsageSummary? usage;
  final Object? error;
  final VoidCallback onTap;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final locale = context.l10n.lang;
    final failed = error != null
        ? (errorMessage(context, error!) ?? context.t('request_failed'))
        : null;
    // The header row on the list rows' grid: their content insets, icon sizes and colours.
    final tile = FTheme.of(context).tileGroupStyle.tileStyle.contentStyle;
    final inset = tile.padding.resolve(TextDirection.ltr);
    Widget stat(String label, int? value) => Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (value == null)
            Container(
              width: 56,
              height: 18,
              margin: const EdgeInsets.symmetric(vertical: 2),
              decoration: BoxDecoration(
                color: c.fill3,
                borderRadius: const BorderRadius.all(
                  Radius.circular(LnRadius.stadium),
                ),
              ),
            )
          else
            Text(
              formatNumber(value, locale),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: ln.text.headline.copyWith(color: c.fg),
            ),
          const SizedBox(height: 2),
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: ln.text.footnote.copyWith(color: c.fgMuted),
          ),
        ],
      ),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
      child: LnTappable(
        onTap: failed != null ? onRetry : onTap,
        semanticLabel: context.t('usage'),
        semanticHint: failed,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: c.fill3,
            borderRadius: const BorderRadius.all(
              Radius.circular(LnRadius.group),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: inset,
                child: Row(
                  children: [
                    IconTheme(
                      data: tile.prefixIconStyle.resolve(const {}),
                      child: const Icon(FIcons.chartColumn),
                    ),
                    SizedBox(width: tile.prefixIconSpacing),
                    Expanded(
                      child: Text(
                        context.t('usage'),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        strutStyle: lnRowStrut,
                        style: tile.titleTextStyle.resolve(const {}),
                      ),
                    ),
                    SizedBox(width: tile.suffixIconSpacing),
                    IconTheme(
                      data: tile.suffixIconStyle.resolve(const {}),
                      child: Icon(
                        failed != null ? FIcons.refreshCw : FIcons.chevronRight,
                      ),
                    ),
                  ],
                ),
              ),
              // The groups' divider: a hairline, 16 dp in from both edges.
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: LnSpace.md),
                child: SizedBox(
                  height: 1 / MediaQuery.devicePixelRatioOf(context),
                  child: ColoredBox(color: c.borderStrong),
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(LnSpace.md),
                child: failed != null
                    ? Text(
                        failed,
                        style: ln.text.footnote.copyWith(color: c.fgMuted),
                      )
                    : Row(
                        children: [
                          stat(context.t('inputTokens'), usage?.input),
                          stat(context.t('outputTokens'), usage?.output),
                          stat(context.t('cachedTokens'), usage?.cached),
                        ],
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
