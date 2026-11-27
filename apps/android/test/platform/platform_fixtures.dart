// Server-shaped JSON for the platform tests (shapes read from the local Lonora server).
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/state/app_state.dart';

final t0 = DateTime.utc(2026, 11, 27, 10);

String iso(DateTime d) => d.toUtc().toIso8601String();

Json agentJson(
  String id,
  String name, {
  String role = 'general',
  String? color,
  String avatar = 'orb',
}) => {'id': id, 'name': name, 'role': role, 'avatar': avatar, 'color': ?color};

Json groupJson(String id, String name, List<String> members, String thread) => {
  'id': id,
  'thread_id': thread,
  'payload': {'name': name, 'member_ids': members},
};

Json lastMessage({
  required String id,
  required int seq,
  String role = 'assistant',
  String? agentId,
  String content = 'Hello',
  DateTime? at,
}) => {
  'id': id,
  'role': role,
  'agent_id': agentId,
  'content': content,
  'preview': content,
  'kind': 'text',
  'seq': seq,
  'created_at': iso(at ?? t0),
};

Json inboxJson(
  String thread, {
  String? agentId,
  String? groupId,
  Json? last,
  int unread = 0,
  bool muted = false,
  bool archived = false,
}) => {
  'thread_id': thread,
  'agent_id': agentId,
  'group_id': groupId,
  'last_message': last,
  'unread_count': unread,
  'last_read_seq': 0,
  'muted': muted,
  'archived': archived,
  'favourite': false,
  'pinned_order': null,
  'hidden_before_seq': 0,
};

Json attentionJson(
  String id, {
  String code = 'approval_required',
  String importance = 'action_required',
  String? agentId,
  String? threadId,
  DateTime? at,
  Json parameters = const {},
}) => {
  'id': id,
  'agent_id': agentId,
  'thread_id': threadId,
  'importance': importance,
  'code': code,
  'status': 'ready',
  'parameters': parameters,
  'created_at': iso(at ?? t0),
};

LonoraEvent messageCreated({
  required String thread,
  required String id,
  String role = 'assistant',
  String? agentId,
  String content = 'Hello',
  DateTime? at,
  int cursor = 1,
}) => LonoraEvent(
  cursor: cursor,
  kind: 'message.created',
  threadId: thread,
  agentId: agentId,
  payload: {
    'id': id,
    'thread_id': thread,
    'role': role,
    'agent_id': agentId,
    'content': content,
    'seq': 5,
    'created_at': iso(at ?? t0),
  },
  createdAt: at ?? t0,
);

/// A shell with Sara (agent, thread t-sara), Omar (personal agent, thread t-omar) and the
/// group «Desk» (Sara + Omar, thread t-desk).
ShellState demoShell({
  bool saraMuted = false,
  bool deskArchived = false,
  List<Json> attention = const [],
}) {
  final agents = [
    Agent.fromJson(agentJson('a-sara', 'Sara', color: 'blue')),
    Agent.fromJson(agentJson('a-omar', 'Omar', role: 'personal')),
  ];
  return ShellState(
    agents: {for (final a in agents) a.id: a},
    agentOrder: [for (final a in agents) a.id],
    groups: {
      'g-desk': Group.fromJson(
        groupJson('g-desk', 'Desk', ['a-sara', 'a-omar'], 't-desk'),
      ),
    },
    inbox: [
      InboxEntry.fromJson(
        inboxJson('t-sara', agentId: 'a-sara', muted: saraMuted),
      ),
      InboxEntry.fromJson(inboxJson('t-omar', agentId: 'a-omar')),
      InboxEntry.fromJson(
        inboxJson('t-desk', groupId: 'g-desk', archived: deskArchived),
      ),
    ],
    attention: attention,
    loaded: true,
  );
}
