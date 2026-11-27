// WP-A1 against a REAL Lonora server (no API mocks): the server step's probe, a refused
// sign-in, sign-in, the account/notification/voice/about reads these screens make, the
// preference writes they send (each restored to its first value in the same test), sign-out.
//
// Runs only when LONORA_TEST_CREDS points at a JSON file {server_url, owner_email,
// owner_password} of a disposable test server (docs/android/analysis/lonora-local-runtime.md).
// Never point it at production. The owner's password is never changed.
import 'dart:convert';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/features/auth/server_check.dart';
import 'package:lonora/features/me/me_data.dart';
import 'package:lonora/features/settings/settings_core_data.dart';
import 'package:lonora/state/actions/session_actions.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../settings_core/feature_harness.dart' show MemorySecureStore;

void main() {
  final credsPath = Platform.environment['LONORA_TEST_CREDS'];
  final creds = credsPath != null && File(credsPath).existsSync()
      ? asJson(jsonDecode(File(credsPath).readAsStringSync()))
      : null;
  late MemorySecureStore secure;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    HttpOverrides.global = null; // real network for this test
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('ai.lonora.android/platform'),
          (call) async => null,
        );
    SharedPreferences.setMockInitialValues({});
    final dir = await Directory.systemTemp.createTemp('lonora_a1_it');
    secure = MemorySecureStore();
    await registerServices(
      apiClient: ApiClient(userAgent: 'Lonora-Android/test'),
      secure: secure,
      local: LocalStore.at(dir),
      prefs: await SharedPreferences.getInstance(),
      info: const AppInfo(
        version: '1.0.0',
        buildNumber: '1',
        packageName: 'ai.lonora.android',
      ),
    );
  });

  test(
    'server probe, refused and accepted sign-in, account reads and writes, sign-out',
    () async {
      final server = checkServerAddress(asStr(creds!['server_url'])).server!;
      final email = asStr(creds['owner_email']);
      final password = asStr(creds['owner_password']);
      final store = Store<AppState>(
        initialState: const AppState(
          session: SessionState(status: SessionStatus.signedOut),
        ),
      );
      realtime = RealtimeController(store);
      api.onUnauthorized = () => handleUnauthorized(store);

      // The server step: a Lonora server that already has its owner.
      expect(await probeOwnerInitialized(server), isTrue);
      // Not Lonora: a path without the route.
      await expectLater(
        api.probe(server, '/onboarding-missing'),
        throwsA(isA<ApiError>()),
      );

      // A wrong password is refused with the code sign-in shows (one attempt: the
      // password bucket is 10 a minute).
      await expectLater(
        store.dispatchAndWait(
          SignInAction(
            server: server,
            email: email,
            password: '$password-wrong',
          ),
        ),
        throwsA(
          isA<ApiError>()
              .having((e) => e.status, 'status', 401)
              .having((e) => e.code, 'code', 'unauthorized'),
        ),
      );
      expect(store.state.session.signedIn, isFalse);

      await store.dispatchAndWait(
        SignInAction(server: server, email: email, password: password),
      );
      expect(store.state.session.signedIn, isTrue);
      expect(store.state.session.owner!.email, email);
      expect(secure.session?.expiresAt, isNotNull);

      // Account reads.
      final profile = await fetchOwnerProfile();
      expect(['notify', 'message', 'call'], contains(profile.channel));
      expect(profile.reachMe.containsKey('timezone'), isTrue);
      final usage = await fetchUsageSummary();
      expect(usage.input, greaterThanOrEqualTo(0));
      final attention = await fetchAttentionPolicy();
      expect(['ar', 'en'], contains(attention.locale));
      final voice = await fetchVoiceStatus();
      expect(voice.transport, 'gpt_live');
      final version = await fetchServerVersion();
      expect(version.version, isNotEmpty);

      // Form of address: only the field sent changes; restored afterwards.
      final changed = await saveOwnerPreferences({'address': 'A1 test'});
      expect(changed.address, 'A1 test');
      expect(changed.name, profile.name);
      final restored = await saveOwnerPreferences({'address': profile.address});
      expect(restored.address, profile.address);

      // Quiet hours as the notifications page sends them (no `enabled`); restored.
      final quiet = await saveOwnerPreferences({
        'reach_me': reachMeWith(profile.reachMe, {
          'quiet_start_minute': 22 * 60,
          'quiet_end_minute': 8 * 60,
          'quiet_start_hour': 22,
          'quiet_end_hour': 8,
        }),
      });
      expect(quiet.quietStartMinute, 22 * 60);
      expect(quiet.quietEndMinute, 8 * 60);
      expect(quiet.channel, profile.channel);
      final back = await saveOwnerPreferences({
        'reach_me': reachMeWith(profile.reachMe, {}),
      });
      expect(back.quietStartMinute, profile.quietStartMinute);
      expect(back.quietEndMinute, profile.quietEndMinute);

      // Time zone as the account page sends it (the whole policy, no `enabled`); an
      // unknown zone is refused with the code the page shows; restored.
      final otherZone = profile.timeZone == 'Asia/Riyadh'
          ? 'Europe/London'
          : 'Asia/Riyadh';
      final zoned = await saveOwnerPreferences({
        'reach_me': reachMeWith(profile.reachMe, {'timezone': otherZone}),
      });
      expect(zoned.timeZone, otherZone);
      expect(zoned.channel, profile.channel);
      await expectLater(
        saveOwnerPreferences({
          'reach_me': reachMeWith(profile.reachMe, {
            'timezone': 'Mars/Olympus',
          }),
        }),
        throwsA(
          isA<ApiError>().having((e) => e.code, 'code', 'invalid_timezone'),
        ),
      );
      final zoneBack = await saveOwnerPreferences({
        'reach_me': reachMeWith(profile.reachMe, {}),
      });
      expect(zoneBack.timeZone, profile.timeZone);

      // «Per agent»: delivery rules keyed by agent id.
      final rules = await fetchAgentAlertRules();
      for (final rule in rules.values) {
        expect(asJson(rule).containsKey('in_app'), isTrue);
      }

      // Confirmed-opportunity alerts; restored.
      final flipped = await saveAttentionPolicy(
        AttentionPolicy(
          opportunities: !attention.opportunities,
          informational: attention.informational,
          locale: attention.locale,
        ),
      );
      expect(flipped.opportunities, !attention.opportunities);
      final policyBack = await saveAttentionPolicy(attention);
      expect(policyBack.opportunities, attention.opportunities);

      // Sign-out revokes the session on the server.
      final token = api.token;
      await store.dispatchAndWait(SignOutAction());
      expect(store.state.session.status, SessionStatus.signedOut);
      expect(secure.session, isNull);
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
    timeout: const Timeout(Duration(minutes: 2)),
  );
}
