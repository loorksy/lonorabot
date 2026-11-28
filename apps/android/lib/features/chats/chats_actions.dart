// The chat list's server actions, shared with Web and the Expo app (apps/mobile/lib/lists-api.ts,
// lists-state.tsx, selection.tsx, list-sheets.tsx, groups.ts): conversation state
// (`POST /threads/prefs`, `/read`, `/read-all`, `/clear`, `PUT /threads/settings`), custom lists
// (`/chat-lists`) and opening a row's canonical conversation. Each action keeps its failure in
// [ChatsAction.failure] for the screen's toast; the inbox is patched with the server's answer.
import 'dart:async';

import 'package:async_redux/async_redux.dart' show NonReentrant;

import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../state/actions/base.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/actions/thread_actions.dart' show withoutCleared;
import '../../state/app_state.dart';
import 'chat_rows.dart';

/// Base of the chat-list actions: [run] does the work; a failure is kept, never thrown.
abstract class ChatsAction extends AppAction {
  Object? failure;

  Future<AppState?> run();

  @override
  Future<AppState?> reduce() async {
    try {
      return await run();
    } on SessionRequestCancelled {
      return null;
    } catch (error) {
      failure = error;
      return null;
    }
  }

  /// A row's canonical conversation for its prefs and lists: an agent with none gets it now; a
  /// group without a known one is skipped ('') — nothing is created as a side effect of a list
  /// action (lists-api.ts:28-34 `ensureThread`).
  Future<String> ensureThread(ChatRow row) async {
    final known = row.threadId;
    if (known != null && known.isNotEmpty) return known;
    if (!row.isAgent) return '';
    final thread = asJson(
      await apiClient.post(
        '/agents/${Uri.encodeComponent(row.id)}/conversation',
      ),
    );
    return asStr(thread['id']);
  }

  /// The conversation a row opens: [ensureThread], and for a group its conversation read
  /// from the group, found among the threads, or created (groups.ts:8-16 `conversation`).
  Future<String> openThread(ChatRow row) =>
      row.isGroup && (row.threadId ?? '').isEmpty
      ? resolveGroupThread(row.id, name: row.name)
      : ensureThread(row);

  Future<String> resolveGroupThread(String groupId, {String name = ''}) async {
    final group = Group.fromJson(
      asJson(await apiClient.get('/groups/${Uri.encodeComponent(groupId)}')),
    );
    final stored = groupThreadId(group);
    if (stored != null && stored.isNotEmpty) return stored;
    final threads =
        asJsonList(await apiClient.get('/threads'))
            .map(Thread.fromJson)
            .where((t) => t.groupId == groupId)
            .toList()
          ..sort(
            (a, b) => (a.createdAt ?? DateTime(0)).compareTo(
              b.createdAt ?? DateTime(0),
            ),
          );
    if (threads.isNotEmpty) return threads.first.id;
    final created = asJson(
      await apiClient.post('/threads', {
        'group_id': groupId,
        'title': group.name.isNotEmpty ? group.name : name,
      }),
    );
    return asStr(created['id']);
  }

  /// The inbox with each returned `ThreadPrefs` merged in order (inbox.ts `mergePrefs`).
  AppState mergePrefs(List<Json> prefs) {
    if (prefs.isEmpty) return state;
    final byThread = <String, List<Json>>{};
    for (final p in prefs) {
      (byThread[asStr(p['thread_id'])] ??= []).add(p);
    }
    final inbox = [
      for (final e in state.shell.inbox)
        (byThread[e.threadId] ?? const <Json>[]).fold(
          e,
          (entry, p) => entry.withPrefs(p),
        ),
    ];
    return state.copyWith(shell: state.shell.copyWith(inbox: inbox));
  }
}

/// Opens a row: the id of its canonical conversation in [threadId].
class OpenRowAction extends ChatsAction {
  OpenRowAction(this.row);
  final ChatRow row;
  String? threadId;

  @override
  Future<AppState?> run() async {
    threadId = await openThread(row);
    if (row.threadId == null) dispatch(RefreshShellAction());
    return null;
  }
}

/// A group's conversation (group page «فتح محادثة المجموعة», created group, share picker).
class OpenGroupThreadAction extends ChatsAction {
  OpenGroupThreadAction(this.groupId);
  final String groupId;
  String? threadId;

  @override
  Future<AppState?> run() async {
    threadId = await resolveGroupThread(groupId);
    return null;
  }
}

/// Pin, mute, archive, favourite or mark unread (`POST /threads/prefs`, lists-state.tsx:150-163).
/// [change] holds `pinned|muted|archived|favourite|marked_unread`.
class ThreadPrefsAction extends ChatsAction {
  ThreadPrefsAction(this.rows, this.change);
  final List<ChatRow> rows;
  final Json change;

  @override
  Future<AppState?> run() async {
    if (rows.isEmpty) return null;
    final ids = <String>[];
    for (final row in rows) {
      final id = await ensureThread(row);
      if (id.isNotEmpty) ids.add(id);
    }
    if (ids.isEmpty) return null;
    final prefs = asJsonList(
      await apiClient.post('/threads/prefs', {'thread_ids': ids, ...change}),
    );
    if (rows.any((r) => r.threadId == null || r.entry == null)) {
      dispatch(RefreshShellAction());
    }
    return mergePrefs(prefs);
  }
}

/// «تمييز كمقروءة»: each row read up to its newest message (`POST /threads/{id}/read`).
class ReadRowsAction extends ChatsAction {
  ReadRowsAction(this.rows);
  final List<ChatRow> rows;

  @override
  Future<AppState?> run() async {
    final prefs = <Json>[];
    for (final row in rows) {
      final entry = row.entry;
      if (entry == null) continue;
      final seq = [
        entry.lastMessage?.seq ?? 0,
        entry.lastReadSeq,
      ].reduce((a, b) => a > b ? a : b);
      prefs.add(
        asJson(
          await apiClient.post('/threads/${entry.threadId}/read', {'seq': seq}),
        ),
      );
    }
    return mergePrefs(prefs);
  }
}

/// «تحديد الكل كمقروء» (`POST /threads/read-all`, Web DesktopList.tsx:67-71): every conversation,
/// archived and muted included, read up to its newest message and its marked dot cleared. The
/// answer holds only the rows that changed; a second call answers `[]`. No confirmation and no
/// undo, as on the web: the read cursor only moves forward. One at a time.
class ReadAllAction extends ChatsAction with NonReentrant<AppState> {
  /// The conversations the server read now (for their tray notifications).
  List<String> changed = const [];

  @override
  Future<AppState?> run() async {
    final prefs = asJsonList(await apiClient.post('/threads/read-all'));
    changed = [for (final p in prefs) asStr(p['thread_id'])];
    // Rows this device still shows unread that the server had already read.
    dispatch(RefreshShellAction());
    return mergePrefs(prefs);
  }
}

/// «مسح الرسائل» / «حذف»: the history is hidden for the owner; the agent, the group and the
/// conversation stay (Q1, Q44). «حذف» also drops the marks (selection.tsx:92-100).
class ClearRowsAction extends ChatsAction {
  ClearRowsAction(this.rows, {this.dropMarks = false});
  final List<ChatRow> rows;
  final bool dropMarks;

  @override
  Future<AppState?> run() async {
    final prefs = <Json>[];
    for (final row in rows) {
      final id = row.threadId;
      if (id == null) continue;
      prefs.add(asJson(await apiClient.post('/threads/$id/clear')));
    }
    var next = mergePrefs(prefs);
    final marked = rows.where((r) => r.entry != null).toList();
    if (dropMarks && marked.isNotEmpty) {
      final reset = asJsonList(
        await apiClient.post('/threads/prefs', {
          'thread_ids': [for (final r in marked) r.entry!.threadId],
          'pinned': false,
          'muted': false,
          'archived': false,
          'favourite': false,
        }),
      );
      // One merge, in order: the store's state does not hold the first one yet.
      next = mergePrefs([...prefs, ...reset]);
    }
    // The conversations this device holds lose the hidden history at once: messages at or
    // below the merged entry's new floor (`hidden_before_seq`).
    for (final p in prefs) {
      final t = next.threads[asStr(p['thread_id'])];
      if (t != null) next = next.withThread(withoutCleared(next, t));
    }
    dispatch(RefreshShellAction());
    return next;
  }
}

/// «إبقاء المحادثات مؤرشفة» (`PUT /threads/settings {keep_archived}`).
class SetKeepArchivedAction extends ChatsAction {
  SetKeepArchivedAction(this.keep);
  final bool keep;

  @override
  Future<AppState?> run() async {
    final saved = asJson(
      await apiClient.put('/threads/settings', {'keep_archived': keep}),
    );
    return state.copyWith(
      shell: state.shell.copyWith(
        keepArchived: asBool(saved['keep_archived'], keep),
      ),
    );
  }
}

AppState _withList(AppState state, ChatList list, {int? at}) {
  final lists = [...state.shell.chatLists];
  final i = lists.indexWhere((l) => l.id == list.id);
  if (i >= 0) {
    lists[i] = list;
  } else if (at != null && at <= lists.length) {
    lists.insert(at, list);
  } else {
    lists.add(list);
  }
  return state.copyWith(shell: state.shell.copyWith(chatLists: lists));
}

/// «إنشاء القائمة» / «حفظ القائمة» (list-sheets.tsx:254-296): name then members; a new list whose
/// members fail is rolled back so the owner never keeps an empty list.
class SaveChatListAction extends ChatsAction {
  SaveChatListAction({this.listId, required this.name, required this.rows});
  final String? listId;
  final String name;
  final List<ChatRow> rows;
  ChatList? saved;

  @override
  Future<AppState?> run() async {
    final ids = <String>[];
    for (final row in rows) {
      final id = await ensureThread(row);
      if (id.isNotEmpty) ids.add(id);
    }
    ChatList list;
    final existing = listId;
    if (existing != null) {
      final before = state.shell.chatLists
          .where((l) => l.id == existing)
          .firstOrNull;
      if (before != null && before.name != name) {
        await apiClient.put('/chat-lists/$existing', {'name': name});
      }
      list = ChatList.fromJson(
        asJson(
          await apiClient.put('/chat-lists/$existing/members', {
            'thread_ids': ids,
          }),
        ),
      );
    } else {
      final created = ChatList.fromJson(
        asJson(await apiClient.post('/chat-lists', {'name': name})),
      );
      try {
        list = ChatList.fromJson(
          asJson(
            await apiClient.put('/chat-lists/${created.id}/members', {
              'thread_ids': ids,
            }),
          ),
        );
      } catch (_) {
        await apiClient
            .delete('/chat-lists/${created.id}')
            .catchError((Object _) => null);
        rethrow;
      }
    }
    saved = list;
    if (rows.any((r) => r.threadId == null)) dispatch(RefreshShellAction());
    return _withList(state, list);
  }
}

/// Adds rows to an existing list (`PUT /chat-lists/{id}/members`); [added] is how many were new.
class AddToChatListAction extends ChatsAction {
  AddToChatListAction(this.list, this.rows);
  final ChatList list;
  final List<ChatRow> rows;
  int added = 0;

  @override
  Future<AppState?> run() async {
    final ids = <String>[];
    for (final row in rows) {
      final id = await ensureThread(row);
      if (id.isNotEmpty && !list.threadIds.contains(id)) ids.add(id);
    }
    added = ids.length;
    final saved = ChatList.fromJson(
      asJson(
        await apiClient.put('/chat-lists/${list.id}/members', {
          'thread_ids': [...list.threadIds, ...ids],
        }),
      ),
    );
    if (rows.any((r) => r.threadId == null)) dispatch(RefreshShellAction());
    return _withList(state, saved);
  }
}

/// «حذف القائمة» (`DELETE /chat-lists/{id}`); [RestoreChatListAction] is its undo.
class DeleteChatListAction extends ChatsAction {
  DeleteChatListAction(this.list);
  final ChatList list;

  @override
  Future<AppState?> run() async {
    await apiClient.delete('/chat-lists/${list.id}');
    return state.copyWith(
      shell: state.shell.copyWith(
        chatLists: state.shell.chatLists.where((l) => l.id != list.id).toList(),
      ),
    );
  }
}

/// «تراجع» after deleting a list: recreate it with its chats at its old place. A recreated list
/// whose chats fail is rolled back (as [SaveChatListAction]); one that cannot be moved stays
/// where the server put it.
class RestoreChatListAction extends ChatsAction {
  RestoreChatListAction(this.list, this.index);
  final ChatList list;
  final int index;
  ChatList? restored;

  @override
  Future<AppState?> run() async {
    final at = index < 0 ? 0 : index;
    final created = ChatList.fromJson(
      asJson(await apiClient.post('/chat-lists', {'name': list.name})),
    );
    ChatList filled;
    try {
      filled = ChatList.fromJson(
        asJson(
          await apiClient.put('/chat-lists/${created.id}/members', {
            'thread_ids': list.threadIds,
          }),
        ),
      );
    } catch (_) {
      await apiClient
          .delete('/chat-lists/${created.id}')
          .catchError((Object _) => null);
      rethrow;
    }
    try {
      final moved = ChatList.fromJson(
        asJson(
          await apiClient.put('/chat-lists/${created.id}', {'position': at}),
        ),
      );
      restored = moved;
      return _withList(state, moved, at: at);
    } on ApiError {
      restored = filled;
      return _withList(state, filled);
    }
  }
}
