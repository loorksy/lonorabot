// End-to-end check of the core client stack against a REAL Lonora server (no mocks of the API):
// sign-in, realtime feed, conversation load, optimistic send with nonce, streamed reply via the
// ported stream reducer, canonical message merge, outbox acknowledgement, sign-out.
//
// Runs only when LONORA_TEST_CREDS points at a JSON file {server_url, owner_email,
// owner_password} of a disposable test server (see docs/android/analysis/lonora-local-runtime.md).
// Never point it at production.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/state/actions/session_actions.dart';
import 'package:lonora/state/actions/thread_actions.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The real client, refusing any order: this flow must never reach the broker.
class NoOrderApiClient extends ApiClient {
  NoOrderApiClient() : super(userAgent: 'Lonora-Android/test');

  static const _order = '/trading/execute';

  @override
  Future<dynamic> post(String path, [Object? body]) {
    if (path.contains(_order)) throw StateError('order attempted: $path');
    return super.post(path, body);
  }

  @override
  Future<dynamic> postWithin(String path, Object body, Duration timeout) {
    if (path.contains(_order)) throw StateError('order attempted: $path');
    return super.postWithin(path, body, timeout);
  }
}

class MemorySecureStore extends SecureStore {
  MemorySecureStore() : super(const FlutterSecureStorage());
  StoredSession? session;
  @override
  Future<StoredSession?> readSession() async => session;
  @override
  Future<void> writeSession(StoredSession s) async => session = s;
  @override
  Future<void> clearSession() async => session = null;
  @override
  Future<String?> lastServer() async => session?.server;
  @override
  Future<String?> lastEmail() async => session?.email;
  @override
  Future<void> rememberServer(String server) async {}
}

Future<T> waitFor<T>(
  Store<AppState> store,
  T? Function(AppState s) probe, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  final now = probe(store.state);
  if (now != null) return now;
  final completer = Completer<T>();
  late StreamSubscription<AppState> sub;
  sub = store.onChange.listen((s) {
    final v = probe(s);
    if (v != null && !completer.isCompleted) {
      completer.complete(v);
      sub.cancel();
    }
  });
  return completer.future.timeout(
    timeout,
    onTimeout: () {
      sub.cancel();
      throw TimeoutException('condition not reached');
    },
  );
}

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
    final dir = await Directory.systemTemp.createTemp('lonora_it');
    await registerServices(
      apiClient: NoOrderApiClient(),
      secure: MemorySecureStore(),
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
    'sign in, live feed, send, streamed reply, sign out',
    () async {
      final server = asStr(creds!['server_url']);
      final store = Store<AppState>(initialState: const AppState());
      realtime = RealtimeController(store);
      api.onUnauthorized = () => handleUnauthorized(store);
      final kinds = <String>[];
      final sub = realtime.events.listen((LonoraEvent e) => kinds.add(e.kind));

      await store.dispatchAndWait(
        SignInAction(
          server: server,
          email: asStr(creds['owner_email']),
          password: asStr(creds['owner_password']),
        ),
      );
      expect(store.state.session.signedIn, isTrue);

      await waitFor(
        store,
        (s) => s.connection == StreamStatus.connected ? true : null,
      );
      await waitFor(
        store,
        (s) => s.shell.loaded && s.shell.agents.isNotEmpty ? true : null,
      );

      final agent = store.state.shell.orderedAgents.firstWhere(
        (a) => !a.paused,
      );
      final ensure = EnsureAgentThreadAction(agent.id);
      await store.dispatchAndWait(ensure);
      final threadId = ensure.threadId!;
      await store.dispatchAndWait(LoadThreadAction(threadId));
      expect(store.state.thread(threadId).loaded, isTrue);

      final text =
          'Android integration ${DateTime.now().microsecondsSinceEpoch}';
      final send = SendMessageAction(threadId, {'content': text});
      final sending = store.dispatchAndWait(send);
      // Optimistic entry exists while the request is in flight.
      expect(store.state.outbox.any((o) => o.nonce == send.nonce), isTrue);
      await sending;
      expect(store.state.outbox.any((o) => o.nonce == send.nonce), isFalse);
      final mine = store.state
          .thread(threadId)
          .messages
          .where((m) => m.clientNonce == send.nonce)
          .toList();
      expect(mine, hasLength(1));
      expect(mine.single.content, text);

      // The scripted model streams the reply; the canonical message then arrives by event.
      final reply = await waitFor(
        store,
        (s) => s
            .thread(threadId)
            .messages
            .where(
              (m) =>
                  m.fromAgent &&
                  m.seq > mine.single.seq &&
                  m.content.contains(text),
            )
            .firstOrNull,
        timeout: const Duration(seconds: 60),
      );
      expect(reply.content, contains(text));
      expect(
        kinds,
        containsAll([
          'run.queued',
          'run.reply_started',
          'run.delta',
          'run.reply_committed',
          'message.created',
        ]),
      );
      final streams = store.state
          .thread(threadId)
          .streams
          .values
          .where((st) => st.inputSeq == mine.single.seq)
          .toList();
      expect(streams, isNotEmpty);
      expect(streams.first.phase, 'committed');
      expect(streams.first.text.trim(), isNotEmpty);

      // Idempotent retry with the same nonce must not create a second message.
      await store.dispatchAndWait(
        SendMessageAction(threadId, {'content': text}, nonce: send.nonce),
      );
      expect(
        store.state
            .thread(threadId)
            .messages
            .where((m) => m.clientNonce == send.nonce),
        hasLength(1),
      );

      await store.dispatchAndWait(SignOutAction());
      expect(store.state.session.signedIn, isFalse);
      await sub.cancel();
    },
    skip: creds == null
        ? 'set LONORA_TEST_CREDS to a disposable test server creds file'
        : false,
    timeout: const Timeout(Duration(minutes: 3)),
  );
}
