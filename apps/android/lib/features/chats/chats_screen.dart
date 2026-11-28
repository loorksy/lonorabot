// المحادثات: round search at the start, «+» at the end, no title, 66 dp rows without dividers, over
// Lonora's rows — every agent and group, ordered as Web and the Expo app order them
// (chat_rows.dart). The Expo app's filters rest hidden above the first row and appear when the list
// is pulled down; a further pull refreshes. A long press opens the row menu; «تحديد» starts the
// multi-selection (its toolbar replaces the header).
import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/models/models.dart';
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
import 'list_sheets.dart';
import 'pull_to_refresh.dart';

/// The filter bar's height: the Expo app's FILTER_H (44 dp chips and a 1 dp line) with the
/// chips' touch height raised to 48 dp.
const double chatFilterExtent = minTouchTarget + 1;

/// Gap between the header circles and the first row (the first row's top lands at 111 dp).
const double _listTopGap = 7;

class ChatsScreen extends StatefulWidget {
  const ChatsScreen({super.key, this.pushed = false, this.select});

  /// The full list pushed over the last-conversation home («كل المحادثات»): a back circle leads
  /// the header, search and «+» stand at its end.
  final bool pushed;

  /// The row key the selection starts on (the drawer's «تحديد»).
  final String? select;

  @override
  State<ChatsScreen> createState() => _ChatsScreenState();
}

class _ChatsScreenState extends State<ChatsScreen>
    with SingleTickerProviderStateMixin {
  String _filter = 'all';
  late Set<String>? _selected = widget.select == null ? null : {widget.select!};
  final _scroll = ScrollController(initialScrollOffset: chatFilterExtent);
  late final FPopoverController _create = FPopoverController(vsync: this);

  @override
  void dispose() {
    _scroll.dispose();
    _create.dispose();
    super.dispose();
  }

  void _endSelection() {
    if (_selected != null && mounted) setState(() => _selected = null);
  }

  void _toggle(String key) => setState(() {
    final next = {...?_selected};
    if (!next.remove(key)) next.add(key);
    _selected = next.isEmpty ? null : next;
  });

  void _setFilter(String filter) {
    HapticFeedback.selectionClick();
    setState(() {
      _filter = filter;
      _selected = null;
    });
  }

  /// Snaps a half-revealed filter bar open or shut (chat-list.tsx:219-225).
  bool _onScrollEnd(ScrollEndNotification n) {
    if (_filter != 'all' || n.depth != 0) return false;
    final y = _scroll.offset;
    if (y > 0 && y < chatFilterExtent) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!_scroll.hasClients) return;
        _scroll.animateTo(
          y > chatFilterExtent / 2 ? chatFilterExtent : 0,
          duration: LnMotion.medium,
          curve: LnMotion.emphasized,
        );
      });
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    registerChatsStrings();
    final ln = context.ln;
    final l10n = context.l10n;
    final shell = context.select((AppState s) => s.shell);
    final outbox = context.select((AppState s) => s.outbox);
    final busy = context.select(busySets);
    final rows = chatRows(
      shell.orderedAgents,
      shell.groups.values,
      shell.inbox,
      outbox: outboxLatest(outbox),
    );
    final newestOutgoing = <String, OutgoingMessage>{};
    for (final o in outbox) {
      final had = newestOutgoing[o.threadId];
      if (had == null || o.createdAt.isAfter(had.createdAt)) {
        newestOutgoing[o.threadId] = o;
      }
    }
    final filter =
        _filter.startsWith('list:') &&
            shell.loaded &&
            !shell.chatLists.any((l) => 'list:${l.id}' == _filter)
        ? 'all'
        : _filter;
    final visible = filterRows(rows, filter, shell.chatLists);
    final indexOfKey = {
      for (var i = 0; i < visible.length; i++) visible[i].key: i,
    };
    final archived = archivedSummary(rows);
    final selected = _selected;
    final picked = selected == null
        ? const <ChatRow>[]
        : rows.where((r) => selected.contains(r.key)).toList();
    final commands = ChatCommands(context, all: rows, onDone: _endSelection);
    final media = MediaQuery.of(context);
    final offline = shell.offline;
    final top = offline ? 0.0 : media.padding.top;
    final headerBottom =
        top + ScreenHeader.topGapDefault - 2 + ScreenHeader.rowHeight;
    final bottom = FloatingTabBar.occupiedHeight(context);

    Widget rowTile(ChatRow row) => ChatRowTile(
      key: ValueKey(row.key),
      row: row,
      agents: shell.agents,
      working: row.isAgent
          ? busy.agents.contains(row.id)
          : busy.threads.contains(row.threadId),
      outgoing: row.threadId == null ? null : newestOutgoing[row.threadId],
      selecting: selected != null,
      selected: selected?.contains(row.key) ?? false,
      onTap: () =>
          selected != null ? _toggle(row.key) : openChatRow(context, row),
      menu: () => commands.rowMenu(
        row,
        select: () => setState(() => _selected = {row.key}),
      ),
    );

    final loading =
        !shell.loaded && shell.agents.isEmpty && shell.lastError == null;
    final failed =
        !shell.loaded && shell.agents.isEmpty && shell.lastError != null;
    final activeList = listIdOf(filter) == null
        ? null
        : shell.chatLists.where((l) => 'list:${l.id}' == filter).firstOrNull;

    Widget? state;
    if (loading) {
      state = SkeletonRows(
        count: 7,
        animate: !(MediaQuery.maybeDisableAnimationsOf(context) ?? false),
        semanticLabel: context.t('sh_loading'),
      );
    } else if (failed) {
      state = ErrorState(
        title: l10n.errorText(shell.lastError),
        retryLabel: l10n.t('sh_retry'),
        onRetry: () => context.dispatch(RefreshShellAction(silent: false)),
      );
    } else if (visible.isEmpty) {
      state = activeList != null
          ? EmptyState(
              icon: FIcons.layers,
              title: l10n.t('sh_noChatsInList', [activeList.name]),
              actionLabel: l10n.t('sh_addChats'),
              onAction: () => showListEditor(
                context,
                list: activeList,
                onSaved: (l) => _setFilter('list:${l.id}'),
              ),
            )
          : EmptyState(
              icon: switch (filter) {
                'unread' => FIcons.checkCheck,
                'fav' => FIcons.heart,
                _ => FIcons.messageCircle,
              },
              title: l10n.t(switch (filter) {
                'unread' => 'sh_noUnread',
                'fav' => 'sh_noFav',
                _ => 'sh_noChats',
              }),
            );
    }

    final list = LayoutBuilder(
      builder: (context, box) {
        final viewport = box.maxHeight;
        final showArchive =
            filter == 'all' && archived.count > 0 && state == null;
        // The state sits a little above the middle of the free area.
        final stateHeight = ((viewport - _listTopGap - bottom) * 0.8).clamp(
          240.0,
          double.infinity,
        );
        final content =
            chatFilterExtent +
            _listTopGap +
            (showArchive ? ArchivedRow.height : 0) +
            (state == null ? visible.length * LnSize.listRow : stateHeight) +
            bottom;
        // Always room to scroll the filter bar out of view (chat-list.tsx:236 minHeight).
        final filler = (viewport + chatFilterExtent - content).clamp(
          0.0,
          double.infinity,
        );
        return NotificationListener<ScrollEndNotification>(
          onNotification: _onScrollEnd,
          child: LnPullToRefresh(
            onRefresh: () => context.dispatchAndWait(RefreshShellAction()),
            spinnerTop: 8,
            child: CustomScrollView(
              controller: _scroll,
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                SliverToBoxAdapter(
                  child: _FilterBar(
                    filter: filter,
                    lists: shell.chatLists,
                    onFilter: _setFilter,
                    onNewList: () => showListEditor(
                      context,
                      onSaved: (l) => _setFilter('list:${l.id}'),
                    ),
                    onListMenu: (l) {
                      // «تراجع» shows the list again only if it was the filter.
                      var wasActive = false;
                      showListMenu(
                        context,
                        l,
                        onSaved: (saved) => _setFilter('list:${saved.id}'),
                        onDeleted: () {
                          wasActive = _filter == 'list:${l.id}';
                          if (wasActive) _setFilter('all');
                        },
                        onRestored: (restored) {
                          if (wasActive && mounted) {
                            _setFilter('list:${restored.id}');
                          }
                        },
                      );
                    },
                  ),
                ),
                const SliverToBoxAdapter(child: SizedBox(height: _listTopGap)),
                if (showArchive)
                  SliverToBoxAdapter(
                    child: ArchivedRow(
                      count: archived.count,
                      unread: archived.unread,
                      onTap: () => context.push(Routes.archived),
                    ),
                  ),
                if (state != null)
                  SliverToBoxAdapter(
                    child: SizedBox(height: stateHeight, child: state),
                  )
                else
                  SliverFixedExtentList(
                    itemExtent: LnSize.listRow,
                    delegate: SliverChildBuilderDelegate(
                      (context, i) => rowTile(visible[i]),
                      childCount: visible.length,
                      // Rows keep their state (an open menu) when the order changes.
                      findChildIndexCallback: (key) => key is ValueKey<String>
                          ? indexOfKey[key.value]
                          : null,
                    ),
                  ),
                SliverToBoxAdapter(child: SizedBox(height: filler + bottom)),
              ],
            ),
          ),
        );
      },
    );

    final search = CircleIconButton(
      icon: const Icon(FIcons.search),
      semanticLabel: l10n.t('sh_search'),
      onTap: () => context.push(Routes.search),
    );
    final create = FPopoverMenu(
      popoverController: _create,
      menuAnchor: AlignmentDirectional.topEnd,
      childAnchor: AlignmentDirectional.bottomEnd,
      spacing: const FPortalSpacing(4),
      menu: [
        FItemGroup(
          children: [
            FItem(
              prefix: const Icon(FIcons.userRoundPlus),
              title: Text(l10n.t('newAgent')),
              onPress: () {
                _create.hide();
                showCreateAgentSheet(context);
              },
            ),
            FItem(
              prefix: const Icon(FIcons.usersRound),
              title: Text(l10n.t('sh_newGroup')),
              onPress: () {
                _create.hide();
                showCreateGroupSheet(context);
              },
            ),
            FItem(
              prefix: const Icon(FIcons.bot),
              title: Text(l10n.t('sh_manageAgents')),
              onPress: () {
                _create.hide();
                context.push(Routes.agents);
              },
            ),
          ],
        ),
        FItemGroup(
          children: [
            FItem(
              prefix: const Icon(FIcons.checkCheck),
              title: Text(l10n.t('chats_markAllRead')),
              onPress: () {
                _create.hide();
                runChatsAction(context, ReadAllAction());
              },
            ),
          ],
        ),
      ],
      child: CircleIconButton(
        icon: const Icon(FIcons.plus),
        semanticLabel: l10n.t('sh_newChat'),
        onTap: _create.toggle,
      ),
    );

    final header = selected != null
        ? SelectionHeader(
            picked: picked,
            commands: commands,
            onCancel: _endSelection,
            onMore: () => commands.more(
              picked,
              visibleKeys: [for (final r in visible) r.key],
              lists: shell.chatLists,
              selectAll: () => setState(
                () =>
                    _selected = {...?_selected, for (final r in visible) r.key},
              ),
            ),
          )
        : ScreenHeader(
            leading: widget.pushed
                ? CircleIconButton(
                    // Lucide chevrons mirror themselves in RTL (matchTextDirection).
                    icon: const Icon(FIcons.chevronLeft),
                    semanticLabel: l10n.t('back'),
                    onTap: () => context.canPop()
                        ? context.pop()
                        : context.go(Routes.chats),
                  )
                : search,
            trailing: widget.pushed
                ? Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [search, create],
                  )
                : create,
          );
    return PopScope(
      canPop: selected == null,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _endSelection();
      },
      child: ColoredBox(
        color: ln.colors.bg,
        child: Column(
          children: [
            NetworkStrip(
              status: offline
                  ? NetworkStripStatus.offline
                  : NetworkStripStatus.hidden,
              label: [
                l10n.t('sh_netOff'),
                l10n.networkWaitingText(
                  outbox.where((o) => o.delivery == Delivery.queued).length,
                ),
              ].where((s) => s.isNotEmpty).join(dotSeparator),
            ),
            Expanded(
              child: MediaQuery.removePadding(
                context: context,
                removeTop: offline,
                child: Stack(
                  children: [
                    Positioned(
                      top: headerBottom,
                      left: 0,
                      right: 0,
                      bottom: 0,
                      child: Semantics(
                        label: l10n.t('sh_conversations'),
                        container: true,
                        child: list,
                      ),
                    ),
                    Positioned(top: 0, left: 0, right: 0, child: header),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The filters (chat-list.tsx:66-139): الكل · غير مقروءة · المفضلة · الوكلاء · المجموعات · each
/// list · «+». Composed chips; a long press on a list opens its menu.
class _FilterBar extends StatelessWidget {
  const _FilterBar({
    required this.filter,
    required this.lists,
    required this.onFilter,
    required this.onNewList,
    required this.onListMenu,
  });

  final String filter;
  final List<ChatList> lists;
  final ValueChanged<String> onFilter;
  final VoidCallback onNewList;
  final ValueChanged<ChatList> onListMenu;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    Widget chip(String key, String label, {VoidCallback? onLong}) {
      final active = filter == key;
      return Padding(
        padding: const EdgeInsetsDirectional.only(end: 8),
        child: LnTappable(
          onTap: () => onFilter(key),
          onLongPress: onLong,
          haptic: onLong != null,
          selected: active,
          semanticLabel: label,
          excludeChildSemantics: true,
          child: SizedBox(
            height: minTouchTarget,
            child: Center(
              child: AnimatedContainer(
                duration: LnMotion.fast,
                height: LnSize.chipHeight,
                padding: const EdgeInsets.symmetric(horizontal: 14),
                alignment: Alignment.center,
                decoration: ShapeDecoration(
                  color: active ? c.fgStrong : c.fill2,
                  shape: const StadiumBorder(),
                ),
                child: Text(
                  label,
                  maxLines: 1,
                  style: ln.text.captionStrong.copyWith(
                    color: active ? c.bg : c.fg,
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    return Semantics(
      container: true,
      label: l10n.t('sh_filterChats'),
      child: SizedBox(
        height: chatFilterExtent,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: LnSpace.pageGutter,
          ),
          children: [
            chip('all', l10n.t('sh_fAll')),
            chip('unread', l10n.t('sh_fUnread')),
            chip('fav', l10n.t('sh_fFav')),
            chip('agents', l10n.t('sh_fAgents')),
            chip('groups', l10n.t('sh_fGroups')),
            for (final list in lists)
              chip(
                'list:${list.id}',
                list.name,
                onLong: () => onListMenu(list),
              ),
            LnTappable(
              onTap: onNewList,
              semanticLabel: l10n.t('sh_newList'),
              child: SizedBox.square(
                dimension: minTouchTarget,
                child: Icon(FIcons.plus, size: 18, color: c.fgMuted),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
