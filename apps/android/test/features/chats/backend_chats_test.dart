// The chats feature against a REAL Lonora server (no API mocks): the shell rows, the unified
// search's payloads, thread prefs (pin/unpin, mark unread/read), custom lists and groups
// (create, open, rename), each read back from the server.
//
// Runs only when LONORA_TEST_CREDS points at a JSON file {server_url, owner_email,
// owner_password} of a disposable test server (docs/android/analysis/lonora-local-runtime.md).
// Never point it at production. What it creates is removed at the end.
import 'dart:convert';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/features/chats/chat_rows.dart';
import 'package:lonora/features/chats/chats_actions.dart';
import 'package:lonora/features/chats/search_feed.dart';
import 'package:lonora/features/chats/search_screen.dart' show fetchSearchPage;
import 'package:lonora/features/groups/group_actions.dart';
import 'package:lonora/state/actions/session_actions.dart';
import 'package:lonora/state/actions/shell_actions.dart';
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

Future<void> _ok(Store<AppState> store, ChatsAction action) async {
  await store.dispatchAndWait(action);
  final failure = action.failure;
  if (failure != null) fail('${action.runtimeType} failed: $failure');
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
    final dir = await Directory.systemTemp.createTemp('lonora_chats_it');
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
    'rows, search, prefs, lists and groups on a real server',
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
      await store.dispatchAndWait(RefreshShellAction());
      expect(store.state.shell.loaded, isTrue);

      // Rows: every agent appears, Lonora (the personal agent) among them.
      var rows = chatRowsOf(store.state);
      expect(rows.where((r) => r.agent?.isPersonal ?? false), hasLength(1));
      expect(
        rows.where((r) => r.isAgent).length,
        store.state.shell.agents.length,
      );

      // Search: the browse feed, then a query, in the shapes the screen reads.
      final browse = await firstSearchPage('', 'all', fetchSearchPage);
      expect(browse.map((s) => s.tab), [
        'chats',
        'messages',
        'tasks',
        'files',
        'other',
      ]);
      final chats = browse.firstWhere((s) => s.tab == 'chats');
      expect(chats.items, isNotEmpty);
      expect(chats.items.first.category, 'chats');
      final messageSection = browse.firstWhere((s) => s.tab == 'messages');
      if (messageSection.items.isNotEmpty) {
        final hit = messageSection.items.first;
        expect(hit.threadId, isNotNull);
        expect(hit.seq, isNotNull);
        final word = hit.snippet
            .split(RegExp(r'\s+'))
            .firstWhere((w) => w.length > 3, orElse: () => hit.snippet);
        final found = await firstSearchPage(word, 'messages', fetchSearchPage);
        expect(found.single.items.map((h) => h.id), contains(hit.id));
      }

      // Prefs: mark a chat unread, then not (server state read back); its read cursor (which
      // only grows) is left where it was.
      final row = rows.firstWhere(
        (r) => r.entry != null && !isArchived(r) && !r.entry!.markedUnread,
      );
      final readBefore = row.entry!.lastReadSeq;
      await _ok(store, ThreadPrefsAction([row], {'marked_unread': true}));
      expect(store.state.shell.entryFor(row.threadId!)!.markedUnread, isTrue);
      await store.dispatchAndWait(RefreshShellAction());
      expect(store.state.shell.entryFor(row.threadId!)!.markedUnread, isTrue);
      await _ok(store, ThreadPrefsAction([row], {'marked_unread': false}));
      expect(store.state.shell.entryFor(row.threadId!)!.markedUnread, isFalse);
      expect(
        store.state.shell.entryFor(row.threadId!)!.lastReadSeq,
        readBefore,
      );

      // «تمييز كمقروءة» on a chat already read to its newest message: the cursor stays.
      final read = chatRowsOf(store.state).where((r) {
        final e = r.entry;
        final last = e?.lastMessage?.seq;
        return e != null && last != null && e.lastReadSeq >= last;
      }).firstOrNull;
      if (read != null) {
        final cursor = read.entry!.lastReadSeq;
        await _ok(store, ReadRowsAction([read]));
        expect(store.state.shell.entryFor(read.threadId!)!.lastReadSeq, cursor);
      }

      // Pin then unpin (another test may hold the three pins: the refusal is the contract).
      if (!isPinned(row)) {
        final pin = ThreadPrefsAction([row], {'pinned': true});
        await store.dispatchAndWait(pin);
        final failure = pin.failure;
        if (failure == null) {
          expect(store.state.shell.entryFor(row.threadId!)!.pinned, isTrue);
          rows = chatRowsOf(store.state);
          expect(rows.first.key, row.key, reason: 'a new pin goes on top');
          await _ok(store, ThreadPrefsAction([row], {'pinned': false}));
          expect(store.state.shell.entryFor(row.threadId!)!.pinned, isFalse);
        } else {
          expect((failure as ApiError).code, 'thread_pin_limit');
        }
      }

      // A custom list with one chat, then removed.
      final listName = 'IT ${DateTime.now().millisecondsSinceEpoch % 100000}';
      final save = SaveChatListAction(name: listName, rows: [row]);
      await _ok(store, save);
      final list = save.saved!;
      expect(list.threadIds, [row.threadId]);
      expect(
        filterRows(
          chatRowsOf(store.state),
          'list:${list.id}',
          store.state.shell.chatLists,
        ).map((r) => r.key),
        [row.key],
      );
      await _ok(store, DeleteChatListAction(list));
      expect(store.state.shell.chatLists.any((l) => l.id == list.id), isFalse);

      // A group: created with its conversation, found again, renamed with its version.
      final members = store.state.shell.orderedAgents
          .take(2)
          .map((a) => a.id)
          .toList();
      final create = CreateGroupAction(
        name: 'Android IT group',
        memberIds: members,
        leadAgentId: members.first,
      );
      await _ok(store, create);
      final group = create.group!;
      try {
        expect(create.threadId, isNotEmpty);
        await store.dispatchAndWait(RefreshShellAction());
        expect(store.state.shell.groups[group.id]?.memberIds, members);
        expect(
          groupThreadId(store.state.shell.groups[group.id]!),
          create.threadId,
        );
        final open = OpenGroupThreadAction(group.id);
        await _ok(store, open);
        expect(open.threadId, create.threadId);
        final fresh = store.state.shell.groups[group.id]!;
        final update = UpdateGroupAction(fresh, {
          ...asJson(fresh.raw['payload']),
          'name': 'Android IT group 2',
        });
        await _ok(store, update);
        expect(update.saved!.name, 'Android IT group 2');
        expect(update.saved!.version, fresh.version + 1);
        // A stale version is refused, never overwritten.
        final stale = UpdateGroupAction(fresh, asJson(fresh.raw['payload']));
        await store.dispatchAndWait(stale);
        expect((stale.failure as ApiError?)?.code, 'version_conflict');
        final rowsNow = chatRowsOf(store.state);
        expect(
          rowsNow.where((r) => r.key == rowKey(ChatRowKind.group, group.id)),
          hasLength(1),
        );
      } finally {
        // Test cleanup only (the app never deletes a group nor its conversation).
        final thread = create.threadId;
        if (thread != null && thread.isNotEmpty) {
          await api.delete('/threads/$thread');
        }
        await api.delete('/groups/${group.id}');
      }
      await store.dispatchAndWait(SignOutAction());
    },
    skip: creds == null ? 'LONORA_TEST_CREDS not set' : false,
    timeout: const Timeout(Duration(minutes: 2)),
  );
}
