// The chat drawer of the last-conversation home: the start-side panel the conversation slides
// away from (LnDrawerScaffold, placed by the home shell). Search at the start and «+» at the end
// over every chat as a compact row (avatar and name, the open conversation highlighted, unread
// counts, pinned and muted marks), and «All chats» at the foot, which opens the full chat list
// (filters, the owner's lists, archived chats, selection, delete…). A tap opens the chat in place
// of the current conversation and closes the drawer; a long press opens the row's menu (the
// list's own: profile, read/unread, pin, mute, archive, select).
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/app_state.dart';
import '../agents/create_agent_sheet.dart';
import '../groups/create_group_sheet.dart';
import 'chat_commands.dart';
import 'chat_rows.dart';
import 'chat_widgets.dart';
import 'chats_actions.dart';
import 'chats_strings.dart';

/// Hands the home shell's drawer controller to the conversation header (its ☰ button) and to the
/// drawer's rows.
class ChatDrawerScope extends InheritedWidget {
  const ChatDrawerScope({
    super.key,
    required this.controller,
    required super.child,
  });

  final LnDrawerController controller;

  static LnDrawerController? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ChatDrawerScope>()?.controller;

  @override
  bool updateShouldNotify(ChatDrawerScope old) => old.controller != controller;
}

class ChatDrawer extends StatefulWidget {
  const ChatDrawer({super.key});

  /// The header circles sit 2 dp higher than a page's.
  static const double headerTopGap = ScreenHeader.topGapDefault - 2;

  @override
  State<ChatDrawer> createState() => _ChatDrawerState();
}

class _ChatDrawerState extends State<ChatDrawer> {
  final _plus = GlobalKey(debugLabel: 'chat drawer +');

  /// A chat without a conversation yet is getting one: further taps wait for it.
  bool _opening = false;

  void _close() => unawaited(ChatDrawerScope.maybeOf(context)?.close());

  /// Opens [row] in place of the current conversation. The drawer closes as the conversation
  /// opens, not before: a chat without a conversation gets one from the server first, and a
  /// drawer already closed (it is not built while closed) could no longer open it.
  Future<void> _open(ChatRow row, String? current) async {
    if (row.threadId != null && row.threadId == current) {
      _close();
      return;
    }
    if (_opening) return;
    _opening = true;
    try {
      await openChatRow(context, row, replace: true, beforeOpen: _close);
    } finally {
      _opening = false;
    }
  }

  /// The row's own rect on the screen (the menu's anchor).
  static Rect? _rectOf(BuildContext context) {
    final box = context.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return null;
    return box.localToGlobal(Offset.zero) & box.size;
  }

  Future<void> _rowMenu(
    BuildContext rowContext,
    ChatRow row,
    ChatCommands commands,
  ) async {
    final rect = _rectOf(rowContext);
    if (rect == null) return;
    await showLnPopoverMenu<void>(
      context,
      anchorRect: rect,
      semanticLabel: row.name,
      actions: commands.rowMenu(
        row,
        // The selection lives on the full list: it opens with this row picked.
        select: () => context.push(Routes.chatList(select: row.key)),
      ),
    );
  }

  Future<void> _create() async {
    final l10n = context.l10n;
    await showLnPopoverMenu<void>(
      context,
      anchorKey: _plus,
      semanticLabel: l10n.t('sh_newChat'),
      actions: [
        LnMenuAction(
          icon: FIcons.userRoundPlus,
          label: l10n.t('newAgent'),
          onSelected: () => showCreateAgentSheet(context),
        ),
        LnMenuAction(
          icon: FIcons.usersRound,
          label: l10n.t('sh_newGroup'),
          onSelected: () => showCreateGroupSheet(context),
        ),
        LnMenuAction(
          icon: FIcons.bot,
          label: l10n.t('sh_manageAgents'),
          onSelected: () => context.push(Routes.agents),
        ),
        LnMenuAction(
          icon: FIcons.checkCheck,
          label: l10n.t('chats_markAllRead'),
          onSelected: () => runChatsAction(context, ReadAllAction()),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    registerChatsStrings();
    final l10n = context.l10n;
    final c = context.ln.colors;
    final shell = context.select((AppState s) => s.shell);
    final outbox = context.select((AppState s) => s.outbox);
    final busy = context.select(busySets);
    final current = context.select((AppState s) => s.openThreadId);
    final rows = chatRows(
      shell.orderedAgents,
      shell.groups.values,
      shell.inbox,
      outbox: outboxLatest(outbox),
    );
    final visible = filterRows(rows, 'all', shell.chatLists);
    final commands = ChatCommands(context, all: rows, onDone: () {});

    Widget row(ChatRow row) {
      final count = rowCount(row);
      final working = row.isAgent
          ? busy.agents.contains(row.id)
          : busy.threads.contains(row.threadId);
      return Builder(
        key: ValueKey(row.key),
        builder: (rowContext) => ChatListRow.compact(
          avatar: ChatRowAvatar(
            row: row,
            agents: shell.agents,
            working: working,
            size: ChatListRow.compactAvatar,
          ),
          title: row.name,
          unreadCount: count,
          unreadDot: rowMarkedOnly(row),
          pinned: isPinned(row),
          muted: isMuted(row),
          current: row.threadId != null && row.threadId == current,
          unreadLabel: l10n.t('sh_unreadN', const [], {'count': count}),
          pinnedLabel: l10n.t('sh_pinned'),
          mutedLabel: l10n.t('sh_muted'),
          onTap: () => unawaited(_open(row, current)),
          onLongPress: () => _rowMenu(rowContext, row, commands),
        ),
      );
    }

    final loading =
        !shell.loaded && shell.agents.isEmpty && shell.lastError == null;
    final failed =
        !shell.loaded && shell.agents.isEmpty && shell.lastError != null;
    final Widget list;
    if (loading) {
      list = Center(child: LnSpinner(semanticLabel: l10n.t('sh_loading')));
    } else if (failed) {
      list = ErrorState(
        title: l10n.errorText(shell.lastError),
        retryLabel: l10n.t('sh_retry'),
        onRetry: () => context.dispatch(RefreshShellAction(silent: false)),
      );
    } else if (visible.isEmpty) {
      list = EmptyState(
        icon: FIcons.messageCircle,
        title: l10n.t('sh_noChats'),
      );
    } else {
      list = ListView.builder(
        padding: const EdgeInsets.only(top: LnSpace.xxs),
        itemExtent: ChatListRow.compactPitch,
        itemCount: visible.length,
        itemBuilder: (context, i) => row(visible[i]),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ScreenHeader(
          topGap: ChatDrawer.headerTopGap,
          leading: CircleIconButton(
            icon: const Icon(FIcons.search),
            semanticLabel: l10n.t('sh_search'),
            onTap: () => context.push(Routes.search),
          ),
          trailing: KeyedSubtree(
            key: _plus,
            child: CircleIconButton(
              icon: const Icon(FIcons.plus),
              semanticLabel: l10n.t('sh_newChat'),
              onTap: _create,
            ),
          ),
        ),
        Expanded(
          child: Semantics(
            container: true,
            label: l10n.t('sh_conversations'),
            child: list,
          ),
        ),
        Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.paddingOf(context).bottom + LnSpace.xs,
          ),
          child: ChatListRow.compact(
            avatar: Icon(FIcons.messagesSquare, size: 24, color: c.fgWarm),
            title: l10n.t('chats_allChats'),
            semanticLabel: l10n.t('chats_allChats'),
            onTap: () => context.push(Routes.chatList()),
          ),
        ),
      ],
    );
  }
}
