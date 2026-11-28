// A link that starts Lonora (the website's "Open in the app"): it arrives while the stored session
// is still being read, when the router shows the splash for every location. It is held and opened
// once the session is known, with the real router, connect and sign-in screens and the real
// BootstrapAction: lonora://connect?server=https://<handle>.lonora.io still reaches the connect
// confirmation, then sign-in for that server with no setup token.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/app/deep_links.dart';
import 'package:lonora/app/router.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/app/splash_screen.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/features/auth/connect_screen.dart';
import 'package:lonora/features/auth/server_screen.dart';
import 'package:lonora/features/auth/sign_in_screen.dart';
import 'package:lonora/state/actions/session_actions.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';

import '../features/settings_core/feature_harness.dart';

const cloud = 'https://handle.lonora.io';
final link = Uri.parse(
  'lonora://connect?server=https%3A%2F%2Fhandle.lonora.io',
);

void main() {
  setUpAll(setUpFeatureTests);

  /// The app at launch: the session not read yet, the real router, [DeepLinks] on it.
  Future<
    ({ScriptedApi api, Store<AppState> store, GoRouter router, DeepLinks links})
  >
  launch(
    WidgetTester tester, {
    String? lastServer,
    StoredSession? stored,
  }) async {
    final api = await setUpServices(
      prefs: const {'lonora.locale': 'en', 'lonora.theme': 'light'},
      stored: stored,
    );
    if (lastServer != null) await secureStore.rememberServer(lastServer);
    final store = Store<AppState>(initialState: const AppState());
    realtime = RealtimeController(store);
    final router = buildRouter(store);
    addTearDown(router.dispose);
    final links = DeepLinks(store: store, router: router);
    addTearDown(links.dispose);
    setFeatureViewport(tester);
    await tester.pumpWidget(featureApp(store, router));
    await tester.pump();
    expect(store.state.session.status, SessionStatus.unknown);
    return (api: api, store: store, router: router, links: links);
  }

  String location(GoRouter router) =>
      router.routerDelegate.currentConfiguration.uri.toString();

  for (final (name, lastServer) in [
    ('a fresh install', null),
    ('an owner signed out of another server', 'https://other.example.com'),
  ]) {
    testWidgets('$name: the link held at launch opens the confirmation, then '
        'sign-in for that server', (tester) async {
      final app = await launch(tester, lastServer: lastServer);
      app.links.open(link);
      await tester.pump();
      // Nothing moves while the session is being read.
      expect(find.byType(SplashScreen), findsOneWidget);
      expect(location(app.router), '/splash');
      await app.store.dispatchAndWait(BootstrapAction());
      await tester.pumpAndSettle();
      expect(app.store.state.session.status, SessionStatus.signedOut);
      expect(
        location(app.router),
        '/connect?server=https%3A%2F%2Fhandle.lonora.io',
      );
      expect(find.byType(ConnectScreen), findsOneWidget);
      expect(find.byType(ServerScreen), findsNothing);
      expect(find.textContaining('handle.lonora.io'), findsOneWidget);
      // Nothing is sent before the owner confirms.
      expect(app.api.calls, isEmpty);
      await tapAndSettle(tester, find.text('Connect'));
      await tester.pump(const Duration(milliseconds: 450));
      await tester.pumpAndSettle();
      expect(app.store.state.session.lastServer, cloud);
      expect(app.store.state.session.pendingSetupToken, isNull);
      expect(find.byType(SignInScreen), findsOneWidget);
      expect(find.textContaining('handle.lonora.io'), findsOneWidget);
      // E-mail and password only: the website account signs in, no setup token.
      expect(find.byType(EditableText), findsNWidgets(2));
      expect(find.text('Setup token'), findsNothing);
      expect(app.api.calls.map((c) => c.path).toSet(), {
        'probe:$cloud/onboarding',
      });
    });
  }

  testWidgets(
    'signed in elsewhere: the held link opens the confirmation, which '
    'says the session there ends',
    (tester) async {
      final app = await launch(
        tester,
        stored: const StoredSession(
          server: testServer,
          token: 'session-token',
          ownerId: 'owner-1',
          email: 'owner@example.com',
        ),
      );
      app.links.open(link);
      await tester.pump();
      expect(find.byType(SplashScreen), findsOneWidget);
      await app.store.dispatchAndWait(BootstrapAction());
      await tester.pumpAndSettle();
      expect(app.store.state.session.status, SessionStatus.signedIn);
      expect(find.byType(ConnectScreen), findsOneWidget);
      expect(find.textContaining('handle.lonora.io'), findsOneWidget);
      expect(find.text('Connect'), findsOneWidget);
      expect(
        find.text(
          'Changing servers signs out of your current session. Sign in with '
          'the new server’s account.',
        ),
        findsOneWidget,
      );
      // Nothing reaches the link's server before the owner confirms.
      expect(
        app.api.calls.where((c) => c.path.contains('handle.lonora.io')),
        isEmpty,
      );
      // The restored session starts the live feed, which nothing here answers: stop it and let
      // its connect timeout run out.
      realtime.stop();
      await tester.pump(const Duration(seconds: 11));
    },
  );

  testWidgets('the newest link wins; one that is not Lonora\'s is ignored', (
    tester,
  ) async {
    final app = await launch(tester);
    app.links.open(
      Uri.parse('lonora://connect?server=https://first.lonora.io'),
    );
    app.links.open(link);
    app.links.open(Uri.parse('https://evil.example/connect?server=x'));
    await app.store.dispatchAndWait(BootstrapAction());
    await tester.pumpAndSettle();
    expect(
      location(app.router),
      '/connect?server=https%3A%2F%2Fhandle.lonora.io',
    );
  });

  testWidgets('once the session is known a link opens at once; a disposed '
      'listener opens nothing', (tester) async {
    final app = await launch(tester);
    app.links.open(link);
    app.links.dispose();
    await app.store.dispatchAndWait(BootstrapAction());
    await tester.pumpAndSettle();
    // Fresh install, link dropped with the app: the first step is choosing a server.
    expect(find.byType(ConnectScreen), findsNothing);
    expect(find.byType(ServerScreen), findsOneWidget);
    final warm = DeepLinks(store: app.store, router: app.router);
    addTearDown(warm.dispose);
    warm.open(link);
    await tester.pumpAndSettle();
    expect(find.byType(ConnectScreen), findsOneWidget);
  });
}
