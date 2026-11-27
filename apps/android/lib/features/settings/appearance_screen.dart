// Appearance: the theme (Follow system / Light / Dark) and the interface language, built from
// forui tile groups.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/prefs_actions.dart';
import '../../state/app_state.dart';
import 'language.dart';
import 'settings_common.dart';

/// «حسب النظام» / «فاتح» / «داكن».
String themeModeLabel(BuildContext context, AppThemeMode mode) =>
    switch (mode) {
      AppThemeMode.system => context.t('set_followSystem'),
      AppThemeMode.light => context.t('sh_light'),
      AppThemeMode.dark => context.t('sh_dark'),
    };

class AppearanceScreen extends StatefulWidget {
  const AppearanceScreen({super.key});

  @override
  State<AppearanceScreen> createState() => _AppearanceScreenState();
}

class _AppearanceScreenState extends State<AppearanceScreen> {
  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    final theme = context.select((AppState s) => s.prefs.themeMode);
    final locale = context.select((AppState s) => s.prefs.locale);
    final language = currentLanguageChoice(locale);
    return SettingsPageScaffold(
      title: context.t('sh_appearance'),
      children: [
        LnSection(
          children: [
            for (final (mode, icon) in const [
              (AppThemeMode.system, FIcons.sunMoon),
              (AppThemeMode.light, FIcons.sun),
              (AppThemeMode.dark, FIcons.moon),
            ])
              ChoiceTile(
                icon: icon,
                title: themeModeLabel(context, mode),
                selected: theme == mode,
                onSelect: () => context.dispatch(SetThemeModeAction(mode)),
              ),
          ],
        ),
        const SectionGap(),
        LnSection(
          title: context.t('language'),
          footer: context.t('set_languageHint'),
          children: [
            for (final choice in LanguageChoice.values)
              ChoiceTile(
                title: languageChoiceLabel(context, choice),
                selected: language == choice,
                onSelect: () async {
                  await applyLanguageChoice(context, choice);
                  // "Follow system" may keep the same language: show the new choice anyway.
                  if (mounted) setState(() {});
                },
              ),
          ],
        ),
      ],
    );
  }
}
