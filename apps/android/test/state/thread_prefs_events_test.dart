// What the owner's other devices learn: a `thread.read` event clears the marked dot (its payload
// carries only the read cursor), and a cleared conversation's hidden history never comes back
// from the cached window or the phone's cache. The open chat's collaboration read keeps its
// last answer when it fails.
import 'package:async_redux/async_redux.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/features/conversation/conversation_actions.dart';
import 'package:lonora/state/actions/thread_actions.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';

import '../features/conversation/conversation_harness.dart';

class _MemoryStore implements LocalStore {
  final Map<String, Object?> docs = {};

  @override
  Future<Object?> read(String scope, String name) async => docs['$scope/$name'];

  @override
  Future<void> write(String scope, String name, Object? value) async =>
      value == null
      ? docs.remove('$scope/$name')
      : docs['$scope/$name'] = value;

  @override
  Future<void> clearScope(String scope) async =>
      docs.removeWhere((key, _) => key.startsWith('$scope/'));
}

InboxEntry entry({
  bool marked = false,
  int unread = 0,
  int read = 0,
  int hidden = 0,
}) => InboxEntry.fromJson({
  'thread_id': threadId,
  'agent_id': agentId,
  'last_message': {'id': 'm5', 'seq': 5},
  'unread_count': unread,
  'last_read_seq': read,
  'marked_unread': marked,
  'hidden_before_seq': hidden,
});

void main() {
  late FakeApi fake;
  late _MemoryStore local;

  setUp(() {
    fake = registerFakeApi();
    local = _MemoryStore();
    if (sl.isRegistered<LocalStore>()) sl.unregister<LocalStore>();
    sl.registerSingleton<LocalStore>(local);
  });

  tearDown(() async {
    if (sl.isRegistered<ApiClient>()) await sl.unregister<ApiClient>();
  });

  group('thread.read', () {
    testWidgets('read elsewhere clears the marked dot and the count', (
      tester,
    ) async {
      final store = Store<AppState>(
        initialState: AppState(
          shell: ShellState(inbox: [entry(marked: true, unread: 2, read: 3)]),
        ),
      );
      expect(store.state.shell.unreadTotal, 2);
      store.dispatch(
        ApplyEventAction(
          const LonoraEvent(
            cursor: 1,
            kind: 'thread.read',
            threadId: threadId,
            payload: {'thread_id': threadId, 'last_read_seq': 5},
          ),
        ),
      );
      await tester.pump();
      final e = store.state.shell.entryFor(threadId)!;
      expect(e.markedUnread, isFalse);
      expect(e.unreadCount, 0);
      expect(store.state.shell.unreadTotal, 0);
    });

    testWidgets('a marked dot with nothing new to read goes too', (
      tester,
    ) async {
      final store = Store<AppState>(
        initialState: AppState(
          shell: ShellState(inbox: [entry(marked: true, read: 5)]),
        ),
      );
      expect(store.state.shell.unreadTotal, 1);
      store.dispatch(
        ApplyEventAction(
          const LonoraEvent(
            cursor: 1,
            kind: 'thread.read',
            threadId: threadId,
            payload: {'thread_id': threadId, 'last_read_seq': 5},
          ),
        ),
      );
      await tester.pump();
      expect(store.state.shell.unreadTotal, 0);
    });

    testWidgets('thread.prefs_updated still carries its own marked_unread', (
      tester,
    ) async {
      final store = Store<AppState>(
        initialState: AppState(shell: ShellState(inbox: [entry(read: 5)])),
      );
      store.dispatch(
        ApplyEventAction(
          const LonoraEvent(
            cursor: 1,
            kind: 'thread.prefs_updated',
            threadId: threadId,
            payload: {'thread_id': threadId, 'marked_unread': true},
          ),
        ),
      );
      await tester.pump();
      expect(store.state.shell.entryFor(threadId)!.markedUnread, isTrue);
    });
  });

  group('cleared history', () {
    AppState cleared() {
      final base = signedIn(
        conversationState(
          messages: [
            for (var i = 1; i <= 5; i++)
              message(
                'm$i',
                i,
                i.isOdd ? 'user' : 'assistant',
                'text $i',
                at(i),
              ),
          ],
        ),
      );
      return base.copyWith(
        shell: base.shell.copyWith(inbox: [entry(read: 5, hidden: 5)]),
      );
    }

    testWidgets('an empty newest page leaves nothing of the cleared window', (
      tester,
    ) async {
      final state = cleared();
      fake.answers['GET /threads/$threadId'] = (_) =>
          state.thread(threadId).thread!.raw;
      fake.answers['GET /threads/$threadId/messages'] = (_) => <Object?>[];
      final store = Store<AppState>(initialState: state);
      await store.dispatchAndWait(LoadThreadAction(threadId));
      expect(store.state.thread(threadId).messages, isEmpty);
    });

    testWidgets('a newer message stays; the cached tail never brings the old '
        'ones back', (tester) async {
      final state = cleared();
      fake.answers['GET /threads/$threadId'] = (_) =>
          state.thread(threadId).thread!.raw;
      fake.answers['GET /threads/$threadId/messages'] = (_) => [
        message('m6', 6, 'assistant', 'after the clear', at(7)).raw,
      ];
      final store = Store<AppState>(initialState: state);
      await store.dispatchAndWait(LoadThreadAction(threadId));
      expect(store.state.thread(threadId).messages.map((m) => m.id), ['m6']);

      // The phone's cache of the conversation still holds the old tail.
      final scope = LocalStore.scope('http://127.0.0.1:1', 'owner-1');
      local.docs['$scope/thread_$threadId'] = {
        'thread': state.thread(threadId).thread!.raw,
        'messages': [for (final m in state.thread(threadId).messages) m.raw],
      };
      final fresh = Store<AppState>(
        initialState: state.copyWith(threads: const {}),
      );
      await fresh.dispatchAndWait(RestoreThreadCacheAction(threadId));
      expect(fresh.state.thread(threadId).messages, isEmpty);
    });

    LonoraEvent messageEvent(String kind, Message m) =>
        LonoraEvent(cursor: 1, kind: kind, threadId: threadId, payload: m.raw);

    testWidgets('a late update of a cleared message (a voice note transcript) '
        'never brings it back; a new message shows', (tester) async {
      final state = cleared();
      final store = Store<AppState>(
        initialState: state.withThread(
          withoutCleared(state, state.thread(threadId)),
        ),
      );
      expect(store.state.thread(threadId).messages, isEmpty);
      store.dispatch(
        ApplyEventAction(
          messageEvent(
            'message.updated',
            message('m3', 3, 'user', 'the transcript', at(3)),
          ),
        ),
      );
      await tester.pump();
      expect(store.state.thread(threadId).messages, isEmpty);
      store.dispatch(
        ApplyEventAction(
          messageEvent(
            'message.created',
            message('m6', 6, 'assistant', 'after the clear', at(7)),
          ),
        ),
      );
      await tester.pump();
      expect(store.state.thread(threadId).messages.map((m) => m.id), ['m6']);
      // The debounced shell refresh.
      await tester.pump(const Duration(milliseconds: 700));
    });

    testWidgets('a clear on another device hides the open history at once', (
      tester,
    ) async {
      final base = cleared();
      final store = Store<AppState>(
        initialState: base.copyWith(
          shell: base.shell.copyWith(inbox: [entry(read: 5)]),
        ),
      );
      expect(store.state.thread(threadId).messages, hasLength(5));
      store.dispatch(
        ApplyEventAction(
          const LonoraEvent(
            cursor: 1,
            kind: 'thread.prefs_updated',
            threadId: threadId,
            payload: {
              'thread_id': threadId,
              'last_read_seq': 5,
              'hidden_before_seq': 4,
            },
          ),
        ),
      );
      await tester.pump();
      expect(store.state.shell.entryFor(threadId)!.hiddenBeforeSeq, 4);
      expect(store.state.thread(threadId).messages.map((m) => m.id), ['m5']);
    });
  });

  group('collaboration', () {
    testWidgets(
      'the open session is kept; a failed read keeps the last answer',
      (tester) async {
        final store = Store<AppState>(
          initialState: signedIn(conversationState()),
        );
        fake.answers['GET /threads/$threadId/collaboration'] = (_) => {
          'id': 's1',
          'state': {'status': 'collaborating'},
        };
        await store.dispatchAndWait(LoadCollaborationAction(threadId));
        expect(collaborationSessionOf(store.state.thread(threadId)), 's1');
        fake.answers['GET /threads/$threadId/collaboration'] = (_) =>
            throw ApiError.network();
        await store.dispatchAndWait(LoadCollaborationAction(threadId));
        expect(collaborationSessionOf(store.state.thread(threadId)), 's1');
        fake.answers['GET /threads/$threadId/collaboration'] = (_) => null;
        await store.dispatchAndWait(LoadCollaborationAction(threadId));
        expect(collaborationSessionOf(store.state.thread(threadId)), isNull);
      },
    );

    testWidgets('a group conversation is never asked', (tester) async {
      final base = signedIn(conversationState());
      final t = base.thread(threadId);
      final store = Store<AppState>(
        initialState: base.withThread(
          t.copyWith(
            thread: Thread.fromJson({'id': threadId, 'group_id': 'g1'}),
          ),
        ),
      );
      await store.dispatchAndWait(LoadCollaborationAction(threadId));
      expect(fake.calls, isEmpty);
    });
  });
}
