// This phone's notification preferences (apps/web NotifyPages.tsx «In-app notifications» and
// «Text preview»): on by default, remembered in device prefs, switched on the Notifications
// page before the opportunities alert.
import 'package:async_redux/async_redux.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/features/settings/notifications_screen.dart';
import 'package:lonora/state/actions/prefs_actions.dart';
import 'package:lonora/state/app_state.dart';

import 'feature_harness.dart';

void main() {
  setUpAll(setUpFeatureTests);

  testWidgets('both on by default; a change is remembered on this phone', (
    tester,
  ) async {
    await setUpServices();
    final store = Store<AppState>(initialState: const AppState());
    await store.dispatchAndWait(LoadPrefsAction());
    expect(store.state.prefs.notify.inApp, isTrue);
    expect(store.state.prefs.notify.preview, isTrue);

    await store.dispatchAndWait(
      SetNotifyPrefsAction(const NotifyPrefs(inApp: false)),
    );
    expect(store.state.prefs.notify.inApp, isFalse);
    expect(store.state.prefs.notify.preview, isTrue);
    expect(devicePrefs.getBool('lonora.notify.in_app'), isFalse);
    expect(devicePrefs.getBool('lonora.notify.preview'), isTrue);

    final relaunched = Store<AppState>(initialState: const AppState());
    await relaunched.dispatchAndWait(LoadPrefsAction());
    expect(relaunched.state.prefs.notify.inApp, isFalse);
    expect(readNotifyPrefs(devicePrefs).inApp, isFalse);
  });

  group('Notifications page', () {
    Future<(ScriptedApi, Store<AppState>)> pump(
      WidgetTester tester, {
      bool attentionFails = false,
    }) async {
      final api = await setUpServices();
      api.on('GET /owner/profile', (_) => profileJson());
      api.on(
        'GET /attention/policy',
        (_) => attentionFails
            ? throw ApiError(status: 500, code: 'request_failed')
            : {'opportunities': true, 'informational': false, 'locale': 'en'},
      );
      final store = testStore(locale: 'en');
      setFeatureViewport(tester);
      await tester.pumpWidget(
        featureApp(store, testRouter(const NotificationsScreen())),
      );
      await tester.pumpAndSettle();
      return (api, store);
    }

    testWidgets('the two switches come before opportunities and save here', (
      tester,
    ) async {
      final (api, store) = await pump(tester);
      await scrollTo(tester, find.text('In-app notifications'));
      final inApp = tester.getTopLeft(find.text('In-app notifications')).dy;
      final preview = tester.getTopLeft(find.text('Text preview')).dy;
      final opportunities = tester
          .getTopLeft(find.text('Notify me about confirmed opportunities'))
          .dy;
      expect(inApp < preview && preview < opportunities, isTrue);
      expect(
        find.text(
          'A bar at the top of the screen when a reply arrives in another conversation',
        ),
        findsOneWidget,
      );
      expect(
        find.text('Show the start of the message in the notification'),
        findsOneWidget,
      );

      await tapAndSettle(tester, find.text('In-app notifications'));
      expect(store.state.prefs.notify.inApp, isFalse);
      expect(devicePrefs.getBool('lonora.notify.in_app'), isFalse);
      await tapAndSettle(tester, find.text('Text preview'));
      expect(store.state.prefs.notify.preview, isFalse);
      expect(devicePrefs.getBool('lonora.notify.preview'), isFalse);
      // Device-only: nothing is written to the server.
      expect(api.calls.where((c) => c.method != 'GET'), isEmpty);
    });

    testWidgets('they show even when the opportunities policy fails', (
      tester,
    ) async {
      await pump(tester, attentionFails: true);
      await scrollTo(tester, find.text('Text preview'));
      expect(find.text('In-app notifications'), findsOneWidget);
      expect(
        find.text('Notify me about confirmed opportunities'),
        findsNothing,
      );
    });
  });
}
