// «المؤرشفة» (apps/mobile/app/archived.tsx, chat-list.tsx:384-432), composed from the kit: the
// archived rows with the same row menu and selection as the list («إلغاء الأرشفة»), the note, and
// «إبقاء المحادثات مؤرشفة» (`PUT /threads/settings`).
import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../../state/actions/base.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/app_state.dart';
import 'chat_commands.dart';
import 'chat_rows.dart';
import 'chat_widgets.dart';
import 'chats_actions.dart';
import 'chats_strings.dart';
import 'pull_to_refresh.dart';

class ArchivedScreen extends StatefulWidget {
  const ArchivedScreen({super.key});

  @override
  State<ArchivedScreen> createState() => _ArchivedScreenState();
}

class _ArchivedScreenState extends State<ArchivedScreen> {
  Set<String>? _selected;
  bool _saving = false;

  void _endSelection() {
    if (_selected != null && mounted) setState(() => _selected = null);
  }

  void _toggle(String key) => setState(() {
    final next = {...?_selected};
    if (!next.remove(key)) next.add(key);
    _selected = next.isEmpty ? null : next;
  });

  Future<void> _keep(bool value) async {
    setState(() => _saving = true);
    final ok = await runChatsAction(context, SetKeepArchivedAction(value));
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) {
      LnToast.show(
        context,
        context.t(value ? 'sh_staysArchived' : 'sh_returnsOnMessage'),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    registerChatsStrings();
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final shell = context.select((AppState s) => s.shell);
    final outbox = context.select((AppState s) => s.outbox);
    final busy = context.select(busySets);
    final all = chatRows(
      shell.orderedAgents,
      shell.groups.values,
      shell.inbox,
      outbox: outboxLatest(outbox),
    );
    final rows = archivedRows(all);
    final selected = _selected;
    final picked = selected == null
        ? const <ChatRow>[]
        : rows.where((r) => selected.contains(r.key)).toList();
    final commands = ChatCommands(context, all: all, onDone: _endSelection);
    final headerHeight = ScreenHeader.heightOf(context) + 8;
    // The page is in the chats tab: the floating tab bar stays over its lower edge.
    final bottom = FloatingTabBar.occupiedHeight(context) + 16;
    Future<void> refresh() => context.dispatchAndWait(RefreshShellAction());

    final keep = shell.keepArchived;
    // forui ellipsizes tile text, which cuts a subtitle to one line: the explanation wraps to
    // three lines here.
    final settings = DefaultTextStyle.merge(
      maxLines: 3,
      child: LnSection(
        children: [
          LnListTile(
            icon: FIcons.archive,
            title: l10n.t('sh_keepArchived'),
            subtitle: l10n.t(keep ? 'sh_keepArchivedOn' : 'sh_keepArchivedOff'),
            trailing: LnSwitch(
              value: keep,
              semanticLabel: l10n.t('sh_keepArchived'),
              onChanged: _saving || !shell.loaded ? null : _keep,
            ),
          ),
        ],
      ),
    );

    Widget body;
    if (!shell.loaded && shell.inbox.isEmpty) {
      body = LnPullToRefresh(
        onRefresh: refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(top: headerHeight, bottom: bottom),
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
                animate:
                    !(MediaQuery.maybeDisableAnimationsOf(context) ?? false),
                semanticLabel: context.t('sh_loading'),
              ),
          ],
        ),
      );
    } else {
      body = LnPullToRefresh(
        onRefresh: refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(top: headerHeight, bottom: bottom),
          children: [
            if (rows.isEmpty)
              SizedBox(
                height: 280,
                child: EmptyState(
                  icon: FIcons.archive,
                  title: l10n.t('sh_noArchived'),
                ),
              )
            else ...[
              for (final row in rows)
                SizedBox(
                  height: LnSize.listRow,
                  child: ChatRowTile(
                    key: ValueKey(row.key),
                    row: row,
                    agents: shell.agents,
                    working: row.isAgent
                        ? busy.agents.contains(row.id)
                        : busy.threads.contains(row.threadId),
                    selecting: selected != null,
                    selected: selected?.contains(row.key) ?? false,
                    onTap: () => selected != null
                        ? _toggle(row.key)
                        : openChatRow(context, row),
                    menu: () => commands.rowMenu(
                      row,
                      select: () => setState(() => _selected = {row.key}),
                    ),
                  ),
                ),
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(
                  LnSpace.listInset,
                  16,
                  LnSpace.listInset,
                  16,
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(FIcons.info, size: 18, color: c.fgSubtle),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        l10n.t('sh_archivedNote'),
                        style: ln.text.caption.copyWith(color: c.fgMuted),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            settings,
          ],
        ),
      );
    }

    final header = selected != null
        ? SelectionHeader(
            picked: picked,
            commands: commands,
            onCancel: _endSelection,
            onMore: () => commands.more(
              picked,
              visibleKeys: [for (final r in rows) r.key],
              lists: shell.chatLists,
              selectAll: () => setState(
                () => _selected = {...?_selected, for (final r in rows) r.key},
              ),
            ),
          )
        : PageHeader(title: l10n.t('sh_archived'));

    return PopScope(
      canPop: selected == null,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _endSelection();
      },
      child: ColoredBox(
        color: c.bg,
        child: Stack(
          children: [
            Positioned.fill(child: body),
            Positioned(top: 0, left: 0, right: 0, child: header),
          ],
        ),
      ),
    );
  }
}
