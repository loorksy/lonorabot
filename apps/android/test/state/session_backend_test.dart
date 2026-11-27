// Sign-out against a REAL Lonora server, with the app's hooks: a before-sign-out hook's
// request races `POST /auth/logout` (as on Expo); whichever wins, sign-out completes, is not
// taken for an expiry, and the session is revoked. Uses only sign-in, `GET /owner/profile`,
// `GET /auth/session` and `POST /auth/logout`.
//
// Runs only when LONORA_TEST_CREDS points at a JSON file {server_url, owner_email,
// owner_password} of a disposable test server. Never point it at production.
import 'dart:convert';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/app/teardown.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/state/actions/session_actions.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../features/settings_core/feature_harness.dart' show MemorySecureStore;

void main() {
  final credsPath = Platform.environment['LONORA_TEST_CREDS'];
  final creds = credsPath != null && File(credsPath).existsSync()
      ? asJson(jsonDecode(File(credsPath).readAsStringSync()))
      : null;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    HttpOverrides.global = null; // real network for this test
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('ai.lonora.android/platform'),
          (call) async => null,
        );
    SharedPreferences.setMockInitialValues({});
    await registerServices(
      apiClient: ApiClient(userAgent: 'Lonora-Android/test'),
      secure: MemorySecureStore(),
      local: LocalStore.at(await Directory.systemTemp.createTemp('lonora_s')),
      prefs: await SharedPreferences.getInstance(),
      info: const AppInfo(
        version: '1.0.0',
        buildNumber: '1',
        packageName: 'ai.lonora.android',
      ),
    );
  });

  test(
    'before-sign-out hooks run on a live session, then it is revoked',
    () async {
      final server = asStr(creds!['server_url']);
      expect(serverAllowed(server), isTrue);
      final store = Store<AppState>(
        initialState: const AppState(
          session: SessionState(status: SessionStatus.signedOut),
        ),
      );
      realtime = RealtimeController(store);
      api.onUnauthorized = () => handleUnauthorized(store);
      // The app's own hooks (the voice call: none runs, so nothing is sent).
      registerSignOutHooks();
      final answers = <Object?>[];
      Future<void> probe() async {
        try {
          await api.get('/owner/profile');
          answers.add('ok');
        } on ApiError catch (e) {
          answers.add(e.status);
        }
      }

      beforeSignOutHooks.add(probe);
      addTearDown(() => beforeSignOutHooks.remove(probe));

      await store.dispatchAndWait(
        SignInAction(
          server: server,
          email: asStr(creds['owner_email']),
          password: asStr(creds['owner_password']),
        ),
      );
      expect(store.state.session.signedIn, isTrue);
      final token = api.token;

      await store.dispatchAndWait(SignOutAction());
      expect(answers.single, anyOf('ok', 401));
      expect(store.state.session.status, SessionStatus.signedOut);
      expect(store.state.session.expired, isFalse);
      expect(api.token, isNull);

      final check = await HttpClient()
          .getUrl(Uri.parse('$server/api/auth/session'))
          .then((r) {
            r.headers.set('authorization', 'Bearer $token');
            return r.close();
          });
      expect(check.statusCode, 401);
      await check.drain<void>();
    },
    skip: creds == null ? 'LONORA_TEST_CREDS not set' : false,
    timeout: const Timeout(Duration(minutes: 1)),
  );
}
