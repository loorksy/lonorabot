// Transcript rows built from the design kit: owner (blue) and agent (grey) bubbles with quotes,
// edited marks, attachments and reactions; the owner's unsent messages with their delivery
// state; group sender rows; system and tool rows.
import 'dart:typed_data';

import 'package:flutter/material.dart' show SelectableText;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/app_state.dart';
import '../rich/artifact_image.dart' show ArtifactBytesCache;
import '../rich/rich_content_view.dart';
import 'composer_assist.dart' show pendingCommandRich;
import 'conversation_timeline.dart';

/// Lonora's text for a message that only carries files (apps/mobile sends `t("attach")`).
bool isAttachPlaceholder(BuildContext context, String content) {
  final l10n = context.l10n;
  final text = content.trim();
  return text == l10n.translate('attach', 'ar') ||
      text == l10n.translate('attach', 'en');
}

/// A canonical message: bubble (or a bare generated interface), attachments, reactions.
class MessageTile extends StatelessWidget {
  const MessageTile({
    super.key,
    required this.message,
    required this.threadId,
    this.quoted,
    this.quotedAuthor,
    this.artifacts = const {},
    this.onLongPress,
    this.onQuoteTap,
    this.onReactionsTap,
    this.onCallBack,
    this.onSwipeReply,
    this.joinTop = false,
    this.joinBottom = false,
    this.bubbleKey,
    this.bubbleOnly = false,
  });

  /// Keys the bubble (or, for files alone, the files): the long-press menu lifts it from there.
  final GlobalKey? bubbleKey;

  /// Only the bubble (or the files of a files-only message), as the long-press menu redraws it.
  final bool bubbleOnly;

  final Message message;
  final String threadId;

  /// Swipe the bubble toward the end side to reply to it.
  final VoidCallback? onSwipeReply;

  /// The bubble joins the same sender's bubble right above / right below (a bubble run).
  final bool joinTop;
  final bool joinBottom;

  /// A call log's tap calls the agent back (direct conversations with a callable agent).
  final VoidCallback? onCallBack;

  /// The message this one replies to, when it is loaded.
  final Message? quoted;
  final String? quotedAuthor;

  /// The conversation's files by id.
  final Map<String, Json> artifacts;
  final VoidCallback? onLongPress;
  final VoidCallback? onQuoteTap;
  final VoidCallback? onReactionsTap;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final owner = message.fromOwner;
    final parts = message.parts;
    final mark = submitMark(message);
    final edited = message.supersededBy != null || mark == 'superseded';
    final editedLabel = edited
        ? l10n.t('uiSubmitEdited')
        : mark == 'not_run'
        ? l10n.t('uiSubmitNotRun')
        : null;
    final filesOnly =
        owner &&
        message.attachmentIds.isNotEmpty &&
        parts.isEmpty &&
        isAttachPlaceholder(context, message.content);
    final body = RichContentView(
      threadId: threadId,
      text: message.content,
      richContent: message.richContent,
      message: message,
      onUserBubble: owner,
      onCallBack: onCallBack,
    );
    final width = MediaQuery.sizeOf(context).width;
    final quote = quoted == null
        ? null
        : BubbleQuote(
            author: quotedAuthor ?? '',
            text: plainLine(quoted!.content).isEmpty
                ? l10n.t('attachments')
                : plainLine(quoted!.content),
          );

    Widget? main;
    if (!filesOnly) {
      if (!owner && RichContentView.drawsOwnBubbles(message.richContent)) {
        // A generated interface is a card of its own, not text in a bubble.
        main = LnTappable(
          onLongPress: onLongPress,
          haptic: true,
          pressOpacity: 1,
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth: width - 2 * LnSpace.pageGutter,
            ),
            child: body,
          ),
        );
      } else {
        main = MessageBubble(
          sender: owner ? BubbleSender.user : BubbleSender.agent,
          quote: quote,
          editedLabel: editedLabel,
          onTap: quoted == null ? null : onQuoteTap,
          onLongPress: onLongPress,
          joinTop: joinTop,
          joinBottom: joinBottom,
          onSwipeReply: onSwipeReply,
          replyLabel: onSwipeReply == null ? null : l10n.t('reply'),
          child: body,
        );
      }
    }

    final align = owner ? CrossAxisAlignment.end : CrossAxisAlignment.start;
    final files = [
      for (final (i, id) in message.attachmentIds.indexed)
        Padding(
          padding: EdgeInsets.only(
            top: main == null && i == 0 ? 0 : LnSpace.sameSenderGap,
          ),
          child: AttachmentView(
            artifactId: id,
            artifact: artifacts[id],
            onLongPress: onLongPress,
          ),
        ),
    ];
    // Files alone stand for the bubble.
    final lifted =
        main ??
        Column(
          crossAxisAlignment: align,
          mainAxisSize: MainAxisSize.min,
          children: files,
        );
    if (bubbleOnly) return lifted;
    return Column(
      crossAxisAlignment: align,
      mainAxisSize: MainAxisSize.min,
      children: [
        KeyedSubtree(key: bubbleKey, child: lifted),
        if (main != null) ...files,
        if (message.reactions.isNotEmpty)
          ReactionChips(reactions: message.reactions, onTap: onReactionsTap),
      ],
    );
  }
}

/// One chip per emoji with its count; the owner's own reaction is tinted. A tap lists who
/// reacted (a 48 dp touch target around the chips).
class ReactionChips extends StatelessWidget {
  const ReactionChips({super.key, required this.reactions, this.onTap});

  final List<Reaction> reactions;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final counts = <String, int>{};
    for (final r in reactions) {
      counts[r.emoji] = (counts[r.emoji] ?? 0) + 1;
    }
    final mine = ownerReaction(reactions);
    return LnTappable(
      onTap: onTap,
      semanticLabel: '${context.t('reactionsTitle')}: ${counts.keys.join(' ')}',
      excludeChildSemantics: true,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 48, minWidth: 48),
        child: Align(
          widthFactor: 1,
          heightFactor: 1,
          alignment: AlignmentDirectional.centerStart,
          child: Wrap(
            spacing: 4,
            runSpacing: 4,
            children: [
              for (final MapEntry(key: emoji, value: count) in counts.entries)
                Container(
                  padding: const EdgeInsetsDirectional.fromSTEB(8, 4, 8, 4),
                  decoration: ShapeDecoration(
                    color: emoji == mine ? c.reactionSelected : c.fill2,
                    shape: StadiumBorder(
                      side: BorderSide(
                        color: emoji == mine
                            ? c.reactionSelectedBorder
                            : c.border,
                      ),
                    ),
                  ),
                  child: Text(
                    count > 1 ? '$emoji ${isolate('$count')}' : emoji,
                    style: ln.text.caption.copyWith(color: c.fg),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The owner's message the server has not acknowledged: a blue bubble with its delivery state
/// («جارٍ الإرسال», «بانتظار الشبكة…», «لم تُرسل الرسالة» with Retry).
class OutgoingTile extends StatelessWidget {
  const OutgoingTile({
    super.key,
    required this.outgoing,
    this.quoted,
    this.quotedAuthor,
    this.artifacts = const {},
    this.onRetry,
    this.onLongPress,
  });

  final OutgoingMessage outgoing;
  final Message? quoted;
  final String? quotedAuthor;
  final Map<String, Json> artifacts;
  final VoidCallback? onRetry;
  final VoidCallback? onLongPress;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final failed = outgoing.delivery == Delivery.failed;
    final status = switch (outgoing.delivery) {
      Delivery.failed => l10n.t('sendFailed'),
      Delivery.queued => l10n.t('sh_waitingNetwork'),
      Delivery.sending => l10n.t('sending'),
    };
    final content = outgoing.content;
    final filesOnly =
        outgoing.attachmentIds.isNotEmpty &&
        isAttachPlaceholder(context, content);
    final showText = content.trim().isNotEmpty && !filesOnly;
    // Drawn as the server's copy will be: a «/» command's chip and the words after it, the
    // mentions marked.
    final command = pendingCommandRich(outgoing.body);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      mainAxisSize: MainAxisSize.min,
      children: [
        // A failed or waiting message keeps its bubble readable: the line below marks it.
        if (showText)
          MessageBubble(
            sender: BubbleSender.user,
            quote: quoted == null
                ? null
                : BubbleQuote(
                    author: quotedAuthor ?? '',
                    text: plainLine(quoted!.content),
                  ),
            onLongPress: onLongPress,
            child: RichContentView(
              threadId: outgoing.threadId,
              text: content,
              richContent: command,
              onUserBubble: true,
            ),
          ),
        for (final (i, id) in outgoing.attachmentIds.indexed)
          Padding(
            padding: EdgeInsets.only(
              top: !showText && i == 0 ? 0 : LnSpace.sameSenderGap,
            ),
            child: AttachmentView(
              artifactId: id,
              artifact: artifacts[id],
              onLongPress: onLongPress,
            ),
          ),
        Semantics(
          liveRegion: true,
          child: Padding(
            padding: const EdgeInsetsDirectional.only(top: 2),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (failed)
                  Padding(
                    padding: const EdgeInsetsDirectional.only(end: 4),
                    child: Icon(FIcons.circleAlert, size: 14, color: c.error),
                  ),
                Flexible(
                  child: Text(
                    status,
                    style: ln.text.small.copyWith(
                      color: failed ? c.error : c.fgMuted,
                    ),
                  ),
                ),
                if (failed && onRetry != null)
                  RowTextButton(label: l10n.t('retry'), onTap: onRetry!),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// A compact text action inside transcript rows (Retry, Stop, Resume…): a 48 dp touch target
/// around a captionStrong label in the selection blue.
class RowTextButton extends StatelessWidget {
  const RowTextButton({
    super.key,
    required this.label,
    required this.onTap,
    this.enabled = true,
    this.destructive = false,
  });

  final String label;
  final VoidCallback onTap;
  final bool enabled;
  final bool destructive;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: onTap,
      enabled: enabled,
      haptic: true,
      semanticLabel: label,
      excludeChildSemantics: true,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 48, minWidth: 48),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Center(
            widthFactor: 1,
            child: Text(
              label,
              style: ln.text.captionStrong.copyWith(
                color: !enabled
                    ? c.fgSubtle
                    : destructive
                    ? c.error
                    : c.selection,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Group conversations name each agent above its first bubble: 16 dp avatar + grey name.
class SenderRow extends StatelessWidget {
  const SenderRow({super.key, required this.agent, this.fallbackName = ''});

  final Agent? agent;
  final String fallbackName;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final a = agent;
    return Padding(
      padding: const EdgeInsetsDirectional.only(start: 4, bottom: 6),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (a != null) ...[
            LonoraAvatar(
              agentId: a.id,
              face: a.avatar,
              color: a.color,
              tradesOnItsOwn: a.tradesOnItsOwn,
              size: 16,
              animate: false,
            ),
            const SizedBox(width: 6),
          ],
          Flexible(
            child: Text(
              a?.name ?? fallbackName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: ln.text.footnote.copyWith(color: ln.colors.fgMuted),
            ),
          ),
        ],
      ),
    );
  }
}

/// A server system line (group created, member joined…): a centred event row.
class SystemRow extends StatelessWidget {
  const SystemRow({super.key, required this.text});
  final String text;

  @override
  Widget build(BuildContext context) => InlineEventRow(
    icon: const Icon(FIcons.info),
    label: plainLine(text),
    alignment: InlineEventAlignment.center,
    emphasized: true,
    showChevron: false,
    maxLines: 3,
  );
}

/// A tool's raw result, folded: «نتيجة الأداة» opens the text.
class ToolResultRow extends StatefulWidget {
  const ToolResultRow({super.key, required this.message});
  final Message message;

  @override
  State<ToolResultRow> createState() => _ToolResultRowState();
}

class _ToolResultRowState extends State<ToolResultRow> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Semantics(
          expanded: _open,
          child: InlineEventRow(
            icon: const Icon(FIcons.wrench),
            label: context.t('toolResult'),
            alignment: InlineEventAlignment.start,
            showChevron: true,
            onTap: () => setState(() => _open = !_open),
          ),
        ),
        if (_open)
          Container(
            margin: const EdgeInsetsDirectional.only(start: LnSpace.md),
            padding: const EdgeInsets.all(12),
            constraints: BoxConstraints(
              maxWidth: MessageBubble.maxWidthFor(
                MediaQuery.sizeOf(context).width,
              ),
            ),
            decoration: BoxDecoration(
              color: c.fill1,
              borderRadius: const BorderRadius.all(
                Radius.circular(LnRadius.image),
              ),
              border: Border.all(color: c.border),
            ),
            child: SelectableText(
              widget.message.content,
              style: ln.text.footnote.copyWith(color: c.fgMuted),
            ),
          ),
      ],
    );
  }
}

/// An attached file: images inline (≤ 232 dp, radius 16, no border), other files as a card with a
/// type tile, name and size. Bytes come from the authenticated `/artifacts/{id}/file` route;
/// credentials never go into an image URL.
class AttachmentView extends StatelessWidget {
  const AttachmentView({
    super.key,
    required this.artifactId,
    this.artifact,
    this.onLongPress,
  });

  final String artifactId;
  final Json? artifact;
  final VoidCallback? onLongPress;

  static const double imageMax = 232;

  @override
  Widget build(BuildContext context) {
    final payload = asJson(artifact?['payload']);
    final mediaType = asStr(payload['media_type']);
    final name = asString(payload['name']) ?? context.t('attach');
    if (artifact != null && isImageType(mediaType)) {
      return LnTappable(
        onTap: () => context.push(Routes.image(artifactId)),
        onLongPress: onLongPress,
        haptic: true,
        semanticLabel: name,
        excludeChildSemantics: true,
        child: ClipRRect(
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.image)),
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: imageMax,
              maxHeight: imageMax * 1.4,
            ),
            child: ArtifactImage(artifactId: artifactId),
          ),
        ),
      );
    }
    return FileCard(
      name: name,
      mediaType: mediaType,
      size: asInt(payload['size']),
      onTap: () => context.push(Routes.artifact(artifactId)),
      onLongPress: onLongPress,
    );
  }
}

/// A file in the transcript: an outlined card as wide as a bubble can be (radius 24, the surface
/// with a hairline), a coloured type tile with the type's glyph at the start, the name on one
/// 16 dp line and its type and size under it.
class FileCard extends StatelessWidget {
  const FileCard({
    super.key,
    required this.name,
    this.mediaType = '',
    this.size,
    this.onTap,
    this.onLongPress,
  });

  final String name;
  final String mediaType;
  final int? size;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  /// The type tile: 32 × 36 dp at 20 dp from the card's start edge.
  static const Size tile = Size(32, 36);
  static const double tileInset = 20;

  /// The type's glyph and tile colour (Lonora's icon set and palette); null: a neutral tile.
  static (IconData, Color?) typeOf(String mediaType, LnPalette c) {
    final type = mediaType.split(';').first.trim().toLowerCase();
    final sub = type.split('/').last;
    if (type.startsWith('video/')) return (FIcons.filePlay, c.error);
    if (type.startsWith('audio/')) return (FIcons.fileAudio, c.brand);
    if (type.startsWith('image/')) return (FIcons.fileImage, c.success);
    if (sub == 'pdf') return (FIcons.fileText, c.error);
    if (sub.contains('sheet') || sub.contains('excel') || sub == 'csv') {
      return (FIcons.fileSpreadsheet, c.success);
    }
    if (sub.contains('zip') || sub.contains('tar') || sub.contains('rar')) {
      return (FIcons.fileArchive, c.warning);
    }
    if (sub.contains('json') ||
        sub.contains('javascript') ||
        sub.contains('html') ||
        sub.contains('xml')) {
      return (FIcons.fileCode, c.selection);
    }
    if (type.startsWith('text/') ||
        sub.contains('word') ||
        sub.contains('document')) {
      return (FIcons.fileText, c.selection);
    }
    return (FIcons.file, null);
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final badge = mediaType.isEmpty ? '' : mimeBadge(mediaType);
    final detail = [
      if (badge.isNotEmpty) badge,
      if (size != null) formatFileSize(size, context.l10n.lang),
    ].join(dotSeparator);
    final (icon, color) = typeOf(mediaType, c);
    return LnTappable(
      onTap: onTap,
      onLongPress: onLongPress,
      haptic: true,
      semanticLabel: detail.isEmpty ? name : '$name, $detail',
      excludeChildSemantics: true,
      child: Container(
        width: MessageBubble.maxWidthFor(MediaQuery.sizeOf(context).width),
        constraints: const BoxConstraints(minHeight: 68),
        padding: const EdgeInsetsDirectional.fromSTEB(
          tileInset,
          LnSpace.sm,
          LnSpace.md,
          LnSpace.sm,
        ),
        decoration: BoxDecoration(
          color: c.surface,
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.card)),
          border: Border.all(color: c.border),
        ),
        child: Row(
          children: [
            Container(
              width: tile.width,
              height: tile.height,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: color ?? c.fill2,
                borderRadius: const BorderRadius.all(Radius.circular(6)),
              ),
              child: Icon(
                icon,
                size: 20,
                color: color == null ? c.fgMuted : LnPalette.inkWhite,
              ),
            ),
            const SizedBox(width: LnSpace.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: ln.text.body.copyWith(color: c.fg),
                  ),
                  if (detail.isNotEmpty)
                    Text(
                      ltr(detail),
                      maxLines: 1,
                      style: ln.text.caption.copyWith(color: c.fgMuted),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Authenticated image bytes from the shared [ArtifactBytesCache] (scoped to the owner and
/// cleared on sign-out), so scrolling does not refetch.
class ArtifactImage extends StatefulWidget {
  const ArtifactImage({super.key, required this.artifactId});
  final String artifactId;

  @override
  State<ArtifactImage> createState() => _ArtifactImageState();
}

class _ArtifactImageState extends State<ArtifactImage> {
  Uint8List? _bytes;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _bytes = ArtifactBytesCache.peek(widget.artifactId);
    if (_bytes == null) _load();
  }

  Future<void> _load() async {
    await Future<void>.value(); // never set state inside initState
    try {
      final bytes = await ArtifactBytesCache.load(widget.artifactId);
      if (mounted) setState(() => _bytes = bytes);
    } catch (_) {
      // Offline, gone or no session: the placeholder stays; a tap opens the viewer.
      if (mounted) setState(() => _failed = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final bytes = _bytes;
    if (bytes != null) {
      return Image.memory(
        bytes,
        gaplessPlayback: true,
        errorBuilder: (_, _, _) => _placeholder(c, failed: true),
      );
    }
    return _placeholder(c, failed: _failed);
  }

  Widget _placeholder(LnPalette c, {required bool failed}) => Container(
    width: AttachmentView.imageMax,
    height: 160,
    color: c.fill2,
    alignment: Alignment.center,
    child: failed
        ? Icon(FIcons.image, size: 28, color: c.fgSubtle)
        : LnSpinner(size: 18, color: c.fgSubtle),
  );
}
