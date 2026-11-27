// A task's details and the new-task form (apps/web/src/shell/domain/TasksPages.tsx `TaskPage`,
// `NewTaskPage`): agent, due time, completion criterion; view the conversation; pause, resume,
// mark as completed (it stops the work, approves nothing), cancel (confirmed) and delete a
// finished one (confirmed). Composed from the kit.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../agents/profile/agent_page.dart';
import '../routines/routines_data.dart' show clock;
import '../settings/settings_common.dart';
import 'tasks_data.dart';

/// What a details sheet ended with.
enum TaskOutcome { changed, deleted, openThread }

/// The details of [task]; pops a [TaskOutcome] (with the thread for [TaskOutcome.openThread]).
class TaskDetailsSheet extends StatefulWidget {
  const TaskDetailsSheet({super.key, required this.task, this.agentName});

  final TaskView task;
  final String? agentName;

  @override
  State<TaskDetailsSheet> createState() => _TaskDetailsSheetState();
}

class _TaskDetailsSheetState extends State<TaskDetailsSheet> {
  late TaskView _task = widget.task;
  bool _busy = false;
  bool _changed = false;

  Future<void> _act(Future<TaskView> Function() run, String toast) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final next = await run();
      if (!mounted) return;
      setState(() => (_task = next, _changed = true));
      LnToast.show(context, context.t(toast), kind: LnToastKind.positive);
    } catch (error) {
      if (!mounted) return;
      showErrorToast(context, error);
      try {
        final fresh = await fetchTask(_task.id);
        if (mounted) setState(() => _task = fresh);
      } catch (_) {}
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _cancel() async {
    final l10n = context.l10n;
    final ok = await showLnConfirm(
      context,
      title: l10n.t('tk_cancelQ'),
      message: l10n.t('tk_cancelBody'),
      confirmLabel: l10n.t('cancel'),
      cancelLabel: l10n.t('tk_keep'),
      destructive: true,
    );
    if (ok && mounted) {
      await _act(() => controlTask(_task, 'cancel'), 'tk_cancelledToast');
    }
  }

  Future<void> _delete() async {
    final l10n = context.l10n;
    final ok = await showLnConfirm(
      context,
      title: l10n.t('tk_deleteQ'),
      confirmLabel: l10n.t('delete'),
      cancelLabel: l10n.t('cancelAction'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() => _busy = true);
    try {
      await deleteTask(_task.id);
      if (!mounted) return;
      LnToast.show(context, l10n.t('tk_deleted'), kind: LnToastKind.positive);
      Navigator.of(context).pop((TaskOutcome.deleted, null));
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
    final ln = context.ln;
    final c = ln.colors;
    final task = _task;
    final due = task.dueAt;
    // Agent- or owner-written text aligns by its own direction, as the description does.
    final ambient = Directionality.of(context);
    Widget fact(String label, String value, {TextDirection? direction}) =>
        Padding(
          padding: const EdgeInsets.only(bottom: LnSpace.sm),
          child: MergeSemantics(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(label, style: ln.text.caption.copyWith(color: c.fgMuted)),
                const SizedBox(height: 2),
                Text(value, textDirection: direction, style: ln.text.body),
              ],
            ),
          ),
        );
    final criterion = task.completionCriteria.trim();
    final kind = switch (task.status) {
      'completed' => StatusChipKind.success,
      'cancelled' || 'paused' => StatusChipKind.neutral,
      'failed' || 'waiting' => StatusChipKind.waiting,
      _ => StatusChipKind.running,
    };
    return PopScope(
      canPop: !_busy,
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              task.title,
              textDirection: textDirectionFor(task.title, ambient),
              style: ln.text.headline,
            ),
            const SizedBox(height: LnSpace.xs),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: StatusChip(
                label: l10n.t(taskStatusKey(task.status)),
                kind: kind,
              ),
            ),
            const SizedBox(height: LnSpace.md),
            if (task.description.trim().isNotEmpty) ...[
              ContentText(task.description.trim(), style: ln.text.body),
              const SizedBox(height: LnSpace.md),
            ],
            if (widget.agentName != null)
              fact(
                l10n.t('rt_agent'),
                widget.agentName!,
                direction: textDirectionFor(widget.agentName!, ambient),
              ),
            fact(
              l10n.t('tk_due'),
              due == null
                  ? l10n.t('tk_notSet')
                  : '${formatDate('d MMM y', l10n.lang, due)} ${clock(due.hour, due.minute)}',
            ),
            fact(
              l10n.t('tk_criterion'),
              criterion.isEmpty ? l10n.t('tk_criterionDefault') : criterion,
              direction: criterion.isEmpty
                  ? null
                  : textDirectionFor(criterion, ambient),
            ),
            const SizedBox(height: LnSpace.xs),
            if (task.thread != null)
              BlockButton(
                label: l10n.t('tk_viewConversation'),
                icon: FIcons.messageCircle,
                onPressed: () =>
                    Navigator.of(context)
                        .pop((TaskOutcome.openThread, task.thread)),
              ),
            const SizedBox(height: LnSpace.sm),
            LnSection(
              padding: EdgeInsets.zero,
              children: [
                // Each button sends its own action: a task held for the owner can offer both.
                if (task.canPause)
                  LnListTile(
                    icon: FIcons.pause,
                    title: l10n.t('pause'),
                    showChevron: false,
                    enabled: !_busy,
                    onTap: () => _act(
                      () => controlTask(task, 'pause'),
                      'tk_paused_toast',
                    ),
                  ),
                if (task.canResume)
                  LnListTile(
                    icon: FIcons.play,
                    title: l10n.t('resume'),
                    showChevron: false,
                    enabled: !_busy,
                    onTap: () =>
                        _act(() => controlTask(task, 'resume'), 'tk_resumed'),
                  ),
                if (!task.done && task.controlRequested != 'complete')
                  WrapTile(
                    icon: FIcons.circleCheck,
                    title: l10n.t('tk_markDone'),
                    subtitle: l10n.t('tk_markDoneHint'),
                    enabled: !_busy,
                    onTap: () => _act(
                      () => completeTask(task),
                      'attentionTaskCompleted',
                    ),
                  ),
                if (task.canCancel && !task.terminal)
                  LnListTile(
                    icon: FIcons.circleX,
                    title: l10n.t('tk_cancelTask'),
                    destructive: true,
                    enabled: !_busy,
                    onTap: _cancel,
                  ),
                if (task.terminal)
                  LnListTile(
                    icon: FIcons.trash2,
                    title: l10n.t('delete'),
                    destructive: true,
                    enabled: !_busy,
                    onTap: _delete,
                  ),
              ],
            ),
            const SizedBox(height: LnSpace.md),
            BlockButton(
              label: l10n.t('close'),
              variant: BlockButtonVariant.secondary,
              onPressed: _busy
                  ? null
                  : () =>
                        Navigator.of(context)
                            .pop(_changed ? (TaskOutcome.changed, null) : null),
            ),
          ],
        ),
      ),
    );
  }
}

/// «إنشاء مهمة»: title, responsible agent, what is needed, due time (default 18:00) and the
/// completion criterion. Pops the created task.
class TaskCreateSheet extends StatefulWidget {
  const TaskCreateSheet({
    super.key,
    required this.agents,
    this.agentId,
    this.now,
  });

  final List<Agent> agents;
  final String? agentId;
  final DateTime? now;

  @override
  State<TaskCreateSheet> createState() => _TaskCreateSheetState();
}

class _TaskCreateSheetState extends State<TaskCreateSheet> {
  final _title = TextEditingController();
  final _needed = TextEditingController();
  final _criterion = TextEditingController();
  late String? _agent =
      widget.agentId ?? (widget.agents.isEmpty ? null : widget.agents.first.id);
  FTime _due = const FTime(18);
  bool _busy = false;
  bool _tried = false;

  @override
  void initState() {
    super.initState();
    for (final c in [_title, _needed, _criterion]) {
      c.addListener(() => setState(() {}));
    }
  }

  @override
  void dispose() {
    for (final c in [_title, _needed, _criterion]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _pickAgent() async {
    final l10n = context.l10n;
    final id = await showLnSheet<String>(
      context,
      title: l10n.t('tk_responsible'),
      builder: (sheet) => SingleChildScrollView(
        child: LnSection(
          padding: EdgeInsets.zero,
          children: [
            for (final a in widget.agents)
              ChoiceTile(
                title: isolate(a.name),
                selected: _agent == a.id,
                onSelect: () => Navigator.of(sheet).pop(a.id),
              ),
          ],
        ),
      ),
    );
    if (id != null) setState(() => _agent = id);
  }

  Future<void> _pickTime() async {
    final controller = FTimePickerController(initial: _due);
    final time = await showLnSheet<FTime>(
      context,
      title: context.t('tk_dueTime'),
      builder: (sheet) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: 200,
            child: Directionality(
              textDirection: TextDirection.ltr,
              child: FTimePicker(controller: controller, hour24: true),
            ),
          ),
          const SizedBox(height: LnSpace.md),
          BlockButton(
            label: context.t('avatarDone'),
            onPressed: () => Navigator.of(sheet).pop(controller.value),
          ),
        ],
      ),
    );
    controller.dispose();
    if (time != null) setState(() => _due = time);
  }

  Future<void> _create() async {
    setState(() => _tried = true);
    final agent = _agent;
    final title = _title.text.trim();
    if (_busy || agent == null || title.isEmpty) return;
    setState(() => _busy = true);
    try {
      final task = await createTask(
        agent,
        title: title,
        description: _needed.text.trim(),
        dueAt: dueFromTime(
          _due.hour,
          _due.minute,
          widget.now ?? DateTime.now(),
        ),
        criteria: _criterion.text.trim(),
      );
      if (!mounted) return;
      LnToast.show(
        context,
        context.t('taskCreated'),
        kind: LnToastKind.positive,
      );
      Navigator.of(context).pop(task);
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
    final c = context.ln.colors;
    final agent = widget.agents.where((a) => a.id == _agent).firstOrNull;
    const tight = EdgeInsets.only(top: LnSpace.sm);
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ContentField(
            controller: _title,
            label: l10n.t('cmdTaskHint'),
            maxLength: 160,
            enabled: !_busy,
            padding: EdgeInsets.zero,
            error: _tried && _title.text.trim().isEmpty
                ? l10n.t('ag_titleRequired')
                : null,
          ),
          const SizedBox(height: LnSpace.sm),
          LnSection(
            padding: EdgeInsets.zero,
            children: [
              WrapTile(
                icon: FIcons.bot,
                title: l10n.t('tk_responsible'),
                subtitle: agent == null ? null : isolate(agent.name),
                trailing: const TileChevron(),
                enabled: !_busy && widget.agents.isNotEmpty,
                onTap: _pickAgent,
              ),
              WrapTile(
                icon: FIcons.clock,
                title: l10n.t('tk_dueTime'),
                subtitle: l10n.t('tk_dueHint'),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      clock(_due.hour, _due.minute),
                      style: context.ln.text.body.copyWith(color: c.fgMuted),
                    ),
                    const TileChevron(),
                  ],
                ),
                enabled: !_busy,
                onTap: _pickTime,
              ),
            ],
          ),
          ContentField(
            controller: _needed,
            label: l10n.t('tk_needed'),
            minLines: 3,
            maxLines: 8,
            maxLength: 16000,
            enabled: !_busy,
            padding: tight,
          ),
          ContentField(
            controller: _criterion,
            label: l10n.t('tk_criterion'),
            hint: l10n.t('tk_criterionDefault'),
            minLines: 2,
            maxLines: 4,
            maxLength: 2000,
            enabled: !_busy,
            padding: tight,
          ),
          const SizedBox(height: LnSpace.lg),
          BlockButton(
            label: l10n.t('sh_createTask'),
            loading: _busy,
            onPressed: agent == null ? null : _create,
          ),
        ],
      ),
    );
  }
}
