// Groups on the server (apps/mobile/app/new-group.tsx:32-47, lib/groups.ts:5-7, and Lonora
// Web's group page): `POST /groups/create` and `PUT /groups/{id} {payload, version}`.
// A group is never deleted from a client (owner decisions Q1, Q44).
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/app_state.dart';
import '../chats/chats_actions.dart';

AppState _withGroup(AppState state, Group group) => state.copyWith(
  shell: state.shell.copyWith(groups: {...state.shell.groups, group.id: group}),
);

/// «إنشاء»: the group and its conversation (`thread_id` in [threadId]).
class CreateGroupAction extends ChatsAction {
  CreateGroupAction({
    required this.name,
    required this.memberIds,
    this.purpose = '',
    this.leadAgentId,
  });

  final String name;
  final List<String> memberIds;
  final String purpose;
  final String? leadAgentId;
  String? threadId;
  Group? group;

  @override
  Future<AppState?> run() async {
    final data = asJson(
      await apiClient.post('/groups/create', {
        'name': name.trim(),
        'member_ids': memberIds,
        'participation': 'mentions_or_lead',
        'purpose': purpose.trim(),
        'lead_agent_id': ?leadAgentId,
      }),
    );
    final created = Group.fromJson(data);
    group = created;
    threadId = asString(data['thread_id']) ?? created.threadId;
    dispatch(RefreshShellAction());
    return _withGroup(state, created);
  }
}

/// «حفظ»: the whole payload with the version it was read at (409 `version_conflict` when it
/// changed elsewhere).
class UpdateGroupAction extends ChatsAction {
  UpdateGroupAction(this.group, this.payload);
  final Group group;
  final Json payload;
  Group? saved;

  @override
  Future<AppState?> run() async {
    final data = asJson(
      await apiClient.put('/groups/${Uri.encodeComponent(group.id)}', {
        'payload': payload,
        'version': group.version,
      }),
    );
    final updated = Group.fromJson(data);
    saved = updated;
    dispatch(RefreshShellAction());
    return _withGroup(state, updated);
  }
}
