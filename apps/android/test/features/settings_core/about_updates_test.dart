// About: «Check for updates» runs an asked check (the sheet, or why there is nothing to
// install) and spins without a second check while it runs, and a found update turns the row
// into «Update available» that opens the sheet (golden dark_ar; fits at 1.3 text scale).

import 'dart:async';

import 'package:flutter/widgets.dart'
    show AssetImage, WidgetsApp, precacheImage;
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/design/design.dart' show LnListTile, LnSpinner;
import 'package:lonora/features/settings/about_screen.dart';
import 'package:lonora/platform/updates/update_service.dart';
import 'package:lonora/state/app_state.dart' show AppThemeMode;

import '../../design/harness.dart' show withRealShadows;
import 'feature_harness.dart';

class _Play implements PlayUpdates {
  UpdateInfo? next;
  Completer<UpdateInfo?>? pending;
  int checks = 0;
  int downloads = 0;
  @override
  Future<UpdateInfo?> check() async {
    checks++;
    return pending?.future ?? next;
  }

  @override
  Future<bool> download() async {
    downloads++;
    return false;
  }

  @override
  Future<void> restart() async {}
}

void main() {
  setUpAll(setUpFeatureTests);

  final service = UpdateService.instance;
  late _Play play;

  setUp(() {
    service.resetForTest();
    play = _Play();
    service
      ..isAndroid = (() => true)
      ..installer = (() async => 'com.android.vending')
      ..play = play;
  });
  tearDown(() {
    service
      ..resetForTest()
      ..isAndroid = (() => false);
  });

  Future<void> pumpAbout(
    WidgetTester tester, {
    String locale = 'en',
    AppThemeMode theme = AppThemeMode.light,
  }) async {
    final api = await setUpServices(
      stored: StoredSession(
        server: testServer,
        token: 'secret-token-never-shown',
        ownerId: testOwner.id,
        email: testOwner.email,
      ),
    );
    api.on('GET /version', (_) => {'version': '0.2.0', 'build': '1a2b3c4'});
    setFeatureViewport(tester);
    await tester.pumpWidget(
      featureApp(
        testStore(locale: locale, theme: theme),
        testRouter(const AboutScreen()),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> settleToast(WidgetTester tester) async {
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  }

  testWidgets('«Check for updates»: up to date, then the sheet', (
    tester,
  ) async {
    await pumpAbout(tester);
    expect(find.text('Update available'), findsNothing);
    await tapAndSettle(tester, find.text('Check for updates'));
    expect(play.checks, 1);
    expect(find.text('You have the latest version.'), findsOneWidget);
    await settleToast(tester);

    play.next = const UpdateInfo(
      versionName: '',
      versionCode: 14,
      viaStore: true,
    );
    await tapAndSettle(tester, find.text('Check for updates'));
    expect(play.checks, 2);
    // The sheet, and the row behind it now says so.
    expect(find.text('Update'), findsOneWidget);
    expect(find.text('Update available'), findsNWidgets(2));
    await tapAndSettle(tester, find.text('Later'));
    expect(find.text('Update available'), findsOneWidget);
    expect(find.text('Check for updates'), findsNothing);
    expect(play.downloads, 0);
  });

  testWidgets('a running check spins and takes no second tap', (tester) async {
    final pending = play.pending = Completer<UpdateInfo?>();
    await pumpAbout(tester);
    final row = find.widgetWithText(LnListTile, 'Check for updates');
    await tester.tap(row);
    await tester.pump();
    expect(
      find.descendant(of: row, matching: find.byType(LnSpinner)),
      findsOneWidget,
    );
    expect(tester.widget<LnListTile>(row).onTap, isNull);
    await tester.tap(row);
    await tester.pump();
    expect(play.checks, 1);
    pending.complete(null);
    await tester.pumpAndSettle();
    expect(
      find.descendant(of: row, matching: find.byType(LnSpinner)),
      findsNothing,
    );
    expect(tester.widget<LnListTile>(row).onTap, isNotNull);
    expect(find.text('You have the latest version.'), findsOneWidget);
    await settleToast(tester);
  });

  testWidgets('a known update opens its sheet without another check', (
    tester,
  ) async {
    await pumpAbout(tester);
    service.available.value = UpdateInfo(
      versionName: '1.2.0',
      versionCode: 12,
      downloadUrl: Uri.parse('https://releases.example.com/l.apk'),
    );
    await tester.pumpAndSettle();
    expect(find.text('Check for updates'), findsNothing);
    expect(find.textContaining('1.2.0'), findsOneWidget);
    await tapAndSettle(tester, find.text('Update available'));
    expect(play.checks, 0);
    expect(find.text('Download'), findsOneWidget);
    await tapAndSettle(tester, find.text('Later'));
  });

  testWidgets('updates off for this build say so', (tester) async {
    service.installer = () async => 'com.android.packageinstaller';
    service.configuredManifest = '';
    await pumpAbout(tester);
    await tapAndSettle(tester, find.text('Check for updates'));
    expect(find.text('Check for updates'), findsOneWidget);
    expect(
      find.text('In-app updates are not available for this build.'),
      findsOneWidget,
    );
    await settleToast(tester);
  });

  final found = UpdateInfo(
    versionName: '1.2.0',
    versionCode: 12,
    downloadUrl: Uri.parse('https://releases.example.com/l.apk'),
  );

  testWidgets('golden dark_ar: «Update available»', (tester) async {
    service.available.value = found;
    await withRealShadows(() async {
      await pumpAbout(tester, locale: 'ar', theme: AppThemeMode.dark);
      // The logo is decoded off the fake clock, so the image matches in any test order.
      await tester.runAsync(
        () => precacheImage(
          const AssetImage('assets/brand/logo.png'),
          tester.element(find.byType(AboutScreen)),
        ),
      );
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(WidgetsApp),
        matchesGoldenFile('goldens/about_update_dark_ar.png'),
      );
    });
  });

  testWidgets('both rows fit at 1.3 text scale', (tester) async {
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await pumpAbout(tester, locale: 'ar');
    expect(tester.takeException(), isNull);
    service.available.value = found;
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
