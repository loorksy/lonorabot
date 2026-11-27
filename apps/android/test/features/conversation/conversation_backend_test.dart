// The conversation's own server calls against a REAL Lonora server (no API mocks): files of a
// thread, upload + send with attachment_ids, the streamed reply handed over to the canonical
// message in the transcript model, an `around` landing, web search toggle, reactions, turning a
// message into a task (cancelled again when still running), and a refused run control recorded
// as an error code.
//
// Runs only when LONORA_TEST_CREDS points at a JSON file {server_url, owner_email,
// owner_password} of a disposable test server. Never point it at production.
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
import 'package:lonora/features/conversation/conversation_actions.dart';
import 'package:lonora/features/conversation/conversation_timeline.dart';
import 'package:lonora/state/actions/session_actions.dart';
import 'package:lonora/state/actions/thread_actions.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _MemorySecureStore extends SecureStore {
  _MemorySecureStore() : super(const FlutterSecureStorage());
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

Future<T> _waitFor<T>(
  Store<AppState> store,
  T? Function(AppState s) probe, {
  Duration timeout = const Duration(seconds: 60),
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
  late Directory dir;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    HttpOverrides.global = null; // real network for this test
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('ai.lonora.android/platform'),
          (call) async => null,
        );
    SharedPreferences.setMockInitialValues({});
    dir = await Directory.systemTemp.createTemp('lonora_conv');
    await registerServices(
      apiClient: ApiClient(userAgent: 'Lonora-Android/test'),
      secure: _MemorySecureStore(),
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
    'conversation actions against the real server',
    () async {
      final store = Store<AppState>(initialState: const AppState());
      realtime = RealtimeController(store);
      api.onUnauthorized = () => handleUnauthorized(store);

      await store.dispatchAndWait(
        SignInAction(
          server: asStr(creds!['server_url']),
          email: asStr(creds['owner_email']),
          password: asStr(creds['owner_password']),
        ),
      );
      expect(store.state.session.signedIn, isTrue);
      await _waitFor(
        store,
        (s) => s.connection == StreamStatus.connected ? true : null,
      );
      await _waitFor(
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
      await store.dispatchAndWait(LoadThreadArtifactsAction(threadId));
      expect(
        store.state.thread(threadId).side[artifactsSideKey],
        isA<List<dynamic>>(),
      );

      // Upload a file the way the composer does, then send it with the text.
      final file = File('${dir.path}/note.txt')
        ..writeAsStringSync('Android conversation attachment');
      final uploaded = asJson(
        await api.upload(
          '/artifacts/upload',
          filePath: file.path,
          fileName: 'note.txt',
          mimeType: 'text/plain',
          fields: {'thread_id': threadId},
        ),
      );
      final artifactId = asStr(uploaded['id']);
      expect(artifactId, isNotEmpty);
      expect(asJson(uploaded['payload'])['name'], 'note.txt');
      store.dispatch(AddThreadArtifactAction(threadId, uploaded));

      final text = 'Conversation test ${DateTime.now().microsecondsSinceEpoch}';
      final send = SendMessageAction(threadId, {
        'content': text,
        'attachment_ids': [artifactId],
      });
      await store.dispatchAndWait(send);
      final mine = store.state
          .thread(threadId)
          .messages
          .firstWhere((m) => m.clientNonce == send.nonce);
      expect(mine.attachmentIds, [artifactId]);

      final reply = await _waitFor(
        store,
        (s) => s
            .thread(threadId)
            .messages
            .where((m) => m.fromAgent && m.seq > mine.seq)
            .firstOrNull,
      );
      // Wait for the run to settle, then the transcript has no preview left for it.
      await _waitFor(
        store,
        (s) =>
            s
                .thread(threadId)
                .runs
                .values
                .any((r) => r.inputSeq == mine.seq && r.isTerminal)
            ? true
            : null,
      );
      final items = buildTimeline(thread: store.state.thread(threadId));
      expect(items.whereType<PreviewItem>(), isEmpty);
      expect(
        items.whereType<MessageItem>().map((i) => i.message.id),
        containsAll([mine.id, reply.id]),
      );

      // The thread's files now include the upload.
      await store.dispatchAndWait(LoadThreadArtifactsAction(threadId));
      expect(
        asJsonList(store.state.thread(threadId).side[artifactsSideKey])
            .map((a) => a['id']),
        contains(artifactId),
      );
      // The test's file goes again, so runs leave no files behind.
      await api.delete('/artifacts/$artifactId');

      // Land around the owner's message.
      await store.dispatchAndWait(LoadThreadAction(threadId, around: mine.seq));
      expect(store.state.thread(threadId).focusSeq, mine.seq);
      expect(
        store.state.thread(threadId).messages.map((m) => m.seq),
        contains(mine.seq),
      );
      await store.dispatchAndWait(LoadNewestAction(threadId));
      expect(store.state.thread(threadId).focusSeq, isNull);

      // Web search on and off.
      final on = ToggleWebSearchAction(threadId, true);
      await store.dispatchAndWait(on);
      expect(on.errorCode, isNull);
      expect(store.state.thread(threadId).thread!.webSearch, isTrue);
      final off = ToggleWebSearchAction(threadId, false);
      await store.dispatchAndWait(off);
      expect(store.state.thread(threadId).thread!.webSearch, isFalse);

      // A quick reaction, then its removal (the screen's action records refusals).
      final react = ConversationReactionAction(
        threadId: threadId,
        messageId: reply.id,
        emoji: '👍',
      );
      await store.dispatchAndWait(react);
      expect(react.errorCode, isNull);
      expect(
        store.state
            .thread(threadId)
            .messages
            .firstWhere((m) => m.id == reply.id)
            .reactions
            .map((r) => (r.reactor, r.emoji)),
        contains(('owner', '👍')),
      );
      final unreact = ConversationReactionAction(
        threadId: threadId,
        messageId: reply.id,
      );
      await store.dispatchAndWait(unreact);
      expect(unreact.errorCode, isNull);
      expect(
        store.state
            .thread(threadId)
            .messages
            .firstWhere((m) => m.id == reply.id)
            .reactions
            .where((r) => r.reactor == 'owner'),
        isEmpty,
      );

      // «تحويل إلى مهمة».
      final task = CreateTaskFromMessageAction(
        threadId: threadId,
        agentId: agent.id,
        message: mine,
      );
      await store.dispatchAndWait(task);
      expect(task.errorCode, isNull);
      // Leave nothing running behind: cancel the task while it can still be cancelled (the
      // scripted model usually completes it at once; a finished task stays as a record).
      final created = asJsonList(
        await api.get('/tasks', query: {'agent_id': agent.id}),
      ).where((t) => t['title'] == mine.content).firstOrNull;
      expect(created, isNotNull);
      if (created!['can_cancel'] == true) {
        await api.post('/tasks/control', {
          'task_id': created['id'],
          'action': 'cancel',
          'expected_version': created['version'],
        });
      }

      // A finished run cannot be retried: the refusal is recorded, never thrown.
      final finished = store.state
          .thread(threadId)
          .runs
          .values
          .firstWhere((r) => r.inputSeq == mine.seq && r.isTerminal);
      final retry = ConversationRunControlAction(finished.id, 'retry');
      await store.dispatchAndWait(retry);
      expect(retry.errorCode, isNotNull);

      await store.dispatchAndWait(SignOutAction());
      expect(store.state.session.signedIn, isFalse);
    },
    skip: creds == null
        ? 'set LONORA_TEST_CREDS to a disposable test server creds file'
        : false,
    timeout: const Timeout(Duration(minutes: 3)),
  );
}
