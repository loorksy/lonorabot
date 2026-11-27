// «التغييرات»: the attributed change log of a memory document with a one-tap undo of one change
// (apps/web/src/pages/MemoryRevisions.tsx, OwnerPage.tsx). Used for an agent's memory and for the
// owner profile. Each edit is a row of the «manage edits» list; opening one shows the whole change
// and its undo. Words are @lonora/core's (`ownerProfileLabel`).
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../settings/settings_common.dart';
import '../profile/agent_data.dart';

/// Who made [row], with its origin (MemoryRevisions.tsx `author`).
String revisionAuthor(MemoryRevision row, String lang) {
  String label(String key) => ownerProfileLabel(key, lang);
  final parts = [
    row.author == 'owner'
        ? label('byOwner')
        : row.author == 'system'
        ? label('bySystem')
        : isolate(row.authorAgentName ?? label('removedAgent')),
    if (row.fromOwnerMessage) label('fromYourMessage'),
    if (row.change == 'revert') label('restoredChange'),
    if (row.change == 'restore') label('restoredVersion'),
  ];
  return parts.join(dotSeparator);
}

/// One change as a line: «أُضيف: …», «حُذف: …» or «الاسم: قديم → جديد».
String revisionChangeLine(Map<String, dynamic> change, String lang) {
  final field = change['field'];
  if (field is String) {
    final before = preferenceValueText(field, change['before'], lang);
    final after = preferenceValueText(field, change['after'], lang);
    // «›» is mirrored by the bidi algorithm, so it points the way the line reads.
    return '${preferenceFieldLabel(field, lang) ?? field}: ${isolate(before)} › ${isolate(after)}';
  }
  final kind = change['change'] == 'removed' ? 'removed' : 'added';
  final text = '${change['text'] ?? ''}'.replaceFirst(RegExp(r'^[-*]\s*'), '');
  return '${ownerProfileLabel(kind, lang)}: ${isolate(text)}';
}

/// «٢٧ نوف ٢٠٢٦ ٠٩:٠٥»: one date label, in [lang]'s date digits.
String revisionTime(DateTime? at, String lang) =>
    at == null ? '' : formatDate('d MMM y HH:mm', lang, at);

/// Whether the server accepts undoing [row]: a move away from «النشاط فقط» is refused
/// (`reach_me_choice_removed`; apps/web OwnerPage.tsx `undoable`).
bool revisionUndoable(MemoryRevision row) => !row.changes.any(
  (c) => c['field'] == 'reach_me' && c['before'] == 'activity',
);

/// The change log as a tile group; [onRevert] undoes one change (the caller reloads). A change
/// already undone shows «استُعيدت» and one the server would refuse offers no undo.
class RevisionList extends StatelessWidget {
  const RevisionList({
    super.key,
    required this.revisions,
    required this.onRevert,
    this.title,
  });

  final List<MemoryRevision> revisions;
  final Future<void> Function(MemoryRevision row) onRevert;
  final String? title;

  /// The changes a later row undid (`reverted_revision_id`).
  Set<String> get _restored => {
    for (final r in revisions) ?r.revertedRevisionId,
  };

  Future<void> _open(
    BuildContext context,
    MemoryRevision row, {
    required bool canUndo,
  }) async {
    final l10n = context.l10n;
    final ln = context.ln;
    final undo = await showLnSheet<bool>(
      context,
      title: revisionAuthor(row, l10n.lang),
      builder: (sheet) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            revisionTime(row.createdAt, l10n.lang),
            style: ln.text.footnote.copyWith(color: ln.colors.fgMuted),
          ),
          const SizedBox(height: LnSpace.sm),
          Flexible(
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final change in row.changes)
                    Padding(
                      padding: const EdgeInsets.only(bottom: LnSpace.xs),
                      child: Text(
                        revisionChangeLine(change, l10n.lang),
                        style: ln.text.body.copyWith(
                          color: change['change'] == 'removed'
                              ? ln.colors.fgMuted
                              : ln.colors.fg,
                        ),
                      ),
                    ),
                  if (row.truncated)
                    Text(
                      ownerProfileLabel('more', l10n.lang),
                      style: ln.text.footnote.copyWith(
                        color: ln.colors.fgMuted,
                      ),
                    ),
                ],
              ),
            ),
          ),
          if (canUndo) ...[
            const SizedBox(height: LnSpace.lg),
            BlockButton(
              label: ownerProfileLabel(
                row.document == 'owner_preferences'
                    ? 'restoreSettings'
                    : 'restore',
                l10n.lang,
              ),
              icon: LnIcons.undo2,
              variant: BlockButtonVariant.secondary,
              onPressed: () => Navigator.of(sheet).pop(true),
            ),
          ],
        ],
      ),
    );
    if (undo == true && context.mounted) await onRevert(row);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final heading = title ?? ownerProfileLabel('history', l10n.lang);
    if (revisions.isEmpty) {
      return LnSection(
        title: heading,
        children: [
          WrapTile(
            icon: FIcons.history,
            title: ownerProfileLabel('noHistory', l10n.lang),
          ),
        ],
      );
    }
    final restored = _restored;
    final muted = context.ln.text.footnote.copyWith(
      color: context.ln.colors.fgMuted,
    );
    return LnSection(
      title: heading,
      children: [
        for (final row in revisions)
          WrapTile(
            icon: row.author == 'owner' ? FIcons.user : FIcons.bot,
            title: revisionAuthor(row, l10n.lang),
            subtitle: [
              revisionTime(row.createdAt, l10n.lang),
              if (row.changes.isNotEmpty)
                revisionChangeLine(row.changes.first, l10n.lang),
            ].join('\n'),
            trailing: restored.contains(row.id)
                ? Text(l10n.t('ag_restoredBadge'), style: muted)
                : revisionUndoable(row)
                ? const Icon(LnIcons.undo2)
                : null,
            onTap: () => _open(
              context,
              row,
              canUndo: !restored.contains(row.id) && revisionUndoable(row),
            ),
          ),
      ],
    );
  }
}
