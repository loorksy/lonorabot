// Message long-press menu, anchored to the message: everything behind it blurred, the message
// lifted at its place, the six quick reactions above it and Reply · Copy · Select text · … below
// it under the message's time. Lonora has no route to forward or delete a sent message (api
// contract §5.4), so those entries are not offered; an unsent message offers Retry and Delete
// (local, confirmed).
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../rich/rich_content_view.dart';

/// Opens the menu of the message drawn by [target] at [targetKey] (the same message, laid out at
/// its size). [onReact] receives the new owner reaction (null removes it); leave it null to hide
/// the reactions pill. [header] tops the menu card (the message's time). Each action runs after
/// the menu has closed (and only while [context] is still mounted).
Future<void> showMessageMenu(
  BuildContext context, {
  required Widget target,
  required GlobalKey targetKey,
  required List<LnMenuAction<String>> actions,
  String? ownReaction,
  ValueChanged<String?>? onReact,
  String? header,
}) async {
  final l10n = context.l10n;
  if (targetKey.currentContext == null) return;
  final picked = await showLnAnchoredMenu<String>(
    context,
    target: target,
    targetKey: targetKey,
    header: header,
    reactionsLabel: l10n.t('quickReaction'),
    reactions: [
      if (onReact != null)
        for (final emoji in reactionEmojis)
          LnReactionOption(
            value: emoji,
            selected: emoji == ownReaction,
            semanticLabel: l10n.t('reactWith', [emoji]),
            child: Text(
              emoji,
              style: const TextStyle(fontSize: LnSize.reactionPickerEmoji),
            ),
          ),
    ],
    actions: [
      for (final a in actions)
        LnMenuAction<String>(
          label: a.label,
          icon: a.icon,
          destructive: a.destructive,
          enabled: a.enabled,
          onSelected: a.onSelected == null
              ? null
              : () {
                  if (context.mounted) a.onSelected!();
                },
        ),
    ],
  );
  if (picked != null && onReact != null && context.mounted) {
    onReact(picked == ownReaction ? null : picked);
  }
}

/// Who reacted to a message; the owner's own reaction is removed with a tap.
Future<void> showReactionsSheet(
  BuildContext context, {
  required List<Reaction> reactions,
  required String Function(String reactor) nameOf,
  required VoidCallback onRemoveOwn,
}) async {
  final l10n = context.l10n;
  var remove = false;
  await showLnSheet<void>(
    context,
    title: l10n.t('reactionsTitle'),
    padding: const EdgeInsetsDirectional.fromSTEB(8, 0, 8, 8),
    builder: (sheet) => SingleChildScrollView(
      child: FItemGroup(
        children: [
          for (final r in reactions)
            FItem(
              prefix: Text(
                r.emoji,
                style: const TextStyle(fontSize: LnSize.reactionListEmoji),
              ),
              title: Text(
                r.reactor == 'owner'
                    ? l10n.t('reactionYou')
                    : nameOf(r.reactor),
              ),
              subtitle: r.reactor == 'owner'
                  ? Text(l10n.t('tapToRemove'))
                  : null,
              onPress: r.reactor == 'owner'
                  ? () {
                      remove = true;
                      Navigator.of(sheet).pop();
                    }
                  : null,
            ),
        ],
      ),
    ),
  );
  if (remove && context.mounted) onRemoveOwn();
}

/// «تحديد النص»: the message's words, drawn as in the transcript (agent Markdown, the owner's
/// plain text) and selectable, on a full-height page sheet with a centred title and a ✕. A
/// generated interface stays in the transcript: the sheet shows the message's text.
Future<void> showSelectTextSheet(
  BuildContext context, {
  required Message message,
  required String threadId,
}) {
  final l10n = context.l10n;
  return showLnStackedSheet<void>(
    context,
    builder: (sheet) {
      final ln = sheet.ln;
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          LnSheetHeader(
            title: l10n.t('conv_selectText'),
            closeLabel: l10n.t('close'),
            plainClose: true,
          ),
          Expanded(
            child: SingleChildScrollView(
              controller: LnStackedSheet.scrollControllerOf(sheet),
              padding: EdgeInsets.fromLTRB(
                LnSpace.pageGutter,
                LnSpace.md,
                LnSpace.pageGutter,
                LnSpace.md + MediaQuery.paddingOf(sheet).bottom,
              ),
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: DefaultTextStyle.merge(
                  style: ln.text.body.copyWith(color: ln.colors.fgWarm),
                  child: RichContentView(
                    threadId: threadId,
                    text: message.content,
                    richContent:
                        RichContentView.drawsOwnBubbles(message.richContent)
                        ? null
                        : message.richContent,
                    onUserBubble: message.fromOwner,
                    selectable: true,
                  ),
                ),
              ),
            ),
          ),
        ],
      );
    },
  );
}
