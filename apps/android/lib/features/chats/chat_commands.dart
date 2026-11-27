// What the row menu and the selection do (apps/mobile/components/shell/selection.tsx `act`):
// each change goes to the server, ends the selection and says what happened in a toast.
// «حذف» and «مسح الرسائل» hide the history for the owner only and always confirm first.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import 'chat_rows.dart';
import 'chats_actions.dart';
import 'list_sheets.dart';

/// Shows a chat-list failure: the pin limit in its own words, other codes through errorText.
void showChatsFailure(BuildContext context, Object failure) {
  if (failure is SessionRequestCancelled) return;
  final l10n = context.l10n;
  if (failure is ApiError && failure.code == 'thread_pin_limit') {
    LnToast.show(context, l10n.t('sh_pin3'), kind: LnToastKind.notice);
    return;
  }
  LnToast.show(
    context,
    l10n.errorText(failure is ApiError ? failure.code : null),
    kind: LnToastKind.error,
  );
}

/// Runs [action]; on failure shows it and returns false.
Future<bool> runChatsAction(BuildContext context, ChatsAction action) async {
  await context.dispatchAndWait(action);
  if (!context.mounted) return false;
  final failure = action.failure;
  if (failure != null) {
    showChatsFailure(context, failure);
    return false;
  }
  return true;
}

/// Opens a row's conversation (an agent with none gets it now). [replace] uses `go` (from
/// screens outside the chats branch); otherwise the conversation is pushed over the list.
Future<void> openChatRow(
  BuildContext context,
  ChatRow row, {
  bool replace = false,
}) async {
  var id = row.threadId;
  if (id == null || id.isEmpty) {
    final action = OpenRowAction(row);
    if (!await runChatsAction(context, action)) return;
    id = action.threadId;
  }
  if (id == null || id.isEmpty || !context.mounted) return;
  if (replace) {
    context.go(Routes.thread(id));
  } else {
    context.push(Routes.thread(id));
  }
}

/// The selection's and the row menu's commands over [all] rows (pin limit arithmetic).
class ChatCommands {
  ChatCommands(this.context, {required this.all, required this.onDone});

  final BuildContext context;
  final List<ChatRow> all;

  /// Ends the selection after a command succeeded.
  final VoidCallback onDone;

  L10n get _l10n => context.l10n;

  Future<bool> _run(ChatsAction action, {String? toast}) async {
    final ok = await runChatsAction(context, action);
    if (!ok || !context.mounted) return false;
    onDone();
    if (toast != null) LnToast.show(context, toast);
    return true;
  }

  /// «تثبيت» / «إلغاء التثبيت»: new pins go on top in the order they were picked.
  Future<void> pin(List<ChatRow> picked) async {
    if (picked.isEmpty) return;
    final n = picked.length;
    if (picked.every(isPinned)) {
      await _run(
        ThreadPrefsAction(picked, {'pinned': false}),
        toast: _l10n.t(n > 1 ? 'sh_chatsUnpinned' : 'sh_chatUnpinned'),
      );
      return;
    }
    if (pinsAfter(all, picked) > pinLimit) {
      LnToast.show(context, _l10n.t('sh_pin3'), kind: LnToastKind.notice);
      return;
    }
    await _run(
      ThreadPrefsAction(
        picked.where((r) => !isPinned(r)).toList().reversed.toList(),
        {'pinned': true},
      ),
      toast: _l10n.t(n > 1 ? 'sh_chatsPinned' : 'sh_chatPinned'),
    );
  }

  Future<void> mute(List<ChatRow> picked) async {
    if (picked.isEmpty) return;
    final allMuted = picked.every(isMuted);
    await _run(
      ThreadPrefsAction(picked, {'muted': !allMuted}),
      toast: _l10n.t(allMuted ? 'sh_notifRestored' : 'sh_notifMuted'),
    );
  }

  /// «أرشفة» with «تراجع»; «إلغاء الأرشفة» when every picked row is archived.
  Future<void> archive(List<ChatRow> picked) async {
    if (picked.isEmpty) return;
    final n = picked.length;
    if (picked.every(isArchived)) {
      await _run(
        ThreadPrefsAction(picked, {'archived': false}),
        toast: _l10n.t(n > 1 ? 'sh_chatsReturned' : 'sh_chatReturned'),
      );
      return;
    }
    final rows = [...picked];
    if (!await _run(ThreadPrefsAction(rows, {'archived': true}))) return;
    if (!context.mounted) return;
    LnToast.show(
      context,
      _l10n.t('sh_chatsArchived', [_l10n.chatsWord(rows.length)]),
      kind: LnToastKind.positive,
      action: (
        _l10n.t('sh_undo'),
        () {
          if (context.mounted) {
            runChatsAction(
              context,
              ThreadPrefsAction(rows, {'archived': false}),
            );
          }
        },
      ),
    );
  }

  /// «تمييز كمقروءة» when any is unread, else «تمييز كغير مقروءة».
  Future<void> read(List<ChatRow> picked) async {
    if (picked.isEmpty) return;
    if (picked.any(rowIsUnread)) {
      await _run(ReadRowsAction(picked));
    } else {
      await _run(ThreadPrefsAction(picked, {'marked_unread': true}));
    }
  }

  Future<void> favourite(List<ChatRow> picked) async {
    if (picked.isEmpty) return;
    final allFav = picked.every(isFavourite);
    await _run(
      ThreadPrefsAction(picked, {'favourite': !allFav}),
      toast: _l10n.t(allFav ? 'sh_removedFav' : 'sh_addedFav'),
    );
  }

  /// «حذف» (clear for the owner, marks dropped) or «مسح الرسائل», after a confirmation.
  Future<void> clear(List<ChatRow> picked, {required bool delete}) async {
    if (picked.isEmpty) return;
    final l10n = _l10n;
    final groups = picked.where((r) => r.isGroup).length;
    final agents = picked.length - groups;
    final word = l10n.chatsWord(picked.length);
    final what = !delete
        ? l10n.t('sh_confClear', [word])
        : agents == 0
        ? l10n.t(groups == 1 ? 'sh_confGroup1' : 'sh_confGroupN', [word])
        : l10n.t(groups > 0 ? 'sh_confMixed' : 'sh_confAgents', [word]);
    final ok = await showLnConfirm(
      context,
      title: l10n.t(delete ? 'sh_deleteChatsQ' : 'sh_clearMessagesQ'),
      message: what,
      confirmLabel: l10n.t(delete ? 'sh_delete' : 'sh_clear'),
      cancelLabel: l10n.t('sh_cancel'),
      destructive: true,
    );
    if (!ok || !context.mounted) return;
    await _run(
      ClearRowsAction([...picked], dropMarks: delete),
      toast: delete
          ? l10n.t('sh_chatsDeleted', [word])
          : l10n.t('sh_messagesCleared'),
    );
  }

  /// «إضافة إلى قائمة»: the owner's lists, or a new list with these chats.
  void addToList(List<ChatRow> picked, List<ChatList> lists) {
    if (picked.isEmpty) return;
    if (lists.isEmpty) {
      showListEditor(
        context,
        initial: picked.map((r) => r.key).toSet(),
        onSaved: (_) => onDone(),
      );
    } else {
      showAddToList(context, picked, onDone: onDone);
    }
  }

  /// «مجموعة من المحددين»: a new group with the picked agents.
  void groupFrom(List<ChatRow> picked) {
    final members = picked.where((r) => r.isAgent).map((r) => r.id).toList();
    onDone();
    context.push(Routes.newGroup(members: members));
  }

  /// The row's long-press menu (profile · read/unread · pin/unpin) with Lonora's mute and archive,
  /// and «تحديد» to start the multi-selection.
  List<LnMenuAction<void>> rowMenu(
    ChatRow row, {
    required VoidCallback select,
  }) {
    final l10n = _l10n;
    final unread = rowIsUnread(row);
    final pinned = isPinned(row);
    final muted = isMuted(row);
    final archived = isArchived(row);
    return [
      LnMenuAction(
        label: l10n.t(row.isAgent ? 'chats_agentProfile' : 'groupSettings'),
        icon: row.isAgent ? FIcons.userRound : FIcons.usersRound,
        onSelected: () => context.push(
          row.isAgent ? Routes.agent(row.id) : Routes.groupSettings(row.id),
        ),
      ),
      LnMenuAction(
        label: l10n.t(unread ? 'sh_markRead' : 'sh_markUnread'),
        icon: unread ? FIcons.checkCheck : FIcons.messageCircle,
        onSelected: () => read([row]),
      ),
      if (!archived)
        LnMenuAction(
          label: l10n.t(pinned ? 'sh_unpin' : 'sh_pin'),
          icon: pinned ? FIcons.pinOff : FIcons.pin,
          onSelected: () => pin([row]),
        ),
      LnMenuAction(
        label: l10n.t(muted ? 'sh_unmute' : 'sh_muteNotifications'),
        icon: muted ? FIcons.bell : FIcons.bellOff,
        onSelected: () => mute([row]),
      ),
      LnMenuAction(
        label: l10n.t(archived ? 'sh_unarchive' : 'sh_archive'),
        icon: archived ? FIcons.archiveRestore : FIcons.archive,
        onSelected: () => archive([row]),
      ),
      LnMenuAction(
        label: l10n.t('chats_select'),
        icon: FIcons.squareCheck,
        onSelected: select,
      ),
    ];
  }

  /// The selection's ⋮ sheet (selection.tsx:229-283).
  Future<void> more(
    List<ChatRow> picked, {
    required List<String> visibleKeys,
    required List<ChatList> lists,
    required VoidCallback selectAll,
  }) async {
    final l10n = _l10n;
    final summary = SelectionSummary(picked, visibleKeys);
    await showLnActionMenu<void>(
      context,
      title: l10n.t('sh_more'),
      actions: [
        if (!summary.allVisiblePicked)
          LnMenuAction(
            label: l10n.t('sh_selectAll'),
            icon: FIcons.checkCheck,
            onSelected: selectAll,
          ),
        LnMenuAction(
          label: l10n.t(summary.anyUnread ? 'sh_markRead' : 'sh_markUnread'),
          icon: summary.anyUnread ? FIcons.checkCheck : FIcons.messageCircle,
          onSelected: () => read(picked),
        ),
        LnMenuAction(
          label: l10n.t(summary.allFavourite ? 'sh_removeFav' : 'sh_addFav'),
          icon: summary.allFavourite ? FIcons.heartOff : FIcons.heart,
          onSelected: () => favourite(picked),
        ),
        LnMenuAction(
          label: l10n.t('sh_addToList'),
          icon: FIcons.layers,
          onSelected: () => addToList(picked, lists),
        ),
        if (summary.agentRows.length >= 2)
          LnMenuAction(
            label: l10n.t('sh_groupFromSelected'),
            icon: FIcons.users,
            onSelected: () => groupFrom(picked),
          ),
        LnMenuAction(
          label: l10n.t('sh_clearMessages'),
          icon: FIcons.trash2,
          destructive: true,
          onSelected: () => clear(picked, delete: false),
        ),
      ],
    );
  }
}

/// The header while selecting (selection.tsx:288-314): ✕ · count | pin · mute · archive ·
/// delete · ⋮, composed from the header circles.
class SelectionHeader extends StatelessWidget {
  const SelectionHeader({
    super.key,
    required this.picked,
    required this.commands,
    required this.onCancel,
    required this.onMore,
  });

  final List<ChatRow> picked;
  final ChatCommands commands;
  final VoidCallback onCancel;
  final VoidCallback onMore;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final l10n = context.l10n;
    final n = picked.length;
    final archived = n > 0 && picked.every(isArchived);
    final allPinned = n > 0 && picked.every(isPinned);
    final allMuted = n > 0 && picked.every(isMuted);
    Widget tool(IconData icon, String label, VoidCallback onTap) =>
        CircleIconButton(icon: Icon(icon), semanticLabel: label, onTap: onTap);
    return Semantics(
      container: true,
      label: l10n.t('sh_selectedChats'),
      child: ScreenHeader(
        leading: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            tool(FIcons.x, l10n.t('sh_cancelSelection'), onCancel),
            const SizedBox(width: 6),
            Semantics(
              container: true,
              liveRegion: true,
              label: '$n ${l10n.t('sh_selected')}',
              child: ExcludeSemantics(
                child: Text(
                  '$n',
                  style: ln.text.display.copyWith(color: ln.colors.fg),
                ),
              ),
            ),
          ],
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (!archived)
              tool(
                allPinned ? FIcons.pinOff : FIcons.pin,
                l10n.t(allPinned ? 'sh_unpin' : 'sh_pin'),
                () => commands.pin(picked),
              ),
            tool(
              allMuted ? FIcons.bell : FIcons.bellOff,
              l10n.t(allMuted ? 'sh_unmute' : 'sh_muteNotifications'),
              () => commands.mute(picked),
            ),
            tool(
              archived ? FIcons.archiveRestore : FIcons.archive,
              l10n.t(archived ? 'sh_unarchive' : 'sh_archive'),
              () => commands.archive(picked),
            ),
            tool(
              FIcons.trash2,
              l10n.t('sh_delete'),
              () => commands.clear(picked, delete: true),
            ),
            tool(FIcons.ellipsisVertical, l10n.t('sh_more'), onMore),
          ],
        ),
      ),
    );
  }
}
