// The Settings page (Routes.settings), pushed from the Me tab's «الإعدادات» card: how Lonora
// reaches the owner on a card of its own, then this phone's preferences (home screen, language,
// appearance, chat experience, voice, clear cache), «التعطل والاستعادة», then About and the app
// version. The home
// screen and the appearance are chosen in place, from a popover at the row.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../app/services.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/prefs_actions.dart';
import '../../state/app_state.dart';
import '../conversation/conversation_header.dart' show showChatPrefsSheet;
import '../me/me_actions.dart';
import '../me/me_data.dart';
import '../trading/trading_strings.dart';
import 'appearance_screen.dart' show themeModeIcon, themeModeLabel;
import 'language.dart';
import 'settings_common.dart';

/// «آخر محادثة» / «كل المحادثات».
String homeModeLabel(BuildContext context, HomeMode mode) => switch (mode) {
  HomeMode.lastChat => context.t('set_homeLastChat'),
  HomeMode.list => context.t('set_homeList'),
};

IconData _homeModeIcon(HomeMode mode) => switch (mode) {
  HomeMode.lastChat => FIcons.messageSquareText,
  HomeMode.list => FIcons.layoutList,
};

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  OwnerProfileData? _profile;
  final _homeRow = GlobalKey();
  final _appearanceRow = GlobalKey();

  @override
  void initState() {
    super.initState();
    unawaited(_loadProfile());
  }

  /// The notifications row's value: how Lonora reaches the owner.
  Future<void> _loadProfile() async {
    try {
      final profile = await fetchOwnerProfile();
      if (mounted) setState(() => _profile = profile);
    } catch (_) {
      // The row shows no value; the notifications page shows the error.
    }
  }

  Future<void> _pickHomeMode() async {
    final current = context.read().prefs.homeMode;
    final chosen = await showRowPicker<HomeMode>(
      context,
      row: _homeRow,
      label: context.t('set_homeScreen'),
      selected: current,
      actions: [
        for (final mode in HomeMode.values)
          LnMenuAction(
            label: homeModeLabel(context, mode),
            icon: _homeModeIcon(mode),
            value: mode,
          ),
      ],
    );
    if (chosen != null && chosen != current && mounted) {
      await context.dispatchAndWait(SetHomeModeAction(chosen));
    }
  }

  Future<void> _pickTheme() async {
    final current = context.read().prefs.themeMode;
    final chosen = await showRowPicker<AppThemeMode>(
      context,
      row: _appearanceRow,
      label: context.t('sh_appearance'),
      selected: current,
      actions: [
        for (final mode in AppThemeMode.values)
          LnMenuAction(
            label: themeModeLabel(context, mode),
            icon: themeModeIcon(mode),
            value: mode,
          ),
      ],
    );
    if (chosen != null && chosen != current && mounted) {
      await context.dispatchAndWait(SetThemeModeAction(chosen));
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

  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    ensureTradingStrings(context);
    final lang = context.l10n.lang;
    final theme = context.select((AppState s) => s.prefs.themeMode);
    final locale = context.select((AppState s) => s.prefs.locale);
    final home = context.select((AppState s) => s.prefs.homeMode);
    final profile = _profile;
    final reachMe = profile == null
        ? null
        : reachMeLabel(profile.channel, lang);
    void open(String route) => context.push(route);

    return SettingsPageScaffold(
      title: context.t('settings'),
      children: [
        LnSection(
          children: [
            LnListTile(
              icon: FIcons.bell,
              title: context.t('notificationsAndContact'),
              // How Lonora reaches the owner: beside the title in Arabic; under it in English,
              // whose longer title leaves no room for a value.
              value: lang == 'ar' ? reachMe : null,
              subtitle: lang == 'ar' ? null : reachMe,
              onTap: () async {
                await context.push(Routes.notifications);
                // The owner may have changed how Lonora reaches them there.
                if (mounted) unawaited(_loadProfile());
              },
            ),
          ],
        ),
        const SectionGap(),
        LnSection(
          children: [
            LnListTile(
              key: _homeRow,
              icon: FIcons.house,
              title: context.t('set_homeScreen'),
              value: homeModeLabel(context, home),
              picker: true,
              onTap: _pickHomeMode,
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
                // "Follow system" may keep the same language: show the new choice anyway.
                if (mounted) setState(() {});
              },
            ),
            LnListTile(
              key: _appearanceRow,
              icon: FIcons.sunMoon,
              title: context.t('sh_appearance'),
              value: themeModeLabel(context, theme),
              picker: true,
              onTap: _pickTheme,
            ),
            // The Web's «Chat experience» settings entry; the conversation header opens the
            // same sheet.
            LnListTile(
              icon: FIcons.messageSquare,
              title: context.t('chatPrefs'),
              onTap: () => showChatPrefsSheet(context),
            ),
            LnListTile(
              icon: FIcons.audioLines,
              title: context.t('voice'),
              onTap: () => open(Routes.voice),
            ),
            LnListTile(
              icon: FIcons.eraser,
              title: context.t('me_clearCache'),
              onTap: _clearCache,
            ),
          ],
        ),
        const SectionGap(),
        // «التعطل والاستعادة»: each broker connection's recovery state.
        LnSection(
          children: [
            LnListTile(
              icon: FIcons.unplug,
              title: context.t('rc_title'),
              onTap: () => open(Routes.recovery),
            ),
          ],
        ),
        const SectionGap(),
        LnSection(
          children: [
            LnListTile(
              icon: FIcons.info,
              title: context.t('me_about'),
              onTap: () => open(Routes.about),
            ),
            LnListTile(
              icon: FIcons.squareAsterisk,
              title: context.t('set_appVersion'),
              value: ltr(appInfo.version),
            ),
          ],
        ),
      ],
    );
  }
}
