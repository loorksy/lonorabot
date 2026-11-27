// «المعرفة»: an agent's notes and links (apps/web/src/shell/domain/GoalsKnowledgePages.tsx
// `KnowledgePage`, `KnowledgeEditPage`; lonora-api-contract §9): list, add a note (title,
// content) or a link (title, http(s) link, note), edit, delete (confirmed). Notes are indexed
// semantic notes (`/agents/{id}/knowledge/notes`); links are agent-bound resources
// (`/knowledge-links`). Composed from the kit.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../settings/settings_common.dart';
import '../profile/agent_data.dart';
import '../profile/agent_page.dart';

/// The first 140 characters, cut by runes so an emoji is never split.
String _preview(String text) {
  final runes = text.runes;
  return runes.length <= 140
      ? text
      : '${String.fromCharCodes(runes.take(140))}…';
}

class KnowledgeSection extends StatelessWidget {
  const KnowledgeSection({
    super.key,
    required this.agentId,
    required this.items,
    required this.onChanged,
  });

  final String agentId;
  final List<KnowledgeItem> items;

  /// Reloads the list after a save or a delete.
  final Future<void> Function() onChanged;

  Future<void> _edit(BuildContext context, [KnowledgeItem? item]) async {
    final changed = await showLnSheet<bool>(
      context,
      maxHeightFraction: 0.92,
      title: context.t(item == null ? 'ag_addKnowledge' : 'ag_editKnowledge'),
      builder: (_) => KnowledgeEditor(agentId: agentId, item: item),
    );
    if (changed == true) await onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final ln = context.ln;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (items.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: LnSpace.xxl),
            child: EmptyState(
              icon: FIcons.bookOpen,
              title: l10n.t('ag_noKnowledge'),
              body: l10n.t('memoryHint'),
            ),
          )
        else
          LnSection(
            children: [
              for (final item in items)
                WrapTile(
                  icon: item.isLink ? FIcons.link : FIcons.notebookPen,
                  title: isolate(item.title),
                  subtitle: item.isLink
                      ? ltr(item.url ?? '')
                      : isolate(_preview(item.content)),
                  trailing: Text(
                    l10n.t(item.isLink ? 'ag_link' : 'ag_note'),
                    style: ln.text.footnote.copyWith(color: ln.colors.fgMuted),
                  ),
                  onTap: () => _edit(context, item),
                ),
            ],
          ),
        const SizedBox(height: LnSpace.lg),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
          child: BlockButton(
            label: l10n.t('ag_addKnowledge'),
            icon: FIcons.plus,
            variant: BlockButtonVariant.secondary,
            onPressed: () => _edit(context),
          ),
        ),
      ],
    );
  }
}

/// The note or link form; pops true after a save or a delete.
class KnowledgeEditor extends StatefulWidget {
  const KnowledgeEditor({super.key, required this.agentId, this.item});

  final String agentId;
  final KnowledgeItem? item;

  @override
  State<KnowledgeEditor> createState() => _KnowledgeEditorState();
}

class _KnowledgeEditorState extends State<KnowledgeEditor> {
  late bool _link = widget.item?.isLink ?? false;
  late final _title = TextEditingController(text: widget.item?.title ?? '');
  late final _url = TextEditingController(text: widget.item?.url ?? '');
  late final _content = TextEditingController(text: widget.item?.content ?? '');
  bool _busy = false;
  bool _tried = false;

  @override
  void initState() {
    super.initState();
    for (final c in [_title, _url, _content]) {
      c.addListener(() => setState(() {}));
    }
  }

  @override
  void dispose() {
    for (final c in [_title, _url, _content]) {
      c.dispose();
    }
    super.dispose();
  }

  bool get _valid =>
      _title.text.trim().isNotEmpty &&
      (_link ? isWebUrl(_url.text) : _content.text.trim().isNotEmpty);

  Future<void> _save() async {
    setState(() => _tried = true);
    if (!_valid || _busy) return;
    setState(() => _busy = true);
    final item = widget.item;
    final title = _title.text.trim();
    try {
      if (_link) {
        final link = {
          'title': title,
          'url': _url.text.trim(),
          'note': _content.text.trim(),
        };
        if (item != null && item.isLink && item.version != null) {
          await saveKnowledgeLink(item.id, item.version!, link);
        } else {
          await addKnowledgeLink(widget.agentId, link);
        }
      } else if (item != null && !item.isLink) {
        await saveKnowledgeNote(
          widget.agentId,
          item.id,
          title,
          _content.text.trim(),
        );
      } else {
        await addKnowledgeNote(widget.agentId, title, _content.text.trim());
      }
      if (!mounted) return;
      LnToast.show(
        context,
        context.t('ag_knowledgeSaved'),
        kind: LnToastKind.positive,
      );
      Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  Future<void> _delete() async {
    final item = widget.item;
    if (item == null || _busy) return;
    final l10n = context.l10n;
    final ok = await showLnConfirm(
      context,
      title: l10n.t('ag_deleteKnowledgeQ'),
      message: l10n.t('ag_deleteKnowledgeBody'),
      confirmLabel: l10n.t('delete'),
      cancelLabel: l10n.t('cancelAction'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() => _busy = true);
    try {
      if (item.isLink) {
        await deleteKnowledgeLink(item.id);
      } else {
        await deleteKnowledgeNote(widget.agentId, item.id);
      }
      if (!mounted) return;
      LnToast.show(
        context,
        l10n.t('ag_knowledgeDeleted'),
        kind: LnToastKind.positive,
      );
      Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    const tight = EdgeInsetsDirectional.only(top: LnSpace.sm);
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.item == null)
            LnSegmented<bool>(
              segments: [
                LnSegment(value: false, label: l10n.t('ag_note')),
                LnSegment(value: true, label: l10n.t('ag_link')),
              ],
              selected: _link,
              onChanged: (v) => setState(() => _link = v),
            ),
          ContentField(
            controller: _title,
            label: l10n.t('ag_titleField'),
            maxLength: 160,
            enabled: !_busy,
            padding: tight,
            error: _tried && _title.text.trim().isEmpty
                ? l10n.t('ag_titleRequired')
                : null,
          ),
          if (_link)
            ContentField(
              controller: _url,
              label: l10n.t('ag_urlField'),
              hint: 'https://',
              ltrOnly: true,
              keyboardType: TextInputType.url,
              maxLength: 2000,
              enabled: !_busy,
              padding: tight,
              error: _tried && !isWebUrl(_url.text)
                  ? l10n.t('ag_invalidUrl')
                  : null,
            ),
          ContentField(
            controller: _content,
            label: l10n.t('ag_contentField'),
            minLines: 4,
            maxLines: 10,
            maxLength: _link ? 4000 : 8000,
            enabled: !_busy,
            padding: tight,
            error: _tried && !_link && _content.text.trim().isEmpty
                ? l10n.t('ag_contentRequired')
                : null,
          ),
          const SizedBox(height: LnSpace.lg),
          BlockButton(label: l10n.t('save'), loading: _busy, onPressed: _save),
          if (widget.item != null) ...[
            const SizedBox(height: LnSpace.xs),
            BlockButton(
              label: l10n.t('delete'),
              icon: FIcons.trash2,
              variant: BlockButtonVariant.destructive,
              onPressed: _busy ? null : _delete,
            ),
          ],
        ],
      ),
    );
  }
}
