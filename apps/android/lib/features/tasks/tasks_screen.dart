// «المهام» (/tasks): Lonora's Task system as the Web shows it (apps/web/src/shell/domain/
// TasksPages.tsx): Active · Scheduled · Completed; each task with its agent and one of the four
// status words; details with its controls; create a task. «Scheduled» is the owner's routines (the
// same board as /routines). Under the active tasks, «Runs» keeps Expo's list of the agents' recent
// runs (apps/mobile/app/(tabs)/tasks.tsx: the agent's face, the run's status, its report
// conversation). Composed from the kit.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons, FTile;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/api/api_error.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/app_state.dart';
import '../agents/profile/agent_page.dart';
import '../agents/profile/agent_strings.dart';
import '../routines/routine_board.dart';
import '../routines/routines_data.dart' show reportThread;
import '../routines/routines_strings.dart';
import '../settings/settings_common.dart';
import 'task_sheets.dart';
import 'tasks_data.dart';
import 'tasks_strings.dart';

enum TaskTab { active, scheduled, done }

class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key});

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> {
  TaskTab _tab = TaskTab.active;
  List<TaskView>? _tasks;
  Object? _error;
  final _board = GlobalKey<RoutineBoardState>();

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final tasks = await fetchTasks();
      if (mounted) setState(() => (_tasks = tasks, _error = null));
    } catch (error) {
      if (error is! SessionRequestCancelled && mounted) {
        setState(() => _error = error);
      }
    }
  }

  Future<void> _create() async {
    if (_tab == TaskTab.scheduled) {
      await _board.currentState?.create();
      return;
    }
    final agents = context.read().shell.orderedAgents;
    final task = await showLnSheet<TaskView>(
      context,
      maxHeightFraction: 0.94,
      title: context.t('sh_createTask'),
      builder: (_) => TaskCreateSheet(agents: agents),
    );
    if (task != null) {
      if (mounted) setState(() => _tab = TaskTab.active);
      await _load();
    }
  }

  Future<void> _open(TaskView task) async {
    final agent = context.read().shell.agents[task.agentId];
    final result = await showLnSheet<(TaskOutcome, String?)>(
      context,
      maxHeightFraction: 0.92,
      title: context.t('tk_details'),
      builder: (_) => TaskDetailsSheet(task: task, agentName: agent?.name),
    );
    if (result == null || !mounted) return;
    final (outcome, thread) = result;
    if (outcome == TaskOutcome.openThread && thread != null) {
      context.go(Routes.thread(thread));
      return;
    }
    await _load();
  }

  Widget _tasksBody(BuildContext context, List<Widget> header) {
    final l10n = context.l10n;
    final agents = context.select((AppState s) => s.shell.agents);
    final tasks = _tasks;
    if (tasks == null) {
      final error = _error;
      return ListView(
        children: [
          ...header,
          if (error == null)
            const SettingsSkeleton(groups: [6])
          else
            Padding(
              padding: const EdgeInsets.only(top: LnSpace.xxl),
              child: LoadFailure(error: error, onRetry: _load),
            ),
        ],
      );
    }
    final shown = [
      for (final t in tasks)
        if ((_tab == TaskTab.done) == t.done) t,
    ];
    return LnRefresh(
      onRefresh: () => Future.wait([
        _load(),
        if (_tab == TaskTab.active)
          context.dispatchAndWait(RefreshShellAction()),
      ]),
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.only(bottom: pageBottomPadding(context)),
        children: [
          ...header,
          if (shown.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: LnSpace.xxl),
              child: EmptyState(
                icon: LnIcons.listChecks,
                title: l10n.t('tk_none'),
                body: _tab == TaskTab.active ? l10n.t('cmdTaskSub') : null,
                actionLabel: _tab == TaskTab.active
                    ? l10n.t('sh_createTask')
                    : null,
                onAction: _tab == TaskTab.active ? _create : null,
              ),
            )
          else
            LnSection(
              children: [
                for (final t in shown)
                  WrapTile(
                    icon: t.status == 'completed'
                        ? FIcons.circleCheck
                        : t.status == 'paused'
                        ? FIcons.pause
                        : t.status == 'cancelled'
                        ? FIcons.circleX
                        : LnIcons.listTodo,
                    title: isolate(t.title),
                    subtitle: [
                      isolate(agents[t.agentId]?.name ?? '—'),
                      l10n.t(taskStatusKey(t.status)),
                    ].join(dotSeparator),
                    trailing: const TileChevron(),
                    onTap: () => _open(t),
                  ),
              ],
            ),
          if (_tab == TaskTab.active) _runs(context),
        ],
      ),
    );
  }

  /// The agents' recent runs (`GET /runs`, kept by the shell), each opening the conversation
  /// it reports to; nothing when there is none.
  Widget _runs(BuildContext context) {
    final l10n = context.l10n;
    final agents = context.select((AppState s) => s.shell.agents);
    final runs = context.select(
      (AppState s) => [
        for (final r in s.shell.runs)
          if (s.shell.agents.containsKey(r.agentId)) r,
      ],
    );
    if (runs.isEmpty) return const SizedBox.shrink();
    final animate = !(MediaQuery.maybeDisableAnimationsOf(context) ?? false);
    return Padding(
      padding: const EdgeInsets.only(top: LnSpace.lg),
      child: LnSection(
        title: l10n.t('tk_runs'),
        children: [
          for (final run in runs)
            FTile(
              prefix: LonoraAvatar(
                agentId: run.agentId,
                face: agents[run.agentId]?.avatar,
                color: agents[run.agentId]?.color,
                state: run.isActive
                    ? LonoraAvatarState.working
                    : LonoraAvatarState.idle,
                size: 40,
                animate: animate,
              ),
              title: Text(
                isolate(agents[run.agentId]?.name ?? '—'),
                maxLines: 2,
              ),
              subtitle: Text(runStatusText(run.status, l10n.lang)),
              suffix: const TileChevron(),
              onPress: () => context.go(Routes.thread(reportThread(run))),
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    registerAgentStrings(l10n);
    registerRoutinesStrings(l10n);
    registerTasksStrings(l10n);
    final tabs = Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter,
        0,
        LnSpace.pageGutter,
        LnSpace.md,
      ),
      child: LnSegmented<TaskTab>(
        segments: [
          LnSegment(value: TaskTab.active, label: l10n.t('tk_active')),
          LnSegment(value: TaskTab.scheduled, label: l10n.t('tk_scheduled')),
          LnSegment(value: TaskTab.done, label: l10n.t('tk_done')),
        ],
        selected: _tab,
        onChanged: (tab) => setState(() => _tab = tab),
      ),
    );
    return AgentPage(
      title: l10n.t('sh_tasks'),
      fallback: Routes.me,
      trailing: CircleIconButton(
        icon: const Icon(FIcons.plus),
        semanticLabel: l10n.t(
          _tab == TaskTab.scheduled ? 'createRoutine' : 'sh_createTask',
        ),
        onTap: _create,
      ),
      body: switch (_tab) {
        TaskTab.scheduled => RoutineBoard(key: _board, header: [tabs]),
        _ => _tasksBody(context, [tabs]),
      },
    );
  }
}
