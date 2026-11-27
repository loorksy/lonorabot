// The Me tab: an ordered entry list, then usage, laid out as forui tile groups. Every entry is a
// Lonora capability.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/session_actions.dart';
import '../../state/app_state.dart';
import '../conversation/conversation_header.dart' show showChatPrefsSheet;
import '../settings/appearance_screen.dart' show themeModeLabel;
import '../settings/language.dart';
import '../settings/settings_common.dart';
import 'me_actions.dart';
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
  bool _signingOut = false;

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

  Future<void> _clearCache() async {
    final confirmed = await showLnConfirm(
      context,
      title: context.t('me_clearCacheQ'),
      message: context.t('me_clearCacheBody'),
      confirmLabel: context.t('sh_clear'),
      cancelLabel: context.t('sh_cancel'),
      destructive: true,
    );
    if (!confirmed || !mounted) return;
    await context.dispatchAndWait(ClearLocalCacheAction());
    if (mounted) {
      LnToast.show(
        context,
        context.t('me_cacheCleared'),
        kind: LnToastKind.positive,
      );
    }
  }

  /// The account page edits the name and form of address the card shows: read them again.
  Future<void> _openAccount() async {
    await context.push(Routes.account);
    if (mounted) await _loadProfile();
  }

  /// Revoking can wait up to 8 s offline: the row stays disabled meanwhile.
  Future<void> _signOut() async {
    if (_signingOut) return;
    setState(() => _signingOut = true);
    try {
      if (await confirmSignOut(context) && mounted) {
        await context.dispatchAndWait(SignOutAction());
      }
    } finally {
      if (mounted) setState(() => _signingOut = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    final ln = context.ln;
    final owner = context.select((AppState s) => s.session.owner);
    final theme = context.select((AppState s) => s.prefs.themeMode);
    final locale = context.select((AppState s) => s.prefs.locale);
    final profile = _profile;
    void open(String route) => context.push(route);

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
            LargeTitleHeader(title: context.t('android_me')),
            const SizedBox(height: LnSpace.md),
            if (owner != null)
              _OwnerCard(owner: owner, profile: profile, onTap: _openAccount),
            const SectionGap(),
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
            const SectionGap(),
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
            const SectionGap(),
            LnSection(
              title: context.t('settings'),
              children: [
                LnListTile(
                  icon: FIcons.bell,
                  title: context.t('notificationsAndContact'),
                  // The Web's value (how Lonora reaches the owner), as a subtitle: the
                  // title is too long for a value beside it in English.
                  subtitle: profile == null
                      ? null
                      : reachMeLabel(profile.channel, context.l10n.lang),
                  onTap: () => open(Routes.notifications),
                ),
                LnListTile(
                  icon: FIcons.audioLines,
                  title: context.t('voice'),
                  onTap: () => open(Routes.voice),
                ),
                LnListTile(
                  icon: FIcons.globe,
                  title: context.t('language'),
                  value: languageChoiceLabel(
                    context,
                    currentLanguageChoice(locale),
                  ),
                  onTap: () async {
                    await pickLanguage(context);
                    if (mounted) setState(() {});
                  },
                ),
                LnListTile(
                  icon: FIcons.sunMoon,
                  title: context.t('sh_appearance'),
                  value: themeModeLabel(context, theme),
                  onTap: () => open(Routes.appearance),
                ),
                // The Web's «Chat experience» settings entry; the conversation header opens
                // the same sheet.
                LnListTile(
                  icon: FIcons.messageSquare,
                  title: context.t('chatPrefs'),
                  onTap: () => showChatPrefsSheet(context),
                ),
                LnListTile(
                  icon: FIcons.eraser,
                  title: context.t('me_clearCache'),
                  onTap: _clearCache,
                ),
                LnListTile(
                  icon: FIcons.info,
                  title: context.t('me_about'),
                  value: ltr(appInfo.version),
                  onTap: () => open(Routes.about),
                ),
              ],
            ),
            const SectionGap(),
            _UsageCard(
              usage: _usage,
              error: _usage == null ? _usageError : null,
              onTap: () => open(Routes.usage),
              onRetry: _loadUsage,
            ),
            const SectionGap(),
            LnSection(
              children: [
                LnListTile(
                  icon: LnIcons.logOut,
                  title: context.t('logout'),
                  subtitle: owner == null
                      ? null
                      : context.t('me_signedInAs', [ltr(owner.email)]),
                  destructive: true,
                  enabled: !_signingOut,
                  onTap: _signOut,
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

/// The owner's card at the top of Me: initial, name, email; opens the account page. Lonora has
/// no owner picture, so the avatar is the name's first letter (as the Web's settings root).
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
                semanticsLabel: '$name, ${owner.email}',
                onPress: () {
                  HapticFeedback.selectionClick();
                  onTap();
                },
                prefix: OwnerInitialAvatar(name: name),
                title: Text(name, maxLines: 1, overflow: TextOverflow.ellipsis),
                subtitle: Text(
                  ltr(owner.email),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                suffix: Icon(FIcons.chevronRight, color: c.chevron),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

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

/// Token usage at the bottom of Me: `GET /usage/summary`, which is three totals; the usage page has
/// the breakdown.
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
        child: Container(
          padding: EdgeInsetsDirectional.fromSTEB(
            inset.left,
            LnSpace.sm,
            inset.right,
            LnSpace.cardPadding,
          ),
          decoration: BoxDecoration(
            color: c.surface,
            border: Border.all(color: c.border),
            borderRadius: const BorderRadius.all(
              Radius.circular(LnRadius.card),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(
                height: 36,
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
                        style: ln.text.title.copyWith(color: c.fg),
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
              const SizedBox(height: LnSpace.xs),
              if (failed != null)
                Text(failed, style: ln.text.footnote.copyWith(color: c.fgMuted))
              else
                Row(
                  children: [
                    stat(context.t('inputTokens'), usage?.input),
                    stat(context.t('outputTokens'), usage?.output),
                    stat(context.t('cachedTokens'), usage?.cached),
                  ],
                ),
            ],
          ),
        ),
      ),
    );
  }
}
