// The interface language choice: Arabic, English, or following the phone. Shared by the Me
// tab's Language row and the Appearance page.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FTileGroup;

import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/prefs_actions.dart';
import 'settings_common.dart';

/// A language choice. [system] follows the phone (Arabic unless the phone is in English, the
/// rule of `LoadPrefsAction`).
enum LanguageChoice { system, ar, en }

/// Whether the owner picked a language or the phone's decides.
LanguageChoice currentLanguageChoice(String locale) {
  try {
    if (localeFollowsSystem) return LanguageChoice.system;
  } catch (_) {
    // No device prefs registered (previews): show the effective language.
  }
  return locale == 'en' ? LanguageChoice.en : LanguageChoice.ar;
}

/// The language's own name («العربية», "English"), or «حسب النظام» for [LanguageChoice.system].
String languageChoiceLabel(BuildContext context, LanguageChoice choice) =>
    switch (choice) {
      LanguageChoice.system => context.t('set_followSystem'),
      LanguageChoice.ar => 'العربية',
      LanguageChoice.en => 'English',
    };

/// Applies [choice]: a fixed language through [SetLocaleAction], or the phone's language.
Future<void> applyLanguageChoice(BuildContext context, LanguageChoice choice) =>
    switch (choice) {
      LanguageChoice.ar => context.dispatchAndWait(SetLocaleAction('ar')),
      LanguageChoice.en => context.dispatchAndWait(SetLocaleAction('en')),
      LanguageChoice.system => context.dispatchAndWait(
        FollowSystemLocaleAction(),
      ),
    };

/// The language picker: a sheet with the three choices; a choice applies at once.
Future<void> pickLanguage(BuildContext context) async {
  final locale = context.read().prefs.locale;
  final current = currentLanguageChoice(locale);
  final chosen = await showLnSheet<LanguageChoice>(
    context,
    title: context.t('language'),
    builder: (sheet) => FTileGroup(
      children: [
        for (final choice in LanguageChoice.values)
          ChoiceTile(
            title: languageChoiceLabel(sheet, choice),
            selected: choice == current,
            onSelect: () => Navigator.of(sheet).pop(choice),
          ),
      ],
    ),
  );
  if (chosen == null || chosen == current || !context.mounted) return;
  await applyLanguageChoice(context, chosen);
}
