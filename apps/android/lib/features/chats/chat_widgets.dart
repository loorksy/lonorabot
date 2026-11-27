// Pieces of the chats feature built from the design kit: the row (the kit's 66 dp [ChatListRow]
// with Lonora's avatar, preview rules and the long-press menu), the archived row, the page header
// of pushed screens, the search pill and the check circle.
import 'dart:math' as math;

import 'package:flutter/material.dart'
    show InputDecoration, Material, MaterialType, TextField;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../../avatar/avatar.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/app_state.dart';
import 'chat_rows.dart';
import 'chat_text.dart';

/// The smallest touch target of the feature's own buttons (Android's 48 dp).
const double minTouchTarget = 48;

LonoraAvatarMember _member(Agent agent) => LonoraAvatarMember(
  agentId: agent.id,
  face: agent.avatar,
  color: agent.color,
  tradesOnItsOwn: agent.tradesOnItsOwn,
);

/// A row's avatar in the 44 dp slot: the agent's own avatar (animated only while it works, as
/// long lists keep static posters), or the group's two members side by side (lead first).
class ChatRowAvatar extends StatelessWidget {
  const ChatRowAvatar({
    super.key,
    required this.row,
    required this.agents,
    this.working = false,
    this.size = LnSize.avatarList,
  });

  final ChatRow row;
  final Map<String, Agent> agents;
  final bool working;
  final double size;

  @override
  Widget build(BuildContext context) {
    final agent = row.agent;
    final Widget avatar;
    if (agent != null) {
      avatar = LonoraAvatar(
        agentId: agent.id,
        face: agent.avatar,
        color: agent.color,
        tradesOnItsOwn: agent.tradesOnItsOwn,
        state: working ? LonoraAvatarState.working : LonoraAvatarState.idle,
        size: size,
        animate: working,
      );
    } else {
      final members = groupMembers(row.group, agents).map(_member).toList();
      final each = size * LnSize.avatarGroup / LnSize.avatarList;
      avatar = members.length < 2
          ? LonoraGroupAvatar(members: members, size: size, animate: false)
          : OverflowBox(
              maxWidth: each * 2,
              maxHeight: size,
              child: LonoraGroupAvatar.pair(
                members: members,
                size: each,
                animate: false,
              ),
            );
    }
    return SizedBox.square(
      dimension: size,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          avatar,
          if (row.paused)
            PositionedDirectional(
              end: -3,
              bottom: -3,
              child: _PausedMark(label: context.t('sh_paused')),
            ),
        ],
      ),
    );
  }
}

/// The paused agent's mark on its avatar (the Expo row's «متوقف» badge, kept on the avatar because
/// [ChatListRow] has no badge slot).
class _PausedMark extends StatelessWidget {
  const _PausedMark({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    return Semantics(
      label: label,
      child: Container(
        width: 18,
        height: 18,
        decoration: BoxDecoration(
          color: c.surface,
          shape: BoxShape.circle,
          border: Border.all(color: c.border),
        ),
        child: Icon(FIcons.pause, size: 10, color: c.fgMuted),
      ),
    );
  }
}

/// What line 2 of a row says (thread-row.tsx:39-142): the newest outbox message, else the last
/// message (the owner's with «أنت:», a group's with the speaker), else the role or purpose;
/// a working agent reads «يعمل…».
({String text, String? prefix, ChatPreviewKind kind}) rowPreview(
  L10n l10n,
  ChatRow row,
  Map<String, Agent> agents, {
  OutgoingMessage? outgoing,
  bool working = false,
}) {
  if (outgoing != null) {
    return (
      text: plainLine(outgoing.content),
      prefix: l10n.t('sh_youSaid'),
      kind: outgoing.delivery == Delivery.failed
          ? ChatPreviewKind.failed
          : ChatPreviewKind.normal,
    );
  }
  if (working) {
    return (
      text: l10n.t('peerWorking'),
      prefix: null,
      kind: ChatPreviewKind.active,
    );
  }
  final last = row.entry?.lastMessage;
  if (last == null) {
    final sub = row.agent != null ? agentRole(l10n, row.agent!) : row.subtitle;
    return (
      text: sub.isNotEmpty ? sub : l10n.t('sh_startChat'),
      prefix: null,
      kind: ChatPreviewKind.normal,
    );
  }
  final mine = last.role == 'user';
  final speaker = !mine && row.isGroup && last.agentId != null
      ? agents[last.agentId]?.name
      : null;
  return (
    text: plainLine(last.preview.isNotEmpty ? last.preview : last.content),
    prefix: mine
        ? l10n.t('sh_youSaid')
        : (speaker == null ? null : '$speaker:'),
    kind: ChatPreviewKind.normal,
  );
}

/// One conversation row: tap opens (or toggles while selecting); a long press opens the row menu as
/// a forui popover, with a medium haptic.
class ChatRowTile extends StatefulWidget {
  const ChatRowTile({
    super.key,
    required this.row,
    required this.agents,
    this.working = false,
    this.outgoing,
    this.selecting = false,
    this.selected = false,
    this.onTap,
    this.menu,
  });

  final ChatRow row;
  final Map<String, Agent> agents;
  final bool working;

  /// The thread's newest message still in this device's outbox.
  final OutgoingMessage? outgoing;
  final bool selecting;
  final bool selected;
  final VoidCallback? onTap;

  /// The long-press menu's entries (built when it opens); null: no menu.
  final List<LnMenuAction<void>> Function()? menu;

  @override
  State<ChatRowTile> createState() => _ChatRowTileState();
}

class _ChatRowTileState extends State<ChatRowTile>
    with SingleTickerProviderStateMixin {
  late final FPopoverController _menu = FPopoverController(vsync: this);
  List<LnMenuAction<void>> _actions = const [];

  @override
  void dispose() {
    _menu.dispose();
    super.dispose();
  }

  void _open() {
    final build = widget.menu;
    if (build == null) return;
    HapticFeedback.mediumImpact();
    setState(() => _actions = build());
    _menu.show();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final row = widget.row;
    final preview = rowPreview(
      l10n,
      row,
      widget.agents,
      outgoing: widget.outgoing,
      working: widget.working,
    );
    final at = widget.outgoing?.createdAt ?? row.entry?.lastMessage?.createdAt;
    final time = at == null ? null : listTime(at, l10n.lang);
    final count = rowCount(row);
    final last = row.entry?.lastMessage;
    final label = [
      row.name,
      if (count > 0)
        l10n.t('sh_unreadN', const [], {'count': count})
      else if (rowMarkedOnly(row))
        l10n.t('sh_unreadMarked'),
      if (widget.outgoing != null)
        widget.outgoing!.delivery == Delivery.failed
            ? l10n.t('sh_notSent')
            : l10n.t('sh_waitingNetwork'),
      if (widget.outgoing == null && last != null && last.role == 'user')
        last.consumed == true ? l10n.t('sh_tickRead') : l10n.t('sh_tickSent'),
      if (row.paused) l10n.t('sh_paused'),
      if (isMuted(row)) l10n.t('sh_muted'),
      if (isPinned(row)) l10n.t('sh_pinned'),
      ?preview.prefix,
      preview.text,
      ?time,
    ].where((s) => s.isNotEmpty).join(listSeparator(l10n.lang));
    final tile = ChatListRow(
      avatar: ChatRowAvatar(
        row: row,
        agents: widget.agents,
        working: widget.working,
      ),
      title: row.name,
      // Isolated so the words keep their own order inside the interface's direction.
      preview: isolate(preview.text),
      previewPrefix: preview.prefix,
      previewKind: preview.kind,
      time: time,
      unreadCount: count,
      unreadDot: rowMarkedOnly(row),
      pinned: isPinned(row),
      muted: isMuted(row),
      selectionMode: widget.selecting,
      selected: widget.selected,
      onTap: () => widget.onTap?.call(),
      onLongPress: widget.selecting || widget.menu == null ? null : _open,
      semanticLabel: label,
    );
    if (widget.menu == null) return tile;
    final c = context.ln.colors;
    return FPopoverMenu(
      popoverController: _menu,
      menu: [
        FItemGroup(
          children: [
            for (final a in _actions)
              FItem(
                enabled: a.enabled,
                prefix: a.icon == null
                    ? null
                    : Icon(a.icon, color: a.destructive ? c.error : null),
                title: Text(
                  a.label,
                  style: a.destructive ? TextStyle(color: c.error) : null,
                ),
                onPress: () {
                  _menu.hide();
                  a.onSelected?.call();
                },
              ),
          ],
        ),
      ],
      child: tile,
    );
  }
}

/// «المؤرشفة» at the top of the list (chat-list.tsx:141-182): the archive mark in the avatar
/// slot, the title, and the unread count (else how many are archived).
class ArchivedRow extends StatelessWidget {
  const ArchivedRow({
    super.key,
    required this.count,
    required this.unread,
    this.onTap,
  });

  final int count;
  final int unread;
  final VoidCallback? onTap;

  static const double height = 54;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final title = context.t('sh_archived');
    final figure = '${unread > 0 ? unread : count}';
    return LnTappable(
      onTap: onTap,
      semanticLabel: '$title, $figure',
      excludeChildSemantics: true,
      child: SizedBox(
        height: height,
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: LnSpace.listInset,
          ),
          child: Row(
            children: [
              SizedBox.square(
                dimension: LnSize.avatarList,
                child: Icon(FIcons.archive, size: 22, color: c.fgMuted),
              ),
              const SizedBox(width: LnSpace.listTextGap),
              Expanded(
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: ln.text.title.copyWith(color: c.fg),
                ),
              ),
              Text(
                figure,
                style: ln.text.captionStrong.copyWith(
                  color: unread > 0 ? c.brand : c.fgMuted,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The header of pushed screens (composed): a back circle at the start, the title centred on
/// the circles' row, an optional trailing widget.
class PageHeader extends StatelessWidget {
  const PageHeader({
    super.key,
    required this.title,
    this.trailing,
    this.onBack,
    this.close = false,
  });

  final String title;
  final Widget? trailing;
  final VoidCallback? onBack;

  /// A ✕ instead of the back chevron (modal screens).
  final bool close;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    // The title keeps clear of up to two header circles on each side.
    final sides = 2 * (LnSpace.pageGutter + 2 * ScreenHeader.rowHeight);
    final width = MediaQuery.sizeOf(context).width;
    return ScreenHeader(
      leading: CircleIconButton(
        // Lucide's chevrons follow the text direction by themselves.
        icon: Icon(close ? FIcons.x : FIcons.chevronLeft),
        semanticLabel: context.t('sh_back'),
        onTap: onBack ?? () => Navigator.of(context).maybePop(),
      ),
      center: SizedBox(
        height: LnSize.headerCircle,
        child: Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: width - sides),
            child: Semantics(
              header: true,
              child: Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                // The pushed-page title style (settings pages, PushedPage, AgentPage).
                style: ln.text.headline.copyWith(color: ln.colors.fg),
              ),
            ),
          ),
        ),
      ),
      trailing: trailing,
    );
  }
}

/// A stadium search field on the surface fill (the header slot of the search screen and the
/// pickers' filter). The pill is [height] tall; its clear button's touch target is
/// [minTouchTarget] square, so the widget is at least that tall.
class SearchPill extends StatelessWidget {
  const SearchPill({
    super.key,
    required this.controller,
    required this.hint,
    this.onChanged,
    this.focusNode,
    this.autofocus = false,
    this.onClear,
    this.clearLabel,
    this.height = LnSize.headerCircle,
  });

  final TextEditingController controller;
  final String hint;
  final ValueChanged<String>? onChanged;
  final FocusNode? focusNode;
  final bool autofocus;
  final VoidCallback? onClear;
  final String? clearLabel;
  final double height;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return SizedBox(
      height: math.max(height, minTouchTarget),
      child: Stack(
        alignment: Alignment.center,
        children: [
          Container(
            height: height,
            decoration: ShapeDecoration(
              color: c.surface,
              shape: StadiumBorder(side: BorderSide(color: c.border)),
              shadows: ln.chromeShadow,
            ),
          ),
          Padding(
            padding: const EdgeInsetsDirectional.only(start: 14),
            child: Row(
              children: [
                Icon(FIcons.search, size: 18, color: c.fgMuted),
                const SizedBox(width: 8),
                Expanded(
                  child: Material(
                    type: MaterialType.transparency,
                    child: TextField(
                      controller: controller,
                      focusNode: focusNode,
                      autofocus: autofocus,
                      onChanged: onChanged,
                      style: ln.text.body.copyWith(color: c.fg),
                      cursorColor: c.brand,
                      textInputAction: TextInputAction.search,
                      maxLines: 1,
                      decoration: InputDecoration.collapsed(
                        hintText: hint,
                        hintStyle: ln.text.body.copyWith(color: c.fgSubtle),
                      ),
                    ),
                  ),
                ),
                ValueListenableBuilder<TextEditingValue>(
                  valueListenable: controller,
                  builder: (context, value, _) => value.text.isEmpty
                      ? const SizedBox(width: 14)
                      : LnTappable(
                          onTap: onClear ?? controller.clear,
                          semanticLabel:
                              clearLabel ?? context.t('sh_clearSearch'),
                          child: SizedBox.square(
                            dimension: minTouchTarget,
                            child: Icon(
                              FIcons.circleX,
                              size: 18,
                              color: c.fgMuted,
                            ),
                          ),
                        ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// A picker row (composed from the list row's parts): avatar, title and subtitle, and a
/// trailing widget (a [SelectionMark], a status, a chevron). The row is the tap target; an
/// [action] (its own button, such as «remove») sits after it, outside the row's tap.
class PickRow extends StatelessWidget {
  const PickRow({
    super.key,
    required this.avatar,
    required this.title,
    this.subtitle,
    this.trailing,
    this.action,
    this.onTap,
    this.checked,
    this.enabled = true,
    this.height = 60,
    this.inset = LnSpace.pageGutter,
  });

  final Widget avatar;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final Widget? action;
  final VoidCallback? onTap;

  /// Non-null for check rows: shows a [SelectionMark] (unless [trailing] is given) and exposes
  /// the checked state to accessibility.
  final bool? checked;
  final bool enabled;
  final double height;

  /// The row's start inset (and end, without an [action]); 0 in a sheet that already pads its
  /// content, so the avatars share the sheet's edge.
  final double inset;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final sub = subtitle;
    final row = Semantics(
      checked: checked,
      enabled: enabled,
      child: LnTappable(
        onTap: enabled ? onTap : null,
        semanticLabel: [
          title,
          if (sub != null && sub.isNotEmpty) sub,
        ].join(', '),
        excludeChildSemantics: true,
        child: Opacity(
          opacity: enabled ? 1 : LnPalette.disabledOpacity,
          child: SizedBox(
            height: height,
            child: Padding(
              padding: EdgeInsetsDirectional.only(
                start: inset,
                end: action == null ? inset : 0,
              ),
              child: Row(
                children: [
                  avatar,
                  const SizedBox(width: LnSpace.sm),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: ln.text.title.copyWith(color: c.fg),
                        ),
                        if (sub != null && sub.isNotEmpty)
                          Text(
                            sub,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: ln.text.caption.copyWith(color: c.fgMuted),
                          ),
                      ],
                    ),
                  ),
                  if (trailing != null) ...[
                    const SizedBox(width: LnSpace.sm),
                    trailing!,
                  ] else if (checked != null) ...[
                    const SizedBox(width: LnSpace.sm),
                    SelectionMark(selected: checked!),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
    if (action == null) return row;
    return Row(
      children: [
        Expanded(child: row),
        Padding(
          padding: const EdgeInsetsDirectional.only(
            end: LnSpace.pageGutter - 8,
          ),
          child: action!,
        ),
      ],
    );
  }
}
