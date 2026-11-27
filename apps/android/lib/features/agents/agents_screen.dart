// «إدارة الوكلاء» (apps/mobile/app/agents.tsx), composed from the list row: every agent with its
// role line and whether it is active or paused (tap → its profile), every group with its size (tap
// → its conversation), and «إنشاء مجموعة».
import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/app_state.dart';
import '../chats/chat_commands.dart';
import '../chats/chat_rows.dart';
import '../chats/chat_text.dart';
import '../chats/chat_widgets.dart';
import '../chats/chats_strings.dart';
import '../chats/pull_to_refresh.dart';

class AgentsScreen extends StatelessWidget {
  const AgentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    registerChatsStrings();
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final shell = context.select((AppState s) => s.shell);
    final rows = chatRows(
      shell.orderedAgents,
      shell.groups.values,
      shell.inbox,
    );
    ChatRow? rowOf(ChatRowKind kind, String id) =>
        rows.where((r) => r.key == rowKey(kind, id)).firstOrNull;
    // Lucide's chevrons follow the text direction by themselves.
    final chevron = Icon(FIcons.chevronRight, size: 18, color: c.chevron);
    Widget title(String text) => Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        LnSpace.listInset,
        18,
        LnSpace.listInset,
        6,
      ),
      child: Semantics(
        header: true,
        child: Text(
          text,
          style: ln.text.captionStrong.copyWith(color: c.fgMuted),
        ),
      ),
    );

    final top = ScreenHeader.heightOf(context) + 4;
    Future<void> refresh() => context.dispatchAndWait(RefreshShellAction());
    Widget body;
    if (!shell.loaded && shell.agents.isEmpty) {
      body = LnPullToRefresh(
        onRefresh: refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(top: top),
          children: [
            if (shell.lastError != null)
              SizedBox(
                height: 320,
                child: ErrorState(
                  title: l10n.errorText(shell.lastError),
                  retryLabel: l10n.t('sh_retry'),
                  onRetry: () =>
                      context.dispatch(RefreshShellAction(silent: false)),
                ),
              )
            else
              SkeletonRows(
                count: 5,
                semanticLabel: l10n.t('sh_loading'),
                animate:
                    !(MediaQuery.maybeDisableAnimationsOf(context) ?? false),
              ),
          ],
        ),
      );
    } else {
      final agents = shell.orderedAgents;
      final groups = shell.groups.values.toList();
      body = LnPullToRefresh(
        onRefresh: refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(
            top: top,
            bottom: MediaQuery.viewPaddingOf(context).bottom + 32,
          ),
          children: [
            title(l10n.t('sh_fAgents')),
            for (final agent in agents)
              () {
                final row = rowOf(ChatRowKind.agent, agent.id);
                final status = l10n.t(agent.paused ? 'sh_paused' : 'sh_active');
                final tone = agent.paused ? c.fgMuted : c.success;
                return PickRow(
                  key: ValueKey('agent-${agent.id}'),
                  height: LnSize.listRow,
                  avatar: row == null
                      ? const SizedBox.square(dimension: LnSize.avatarList)
                      : ChatRowAvatar(row: row, agents: shell.agents),
                  title: agent.name,
                  subtitle: agentRole(l10n, agent),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 7,
                        height: 7,
                        decoration: BoxDecoration(
                          color: tone,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        status,
                        style: ln.text.caption.copyWith(
                          color: agent.paused ? tone : c.successText,
                        ),
                      ),
                      const SizedBox(width: 4),
                      chevron,
                    ],
                  ),
                  onTap: () => context.push(Routes.agent(agent.id)),
                );
              }(),
            title(l10n.t('sh_fGroups')),
            if (groups.isEmpty)
              Padding(
                padding: const EdgeInsetsDirectional.symmetric(
                  horizontal: LnSpace.listInset,
                  vertical: 12,
                ),
                child: Text(
                  l10n.t('sh_noGroupsYet'),
                  style: ln.text.caption.copyWith(color: c.fgMuted),
                ),
              ),
            for (final group in groups)
              () {
                final row = rowOf(ChatRowKind.group, group.id);
                return PickRow(
                  key: ValueKey('group-${group.id}'),
                  height: LnSize.listRow,
                  avatar: row == null
                      ? const SizedBox.square(dimension: LnSize.avatarList)
                      : ChatRowAvatar(row: row, agents: shell.agents),
                  title: group.name,
                  subtitle: l10n.agentsWord(group.memberIds.length),
                  trailing: chevron,
                  onTap: row == null
                      ? null
                      : () => openChatRow(context, row, replace: true),
                );
              }(),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.pageGutter,
                20,
                LnSpace.pageGutter,
                0,
              ),
              child: BlockButton(
                label: l10n.t('sh_createGroup'),
                icon: FIcons.usersRound,
                variant: BlockButtonVariant.secondary,
                onPressed: () => context.push(Routes.newGroup()),
              ),
            ),
          ],
        ),
      );
    }

    return ColoredBox(
      color: c.bg,
      child: Stack(
        children: [
          Positioned.fill(child: body),
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: PageHeader(title: l10n.t('sh_fAgents')),
          ),
        ],
      ),
    );
  }
}
