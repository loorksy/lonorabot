// Lead glue: the files library's path and its route (agent and conversation scopes), one haptic
// when a voice note starts (the composer's hold or the mic's tap), and an older page that did not arrive
// recorded as an error code (also against a real server when LONORA_TEST_CREDS names one).
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/app/router.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/conversation/conversation_composer.dart';
import 'package:lonora/features/files/artifacts_screen.dart';
import 'package:lonora/features/files/files_data.dart';
import 'package:lonora/features/voice/voice_note_button.dart';
import 'package:lonora/state/actions/base.dart';
import 'package:lonora/state/actions/thread_actions.dart';
import 'package:lonora/state/app_state.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../features/market/wpf_harness.dart';

class _Recorder implements VoiceNoteRecorder {
  @override
  Future<PermissionStatus> permission() async => PermissionStatus.granted;
  @override
  Future<void> start(String path) async {}
  @override
  Future<String?> stop() async => null;
  @override
  Future<void> cancel() async {}
  @override
  Future<void> pause() async {}
  @override
  Future<void> resume() async {}
  @override
  Stream<double> levels() => const Stream.empty();
  @override
  Future<void> dispose() async {}
}

void main() {
  setUpAll(setUpWpf);
  setUp(resetWpf);

  group('files library route', () {
    test('Routes.artifacts scopes', () {
      expect(Routes.artifacts(), '/files');
      expect(Routes.artifacts(threadId: 't1'), '/files?thread=t1');
      expect(Routes.artifacts(agentId: 'a1'), '/files?agent=a1');
      expect(
        Routes.artifacts(threadId: 't1', agentId: 'a1'),
        '/files?thread=t1&agent=a1',
      );
    });

    testWidgets('/files passes the conversation and the agent', (tester) async {
      await tester.pumpWidget(const SizedBox());
      final router = buildRouter(wpfStore());
      addTearDown(router.dispose);
      final files = router.configuration.routes.whereType<GoRoute>().firstWhere(
        (r) => r.path == '/files',
      );
      final uri = Uri.parse(Routes.artifacts(threadId: 't1', agentId: 'a1'));
      final screen = files.builder!(
        tester.element(find.byType(SizedBox)),
        GoRouterState(
          router.configuration,
          uri: uri,
          matchedLocation: '/files',
          fullPath: '/files',
          pathParameters: const {},
          pageKey: const ValueKey('files'),
        ),
      ) as ArtifactsScreen;
      expect(screen.threadId, 't1');
      expect(screen.agentId, 'a1');
    });
  });

  testWidgets('a voice note starts with one haptic: the hold\'s, or the '
      'mic tap\'s light one', (tester) async {
    final haptics = <Object?>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'HapticFeedback.vibrate') {
          haptics.add(call.arguments);
        }
        return null;
      },
    );
    VoiceNoteButton.recorderFactory = _Recorder.new;
    VoiceNoteButton.recordingsDir = () async => Directory.systemTemp.path;
    await pumpWpf(
      tester,
      const Scaffold(
        body: Align(
          alignment: Alignment.bottomCenter,
          child: ConversationComposer(threadId: 't-gold'),
        ),
      ),
      locale: 'en',
    );
    // A long press on the empty composer starts the note.
    final gesture = await tester.startGesture(
      tester.getCenter(find.byType(EditableText)),
    );
    await tester.pump(const Duration(milliseconds: 600));
    await tester.pump();
    // Every haptic counts: the composer's hold gives the only one.
    expect(haptics, ['HapticFeedbackType.mediumImpact']);
    // Slide toward the start: cancelled, nothing sent.
    await gesture.moveBy(const Offset(-60, 0));
    await gesture.moveBy(const Offset(-60, 0));
    await tester.pump();
    await gesture.up();
    await tester.pumpAndSettle();
    // The mic's tap records hands-free with one light haptic.
    haptics.clear();
    await tester.tap(
      find.byWidgetPredicate(
        (w) => w is LnTappable && w.semanticLabel == 'Voice message',
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(haptics, ['HapticFeedbackType.lightImpact']);
    await tester.pumpAndSettle();
    await unmount(tester);
  });

  group('LoadOlderAction', () {
    AppState withHistory() => wpfStore().state.withThread(
      ThreadState(
        threadId: 't1',
        hasOlder: true,
        loaded: true,
        messages: [
          Message.fromJson(const {
            'id': 'm-50',
            'thread_id': 't1',
            'seq': 50,
            'role': 'owner',
            'content': 'hi',
          }),
        ],
      ),
    );

    test('a page that did not arrive is an error code', () async {
      final store = wpfStore();
      store.dispatch(_Seed(withHistory()));
      fakeApi.on(
        'GET /threads/t1/messages',
        (_, _) => throw ApiError(status: 503, code: 'service_unavailable'),
      );
      final failed = LoadOlderAction('t1');
      await store.dispatchAndWait(failed);
      expect(failed.errorCode, 'service_unavailable');
      expect(store.state.thread('t1').loadingOlder, isFalse);
      expect(store.state.thread('t1').hasOlder, isTrue);

      fakeApi.on(
        'GET /threads/t1/messages',
        (_, query) => [
          {
            'id': 'm-49',
            'thread_id': 't1',
            'seq': 49,
            'role': 'owner',
            'content': 'earlier',
          },
        ],
      );
      final ok = LoadOlderAction('t1');
      await store.dispatchAndWait(ok);
      expect(ok.errorCode, isNull);
      expect(store.state.thread('t1').messages.first.seq, 49);

      // A short page ended the history: nothing more is asked for, and no code either.
      final none = LoadOlderAction('t1');
      await store.dispatchAndWait(none);
      expect(none.errorCode, isNull);
      expect(fakeApi.callsTo('GET', '/threads/t1/messages'), hasLength(2));
    });
  });

  // Against the disposable local server named by LONORA_TEST_CREDS (reads only; the session
  // this test opens is logged out at the end).
  final credsPath = Platform.environment['LONORA_TEST_CREDS'];
  final creds = credsPath != null && File(credsPath).existsSync()
      ? asJson(jsonDecode(File(credsPath).readAsStringSync()))
      : null;
  test('real server: older pages and the agent\'s files', () async {
    HttpOverrides.global = null;
    final real = ApiClient(userAgent: 'Lonora-Android/test')
      ..configure(server: asStr(creds!['server_url']));
    final login = asJson(
      await real.post('/auth/mobile/login', {
        'email': asStr(creds['owner_email']),
        'password': asStr(creds['owner_password']),
      }),
    );
    real.configure(
      server: asStr(creds['server_url']),
      token: asStr(login['token']),
    );
    await registerServices(
      apiClient: real,
      local: LocalStore.at(Directory.systemTemp.createTempSync('glue')),
      prefs: await SharedPreferences.getInstance(),
      info: const AppInfo(
        version: '1.0.0',
        buildNumber: '1',
        packageName: 'ai.lonora.android',
      ),
    );
    try {
      // A conversation's newest message, then the page before it.
      final inbox = asJsonList(await real.get('/threads/inbox'));
      final row = inbox.firstWhere(
        (r) => (asInt(asJson(r['last_message'])['seq']) ?? 0) > 1,
      );
      final thread = asStr(row['thread_id']);
      final newest = asJsonList(
        await real.get('/threads/$thread/messages', query: {'limit': 1}),
      ).map(Message.fromJson).toList();
      final store = wpfStore();
      store.dispatch(
        _Seed(
          store.state.withThread(
            ThreadState(
              threadId: thread,
              hasOlder: true,
              loaded: true,
              messages: newest,
            ),
          ),
        ),
      );
      final ok = LoadOlderAction(thread);
      await store.dispatchAndWait(ok);
      expect(ok.errorCode, isNull);
      expect(
        store.state.thread(thread).messages.first.seq,
        lessThan(newest.single.seq),
      );

      store.dispatch(
        _Seed(
          store.state.withThread(
            ThreadState(
              threadId: 'no-such-thread',
              hasOlder: true,
              loaded: true,
              messages: newest,
            ),
          ),
        ),
      );
      final missing = LoadOlderAction('no-such-thread');
      await store.dispatchAndWait(missing);
      expect(missing.errorCode, 'thread_not_found');

      // The server's agent filter is by the file's own agent only; the library's agent
      // scope also counts the files of the agent's conversations (their rows carry no agent).
      final agent = asStr(row['agent_id']);
      final all = await fetchArtifacts();
      final own = asJsonList(
        await real.get('/artifacts', query: {'agent_id': agent}),
      ).map((j) => asStr(j['id']));
      expect(
        all.where((r) => r.agentId == agent).map((r) => r.id),
        containsAll(own),
      );
    } finally {
      await real.post('/auth/logout');
    }
  }, skip: creds == null ? 'LONORA_TEST_CREDS not set' : false);
}

class _Seed extends AppAction {
  _Seed(this.value);
  final AppState value;
  @override
  AppState reduce() => value;
}
