import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../l10n/bidi.dart' show textDirectionFor;
import '../theme.dart';
import '../tokens.dart';
import 'badges.dart';
import 'tappable.dart';

/// How a row's preview line is decorated.
enum ChatPreviewKind {
  /// Plain muted preview.
  normal,

  /// Unsent draft: the prefix (e.g. "Draft:") is shown in the brand colour.
  draft,

  /// Last message failed to send: alert icon and prefix in the error colour.
  failed,

  /// Agent is working: preview shown in the brand colour.
  active,
}

/// Conversation row (66 dp, 24 dp side insets, 44 dp avatar slot, title 16/500, time 14 muted, one-line
/// muted preview). No dividers. Supports unread pill/dot, pinned and muted marks, draft/failed preview
/// prefixes and a selection state. The title and preview read in their own direction (an English
/// preview in the Arabic interface reads left to right, its ellipsis at the end of the English run)
/// and stay aligned to the interface's start.
///
/// [ChatListRow.compact] is the chat drawer's row.
class ChatListRow extends StatelessWidget {
  const ChatListRow({
    super.key,
    required this.avatar,
    required this.title,
    this.preview,
    this.time,
    this.previewKind = ChatPreviewKind.normal,
    this.previewPrefix,
    this.unreadCount = 0,
    this.unreadDot = false,
    this.pinned = false,
    this.muted = false,
    this.selected = false,
    this.selectionMode = false,
    this.onTap,
    this.onLongPress,
    this.semanticLabel,
    this.unreadLabel,
    this.pinnedLabel,
    this.mutedLabel,
  }) : compact = false,
       current = false;

  /// The chat drawer's row: 62 dp pitch, 32 dp avatar slot whose start is 22 dp from the edge, a
  /// one-line 16/500 title 20 dp after it (muted and pinned marks follow it), and the time and
  /// unread pill or dot at the end, 28 dp from the edge. [preview] adds a one-line 14 dp second line
  /// with the same decorations as the full row; leave it null for the name-only row. [current]
  /// marks the open conversation: a [LnPalette.fill1] rounded rect (radius 16, 60 dp tall, 8 dp from
  /// both edges) and the selected flag for screen readers. A selected row in [selectionMode] takes
  /// the full row's [LnPalette.fill2] in the same shape.
  ///
  /// A [GroupAvatarPair] passed here should use `size: 20` to fit the 32 dp column.
  const ChatListRow.compact({
    super.key,
    required this.avatar,
    required this.title,
    this.preview,
    this.time,
    this.previewKind = ChatPreviewKind.normal,
    this.previewPrefix,
    this.unreadCount = 0,
    this.unreadDot = false,
    this.pinned = false,
    this.muted = false,
    this.current = false,
    this.selected = false,
    this.selectionMode = false,
    this.onTap,
    this.onLongPress,
    this.semanticLabel,
    this.unreadLabel,
    this.pinnedLabel,
    this.mutedLabel,
  }) : compact = true;

  /// Compact geometry (dp). Lonora-specific values for the drawer.
  static const double compactPitch = 62;
  static const double compactAvatar = 32;
  static const double compactAvatarInset = 22;
  static const double compactTextGap = 20;
  static const double compactHighlightHeight = 60;
  static const double compactHighlightInset = LnSpace.xs;
  static const double compactRadius = 16;

  /// Avatar in a 44 × 44 slot (32 × 32 in [ChatListRow.compact]; [GroupAvatarPair] may overflow
  /// it).
  final Widget avatar;
  final String title;
  final String? preview;

  /// Pre-formatted time ("10:12", "Thursday", "Nov 22").
  final String? time;
  final ChatPreviewKind previewKind;

  /// Localised prefix such as "Draft:" or "Not sent:".
  final String? previewPrefix;
  final int unreadCount;
  final bool unreadDot;
  final bool pinned;
  final bool muted;
  final bool selected;

  /// The [ChatListRow.compact] layout.
  final bool compact;

  /// The open conversation, highlighted in the drawer ([ChatListRow.compact] only).
  final bool current;

  /// Shows the selection check affordance on every row.
  final bool selectionMode;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  /// Overrides the composed accessibility label.
  final String? semanticLabel;

  /// Localized words of the composed label: the unread count ("3 unread"), "pinned" and "muted".
  /// English when omitted.
  final String? unreadLabel;
  final String? pinnedLabel;
  final String? mutedLabel;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final hasUnread = unreadCount > 0 || unreadDot;
    final ui = Directionality.of(context);
    final align = ui == TextDirection.rtl ? TextAlign.right : TextAlign.left;

    final timeText = Text(
      time ?? '',
      maxLines: 1,
      style: ln.text.caption.copyWith(
        color: hasUnread && !muted ? c.brand : c.fgMuted,
      ),
    );
    final Widget unread = unreadCount > 0
        ? UnreadPill(count: unreadCount, muted: muted)
        : DotBadge(ring: false, color: muted ? c.fgSubtle : c.brand);

    final titleRow = Row(
      children: [
        Expanded(
          child: Text(
            title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textDirection: textDirectionFor(title, ui),
            textAlign: align,
            style: ln.text.title.copyWith(color: c.fg),
          ),
        ),
        if (muted) ...[
          const SizedBox(width: 4),
          Icon(FIcons.bellOff, size: 14, color: c.fgSubtle),
        ],
        if (pinned) ...[
          const SizedBox(width: 4),
          Icon(FIcons.pin, size: 14, color: c.fgSubtle),
        ],
        if (time != null && !compact) ...[const SizedBox(width: 8), timeText],
      ],
    );

    final prefixColor = switch (previewKind) {
      ChatPreviewKind.draft => c.brand,
      ChatPreviewKind.failed => c.error,
      _ => c.fgMuted,
    };
    final previewStyle = ln.text.caption.copyWith(
      color: previewKind == ChatPreviewKind.active ? c.brand : c.fgMuted,
    );
    final prefixStyle = ln.text.caption.copyWith(color: prefixColor);
    // Each part reads in the direction of its own letters (the interface's when it has none).
    final previewDirection = textDirectionFor(preview ?? '', ui);
    final prefixDirection = previewPrefix == null
        ? previewDirection
        : textDirectionFor(previewPrefix!, ui);
    final previewRow = Row(
      children: [
        if (previewKind == ChatPreviewKind.failed) ...[
          Icon(FIcons.circleAlert, size: 14, color: c.error),
          const SizedBox(width: 4),
        ],
        Expanded(
          child: prefixDirection == previewDirection
              ? Text.rich(
                  TextSpan(
                    children: [
                      if (previewPrefix != null)
                        TextSpan(text: '$previewPrefix ', style: prefixStyle),
                      TextSpan(text: preview ?? ''),
                    ],
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textDirection: previewDirection,
                  textAlign: align,
                  style: previewStyle,
                )
              // A prefix and a message in different directions ("أنت:" before English, an
              // English speaker before Arabic) each read in their own direction; the prefix
              // leads at the interface's start and takes at most half the line.
              : LayoutBuilder(
                  builder: (context, constraints) => Row(
                    children: [
                      ConstrainedBox(
                        constraints: BoxConstraints(
                          maxWidth: constraints.maxWidth / 2,
                        ),
                        child: Text(
                          previewPrefix!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          textDirection: prefixDirection,
                          style: prefixStyle,
                        ),
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          preview ?? '',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          textDirection: previewDirection,
                          textAlign: align,
                          style: previewStyle,
                        ),
                      ),
                    ],
                  ),
                ),
        ),
        if (hasUnread && !compact) ...[const SizedBox(width: 8), unread],
      ],
    );

    final label =
        semanticLabel ??
        [
          title,
          if (unreadCount > 0) unreadLabel ?? '$unreadCount unread',
          ?previewPrefix,
          ?preview,
          ?time,
          if (pinned) pinnedLabel ?? 'pinned',
          if (muted) mutedLabel ?? 'muted',
        ].join(', ');

    if (compact) {
      return LnTappable(
        onTap: onTap,
        onLongPress: onLongPress,
        pressScale: 0.985,
        pressOpacity: 1,
        selected: selectionMode ? selected : (current ? true : null),
        semanticLabel: label,
        excludeChildSemantics: true,
        child: SizedBox(
          height: compactPitch,
          child: Center(
            child: AnimatedContainer(
              duration: LnMotion.fast,
              height: compactHighlightHeight,
              margin: const EdgeInsetsDirectional.symmetric(
                horizontal: compactHighlightInset,
              ),
              // Avatar 22 dp and trailing marks 28 dp from the drawer's edges.
              padding: const EdgeInsetsDirectional.fromSTEB(
                compactAvatarInset - compactHighlightInset,
                0,
                LnSpace.lg,
                0,
              ),
              decoration: BoxDecoration(
                color: selected
                    ? c.fill2
                    : current
                    ? c.fill1
                    : const Color(0x00000000),
                borderRadius: const BorderRadius.all(
                  Radius.circular(compactRadius),
                ),
              ),
              child: Row(
                children: [
                  SizedBox.square(
                    dimension: compactAvatar,
                    child: Stack(
                      clipBehavior: Clip.none,
                      alignment: Alignment.center,
                      children: [
                        avatar,
                        if (selectionMode)
                          PositionedDirectional(
                            end: -6,
                            bottom: -6,
                            child: SelectionMark(selected: selected),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(width: compactTextGap),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        titleRow,
                        if (preview != null || previewPrefix != null) ...[
                          const SizedBox(height: 1.5),
                          previewRow,
                        ],
                      ],
                    ),
                  ),
                  if (time != null) ...[const SizedBox(width: 8), timeText],
                  if (hasUnread) ...[const SizedBox(width: 8), unread],
                ],
              ),
            ),
          ),
        ),
      );
    }

    return LnTappable(
      onTap: onTap,
      onLongPress: onLongPress,
      pressScale: 0.985,
      pressOpacity: 1,
      selected: selectionMode ? selected : null,
      semanticLabel: label,
      excludeChildSemantics: true,
      child: AnimatedContainer(
        duration: LnMotion.fast,
        height: LnSize.listRow,
        margin: const EdgeInsetsDirectional.symmetric(horizontal: LnSpace.xs),
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: LnSpace.listInset - LnSpace.xs,
        ),
        decoration: BoxDecoration(
          color: selected ? c.fill2 : const Color(0x00000000),
          borderRadius: const BorderRadius.all(Radius.circular(18)),
        ),
        child: Row(
          children: [
            SizedBox.square(
              dimension: LnSize.avatarList,
              child: Stack(
                clipBehavior: Clip.none,
                alignment: Alignment.center,
                children: [
                  avatar,
                  if (selectionMode)
                    PositionedDirectional(
                      end: -4,
                      bottom: -4,
                      child: SelectionMark(selected: selected),
                    ),
                ],
              ),
            ),
            const SizedBox(width: LnSpace.listTextGap),
            Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [titleRow, const SizedBox(height: 1.5), previewRow],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The round check of a selectable row (22 dp): the selection colour with a white check when on, the
/// surface with a subtle ring when off. Decorative: the row carries the selected state.
class SelectionMark extends StatelessWidget {
  const SelectionMark({super.key, required this.selected});

  final bool selected;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    return AnimatedContainer(
      duration: LnMotion.fast,
      width: 22,
      height: 22,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: selected ? c.selection : c.surface,
        border: Border.all(
          color: selected ? c.surface : c.fgSubtle,
          width: 1.5,
        ),
      ),
      child: selected ? Icon(FIcons.check, size: 14, color: c.onAccent) : null,
    );
  }
}

/// Two 28 dp avatars side by side, 1 dp apart, centred on the 44 dp avatar column (the pair
/// overflows it slightly).
class GroupAvatarPair extends StatelessWidget {
  const GroupAvatarPair({
    super.key,
    required this.first,
    required this.second,
    this.size = LnSize.avatarGroup,
  });

  final Widget first;
  final Widget second;
  final double size;

  @override
  Widget build(BuildContext context) => SizedBox.square(
    dimension: LnSize.avatarList,
    child: OverflowBox(
      maxWidth: size * 2 + 1,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox.square(dimension: size, child: first),
          const SizedBox(width: 1),
          SizedBox.square(dimension: size, child: second),
        ],
      ),
    ),
  );
}
