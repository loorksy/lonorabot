// «Follow system» for the interface language lives with the other device prefs
// (prefs_actions.dart): no stored language, and the launch rule decides.
import 'package:async_redux/async_redux.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/features/settings/language.dart';
import 'package:lonora/state/actions/prefs_actions.dart';
import 'package:lonora/state/app_state.dart';

import 'feature_harness.dart';

void main() {
  testWidgets(
    'following the phone forgets the choice and uses the launch rule',
    (tester) async {
      await setUpServices(prefs: {'lonora.locale': 'ar'});
      final store = Store<AppState>(initialState: const AppState());
      await store.dispatchAndWait(LoadPrefsAction());
      expect(store.state.prefs.locale, 'ar');
      expect(localeFollowsSystem, isFalse);
      expect(currentLanguageChoice('ar'), LanguageChoice.ar);

      await store.dispatchAndWait(FollowSystemLocaleAction());
      expect(devicePrefs.getString('lonora.locale'), isNull);
      expect(localeFollowsSystem, isTrue);
      expect(
        currentLanguageChoice(store.state.prefs.locale),
        LanguageChoice.system,
      );

      // The same language a launch without a stored choice picks.
      final relaunched = Store<AppState>(initialState: const AppState());
      await relaunched.dispatchAndWait(LoadPrefsAction());
      expect(store.state.prefs.locale, relaunched.state.prefs.locale);

      await store.dispatchAndWait(SetLocaleAction('en'));
      expect(localeFollowsSystem, isFalse);
      expect(currentLanguageChoice('en'), LanguageChoice.en);
    },
  );
}
