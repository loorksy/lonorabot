// Custom lists (apps/mobile/components/shell/list-sheets.tsx, WhatsApp «القوائم»): a list's name
// and chats in one sheet (composed: the Expo app's two pages share one sheet here), the list
// chip's menu (edit, the chats, delete with confirmation and «تراجع»), and «إضافة إلى قائمة».
import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../../core/api/api_error.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import 'chat_commands.dart';
import 'chat_rows.dart';
import 'chat_text.dart';
import 'chat_widgets.dart';
import 'chats_actions.dart';

const _listNameMax = 30;

String _listSize(L10n l10n, int count) =>
    count > 0 ? l10n.chatsWord(count) : l10n.t('sh_listUnitEmpty');

/// «قائمة جديدة» / «تعديل القائمة»: name, then the agents and groups to keep in it.
/// [onSaved] receives the saved list (the chats screen then filters by it). [membersOnly]
/// (a list's «المحادثات») is the Expo app's pick page: «إضافة إلى «…»», the chats only.
Future<void> showListEditor(
  BuildContext context, {
  ChatList? list,
  Set<String> initial = const {},
  ValueChanged<ChatList>? onSaved,
  bool membersOnly = false,
}) {
  final l10n = context.l10n;
  final pick = membersOnly && list != null;
  return showLnSheet<void>(
    context,
    title: pick
        ? l10n.t('sh_addTo', [list.name])
        : l10n.t(list == null ? 'sh_newList' : 'sh_editList'),
    builder: (_) => _ListEditor(
      list: list,
      initial: initial,
      onSaved: onSaved,
      membersOnly: pick,
    ),
  );
}

class _ListEditor extends StatefulWidget {
  const _ListEditor({
    this.list,
    required this.initial,
    this.onSaved,
    this.membersOnly = false,
  });
  final ChatList? list;
  final Set<String> initial;
  final ValueChanged<ChatList>? onSaved;
  final bool membersOnly;

  @override
  State<_ListEditor> createState() => _ListEditorState();
}

class _ListEditorState extends State<_ListEditor> {
  late final TextEditingController _name = TextEditingController(
    text: widget.list?.name ?? '',
  );
  final _query = TextEditingController();
  late Set<String> _keys;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    final list = widget.list;
    _keys = list == null
        ? {...widget.initial}
        : listMemberRows(
            chatRowsOf(context.read()),
            list,
          ).map((r) => r.key).toSet();
  }

  @override
  void dispose() {
    _name.dispose();
    _query.dispose();
    super.dispose();
  }

  Future<void> _save(List<ChatRow> rows) async {
    final l10n = context.l10n;
    final name = _name.text.trim();
    if (name.isEmpty || _busy) return;
    final lists = context.read().shell.chatLists;
    void taken() => LnToast.show(
      context,
      l10n.t('sh_listTaken', const [], {'name': name}),
      kind: LnToastKind.notice,
    );
    if (lists.any((l) => l.id != widget.list?.id && l.name == name)) {
      taken();
      return;
    }
    setState(() => _busy = true);
    final action = SaveChatListAction(
      listId: widget.list?.id,
      name: name,
      rows: rows.where((r) => _keys.contains(r.key)).toList(),
    );
    await context.dispatchAndWait(action);
    if (!mounted) return;
    setState(() => _busy = false);
    final failure = action.failure;
    if (failure != null) {
      if (failure is ApiError && failure.code == 'chat_list_name_taken') {
        taken();
      } else {
        showChatsFailure(context, failure);
      }
      return;
    }
    final saved = action.saved;
    Navigator.of(context).pop();
    if (saved != null) widget.onSaved?.call(saved);
    LnToast.show(
      context,
      l10n.t(
        widget.list == null ? 'sh_listCreated' : 'sh_listSaved',
        const [],
        {'name': name},
      ),
      kind: LnToastKind.positive,
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final c = context.ln.colors;
    final shell = context.select((AppState s) => s.shell);
    final rows = chatRows(
      shell.orderedAgents,
      shell.groups.values,
      shell.inbox,
    );
    String sub(ChatRow row) {
      final role = row.agent != null
          ? agentRole(l10n, row.agent!)
          : row.subtitle;
      return role.isNotEmpty ? role : (row.isGroup ? l10n.t('sh_group') : '');
    }

    final q = foldSearch(_query.text);
    final shown = rows
        .where(
          (r) => q.isEmpty || foldSearch('${r.name} ${sub(r)}').contains(q),
        )
        .toList();
    final count = _keys.length;
    final editing = widget.list != null;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (!widget.membersOnly) ...[
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: LnTextField(
              controller: _name,
              label: l10n.t('sh_listName'),
              hint: l10n.t('sh_listNamePlaceholder'),
              helper: l10n.t('sh_listHint'),
              autofocus: !editing,
              inputFormatters: [LengthLimitingTextInputFormatter(_listNameMax)],
              onChanged: (_) => setState(() {}),
            ),
          ),
          const SizedBox(height: 12),
        ],
        SearchPill(
          controller: _query,
          hint: l10n.t('sh_search'),
          height: 40,
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 8),
        Flexible(
          child: Semantics(
            label: l10n.t('sh_agentsAndGroups'),
            child: shown.isEmpty
                ? Padding(
                    padding: const EdgeInsets.all(20),
                    child: Text(
                      l10n.t('sh_noResults'),
                      textAlign: TextAlign.center,
                      style: context.ln.text.caption.copyWith(color: c.fgMuted),
                    ),
                  )
                : ListView(
                    shrinkWrap: true,
                    padding: EdgeInsets.zero,
                    children: [
                      for (final row in shown)
                        PickRow(
                          avatar: ChatRowAvatar(
                            row: row,
                            agents: shell.agents,
                            size: 40,
                          ),
                          title: row.name,
                          subtitle: sub(row),
                          checked: _keys.contains(row.key),
                          onTap: () => setState(() {
                            if (!_keys.remove(row.key)) _keys.add(row.key);
                          }),
                        ),
                    ],
                  ),
          ),
        ),
        const SizedBox(height: 12),
        BlockButton(
          label: editing
              ? (count > 0
                    ? l10n.t('sh_saveListN', const [], {'count': count})
                    : l10n.t('sh_saveList'))
              : (count > 0
                    ? l10n.t('sh_createListN', const [], {'count': count})
                    : l10n.t('sh_createList')),
          loading: _busy,
          onPressed: _name.text.trim().isEmpty || _busy
              ? null
              : () => _save(rows),
        ),
      ],
    );
  }
}

/// A list chip's menu (list-sheets.tsx:380-410): edit, the chats, delete. [onRestored] runs
/// when the deletion's «تراجع» recreated the list.
Future<void> showListMenu(
  BuildContext context,
  ChatList list, {
  ValueChanged<ChatList>? onSaved,
  VoidCallback? onDeleted,
  ValueChanged<ChatList>? onRestored,
}) {
  final l10n = context.l10n;
  final members = listMemberRows(chatRowsOf(context.read()), list).length;
  return showLnActionMenu<void>(
    context,
    title: '${list.name}$dotSeparator${_listSize(l10n, members)}',
    actions: [
      LnMenuAction(
        label: l10n.t('sh_editList'),
        icon: FIcons.squarePen,
        onSelected: () => showListEditor(context, list: list, onSaved: onSaved),
      ),
      LnMenuAction(
        label: l10n.t('sh_theChats'),
        icon: FIcons.users,
        onSelected: () => showListEditor(
          context,
          list: list,
          onSaved: onSaved,
          membersOnly: true,
        ),
      ),
      LnMenuAction(
        label: l10n.t('sh_deleteList'),
        icon: FIcons.trash2,
        destructive: true,
        onSelected: () => _deleteList(
          context,
          list,
          onDeleted: onDeleted,
          onRestored: onRestored,
        ),
      ),
    ],
  );
}

Future<void> _deleteList(
  BuildContext context,
  ChatList list, {
  VoidCallback? onDeleted,
  ValueChanged<ChatList>? onRestored,
}) async {
  final l10n = context.l10n;
  final ok = await showLnConfirm(
    context,
    title: l10n.t('sh_deleteList'),
    message: list.name,
    confirmLabel: l10n.t('sh_delete'),
    cancelLabel: l10n.t('sh_cancel'),
    destructive: true,
  );
  if (!ok || !context.mounted) return;
  final index = context.read().shell.chatLists.indexWhere(
    (l) => l.id == list.id,
  );
  if (!await runChatsAction(context, DeleteChatListAction(list))) return;
  if (!context.mounted) return;
  onDeleted?.call();
  LnToast.show(
    context,
    l10n.t('sh_listDeleted', [list.name]),
    action: (
      l10n.t('sh_undo'),
      () async {
        if (!context.mounted) return;
        final restore = RestoreChatListAction(list, index);
        if (!await runChatsAction(context, restore)) return;
        final restored = restore.restored;
        if (restored != null) onRestored?.call(restored);
      },
    ),
  );
}

/// «إضافة إلى قائمة»: the owner's lists with their sizes, then «قائمة جديدة».
Future<void> showAddToList(
  BuildContext context,
  List<ChatRow> picked, {
  VoidCallback? onDone,
}) {
  final l10n = context.l10n;
  final state = context.read();
  final rows = chatRowsOf(state);
  return showLnSheet<void>(
    context,
    title: l10n.t('sh_addToList'),
    builder: (sheet) {
      final c = sheet.ln.colors;
      Widget disc(IconData icon) => Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(color: c.fill2, shape: BoxShape.circle),
        child: Icon(icon, size: 20, color: c.fgMuted),
      );
      Future<void> add(ChatList list) async {
        final action = AddToChatListAction(list, picked);
        await sheet.dispatchAndWait(action);
        if (!sheet.mounted) return;
        if (action.failure != null) {
          showChatsFailure(sheet, action.failure!);
          return;
        }
        Navigator.of(sheet).pop();
        onDone?.call();
        LnToast.show(
          sheet,
          action.added > 0
              ? l10n.t('sh_addedToList', [
                  l10n.chatsWord(action.added),
                  list.name,
                ])
              : l10n.t('sh_allInList', [list.name]),
          kind: LnToastKind.positive,
        );
      }

      return ListView(
        shrinkWrap: true,
        padding: EdgeInsets.zero,
        children: [
          for (final list in state.shell.chatLists)
            PickRow(
              avatar: disc(FIcons.layers),
              title: list.name,
              subtitle: _listSize(l10n, listMemberRows(rows, list).length),
              onTap: () => add(list),
            ),
          PickRow(
            avatar: disc(FIcons.plus),
            title: l10n.t('sh_newList'),
            subtitle: l10n.t('sh_willBeAdded', [l10n.chatsWord(picked.length)]),
            onTap: () {
              Navigator.of(sheet).pop();
              showListEditor(
                context,
                initial: picked.map((r) => r.key).toSet(),
                onSaved: (_) => onDone?.call(),
              );
            },
          ),
        ],
      );
    },
  );
}
