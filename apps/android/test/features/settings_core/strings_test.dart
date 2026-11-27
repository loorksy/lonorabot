// Every WP-A1 screen registers its own Android-only labels and asks for no key the catalogs
// lack, in both languages (checked on a fresh catalog, as at app start).
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/app_strings.dart';
import 'package:lonora/features/auth/connect_screen.dart';
import 'package:lonora/features/auth/server_screen.dart';
import 'package:lonora/features/auth/sign_in_screen.dart';
import 'package:lonora/features/me/me_screen.dart';
import 'package:lonora/features/settings/about_screen.dart';
import 'package:lonora/features/settings/account_screen.dart';
import 'package:lonora/features/settings/appearance_screen.dart';
import 'package:lonora/features/settings/notifications_screen.dart';
import 'package:lonora/features/settings/voice_settings_screen.dart';
import 'package:lonora/l10n/l10n.dart';

import 'feature_harness.dart';

void main() {
  setUpAll(setUpFeatureTests);

  final screens = <String, (Widget, bool)>{
    'me': (const MeScreen(), true),
    'account': (const AccountScreen(), true),
    'appearance': (const AppearanceScreen(), true),
    'notifications': (const NotificationsScreen(), true),
    'voice': (const VoiceSettingsScreen(), true),
    'about': (const AboutScreen(), true),
    'licenses': (const LicensesPage(), true),
    'sign-in': (const SignInScreen(), false),
    'server': (const ServerScreen(), false),
    'connect': (
      const ConnectScreen(server: 'https://home.lonora.cloud'),
      false,
    ),
  };

  for (final locale in ['ar', 'en']) {
    for (final MapEntry(key: name, value: (screen, signedIn))
        in screens.entries) {
      testWidgets('$name ($locale) needs no missing label', (tester) async {
        final fresh = (await tester.runAsync(L10n.load))!;
        registerAppStrings();
        testL10n = fresh;
        final api = await setUpServices();
        api.on('GET /owner/profile', (_) => profileJson(name: 'Ahmed'));
        api.on(
          'GET /voice/status',
          (_) => {'transport': 'gpt_live', 'transport_configured': true},
        );
        api.on('GET /version', (_) => {'version': '0.2.0', 'build': null});
        api.on(
          'GET /attention/policy',
          (_) => {
            'opportunities': true,
            'informational': false,
            'locale': locale,
          },
        );
        final store = testStore(signedIn: signedIn, locale: locale);
        setFeatureViewport(tester);
        await tester.pumpWidget(featureApp(store, testRouter(screen)));
        await tester.pump(const Duration(milliseconds: 450));
        await tester.pumpAndSettle();
        expect(fresh.debugMissingKeys, isEmpty);
      });
    }
  }
}
