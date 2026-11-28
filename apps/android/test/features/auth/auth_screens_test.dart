// Sign-in, owner setup, server step and connect links (a Lonora Cloud link without a setup
// token lands on sign-in for its server), the sign-up link to lonora.io, plus sign-in goldens
// (with an error).
//
// Regenerate goldens with: flutter test --update-goldens test/features/auth
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart' show TextField;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart' show GoRouterState;
import 'package:lonora/app/deep_links.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/design/design.dart' show LnPalette;
import 'package:lonora/features/auth/connect_screen.dart';
import 'package:lonora/features/auth/server_check.dart';
import 'package:lonora/features/auth/server_screen.dart';
import 'package:lonora/features/auth/sign_in_screen.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';

import '../../design/harness.dart';
import '../settings_core/feature_harness.dart';

void main() {
  setUpAll(setUpFeatureTests);

  group('server address rules', () {
    test('normalises and keeps https', () {
      expect(
        checkServerAddress(' lonora.example.com/api/ ').server,
        'https://lonora.example.com',
      );
    });
    test('http only for local addresses', () {
      expect(
        checkServerAddress('http://192.168.1.4:8840').server,
        'http://192.168.1.4:8840',
      );
      expect(
        checkServerAddress('http://127.0.0.1:8840').server,
        'http://127.0.0.1:8840',
      );
      expect(
        checkServerAddress('http://lonora.example.com').error,
        'auth_httpsRequired',
      );
    });
    test('refuses credentials, queries and other schemes', () {
      expect(
        checkServerAddress('https://u:p@x.example').error,
        'invalid_server',
      );
      expect(
        checkServerAddress('https://x.example/?a=1').error,
        'invalid_server',
      );
      expect(checkServerAddress('ftp://x.example').error, 'invalid_server');
      expect(checkServerAddress('').error, 'invalid_server');
    });
    test('host shown to the owner', () {
      expect(serverHost('https://lonora.example.com'), 'lonora.example.com');
      expect(serverHost('http://192.168.1.4:8840'), '192.168.1.4:8840');
    });
  });

  Future<(ScriptedApi, Store<AppState>)> pumpSignIn(
    WidgetTester tester, {
    String locale = 'ar',
    AppThemeMode theme = AppThemeMode.light,
    bool ownerInitialized = true,
    SessionState? session,
  }) async {
    final api = await setUpServices();
    api.onProbe = (server, path, body) => path == '/onboarding' && body == null
        ? {'owner_initialized': ownerInitialized}
        : {'owner_initialized': true};
    api.on(
      'POST /auth/mobile/login',
      (_) => throw ApiError(status: 401, code: 'unauthorized'),
    );
    final store = testStore(
      signedIn: false,
      locale: locale,
      theme: theme,
      session: session,
    );
    setFeatureViewport(tester);
    await tester.pumpWidget(
      featureApp(store, testRouter(const SignInScreen())),
    );
    await tester.pump(const Duration(milliseconds: 450));
    await tester.pumpAndSettle();
    return (api, store);
  }

  Future<void> fillAndSubmit(WidgetTester tester, String password) async {
    final fields = find.byType(EditableText);
    await tester.enterText(fields.at(0), 'owner@example.com');
    await tester.enterText(fields.at(1), password);
    await tester.pumpAndSettle();
  }

  /// The [index]th field on screen: its input flags and the direction its text reads in.
  ({TextField field, TextDirection direction}) fieldAt(
    WidgetTester tester,
    int index,
  ) {
    final editable = find.byType(EditableText).at(index);
    return (
      field: tester.widget<TextField>(
        find.ancestor(of: editable, matching: find.byType(TextField)),
      ),
      direction: tester
          .state<EditableTextState>(editable)
          .renderEditable
          .textDirection,
    );
  }

  testWidgets('wrong password shows the server\'s refusal', (tester) async {
    final (api, store) = await pumpSignIn(tester, locale: 'en');
    expect(find.text('Sign in'), findsWidgets);
    expect(find.textContaining('lonora.example.com'), findsOneWidget);
    await fillAndSubmit(tester, 'not-the-password');
    await tapAndSettle(tester, find.text('Sign in').last);
    expect(
      find.text('Check your credentials or sign in again.'),
      findsOneWidget,
    );
    expect(api.callsTo('POST', '/auth/mobile/login'), hasLength(1));
    expect(store.state.session.signedIn, isFalse);
  });

  testWidgets('rate limiting reads as wait and retry', (tester) async {
    final (api, _) = await pumpSignIn(tester, locale: 'en');
    api.on(
      'POST /auth/mobile/login',
      (_) => throw ApiError(
        status: 429,
        code: 'rate_limited',
        retryAfter: const Duration(seconds: 60),
      ),
    );
    await fillAndSubmit(tester, 'whatever-password');
    await tapAndSettle(tester, find.text('Sign in').last);
    expect(find.text('Wait a moment and try again.'), findsOneWidget);
  });

  testWidgets('a server without an owner shows the setup form', (tester) async {
    final (api, _) = await pumpSignIn(
      tester,
      locale: 'en',
      ownerInitialized: false,
    );
    expect(find.text('Set up Lonora'), findsOneWidget);
    expect(find.text('Setup token'), findsOneWidget);
    final fields = find.byType(EditableText);
    await tester.enterText(fields.at(0), 'owner@example.com');
    await tester.enterText(fields.at(1), 'a-long-enough-password');
    await tester.enterText(fields.at(2), 'short-token');
    await tester.pumpAndSettle();
    await tapAndSettle(tester, find.text('Create workspace'));
    expect(
      find.textContaining('The setup token is at least 24 characters'),
      findsOneWidget,
    );
    expect(api.calls.where((c) => c.method == 'POST'), isEmpty);
  });

  testWidgets('a connect link fills the setup token for its own server', (
    tester,
  ) async {
    const token = 'abcdefghijklmnopqrstuvwxyz0123';
    await pumpSignIn(
      tester,
      locale: 'en',
      ownerInitialized: false,
      session: const SessionState(
        status: SessionStatus.signedOut,
        lastServer: testServer,
        pendingSetupToken: (server: testServer, token: token),
      ),
    );
    final fields = tester.widgetList<EditableText>(find.byType(EditableText));
    expect(fields.last.controller.text, token);
  });

  testWidgets(
    'the setup token is never revealed and leaves with the setup form',
    (tester) async {
      const token = 'abcdefghijklmnopqrstuvwxyz0123';
      var initialized = false;
      final (api, _) = await pumpSignIn(
        tester,
        locale: 'en',
        ownerInitialized: false,
        session: const SessionState(
          status: SessionStatus.signedOut,
          lastServer: testServer,
          pendingSetupToken: (server: testServer, token: token),
        ),
      );
      // One eye only: the password's. The token field has none.
      expect(find.byIcon(FIcons.eye), findsOneWidget);
      expect(
        tester
            .widgetList<EditableText>(find.byType(EditableText))
            .last
            .obscureText,
        isTrue,
      );
      // The owner was created elsewhere meanwhile: setup is refused, the server is asked
      // again, the form turns to sign-in and the token is dropped.
      api.onProbe = (_, _, body) => body == null
          ? {'owner_initialized': initialized}
          : throw ApiError(status: 403, code: 'forbidden');
      initialized = true;
      final fields = find.byType(EditableText);
      await tester.enterText(fields.at(0), 'owner@example.com');
      await tester.enterText(fields.at(1), 'a-long-enough-password');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, find.text('Create workspace'));
      expect(find.text('Setup token'), findsNothing);
      expect(find.text('Sign in'), findsWidgets);
      final token2 = find.byWidgetPredicate(
        (w) => w is EditableText && w.controller.text == token,
      );
      expect(token2, findsNothing);
    },
  );

  group('sign-up link (Lonora Cloud)', () {
    const url = 'https://lonora.io/#start';
    const launcher = MethodChannel('plugins.flutter.io/url_launcher');
    late List<MethodCall> launches;

    /// Records every launch; [answer] is what the platform says (opened or not).
    void mockLauncher([FutureOr<bool> Function()? answer]) {
      launches = [];
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(launcher, (call) async {
        launches.add(call);
        return answer == null ? true : await answer();
      });
      addTearDown(() => messenger.setMockMethodCallHandler(launcher, null));
    }

    for (final (locale, line) in [
      ('ar', 'ما عندك حساب؟ سجّل من lonora.io'),
      ('en', 'No account? Sign up at lonora.io'),
    ]) {
      testWidgets('under sign-in, one link opens $url in the browser '
          '($locale)', (tester) async {
        mockLauncher();
        final semantics = tester.ensureSemantics();
        final (api, _) = await pumpSignIn(tester, locale: locale);
        expect(
          find.textContaining('lonora.io', findRichText: true),
          findsOneWidget,
        );
        final link = find.bySemanticsLabel(line);
        final node = tester.getSemantics(link);
        // A link with its address, not a button; a 48 dp target.
        expect(
          node,
          isSemantics(
            label: line,
            isLink: true,
            isButton: false,
            hasTapAction: true,
          ),
        );
        expect(node.getSemanticsData().linkUrl, Uri.parse(url));
        expect(node.rect.height, greaterThanOrEqualTo(48));
        // Below «Sign in».
        final signIn = find.text(locale == 'ar' ? 'تسجيل الدخول' : 'Sign in');
        expect(
          tester.getTopLeft(link).dy,
          greaterThan(tester.getBottomLeft(signIn.last).dy),
        );
        await tester.tap(link);
        await tester.pumpAndSettle();
        expect(launches, hasLength(1));
        final args = launches.single.arguments as Map;
        expect(launches.single.method, 'launch');
        expect(args['url'], url);
        // Outside the app: no in-app web view.
        expect(args['useWebView'], isFalse);
        // The screen reader's tap does the same.
        tester.semantics.tap(find.semantics.byLabel(line));
        await tester.pumpAndSettle();
        expect(launches, hasLength(2));
        // Nothing reaches the server (only the sign-in screen's own probe).
        expect(api.calls.where((c) => !c.path.startsWith('probe:')), isEmpty);
        semantics.dispose();
      });
    }

    testWidgets('a second tap while the browser opens launches nothing', (
      tester,
    ) async {
      final opened = Completer<bool>();
      mockLauncher(() => opened.future);
      await pumpSignIn(tester, locale: 'en');
      final link = find.bySemanticsLabel('No account? Sign up at lonora.io');
      await tester.tap(link);
      await tester.pump();
      await tester.tap(link);
      await tester.pump();
      expect(launches, hasLength(1));
      opened.complete(true);
      await tester.pumpAndSettle();
      await tester.tap(link);
      await tester.pumpAndSettle();
      expect(launches, hasLength(2));
    });

    testWidgets('no browser to open it says so', (tester) async {
      mockLauncher(() => false);
      await pumpSignIn(tester, locale: 'en');
      await tester.tap(
        find.bySemanticsLabel('No account? Sign up at lonora.io'),
      );
      await tester.pumpAndSettle();
      expect(find.text('The link could not be opened.'), findsOneWidget);
      await tester.pump(const Duration(seconds: 4));
      await tester.pumpAndSettle();
    });

    for (final initialized in [true, false]) {
      testWidgets('the line waits for the server\'s answer (owner '
          '${initialized ? 'set' : 'not set yet'})', (tester) async {
        final answer = Completer<Object?>();
        final api = await setUpServices();
        api.onProbe = (_, _, _) => answer.future;
        final store = testStore(signedIn: false, locale: 'en');
        setFeatureViewport(tester);
        await tester.pumpWidget(
          featureApp(store, testRouter(const SignInScreen())),
        );
        await tester.pump(const Duration(milliseconds: 450));
        await tester.pump();
        // Still asking the server: no line, so none flashes before the setup form.
        expect(api.calls.map((c) => c.path), [
          'probe:https://lonora.example.com/onboarding',
        ]);
        expect(
          find.textContaining('lonora.io', findRichText: true),
          findsNothing,
        );
        answer.complete({'owner_initialized': initialized});
        await tester.pumpAndSettle();
        expect(
          find.text('Set up Lonora'),
          initialized ? findsNothing : findsOneWidget,
        );
        expect(
          find.bySemanticsLabel('No account? Sign up at lonora.io'),
          initialized ? findsOneWidget : findsNothing,
        );
      });
    }

    testWidgets('the owner setup form has no sign-up link', (tester) async {
      await pumpSignIn(tester, locale: 'en', ownerInitialized: false);
      expect(find.text('Set up Lonora'), findsOneWidget);
      expect(
        find.textContaining('lonora.io', findRichText: true),
        findsNothing,
      );
    });
  });

  group('owner setup', () {
    /// Signing in starts the realtime feed, which nothing here answers: stop it and let its
    /// connect timeout run out.
    Future<void> stopRealtime(WidgetTester tester) async {
      realtime.stop();
      await tester.pump(const Duration(seconds: 11));
    }

    Future<(ScriptedApi, Store<AppState>)> pumpSetup(
      WidgetTester tester,
      Object? Function() onCreate,
    ) async {
      final (api, store) = await pumpSignIn(
        tester,
        locale: 'en',
        ownerInitialized: false,
      );
      api.onProbe = (server, path, body) =>
          body == null ? {'owner_initialized': false} : onCreate();
      api.on(
        'POST /auth/mobile/login',
        (_) => {
          'token': 'session-token',
          'expires_in': 3600,
          'owner': {'id': 'owner-1', 'email': 'owner@example.com'},
        },
      );
      final fields = find.byType(EditableText);
      await tester.enterText(fields.at(0), 'owner@example.com');
      await tester.enterText(fields.at(1), 'a-long-enough-password');
      await tester.enterText(fields.at(2), 'abcdefghijklmnopqrstuvwxyz0123');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, find.text('Create workspace'));
      return (api, store);
    }

    testWidgets('creates the owner, then signs in', (tester) async {
      final (api, store) = await pumpSetup(
        tester,
        () => {'owner_initialized': true},
      );
      final create = api.calls.singleWhere(
        (c) => c.method == 'POST' && c.path.endsWith('/onboarding'),
      );
      expect(create.path, 'probe:$testServer/onboarding');
      expect(create.body, {
        'email': 'owner@example.com',
        'password': 'a-long-enough-password',
        'bootstrap_token': 'abcdefghijklmnopqrstuvwxyz0123',
      });
      expect(api.callsTo('POST', '/auth/mobile/login'), hasLength(1));
      expect(store.state.session.signedIn, isTrue);
      expect(store.state.session.owner?.email, 'owner@example.com');
      await stopRealtime(tester);
    });

    testWidgets('an owner created meanwhile still signs in (409)', (
      tester,
    ) async {
      final (api, store) = await pumpSetup(
        tester,
        () => throw ApiError(status: 409, code: 'owner_already_initialized'),
      );
      expect(api.callsTo('POST', '/auth/mobile/login'), hasLength(1));
      expect(store.state.session.signedIn, isTrue);
      await stopRealtime(tester);
    });
  });

  testWidgets(
    'a connect link, then another server: sign-in follows the change',
    (tester) async {
      const token = 'abcdefghijklmnopqrstuvwxyz0123';
      final api = await setUpServices();
      api.onProbe = (_, _, _) => {'owner_initialized': false};
      final store = testStore(
        signedIn: false,
        locale: 'en',
        session: const SessionState(status: SessionStatus.signedOut),
      );
      setFeatureViewport(tester);
      await tester.pumpWidget(
        featureApp(
          store,
          testRouter(
            const ConnectScreen(
              server: 'https://home.lonora.cloud',
              token: token,
            ),
            pages: {
              Routes.signIn: (_) => const SignInScreen(),
              Routes.server: (_) => const ServerScreen(),
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tapAndSettle(tester, find.text('Connect'));
      await tester.pump(const Duration(milliseconds: 450));
      await tester.pumpAndSettle();
      expect(find.textContaining('home.lonora.cloud'), findsOneWidget);
      expect(
        tester
            .widgetList<EditableText>(find.byType(EditableText))
            .last
            .controller
            .text,
        token,
      );

      // The server row opens the server step; another server is chosen there.
      await tapAndSettle(tester, find.textContaining('home.lonora.cloud'));
      await tester.enterText(find.byType(EditableText), 'other.example.com');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, find.text('Continue'));
      await tester.pump(const Duration(milliseconds: 450));
      await tester.pumpAndSettle();

      expect(store.state.session.lastServer, 'https://other.example.com');
      expect(find.textContaining('other.example.com'), findsOneWidget);
      expect(find.textContaining('home.lonora.cloud'), findsNothing);
      expect(api.calls.last.path, 'probe:https://other.example.com/onboarding');
      // The link's token was for the other server: the form does not carry it.
      for (final field in tester.widgetList<EditableText>(
        find.byType(EditableText),
      )) {
        expect(field.controller.text, isNot(token));
      }
    },
  );

  testWidgets('expired session is explained', (tester) async {
    await pumpSignIn(
      tester,
      locale: 'en',
      session: const SessionState(
        status: SessionStatus.signedOut,
        lastServer: testServer,
        expired: true,
      ),
    );
    expect(find.text('Your session ended. Sign in again.'), findsOneWidget);
  });

  group('server step', () {
    Future<(ScriptedApi, Store<AppState>)> pumpServer(
      WidgetTester tester, {
      Object? Function(String, String, Object?)? probe,
    }) async {
      final api = await setUpServices();
      api.onProbe = probe;
      final store = testStore(
        signedIn: false,
        locale: 'en',
        session: const SessionState(status: SessionStatus.signedOut),
      );
      setFeatureViewport(tester);
      await tester.pumpWidget(
        featureApp(store, testRouter(const ServerScreen())),
      );
      await tester.pumpAndSettle();
      return (api, store);
    }

    testWidgets('the address reads left to right, uncorrected', (tester) async {
      await pumpServer(tester);
      final address = fieldAt(tester, 0);
      expect(address.direction, TextDirection.ltr);
      expect(address.field.autocorrect, isFalse);
    });

    testWidgets('remote http is refused before any request', (tester) async {
      final (api, _) = await pumpServer(tester);
      await tester.enterText(
        find.byType(EditableText),
        'http://lonora.example.com',
      );
      await tester.pumpAndSettle();
      await tapAndSettle(tester, find.text('Continue'));
      expect(find.textContaining('must start with https://'), findsOneWidget);
      expect(api.calls, isEmpty);
    });

    testWidgets('an address that is not Lonora is refused', (tester) async {
      await pumpServer(tester, probe: (_, _, _) => {'hello': 'world'});
      await tester.enterText(find.byType(EditableText), 'example.org');
      await tester.pumpAndSettle();
      await tapAndSettle(tester, find.text('Continue'));
      expect(
        find.text(
          'This address did not answer as a Lonora server. Check the address.',
        ),
        findsOneWidget,
      );
    });

    group('while signed in', () {
      Future<(ScriptedApi, Store<AppState>)> pumpSignedIn(
        WidgetTester tester,
        String address,
      ) async {
        final api = await setUpServices();
        final store = testStore(locale: 'en');
        setFeatureViewport(tester);
        await tester.pumpWidget(
          featureApp(store, testRouter(const ServerScreen())),
        );
        await tester.pumpAndSettle();
        await tester.enterText(find.byType(EditableText), address);
        await tester.pumpAndSettle();
        // The button's spinner turns while the confirmation is open: no settling.
        await tester.tap(find.text('Save'));
        for (var i = 0; i < 8; i++) {
          await tester.pump(const Duration(milliseconds: 100));
        }
        return (api, store);
      }

      testWidgets('another server asks, revokes this session, then sign-in', (
        tester,
      ) async {
        final (api, store) = await pumpSignedIn(tester, 'other.example.com');
        expect(
          api.calls.single.path,
          'probe:https://other.example.com/onboarding',
        );
        expect(
          find.text(
            'Changing servers signs out of your current session. '
            'Sign in with the new server’s account.',
          ),
          findsNWidgets(2),
        );
        expect(store.state.session.signedIn, isTrue);
        await tapAndSettle(tester, find.text('Save').last);
        expect(api.callsTo('POST', '/auth/logout'), hasLength(1));
        expect(store.state.session.status, SessionStatus.signedOut);
        expect(store.state.session.lastServer, 'https://other.example.com');
        expect(find.text('stub:${Routes.signIn}'), findsOneWidget);
      });

      testWidgets('cancelling keeps the session and the server', (
        tester,
      ) async {
        final (api, store) = await pumpSignedIn(tester, 'other.example.com');
        await tapAndSettle(tester, find.text('Cancel'));
        expect(api.callsTo('POST', '/auth/logout'), isEmpty);
        expect(store.state.session.signedIn, isTrue);
        expect(store.state.session.server, testServer);
        expect(store.state.session.lastServer, testServer);
      });

      testWidgets('the same server just leaves', (tester) async {
        final (api, store) = await pumpSignedIn(tester, 'lonora.example.com');
        expect(api.callsTo('POST', '/auth/logout'), isEmpty);
        expect(store.state.session.signedIn, isTrue);
        expect(find.text('stub:${Routes.me}'), findsOneWidget);
      });
    });

    testWidgets('a Lonora server is remembered and sign-in follows', (
      tester,
    ) async {
      final (api, store) = await pumpServer(tester);
      await tester.enterText(
        find.byType(EditableText),
        'lonora.example.com/api',
      );
      await tester.pumpAndSettle();
      await tapAndSettle(tester, find.text('Continue'));
      expect(
        api.calls.single.path,
        'probe:https://lonora.example.com/onboarding',
      );
      expect(store.state.session.lastServer, 'https://lonora.example.com');
      expect(find.text('stub:${Routes.signIn}'), findsOneWidget);
    });
  });

  group('connect link', () {
    testWidgets('an invalid link says so and connects nothing', (tester) async {
      await setUpServices();
      final store = testStore(signedIn: false, locale: 'en');
      setFeatureViewport(tester);
      await tester.pumpWidget(
        featureApp(
          store,
          testRouter(const ConnectScreen(server: 'http://lonora.example.com')),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        find.textContaining('This connect link is not valid'),
        findsOneWidget,
      );
      expect(find.text('Connect'), findsNothing);
    });

    testWidgets('signed in elsewhere: says so, then revokes on confirm', (
      tester,
    ) async {
      final api = await setUpServices();
      final store = testStore(locale: 'en');
      setFeatureViewport(tester);
      await tester.pumpWidget(
        featureApp(
          store,
          testRouter(
            const ConnectScreen(
              server: 'https://home.lonora.cloud',
              token: 'abcdefghijklmnopqrstuvwxyz0123',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('Changing servers signs out'), findsOneWidget);
      expect(api.calls, isEmpty);
      await tapAndSettle(tester, find.text('Connect'));
      expect(api.callsTo('POST', '/auth/logout'), hasLength(1));
      expect(store.state.session.status, SessionStatus.signedOut);
      expect(store.state.session.lastServer, 'https://home.lonora.cloud');
      expect(find.text('stub:${Routes.signIn}'), findsOneWidget);
    });

    testWidgets('signed in to the same server: nothing to revoke', (
      tester,
    ) async {
      await setUpServices();
      final store = testStore(locale: 'en');
      setFeatureViewport(tester);
      await tester.pumpWidget(
        featureApp(store, testRouter(const ConnectScreen(server: testServer))),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('Changing servers signs out'), findsNothing);
    });

    group(
      'Lonora Cloud: lonora://connect?server=https://<handle>.lonora.io',
      () {
        const cloud = 'https://handle.lonora.io';

        /// The link opened from the app's own mapping, with the real connect and sign-in screens.
        late List<String> probed;

        Future<(ScriptedApi, Store<AppState>)> openLink(
          WidgetTester tester,
          String link, {
          bool ownerInitialized = true,
        }) async {
          probed = [];
          final api = await setUpServices();
          api.onProbe = (server, path, body) {
            probed.add('$server $path');
            return {'owner_initialized': ownerInitialized};
          };
          final store = testStore(
            signedIn: false,
            locale: 'en',
            session: const SessionState(status: SessionStatus.signedOut),
          );
          setFeatureViewport(tester);
          final location = DeepLinks.locationFor(Uri.parse(link))!;
          await tester.pumpWidget(
            featureApp(
              store,
              testRouter(
                const SizedBox(),
                initialLocation: location,
                pages: {
                  Routes.connect: (context) {
                    final query = GoRouterState.of(context).uri.queryParameters;
                    return ConnectScreen(
                      server: query['server'] ?? '',
                      token: query['token'],
                    );
                  },
                  Routes.signIn: (_) => const SignInScreen(),
                },
              ),
            ),
          );
          await tester.pumpAndSettle();
          return (api, store);
        }

        testWidgets('a server without a token: confirm, then sign-in for that '
            'server with the website account', (tester) async {
          expect(
            DeepLinks.locationFor(Uri.parse('lonora://connect?server=$cloud')),
            '/connect?server=https%3A%2F%2Fhandle.lonora.io',
          );
          final (api, store) = await openLink(
            tester,
            'lonora://connect?server=$cloud',
          );
          expect(find.textContaining('handle.lonora.io'), findsOneWidget);
          // Nothing happens before the owner confirms.
          expect(api.calls, isEmpty);
          await tapAndSettle(tester, find.text('Connect'));
          await tester.pump(const Duration(milliseconds: 450));
          await tester.pumpAndSettle();
          expect(store.state.session.lastServer, cloud);
          expect(store.state.session.pendingSetupToken, isNull);
          // Sign-in for that server: its host in the server row, e-mail and password only.
          expect(find.byType(SignInScreen), findsOneWidget);
          expect(find.textContaining('handle.lonora.io'), findsOneWidget);
          expect(find.text('Sign in'), findsWidgets);
          expect(find.text('Setup token'), findsNothing);
          expect(find.byType(EditableText), findsNWidgets(2));
          expect(probed.toSet(), {'$cloud /onboarding'});
          // Signing in goes to that server.
          String? signedInAt;
          api.on('POST /auth/mobile/login', (_) {
            signedInAt = api.server;
            throw ApiError(status: 401, code: 'unauthorized');
          });
          await fillAndSubmit(tester, 'the-website-password');
          await tapAndSettle(tester, find.text('Sign in').last);
          expect(api.callsTo('POST', '/auth/mobile/login'), hasLength(1));
          expect(signedInAt, cloud);
        });

        testWidgets('a server and a setup token keep the first-run setup', (
          tester,
        ) async {
          const token = 'abcdefghijklmnopqrstuvwxyz0123';
          final (_, store) = await openLink(
            tester,
            'lonora://connect?server=$cloud&token=$token',
            ownerInitialized: false,
          );
          await tapAndSettle(tester, find.text('Connect'));
          await tester.pump(const Duration(milliseconds: 450));
          await tester.pumpAndSettle();
          expect(store.state.session.pendingSetupToken, (
            server: cloud,
            token: token,
          ));
          expect(find.text('Set up Lonora'), findsOneWidget);
          final fields = tester.widgetList<EditableText>(
            find.byType(EditableText),
          );
          expect(fields.last.controller.text, token);
        });

        testWidgets('a remote http server is refused before anything is sent', (
          tester,
        ) async {
          expect(
            DeepLinks.locationFor(
              Uri.parse('lonora://connect?server=http://handle.lonora.io'),
            ),
            Routes.connect,
          );
          final (api, store) = await openLink(
            tester,
            'lonora://connect?server=http://handle.lonora.io',
          );
          expect(
            find.textContaining('This connect link is not valid'),
            findsOneWidget,
          );
          expect(find.text('Connect'), findsNothing);
          expect(api.calls, isEmpty);
          expect(store.state.session.lastServer, isNull);
          // The screen itself refuses it too, should the address reach it another way.
          await tester.pumpWidget(
            featureApp(
              store,
              testRouter(
                const ConnectScreen(server: 'http://handle.lonora.io'),
              ),
            ),
          );
          await tester.pumpAndSettle();
          expect(find.text('Connect'), findsNothing);
        });
      },
    );

    testWidgets('confirming holds the token for that server only', (
      tester,
    ) async {
      await setUpServices();
      final store = testStore(signedIn: false, locale: 'en');
      setFeatureViewport(tester);
      await tester.pumpWidget(
        featureApp(
          store,
          testRouter(
            const ConnectScreen(
              server: 'https://home.lonora.cloud',
              token: 'abcdefghijklmnopqrstuvwxyz0123',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('home.lonora.cloud'), findsOneWidget);
      expect(store.state.session.pendingSetupToken, isNull);
      await tapAndSettle(tester, find.text('Connect'));
      expect(store.state.session.lastServer, 'https://home.lonora.cloud');
      expect(store.state.session.pendingSetupToken, (
        server: 'https://home.lonora.cloud',
        token: 'abcdefghijklmnopqrstuvwxyz0123',
      ));
      expect(find.text('stub:${Routes.signIn}'), findsOneWidget);
    });
  });

  testWidgets('e-mail and secrets read left to right in Arabic, uncorrected', (
    tester,
  ) async {
    // Owner setup: e-mail, password, setup token.
    await pumpSignIn(tester, ownerInitialized: false);
    expect(find.byType(EditableText), findsNWidgets(3));
    final email = fieldAt(tester, 0);
    expect(email.direction, TextDirection.ltr);
    expect(email.field.autocorrect, isFalse);
    for (final i in [1, 2]) {
      final secret = fieldAt(tester, i);
      expect(secret.direction, TextDirection.ltr, reason: 'field $i');
      expect(secret.field.autocorrect, isFalse, reason: 'field $i');
      expect(secret.field.enableSuggestions, isFalse, reason: 'field $i');
      expect(
        secret.field.enableIMEPersonalizedLearning,
        isFalse,
        reason: 'field $i',
      );
    }
  });

  testWidgets('ms:C3 in Arabic the password box lines up with the e-mail box', (
    tester,
  ) async {
    await pumpSignIn(tester);
    await fillAndSubmit(tester, 'not-the-password');
    final email = tester.getRect(find.byType(EditableText).at(0));
    final password = tester.getRect(find.byType(EditableText).at(1));
    // Both texts start at the box's left padding; the eye is at the right end.
    expect(password.left, email.left);
    expect(
      tester.getRect(find.byIcon(FIcons.eye)).center.dx,
      greaterThan(password.center.dx),
    );
  });

  testWidgets('ms:C17 «Change» is drawn in the link colour', (tester) async {
    await pumpSignIn(tester, theme: AppThemeMode.dark);
    final change = tester.widget<Text>(find.text('تغيير'));
    expect(change.style!.color, LnPalette.dark.link);
  });

  testWidgets('the eye, the language switch and the server row are buttons '
      'with the tap action', (tester) async {
    final (_, store) = await pumpSignIn(tester, locale: 'en');
    final semantics = tester.ensureSemantics();
    final controls = {
      FIcons.eye: 'Show password',
      'العربية': 'العربية',
      'lonora.example.com': 'Lonora server URL: lonora.example.com',
    };
    for (final MapEntry(key: control, value: label) in controls.entries) {
      expect(
        tester.getSemantics(
          control is IconData
              ? find.byIcon(control)
              : find.textContaining(control as String),
        ),
        isSemantics(label: label, isButton: true, hasTapAction: true),
        reason: label,
      );
    }
    tester.semantics.tap(find.semantics.byLabel('Show password'));
    await tester.pumpAndSettle();
    expect(find.byIcon(FIcons.eyeOff), findsOneWidget);
    tester.semantics.tap(find.semantics.byLabel('العربية'));
    await tester.pumpAndSettle();
    expect(store.state.prefs.locale, 'ar');
    tester.semantics.tap(
      find.semantics.byLabel(RegExp(r'lonora\.example\.com')),
    );
    await tester.pumpAndSettle();
    expect(find.text('stub:${Routes.server}'), findsOneWidget);
    semantics.dispose();
  });

  testWidgets('text at 1.3× lays out without overflow', (tester) async {
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await pumpSignIn(tester, ownerInitialized: false);
    await fillAndSubmit(tester, 'not-the-password');
    expect(tester.takeException(), isNull);
  });

  testWidgets('golden server step light_en', (tester) async {
    await withRealShadows(() async {
      await setUpServices();
      final store = testStore(
        signedIn: false,
        locale: 'en',
        session: const SessionState(status: SessionStatus.signedOut),
      );
      setFeatureViewport(tester);
      await tester.pumpWidget(
        featureApp(store, testRouter(const ServerScreen())),
      );
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(EditableText),
        'http://lonora.example.com',
      );
      await tester.pumpAndSettle();
      await tapAndSettle(tester, find.text('Continue'));
      FocusManager.instance.primaryFocus?.unfocus();
      await tester.pumpAndSettle();
      expect(find.textContaining('must start with https://'), findsOneWidget);
      await expectLater(
        find.byType(WidgetsApp),
        matchesGoldenFile('goldens/server_light_en.png'),
      );
    });
  });

  testWidgets('golden connect dark_ar', (tester) async {
    await withRealShadows(() async {
      await setUpServices();
      final store = testStore(
        signedIn: false,
        locale: 'ar',
        theme: AppThemeMode.dark,
      );
      setFeatureViewport(tester);
      await tester.pumpWidget(
        featureApp(
          store,
          testRouter(
            const ConnectScreen(
              server: 'https://home.lonora.cloud',
              token: 'abcdefghijklmnopqrstuvwxyz0123',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(WidgetsApp),
        matchesGoldenFile('goldens/connect_dark_ar.png'),
      );
    });
  });

  for (final v in goldenVariants) {
    testWidgets('golden sign-in error ${v.name}', (tester) async {
      await withRealShadows(() async {
        await pumpSignIn(tester, locale: v.locale, theme: v.theme);
        await fillAndSubmit(tester, 'not-the-password');
        await tester.tap(find.byType(EditableText).at(1));
        await tester.testTextInput.receiveAction(TextInputAction.done);
        await tester.pumpAndSettle();
        FocusManager.instance.primaryFocus?.unfocus();
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/sign_in_error_${v.name}.png'),
        );
      });
    });
  }
}
