// The conversation list's rows, filters and selection arithmetic: a port of
// packages/core/src/chat-rows.ts and inbox.ts (shared by Lonora Web and the Expo app). A row is
// every agent and every group, with the owner's state of its canonical conversation when one exists
// (the inbox projection). The order is chat-rows.ts's: pinned first in pin order, then the latest
// message (one still in this device's outbox counts the moment it is written; a chat with no
// visible message sorts last), then the agents before the groups as the server lists them. Nothing
// here is stored or fetched.
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../l10n/bidi.dart' show listSeparator;
import '../../state/app_state.dart';

enum ChatRowKind { agent, group }

/// The built-in filters of the list, then the owner's lists as `list:<id>`.
const builtinFilters = ['all', 'unread', 'fav', 'agents', 'groups'];

/// The pin limit the server enforces (409 `thread_pin_limit`), chat-rows.ts:23.
const pinLimit = 3;

/// The members a group can be given in this app (apps/mobile/components/bot-member-picker.tsx:67).
const groupMemberLimit = 12;

String rowKey(ChatRowKind kind, String id) => '${kind.name}:$id';

class ChatRow {
  const ChatRow({
    required this.key,
    required this.kind,
    required this.id,
    required this.name,
    this.agent,
    this.group,
    this.entry,
    this.threadId,
    this.subtitle = '',
    this.paused = false,
    this.lastActivityAt,
  });

  /// `agent:<id>` or `group:<id>`: the key the list, the selection and the lists share.
  final String key;
  final ChatRowKind kind;
  final String id;
  final Agent? agent;
  final Group? group;

  /// The canonical conversation's inbox entry, when one exists.
  final InboxEntry? entry;
  final String? threadId;
  final String name;

  /// What line 2 says before anything was said: the group's purpose (agents: their role line).
  final String subtitle;
  final bool paused;

  /// The latest message's time (or the newest outbox entry's); null when the chat has none.
  final DateTime? lastActivityAt;

  bool get isAgent => kind == ChatRowKind.agent;
  bool get isGroup => kind == ChatRowKind.group;
}

/// A group's conversation id as the server stores it (`state.thread_id`, groups.ts:7).
String? groupThreadId(Group group) {
  final state = asString(asJson(group.raw['state'])['thread_id']);
  return state != null && state.isNotEmpty ? state : group.threadId;
}

/// A group's purpose (`payload.purpose`, GroupCreate).
String groupPurpose(Group group) =>
    asStr(asJson(group.raw['payload'])['purpose']);

/// The newest time per thread of this device's outbox (ChatRow `OutboxLatest`).
Map<String, DateTime> outboxLatest(Iterable<OutgoingMessage> outbox) {
  final out = <String, DateTime>{};
  for (final o in outbox) {
    final at = out[o.threadId];
    if (at == null || o.createdAt.isAfter(at)) out[o.threadId] = o.createdAt;
  }
  return out;
}

DateTime? _latest(DateTime? a, DateTime? b) {
  if (a == null) return b;
  if (b == null) return a;
  return b.isAfter(a) ? b : a;
}

/// Every agent and group as a row, in the list's order (chat-rows.ts:53-117).
List<ChatRow> chatRows(
  List<Agent> agents,
  Iterable<Group> groups,
  List<InboxEntry> entries, {
  Map<String, DateTime> outbox = const {},
}) {
  final byEntity = <String, InboxEntry>{};
  for (final entry in entries) {
    final key = entry.agentId != null
        ? rowKey(ChatRowKind.agent, entry.agentId!)
        : entry.groupId != null
        ? rowKey(ChatRowKind.group, entry.groupId!)
        : null;
    if (key != null) byEntity.putIfAbsent(key, () => entry);
  }
  final rows = <ChatRow>[
    for (final agent in agents)
      () {
        final key = rowKey(ChatRowKind.agent, agent.id);
        final entry = byEntity[key];
        return ChatRow(
          key: key,
          kind: ChatRowKind.agent,
          id: agent.id,
          agent: agent,
          entry: entry,
          threadId: entry?.threadId,
          name: agent.name,
          subtitle: agent.title.isNotEmpty ? agent.title : agent.description,
          paused: agent.paused,
          lastActivityAt: _latest(
            entry?.lastMessage?.createdAt,
            entry == null ? null : outbox[entry.threadId],
          ),
        );
      }(),
    for (final group in groups)
      () {
        final key = rowKey(ChatRowKind.group, group.id);
        final entry = byEntity[key];
        final threadId = entry?.threadId ?? groupThreadId(group);
        return ChatRow(
          key: key,
          kind: ChatRowKind.group,
          id: group.id,
          group: group,
          entry: entry,
          threadId: threadId,
          name: group.name,
          subtitle: groupPurpose(group),
          lastActivityAt: _latest(
            entry?.lastMessage?.createdAt,
            threadId == null ? null : outbox[threadId],
          ),
        );
      }(),
  ];
  final indexed = [for (var i = 0; i < rows.length; i++) (rows[i], i)];
  indexed.sort((first, second) {
    final pinA = _pinIndex(first.$1);
    final pinB = _pinIndex(second.$1);
    if (pinA != pinB) return pinA.compareTo(pinB);
    final a = first.$1.lastActivityAt;
    final b = second.$1.lastActivityAt;
    if (a != b) {
      if (a == null) return 1;
      if (b == null) return -1;
      if (!a.isAtSameMomentAs(b)) return b.compareTo(a);
    }
    return first.$2.compareTo(second.$2);
  });
  return [for (final (row, _) in indexed) row];
}

/// [chatRows] over the app state (agents in server order, groups, inbox, this device's outbox).
List<ChatRow> chatRowsOf(AppState state) => chatRows(
  state.shell.orderedAgents,
  state.shell.groups.values,
  state.shell.inbox,
  outbox: outboxLatest(state.outbox),
);

const _noPin = 1 << 52;

int _pinIndex(ChatRow row) => !isArchived(row) && row.entry?.pinnedOrder != null
    ? row.entry!.pinnedOrder!
    : _noPin;

bool isArchived(ChatRow row) => row.entry?.archived ?? false;
bool isPinned(ChatRow row) => _pinIndex(row) != _noPin;
bool isMuted(ChatRow row) => row.entry?.muted ?? false;
bool isFavourite(ChatRow row) => row.entry?.favourite ?? false;

/// The count pill, or 1 for a conversation marked unread with no new messages (inbox.ts:9-12).
int inboxUnread(InboxEntry entry) =>
    entry.unreadCount > 0 ? entry.unreadCount : (entry.markedUnread ? 1 : 0);

int rowUnread(ChatRow row) => row.entry == null ? 0 : inboxUnread(row.entry!);
bool rowIsUnread(ChatRow row) => rowUnread(row) > 0;

/// The dot: marked unread with no new message.
bool rowMarkedOnly(ChatRow row) =>
    row.entry != null && row.entry!.unreadCount == 0 && row.entry!.markedUnread;

/// The count pill: the agent's messages after the read cursor.
int rowCount(ChatRow row) => row.entry?.unreadCount ?? 0;

String? listIdOf(String filter) =>
    filter.startsWith('list:') ? filter.substring(5) : null;

/// The main list under one filter: archived rows never appear in it (chat-rows.ts:140-166).
List<ChatRow> filterRows(
  List<ChatRow> rows,
  String filter, [
  List<ChatList> lists = const [],
]) {
  final listId = listIdOf(filter);
  final members = listId == null
      ? null
      : (lists.where((l) => l.id == listId).firstOrNull?.threadIds ?? const [])
            .toSet();
  return rows.where((row) {
    if (isArchived(row)) return false;
    return switch (filter) {
      'all' => true,
      'unread' => rowIsUnread(row),
      'fav' => isFavourite(row),
      'agents' => row.isAgent,
      'groups' => row.isGroup,
      _ =>
        members != null &&
            row.threadId != null &&
            members.contains(row.threadId),
    };
  }).toList();
}

List<ChatRow> archivedRows(List<ChatRow> rows) =>
    rows.where(isArchived).toList();

/// The «المؤرشفة» row: the archived count, and how many of them are unread.
({int count, int unread}) archivedSummary(List<ChatRow> rows) {
  final archived = archivedRows(rows);
  return (count: archived.length, unread: archived.where(rowIsUnread).length);
}

/// A list chip's members that are still rows (an agent or group that exists).
List<ChatRow> listMemberRows(List<ChatRow> rows, ChatList list) {
  final members = list.threadIds.toSet();
  return rows
      .where((row) => row.threadId != null && members.contains(row.threadId))
      .toList();
}

/// What the selection toolbar and its ⋮ menu offer for the picked rows (chat-rows.ts:181-194).
class SelectionSummary {
  SelectionSummary(List<ChatRow> picked, List<String> visibleKeys)
    : count = picked.length,
      allPinned = picked.isNotEmpty && picked.every(isPinned),
      allMuted = picked.isNotEmpty && picked.every(isMuted),
      allArchived = picked.isNotEmpty && picked.every(isArchived),
      anyUnread = picked.any(rowIsUnread),
      allFavourite = picked.isNotEmpty && picked.every(isFavourite),
      allVisiblePicked = visibleKeys.every(
        picked.map((r) => r.key).toSet().contains,
      ),
      agentRows = picked.where((r) => r.isAgent).toList(),
      groupRows = picked.where((r) => r.isGroup).toList();

  final int count;
  final bool allPinned;
  final bool allMuted;
  final bool allArchived;
  final bool anyUnread;
  final bool allFavourite;
  final bool allVisiblePicked;
  final List<ChatRow> agentRows;
  final List<ChatRow> groupRows;
}

/// Pins after pinning every picked row that is not pinned yet; more than [pinLimit] is refused.
int pinsAfter(List<ChatRow> rows, List<ChatRow> picked) =>
    rows.where(isPinned).length + picked.where((r) => !isPinned(r)).length;

/// «مجموعة من المحددين»: the new group's name, from up to three of the agents' names, joined
/// with the list separator of the owner's language [locale].
String groupDraftName(List<String> names, String locale) =>
    names.where((n) => n.isNotEmpty).take(3).join(listSeparator(locale));

/// A group's members, the lead first (apps/mobile/components/shell/kit.tsx:29-39).
List<Agent> groupMembers(Group? group, Map<String, Agent> agents) {
  if (group == null) return const [];
  final ids = group.memberIds;
  final lead = group.leadAgentId;
  final ordered = lead != null && ids.contains(lead)
      ? [lead, ...ids.where((id) => id != lead)]
      : ids;
  return [for (final id in ordered) ?agents[id]];
}

/// The agents and the conversations that have a run queued, leased or running
/// (shell-data.tsx:225-229), the conversation snapshots' newer run states taking precedence
/// over the shell's list. Equal when the same agents and conversations are busy.
class BusySets {
  BusySets._(this.agents, this.threads)
    : _key =
          '${(agents.toList()..sort()).join(',')}|'
          '${(threads.toList()..sort()).join(',')}';

  final Set<String> agents;
  final Set<String> threads;
  final String _key;

  @override
  bool operator ==(Object other) => other is BusySets && other._key == _key;

  @override
  int get hashCode => _key.hashCode;
}

List<Object>? _busySources;
BusySets? _busyLast;

/// The [BusySets] of [state], recomputed only when a run list it reads changed (a selector
/// runs on every dispatch, streamed tokens included).
BusySets busySets(AppState state) {
  final sources = <Object>[
    state.shell.runs,
    for (final t in state.threads.values) t.runs,
  ];
  final last = _busyLast;
  final before = _busySources;
  if (last != null && before != null && before.length == sources.length) {
    var same = true;
    for (var i = 0; same && i < sources.length; i++) {
      same = identical(before[i], sources[i]);
    }
    if (same) return last;
  }
  final runs = <String, Run>{for (final r in state.shell.runs) r.id: r};
  for (final t in state.threads.values) {
    runs.addAll(t.runs);
  }
  final active = runs.values.where((r) => r.isActive).toList();
  _busySources = sources;
  return _busyLast = BusySets._(
    {for (final r in active) r.agentId},
    {for (final r in active) r.threadId},
  );
}
