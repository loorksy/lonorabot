// Message long-press menu: the six quick reactions, then Reply · Copy · Select text · …; geometry
// composed from the kit's sheet and forui items. Lonora has no route to forward or delete a sent
// message (api contract §5.4), so those entries are not offered; an unsent message offers Retry and
// Delete (local, confirmed).
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../rich/rich_content_view.dart';

/// Opens the menu of a message. [onReact] receives the new owner reaction (null removes it);
/// leave it null to hide the reactions row. Each action runs after the sheet has closed (and
/// only while [context] is still mounted).
Future<void> showMessageMenu(
  BuildContext context, {
  required List<LnMenuAction<void>> actions,
  String? ownReaction,
  ValueChanged<String?>? onReact,
  String? title,
}) async {
  VoidCallback? chosen;
  await showLnSheet<void>(
    context,
    title: title,
    padding: const EdgeInsetsDirectional.fromSTEB(8, 0, 8, 8),
    builder: (sheet) => SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (onReact != null)
            Padding(
              padding: const EdgeInsets.only(bottom: LnSpace.sm),
              child: ReactionPicker(
                selected: ownReaction,
                onPick: (emoji) {
                  chosen = () => onReact(emoji == ownReaction ? null : emoji);
                  Navigator.of(sheet).pop();
                },
              ),
            ),
          if (actions.isNotEmpty)
            FItemGroup(
              children: [
                for (final a in actions)
                  _item(sheet, a, () {
                    chosen = a.onSelected;
                    Navigator.of(sheet).pop();
                  }),
              ],
            ),
        ],
      ),
    ),
  );
  if (context.mounted) chosen?.call();
}

FItem _item(BuildContext context, LnMenuAction<void> a, VoidCallback onPress) {
  final c = context.ln.colors;
  final color = a.destructive ? c.error : null;
  return FItem(
    enabled: a.enabled,
    onPress: onPress,
    prefix: a.icon == null ? null : Icon(a.icon, color: color),
    title: Text(a.label, style: color == null ? null : TextStyle(color: color)),
  );
}

/// The six reactions the server accepts, the owner's own one highlighted.
class ReactionPicker extends StatelessWidget {
  const ReactionPicker({super.key, this.selected, required this.onPick});

  final String? selected;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final l10n = context.l10n;
    return Semantics(
      label: l10n.t('quickReaction'),
      container: true,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          for (final emoji in reactionEmojis)
            LnTappable(
              onTap: () => onPick(emoji),
              haptic: true,
              selected: emoji == selected,
              semanticLabel: l10n.t('reactWith', [emoji]),
              excludeChildSemantics: true,
              child: Container(
                width: 48,
                height: 48,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: emoji == selected ? c.fill4 : null,
                ),
                child: Text(
                  emoji,
                  style: const TextStyle(fontSize: LnSize.reactionPickerEmoji),
                ),
              ),
            ),
        ],
      ),
    );
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
/// plain text) and selectable. A generated interface stays in the transcript: the sheet shows
/// the message's text.
Future<void> showSelectTextSheet(
  BuildContext context, {
  required Message message,
  required String threadId,
}) => showLnSheet<void>(
  context,
  title: context.t('conv_selectText'),
  builder: (sheet) => SingleChildScrollView(
    child: Padding(
      padding: const EdgeInsetsDirectional.symmetric(horizontal: 4),
      child: Align(
        alignment: AlignmentDirectional.centerStart,
        child: DefaultTextStyle.merge(
          style: sheet.ln.text.body.copyWith(color: sheet.ln.colors.fg),
          child: RichContentView(
            threadId: threadId,
            text: message.content,
            richContent: RichContentView.drawsOwnBubbles(message.richContent)
                ? null
                : message.richContent,
            onUserBubble: message.fromOwner,
            selectable: true,
          ),
        ),
      ),
    ),
  ),
);
