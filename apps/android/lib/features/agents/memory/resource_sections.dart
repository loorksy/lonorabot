// «الأهداف» and «مسودة العمل»: an agent's light goals (their own tab) and its scratchpad (a group
// under Knowledge, as the Web's Knowledge page holds it), Lonora's generic
// agent-bound resources (apps/web/src/shell/domain/GoalsKnowledgePages.tsx `GoalsPage`,
// `GoalEditPage`; apps/web/src/pages/ScratchpadSection.tsx). Goals: list, add, edit, mark
// completed (`/agent-goals`; a light goal schedules nothing and grants no authority).
// Scratchpad: list, add, edit, delete (confirmed) (`/scratchpad`). Every edit sends the row's
// version. Composed from the kit.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons, FTileMixin;

import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../settings/settings_common.dart';
import '../profile/agent_data.dart';
import '../profile/agent_page.dart';

/// The first 140 characters, cut by runes so an emoji is never split.
String _preview(String text) {
  final t = text.trim().replaceAll(RegExp(r'\s+'), ' ');
  final runes = t.runes;
  return runes.length <= 140 ? t : '${String.fromCharCodes(runes.take(140))}…';
}

/// A list of [rows] with an add button. With a [title] it is one titled group among others
/// (an empty list is one row); without, it fills its tab (an empty state).
class _ResourceList extends StatelessWidget {
  const _ResourceList({
    this.title,
    required this.rows,
    required this.emptyIcon,
    required this.emptyTitle,
    required this.addLabel,
    required this.tile,
    required this.onOpen,
  });

  final String? title;
  final List<AgentResource> rows;
  final IconData emptyIcon;
  final String emptyTitle;
  final String addLabel;
  final FTileMixin Function(AgentResource row) tile;
  final void Function([AgentResource? row]) onOpen;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (rows.isEmpty && title == null)
        Padding(
          padding: const EdgeInsets.only(top: LnSpace.xxl),
          child: EmptyState(icon: emptyIcon, title: emptyTitle),
        )
      else
        LnSection(
          title: title,
          children: [
            if (rows.isEmpty) WrapTile(icon: emptyIcon, title: emptyTitle),
            for (final row in rows) tile(row),
          ],
        ),
      const SizedBox(height: LnSpace.lg),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
        child: BlockButton(
          label: addLabel,
          icon: FIcons.plus,
          variant: BlockButtonVariant.secondary,
          onPressed: onOpen,
        ),
      ),
    ],
  );
}

class GoalsSection extends StatelessWidget {
  const GoalsSection({
    super.key,
    required this.agentId,
    required this.rows,
    required this.onChanged,
  });

  final String agentId;
  final List<AgentResource> rows;
  final Future<void> Function() onChanged;

  Future<void> _open(BuildContext context, [AgentResource? row]) async {
    final saved = await showLnSheet<bool>(
      context,
      maxHeightFraction: 0.92,
      title: context.t(row == null ? 'ag_addGoal' : 'ag_editGoal'),
      builder: (_) => GoalEditor(agentId: agentId, row: row),
    );
    if (saved == true) await onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final muted = context.ln.text.footnote.copyWith(
      color: context.ln.colors.fgMuted,
    );
    return _ResourceList(
      rows: rows,
      emptyIcon: FIcons.target,
      emptyTitle: l10n.t('ag_noGoals'),
      addLabel: l10n.t('ag_addGoal'),
      onOpen: ([row]) => _open(context, row),
      tile: (row) {
        final done = row.payload['done'] == true;
        final description = row.text('description');
        return WrapTile(
          icon: done ? FIcons.circleCheck : FIcons.target,
          title: isolate(row.text('title')),
          subtitle: description.isEmpty ? null : isolate(_preview(description)),
          trailing: Text(l10n.t(done ? 'completed' : 'active'), style: muted),
          onTap: () => _open(context, row),
        );
      },
    );
  }
}

/// «تحرير الهدف»: title, description and Completed; pops true once saved.
class GoalEditor extends StatefulWidget {
  const GoalEditor({super.key, required this.agentId, this.row});

  final String agentId;
  final AgentResource? row;

  @override
  State<GoalEditor> createState() => _GoalEditorState();
}

class _GoalEditorState extends State<GoalEditor> {
  late final _title = TextEditingController(text: widget.row?.text('title'));
  late final _description = TextEditingController(
    text: widget.row?.text('description'),
  );
  late bool _done = widget.row?.payload['done'] == true;
  bool _busy = false;
  bool _tried = false;

  @override
  void initState() {
    super.initState();
    _title.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _title.dispose();
    _description.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _tried = true);
    final title = _title.text.trim();
    if (title.isEmpty || _busy) return;
    final goal = {
      'title': title,
      'description': _description.text.trim(),
      'done': _done,
    };
    setState(() => _busy = true);
    try {
      final row = widget.row;
      if (row == null) {
        await createAgentResource(goalsKind, widget.agentId, goal);
      } else {
        await saveAgentResource(goalsKind, row, goal);
      }
      if (!mounted) return;
      LnToast.show(context, context.t('saved'), kind: LnToastKind.positive);
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
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ContentField(
            controller: _title,
            label: l10n.t('ag_goalTitle'),
            maxLength: 160,
            enabled: !_busy,
            padding: EdgeInsets.zero,
            error: _tried && _title.text.trim().isEmpty
                ? l10n.t('ag_titleRequired')
                : null,
          ),
          ContentField(
            controller: _description,
            label: l10n.t('description'),
            minLines: 3,
            maxLines: 8,
            maxLength: 2000,
            enabled: !_busy,
            padding: const EdgeInsets.only(top: LnSpace.sm),
          ),
          const SizedBox(height: LnSpace.sm),
          LnSection(
            padding: EdgeInsets.zero,
            children: [
              SwitchTile(
                icon: FIcons.circleCheck,
                title: l10n.t('completed'),
                value: _done,
                onChanged: _busy ? null : (v) => setState(() => _done = v),
              ),
            ],
          ),
          const SizedBox(height: LnSpace.lg),
          BlockButton(label: l10n.t('save'), loading: _busy, onPressed: _save),
        ],
      ),
    );
  }
}

class ScratchpadSection extends StatelessWidget {
  const ScratchpadSection({
    super.key,
    required this.agentId,
    required this.rows,
    required this.onChanged,
  });

  final String agentId;
  final List<AgentResource> rows;
  final Future<void> Function() onChanged;

  Future<void> _open(BuildContext context, [AgentResource? row]) async {
    final saved = await showLnSheet<bool>(
      context,
      maxHeightFraction: 0.92,
      title: context.t(row == null ? 'ag_addScratch' : 'ag_editScratch'),
      builder: (_) => ScratchEditor(agentId: agentId, row: row),
    );
    if (saved == true) await onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return _ResourceList(
      title: l10n.t('ag_scratchpadTab'),
      rows: rows,
      emptyIcon: FIcons.notebookText,
      emptyTitle: l10n.t('ag_noScratchpad'),
      addLabel: l10n.t('ag_addScratch'),
      onOpen: ([row]) => _open(context, row),
      tile: (row) {
        final content = row.text('content');
        return WrapTile(
          icon: FIcons.notebookText,
          title: isolate(row.text('title')),
          subtitle: content.trim().isEmpty ? null : isolate(_preview(content)),
          trailing: const TileChevron(),
          onTap: () => _open(context, row),
        );
      },
    );
  }
}

/// One scratchpad item: title and content, Save, and Delete (confirmed) for an existing one;
/// pops true after a save or a delete.
class ScratchEditor extends StatefulWidget {
  const ScratchEditor({super.key, required this.agentId, this.row});

  final String agentId;
  final AgentResource? row;

  @override
  State<ScratchEditor> createState() => _ScratchEditorState();
}

class _ScratchEditorState extends State<ScratchEditor> {
  late final _title = TextEditingController(text: widget.row?.text('title'));
  late final _content = TextEditingController(
    text: widget.row?.text('content'),
  );
  bool _busy = false;
  bool _tried = false;

  @override
  void initState() {
    super.initState();
    for (final c in [_title, _content]) {
      c.addListener(() => setState(() {}));
    }
  }

  @override
  void dispose() {
    _title.dispose();
    _content.dispose();
    super.dispose();
  }

  bool get _valid =>
      _title.text.trim().isNotEmpty && _content.text.trim().isNotEmpty;

  Future<void> _save() async {
    setState(() => _tried = true);
    if (!_valid || _busy) return;
    final item = {'title': _title.text.trim(), 'content': _content.text};
    setState(() => _busy = true);
    try {
      final row = widget.row;
      if (row == null) {
        await createAgentResource(scratchpadKind, widget.agentId, item);
      } else {
        await saveAgentResource(scratchpadKind, row, item);
      }
      if (!mounted) return;
      LnToast.show(context, context.t('saved'), kind: LnToastKind.positive);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  Future<void> _delete() async {
    final row = widget.row;
    if (row == null || _busy) return;
    final l10n = context.l10n;
    final ok = await showLnConfirm(
      context,
      title: l10n.t('ag_deleteScratchQ'),
      message: l10n.t('ag_deleteScratchBody'),
      confirmLabel: l10n.t('delete'),
      cancelLabel: l10n.t('cancelAction'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() => _busy = true);
    try {
      await deleteAgentResource(scratchpadKind, row.id);
      if (!mounted) return;
      LnToast.show(
        context,
        l10n.t('ag_scratchDeleted'),
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
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ContentField(
            controller: _title,
            label: l10n.t('ag_titleField'),
            maxLength: 80,
            enabled: !_busy,
            padding: EdgeInsets.zero,
            error: _tried && _title.text.trim().isEmpty
                ? l10n.t('ag_titleRequired')
                : null,
          ),
          ContentField(
            controller: _content,
            label: l10n.t('ag_contentField'),
            minLines: 5,
            maxLines: 14,
            maxLength: 16000,
            enabled: !_busy,
            padding: const EdgeInsets.only(top: LnSpace.sm),
            error: _tried && _content.text.trim().isEmpty
                ? l10n.t('ag_contentRequired')
                : null,
          ),
          const SizedBox(height: LnSpace.lg),
          BlockButton(label: l10n.t('save'), loading: _busy, onPressed: _save),
          if (widget.row != null) ...[
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
