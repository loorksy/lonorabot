// Session actions: the server-address rule where a server enters the session (restored at
// launch, a server change, a connect link, sign-in, owner setup), a connect link's setup token
// across a server change, the sign-out order (hooks alongside the revocation, bounded, then the
// fence) and the shell's inbox error.
import 'dart:async';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/app/teardown.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/features/voice/voice_api.dart';
import 'package:lonora/state/actions/session_actions.dart';
import 'package:lonora/state/actions/shell_actions.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../features/settings_core/feature_harness.dart';

const remoteHttp = 'http://lonora.example.com';
final token = 'T' * 24;

Matcher get httpsRefusal => throwsA(
  isA<ApiError>().having((e) => e.code, 'code', 'auth_httpsRequired'),
);

MemorySecureStore get memorySecure => secureStore as MemorySecureStore;

/// The services with the app's real [ApiClient] (its request guard), inside `testWidgets` so
/// nothing can leave the test host.
Future<ApiClient> setUpRealClient() async {
  SharedPreferences.setMockInitialValues({});
  final client = ApiClient(userAgent: 'Lonora-Android/test');
  await registerServices(
    apiClient: client,
    secure: MemorySecureStore(),
    local: MemoryLocalStore(),
    prefs: await SharedPreferences.getInstance(),
    info: const AppInfo(
      version: '1.0.0',
      buildNumber: '7',
      packageName: 'ai.lonora.android',
    ),
  );
  return client;
}

/// Records how the voice call was ended and whether the session was still valid then.
class RecordingCalls extends VoiceCallController {
  final ended = <({bool finalize, String? token})>[];

  @override
  Future<void> end({bool finalize = true}) async =>
      ended.add((finalize: finalize, token: api.token));
}

/// The test binding's HTTP mock (an empty 400 for everything), except that `/held` is
/// answered only once [answer] completes.
class _HoldingOverrides extends HttpOverrides {
  _HoldingOverrides(this.inner, this.answer);
  final HttpOverrides inner;
  final Future<void> answer;

  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      _HoldingClient(inner.createHttpClient(context), answer);
}

class _HoldingClient implements HttpClient {
  _HoldingClient(this.inner, this.answer);
  final HttpClient inner;
  final Future<void> answer;

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async {
    if (url.path.endsWith('/held')) await answer;
    return inner.openUrl(method, url);
  }

  @override
  void close({bool force = false}) => inner.close(force: force);

  // Timeouts and other settings dio sets are irrelevant to the mock.
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  // Also mocks HTTP: no request of this file can leave the test host.
  TestWidgetsFlutterBinding.ensureInitialized();

  group('server change', () {
    SessionState linked(String server) => SessionState(
      status: SessionStatus.signedOut,
      lastServer: server,
      pendingSetupToken: (server: server, token: token),
    );

    test("another server drops the connect link's setup token", () async {
      await setUpServices();
      final store = testStore(session: linked('https://a.example'));
      await store.dispatchAndWait(ChangeServerAction('https://b.example'));
      expect(store.state.session.lastServer, 'https://b.example');
      expect(store.state.session.pendingSetupToken, isNull);
      expect(await secureStore.lastServer(), 'https://b.example');
    });

    test('the same server, written another way, keeps it', () async {
      await setUpServices();
      final store = testStore(session: linked('https://a.example/api/'));
      await store.dispatchAndWait(ChangeServerAction('https://a.example'));
      expect(store.state.session.pendingSetupToken?.token, token);
    });

    test('a remote plain-http server is refused before signing out', () async {
      final api = await setUpServices();
      final store = testStore();
      await expectLater(
        store.dispatchAndWait(ChangeServerAction(remoteHttp)),
        httpsRefusal,
      );
      expect(store.state.session.signedIn, isTrue);
      expect(api.callsTo('POST', '/auth/logout'), isEmpty);
      expect(await secureStore.lastServer(), isNot(remoteHttp));
    });
  });

  test('a connect link to a remote plain-http server is refused', () async {
    final api = await setUpServices();
    final store = testStore();
    await expectLater(
      store.dispatchAndWait(
        ConnectLinkAction(server: remoteHttp, token: token),
      ),
      httpsRefusal,
    );
    expect(store.state.session.signedIn, isTrue);
    expect(store.state.session.lastServer, testServer);
    expect(store.state.session.pendingSetupToken, isNull);
    expect(api.callsTo('POST', '/auth/logout'), isEmpty);
    expect(await secureStore.lastServer(), isNot(remoteHttp));
  });

  group('restored at launch', () {
    test('a session on a remote plain-http server is dropped unsent', () async {
      final api = await setUpServices(
        stored: const StoredSession(
          server: remoteHttp,
          token: 'secret-token-never-sent',
          ownerId: 'owner-1',
          email: 'owner@example.com',
        ),
      );
      final store = Store<AppState>(initialState: const AppState());
      realtime = RealtimeController(store);
      await store.dispatchAndWait(BootstrapAction());
      expect(store.state.session.status, SessionStatus.signedOut);
      expect(store.state.session.lastServer, isNull);
      expect(store.state.session.expired, isFalse);
      expect(memorySecure.session, isNull);
      expect(api.server, isNull);
      expect(api.token, isNull);
      expect(api.calls, isEmpty);
    });

    test('a session on a local plain-http server still restores', () async {
      const local = 'http://127.0.0.1:9';
      final api = await setUpServices(
        stored: const StoredSession(
          server: local,
          token: 'local-token',
          ownerId: 'owner-1',
          email: 'owner@example.com',
        ),
      );
      final store = Store<AppState>(initialState: const AppState());
      realtime = RealtimeController(store);
      addTearDown(realtime.stop);
      await store.dispatchAndWait(BootstrapAction());
      expect(store.state.session.signedIn, isTrue);
      expect(store.state.session.lastServer, local);
      expect(api.server, local);
    });
  });

  group('sign-in and owner setup', () {
    testWidgets('a remote plain-http server gets no password', (tester) async {
      final client = await setUpRealClient();
      final store = testStore(signedIn: false);
      await expectLater(
        store.dispatchAndWait(
          SignInAction(
            server: remoteHttp,
            email: 'owner@example.com',
            password: 'correct horse battery',
          ),
        ),
        httpsRefusal,
      );
      await expectLater(
        store.dispatchAndWait(
          SetupOwnerAction(
            server: remoteHttp,
            email: 'owner@example.com',
            password: 'correct horse battery',
            bootstrapToken: token,
          ),
        ),
        httpsRefusal,
      );
      expect(store.state.session.signedIn, isFalse);
      expect(memorySecure.session, isNull);
      expect(client.token, isNull);
    });
  });

  group('sign-out', () {
    late ScriptedApi api;
    late Store<AppState> store;

    Future<void> signedIn() async {
      api = await setUpServices();
      api.configure(server: testServer, token: 'live-token');
      store = testStore();
    }

    void addHook(
      List<Future<void> Function()> list,
      Future<void> Function() hook,
    ) {
      list.add(hook);
      addTearDown(() => list.remove(hook));
    }

    testWidgets(
      'before-hooks run alongside the revocation, with the session still valid',
      (tester) async {
        await signedIn();
        final release = Completer<void>();
        String? tokenInHook;
        final tokenAfter = <String?>[];
        addHook(beforeSignOutHooks, () async {
          tokenInHook = api.token;
          await release.future;
        });
        addHook(signOutHooks, () async => tokenAfter.add(api.token));

        final done = store.dispatchAndWait(SignOutAction());
        await tester.pump();
        expect(tokenInHook, 'live-token');
        // The revocation did not wait for the hook.
        expect(api.callsTo('POST', '/auth/logout'), hasLength(1));
        expect(store.state.session.signedIn, isTrue);
        expect(tokenAfter, isEmpty);

        release.complete();
        await tester.pump();
        await done;
        expect(store.state.session.signedIn, isFalse);
        expect(api.token, isNull);
        expect(tokenAfter, [null]);
      },
    );

    testWidgets(
      'a failing or endless hook neither stops the revocation nor holds sign-out past 3 s',
      (tester) async {
        await signedIn();
        addHook(beforeSignOutHooks, () async => throw StateError('broken'));
        addHook(beforeSignOutHooks, () => Completer<void>().future);

        final done = store.dispatchAndWait(SignOutAction());
        await tester.pump();
        expect(api.callsTo('POST', '/auth/logout'), hasLength(1));
        await tester.pump(const Duration(milliseconds: 2900));
        expect(store.state.session.signedIn, isTrue);
        await tester.pump(const Duration(milliseconds: 200));
        await done;
        expect(store.state.session.signedIn, isFalse);
        expect(api.token, isNull);
      },
    );

    testWidgets(
      "the fence cancels a hook's request still in flight after 3 s",
      (tester) async {
        final client = await setUpRealClient();
        client.configure(server: testServer, token: 'live-token');
        store = testStore();
        final answer = Completer<void>();
        final previous = HttpOverrides.current;
        HttpOverrides.global = _HoldingOverrides(previous!, answer.future);
        addTearDown(() => HttpOverrides.global = previous);
        Object? outcome;
        addHook(beforeSignOutHooks, () async {
          try {
            await client.get('/held');
          } catch (e) {
            outcome = e;
          }
        });

        final done = store.dispatchAndWait(SignOutAction());
        await tester.pump(const Duration(milliseconds: 2900));
        expect(store.state.session.signedIn, isTrue);
        expect(outcome, isNull);
        await tester.pump(const Duration(milliseconds: 200));
        await done;
        expect(store.state.session.signedIn, isFalse);
        expect(client.token, isNull);
        expect(outcome, isA<SessionRequestCancelled>());

        // Its late answer is dropped.
        answer.complete();
        await tester.pump();
        expect(outcome, isA<SessionRequestCancelled>());
      },
    );

    testWidgets('a 401 while signing out does not mark the session expired', (
      tester,
    ) async {
      await signedIn();
      final release = Completer<void>();
      addHook(beforeSignOutHooks, () => release.future);

      final done = store.dispatchAndWait(SignOutAction());
      await tester.pump();
      final expiry = store.dispatchAndWait(
        SignOutAction(expired: true, revoke: false),
      );
      await tester.pump();
      release.complete();
      await tester.pump();
      await done;
      await expiry;
      expect(store.state.session.signedIn, isFalse);
      expect(store.state.session.expired, isFalse);
      expect(store.state.session.lastServer, testServer);
      expect(api.callsTo('POST', '/auth/logout'), hasLength(1));
    });

    testWidgets('an expiry runs only the after-hooks', (tester) async {
      await signedIn();
      var before = 0, after = 0;
      addHook(beforeSignOutHooks, () async => before++);
      addHook(signOutHooks, () async => after++);
      await store.dispatchAndWait(SignOutAction(expired: true, revoke: false));
      expect((before, after), (0, 1));
      expect(store.state.session.expired, isTrue);
      expect(api.callsTo('POST', '/auth/logout'), isEmpty);
    });

    testWidgets('the app ends a voice call on the server before revoking', (
      tester,
    ) async {
      await signedIn();
      final calls = RecordingCalls();
      final previous = VoiceCalls.controller;
      VoiceCalls.controller = calls;
      final before = List.of(beforeSignOutHooks);
      final after = List.of(signOutHooks);
      addTearDown(() {
        VoiceCalls.controller = previous;
        beforeSignOutHooks
          ..clear()
          ..addAll(before);
        signOutHooks
          ..clear()
          ..addAll(after);
      });
      registerSignOutHooks();
      expect(beforeSignOutHooks, hasLength(before.length + 1));
      expect(signOutHooks, hasLength(after.length + 1));

      await store.dispatchAndWait(SignOutAction());
      expect(calls.ended, [(finalize: true, token: 'live-token')]);
      expect(store.state.session.signedIn, isFalse);
    });
  });

  group('shell refresh', () {
    test('inboxError names the inbox failure only', () async {
      final api = await setUpServices();
      final store = testStore();
      api.on(
        'GET /threads/inbox',
        (_) => throw ApiError(status: 503, code: 'maintenance'),
      );
      await store.dispatchAndWait(RefreshShellAction());
      expect(store.state.shell.inboxError, 'maintenance');

      api.on('GET /threads/inbox', (_) => const <Object?>[]);
      api.on(
        'GET /groups',
        (_) => throw ApiError(status: 500, code: 'request_failed'),
      );
      await store.dispatchAndWait(RefreshShellAction());
      expect(store.state.shell.inboxError, isNull);
      expect(store.state.shell.lastError, 'request_failed');
    });
  });
}
