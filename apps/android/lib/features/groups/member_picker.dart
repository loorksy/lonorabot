// The agents a group can hold, as check-circle rows with a search filter («Add members», member
// search, member limit). Lonora's limit is the Expo picker's (bot-member-picker.tsx:67, 12 agents);
// delegated agents are not offered (Lonora Web).
import 'package:flutter/widgets.dart';

import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../chats/chat_rows.dart';
import '../chats/chat_text.dart';
import '../chats/chat_widgets.dart';

/// The agents a group may include.
List<Agent> groupCandidates(List<Agent> agents) =>
    agents.where((a) => a.role != 'delegated').toList();

/// Check rows over [agents]; [selected] in pick order. Once [limit] are picked (null: no limit)
/// the other rows are dimmed and a line says why. Lays out as a column (place it inside a
/// scroll view).
class MemberPicker extends StatelessWidget {
  const MemberPicker({
    super.key,
    required this.agents,
    required this.selected,
    required this.onChanged,
    this.query = '',
    this.enabled = true,
    this.limit = groupMemberLimit,
  });

  final List<Agent> agents;
  final List<String> selected;
  final ValueChanged<List<String>> onChanged;
  final String query;
  final bool enabled;
  final int? limit;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final c = context.ln.colors;
    final q = foldSearch(query);
    final shown = agents.where((a) {
      if (q.isEmpty) return true;
      return foldSearch('${a.name} ${agentRole(l10n, a)}').contains(q);
    }).toList();
    if (shown.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(20),
        child: Text(
          l10n.t('sh_noResults'),
          textAlign: TextAlign.center,
          style: context.ln.text.caption.copyWith(color: c.fgMuted),
        ),
      );
    }
    final max = limit;
    final full = max != null && selected.length >= max;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final agent in shown)
          () {
            final on = selected.contains(agent.id);
            final row = ChatRow(
              key: rowKey(ChatRowKind.agent, agent.id),
              kind: ChatRowKind.agent,
              id: agent.id,
              agent: agent,
              name: agent.name,
            );
            return PickRow(
              key: ValueKey('member-${agent.id}'),
              avatar: ChatRowAvatar(row: row, agents: const {}, size: 40),
              title: agent.name,
              subtitle: agentRole(l10n, agent),
              checked: on,
              enabled: enabled && (on || !full),
              onTap: () => onChanged(
                on
                    ? selected.where((id) => id != agent.id).toList()
                    : [...selected, agent.id],
              ),
            );
          }(),
        if (full && enabled)
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(
              LnSpace.pageGutter,
              8,
              LnSpace.pageGutter,
              0,
            ),
            child: Text(
              l10n.t('groups_limit', [max]),
              style: context.ln.text.caption.copyWith(color: c.fgMuted),
            ),
          ),
      ],
    );
  }
}
