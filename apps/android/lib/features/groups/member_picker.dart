// The agents a group can hold, as check-circle rows with a search filter («Add members», member
// search, member limit). Lonora's limit is the Expo picker's (bot-member-picker.tsx:67, 12 agents);
// delegated agents are not offered (Lonora Web). A row is 70 dp: the 40 dp avatar, the name over
// its role line, and a 24 dp check circle; hairlines between rows run under the text only.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../chats/chat_rows.dart';
import '../chats/chat_text.dart';
import '../chats/chat_widgets.dart';

/// The agents a group may include.
List<Agent> groupCandidates(List<Agent> agents) =>
    agents.where((a) => a.role != 'delegated').toList();

/// The avatar of [agent] in a member row or chip.
Widget memberAvatar(Agent agent, double size) => ChatRowAvatar(
  row: ChatRow(
    key: rowKey(ChatRowKind.agent, agent.id),
    kind: ChatRowKind.agent,
    id: agent.id,
    agent: agent,
    name: agent.name,
  ),
  agents: const {},
  size: size,
);

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
    this.inset = LnSpace.pageGutter,
  });

  final List<Agent> agents;
  final List<String> selected;
  final ValueChanged<List<String>> onChanged;
  final String query;
  final bool enabled;
  final int? limit;

  /// The rows' side inset.
  final double inset;

  /// A row's height.
  static const double rowHeight = 70;

  /// Avatar → text.
  static const double textGap = 14;

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
    final hairline = 1 / MediaQuery.devicePixelRatioOf(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final (i, agent) in shown.indexed) ...[
          if (i > 0)
            Padding(
              padding: EdgeInsetsDirectional.only(
                start: inset + 40 + textGap,
                end: inset,
              ),
              child: Container(height: hairline, color: c.border),
            ),
          () {
            final on = selected.contains(agent.id);
            return MemberRow(
              key: ValueKey('member-${agent.id}'),
              agent: agent,
              subtitle: agentRole(l10n, agent),
              checked: on,
              inset: inset,
              enabled: enabled && (on || !full),
              onTap: () => onChanged(
                on
                    ? selected.where((id) => id != agent.id).toList()
                    : [...selected, agent.id],
              ),
            );
          }(),
        ],
        if (full && enabled)
          Padding(
            padding: EdgeInsetsDirectional.fromSTEB(inset, 8, inset, 0),
            child: Text(
              l10n.t('groups_limit', [max]),
              style: context.ln.text.caption.copyWith(color: c.fgMuted),
            ),
          ),
      ],
    );
  }
}

/// One check row of [MemberPicker]: the whole row is the button, its checked state spoken.
class MemberRow extends StatelessWidget {
  const MemberRow({
    super.key,
    required this.agent,
    required this.subtitle,
    required this.checked,
    required this.onTap,
    this.enabled = true,
    this.inset = LnSpace.pageGutter,
  });

  final Agent agent;
  final String subtitle;
  final bool checked;
  final VoidCallback onTap;
  final bool enabled;
  final double inset;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return MergeSemantics(
      child: Semantics(
        checked: checked,
        enabled: enabled,
        child: LnTappable(
          onTap: enabled ? onTap : null,
          semanticLabel: [
            agent.name,
            if (subtitle.isNotEmpty) subtitle,
          ].join(', '),
          excludeChildSemantics: true,
          child: Opacity(
            opacity: enabled ? 1 : LnPalette.disabledOpacity,
            child: SizedBox(
              height: MemberPicker.rowHeight,
              child: Padding(
                padding: EdgeInsetsDirectional.symmetric(horizontal: inset),
                child: Row(
                  children: [
                    memberAvatar(agent, 40),
                    const SizedBox(width: MemberPicker.textGap),
                    Expanded(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(
                            agent.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: ln.text.body.copyWith(color: c.fgWarm),
                          ),
                          if (subtitle.isNotEmpty)
                            Text(
                              subtitle,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: ln.text.caption.copyWith(color: c.fgMuted),
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(width: LnSpace.sm),
                    MemberCheck(checked: checked),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A 24 dp check circle: a 1.5 dp ring in the secondary ink, or the action blue
/// ([LnPalette.selectionFill]) with a white check when [checked].
class MemberCheck extends StatelessWidget {
  const MemberCheck({super.key, required this.checked});

  final bool checked;

  static const double size = 24;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    return AnimatedContainer(
      duration: LnMotion.fast,
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: checked ? c.selectionFill : null,
        border: checked ? null : Border.all(color: c.fgMuted, width: 1.5),
      ),
      child: checked ? Icon(FIcons.check, size: 16, color: c.onAccent) : null,
    );
  }
}
