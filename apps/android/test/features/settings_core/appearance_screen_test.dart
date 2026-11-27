// Appearance: Follow system / Light / Dark and the interface language, plus goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/settings_core
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/features/settings/appearance_screen.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart';
import 'feature_harness.dart';

void main() {
  setUpAll(setUpFeatureTests);

  testWidgets('theme choice applies and is remembered', (tester) async {
    await setUpServices(prefs: {'lonora.locale': 'en'});
    final store = testStore(locale: 'en');
    setFeatureViewport(tester);
    await tester.pumpWidget(
      featureApp(store, testRouter(const AppearanceScreen())),
    );
    await tester.pumpAndSettle();

    expect(find.text('Appearance'), findsOneWidget);
    await tester.tap(find.text('Dark'));
    await tester.pumpAndSettle();
    expect(store.state.prefs.themeMode, AppThemeMode.dark);
    expect(devicePrefs.getString('lonora.theme'), 'dark');

    await tester.tap(find.text('Follow system').first);
    await tester.pumpAndSettle();
    expect(store.state.prefs.themeMode, AppThemeMode.system);
  });

  testWidgets('language: Arabic, then following the phone', (tester) async {
    await setUpServices(prefs: {'lonora.locale': 'en'});
    final store = testStore(locale: 'en');
    setFeatureViewport(tester);
    await tester.pumpWidget(
      featureApp(store, testRouter(const AppearanceScreen())),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('العربية'));
    await tester.pumpAndSettle();
    expect(store.state.prefs.locale, 'ar');
    expect(devicePrefs.getString('lonora.locale'), 'ar');
    expect(find.text('المظهر'), findsOneWidget);

    // «حسب النظام» appears twice (theme and language); the language one is the last.
    await tester.tap(find.text('حسب النظام').last);
    await tester.pumpAndSettle();
    expect(devicePrefs.getString('lonora.locale'), isNull);
    // The test host's language is English, which "Follow system" adopts.
    expect(store.state.prefs.locale, 'en');
    expect(find.text('Follow system'), findsNWidgets(2));
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      await withRealShadows(() async {
        await setUpServices(prefs: {'lonora.locale': v.locale});
        final store = testStore(locale: v.locale, theme: v.theme);
        setFeatureViewport(tester);
        await tester.pumpWidget(
          featureApp(store, testRouter(const AppearanceScreen())),
        );
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/appearance_${v.name}.png'),
        );
      });
    });
  }
}
