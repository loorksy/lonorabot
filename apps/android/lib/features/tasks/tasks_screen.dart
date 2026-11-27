// «المهام» (/tasks): Lonora's Task system as the Web shows it (apps/web/src/shell/domain/
// TasksPages.tsx): Active · Scheduled · Completed; each task with its agent and one of the four
// status words; details with its controls; create a task. «Scheduled» is the owner's routines (the
// same board as /routines). Under the active tasks, «Runs» keeps Expo's list of the agents' recent
// runs (apps/mobile/app/(tabs)/tasks.tsx: the agent's face, the run's status, its report
// conversation). A search (the header's magnifier) finds active and completed tasks by title or
// agent: the field at the start of the header, a plain ✕ at its end. Composed from the kit.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart'
    show InputDecoration, Scaffold, TextAlignVertical, TextField;
import 'package:flutter/services.dart' show TextInputAction;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons, FTile;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/api/api_error.dart';
import '../../core/models/models.dart' show Agent;
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

  /// The search's text; null while the page is not searching.
  String? _query;
  final _search = TextEditingController();

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _startSearch() => setState(() => _query = '');

  void _endSearch() {
    _search.clear();
    setState(() => _query = null);
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
              children: [for (final t in shown) _taskTile(t, agents, l10n)],
            ),
          if (_tab == TaskTab.active) _runs(context),
        ],
      ),
    );
  }

  /// A task's row: its status icon, title, agent and status word; opens its details.
  WrapTile _taskTile(TaskView t, Map<String, Agent> agents, L10n l10n) =>
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
      );

  /// The search page: the field and its ✕ in the header, then the active and completed tasks
  /// whose title or agent contains the text (nothing before a word is typed). Back ends the
  /// search.
  Widget _searchPage(BuildContext context, String query) {
    final l10n = context.l10n;
    final c = context.ln.colors;
    final agents = context.select((AppState s) => s.shell.agents);
    final tasks = _tasks;
    final needle = query.trim().toLowerCase();
    bool matches(TaskView t) =>
        t.title.toLowerCase().contains(needle) ||
        (agents[t.agentId]?.name.toLowerCase().contains(needle) ?? false);
    final found = [
      if (tasks != null && needle.isNotEmpty)
        for (final t in tasks)
          if (matches(t)) t,
    ];
    final Widget results;
    if (needle.isEmpty) {
      results = const SizedBox.shrink();
    } else if (tasks == null) {
      results = _error == null
          ? const SettingsSkeleton(groups: [4])
          : LoadFailure(error: _error!, onRetry: _load);
    } else if (found.isEmpty) {
      results = Padding(
        padding: const EdgeInsets.only(top: LnSpace.xxl),
        child: EmptyState(
          icon: FIcons.search,
          title: l10n.t('sh_noResultsTitle'),
          body: l10n.t('sh_noResultsFor', const [], {'q': isolate(query)}),
        ),
      );
    } else {
      results = LnSection(
        children: [for (final t in found) _taskTile(t, agents, l10n)],
      );
    }
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _endSearch();
      },
      child: Scaffold(
        backgroundColor: c.bg,
        body: Column(
          children: [
            Padding(
              // The header row's place: the field where the title row is, the ✕ in the touch
              // box of the end circle.
              padding: EdgeInsetsDirectional.fromSTEB(
                LnSpace.pageGutter,
                MediaQuery.paddingOf(context).top +
                    ScreenHeader.topGapDefault -
                    2,
                LnSpace.pageGutter - 2,
                0,
              ),
              child: SizedBox(
                height: ScreenHeader.rowHeight,
                child: Row(
                  children: [
                    Expanded(
                      child: TaskSearchField(
                        controller: _search,
                        hint: l10n.t('tk_searchPh'),
                        onChanged: (text) => setState(() => _query = text),
                      ),
                    ),
                    const SizedBox(width: LnSpace.xs),
                    LnTappable(
                      onTap: _endSearch,
                      semanticLabel: l10n.t('sh_closeSearch'),
                      child: SizedBox.square(
                        dimension: LnSize.minTouch,
                        child: Icon(
                          FIcons.x,
                          size: LnSize.chromeIcon,
                          color: c.fg,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: LnSpace.xs),
            Expanded(
              child: ListView(
                padding: EdgeInsets.only(
                  top: LnSpace.xs,
                  bottom: pageBottomPadding(context),
                ),
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.onDrag,
                children: [results],
              ),
            ),
          ],
        ),
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
    final query = _query;
    if (query != null) return _searchPage(context, query);
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
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // The search looks through tasks: not offered among the routines.
          if (_tab != TaskTab.scheduled)
            CircleIconButton(
              icon: const Icon(FIcons.search),
              semanticLabel: l10n.t('sh_search'),
              onTap: _startSearch,
            ),
          CircleIconButton(
            icon: const Icon(FIcons.plus),
            semanticLabel: l10n.t(
              _tab == TaskTab.scheduled ? 'createRoutine' : 'sh_createTask',
            ),
            onTap: _create,
          ),
        ],
      ),
      body: switch (_tab) {
        TaskTab.scheduled => RoutineBoard(key: _board, header: [tabs]),
        _ => _tasksBody(context, [tabs]),
      },
    );
  }
}

/// The task search's field: a 44 dp rounded rectangle (radius 12) in the cards' 6 % fill, no
/// border or shadow; a 20 dp magnifier 12 dp in from the start; the hint in the tertiary ink;
/// the caret in the action blue. The text takes the whole 48 dp row as its touch target. It
/// takes focus as it opens.
class TaskSearchField extends StatelessWidget {
  const TaskSearchField({
    super.key,
    required this.controller,
    required this.hint,
    required this.onChanged,
  });

  final TextEditingController controller;
  final String hint;
  final ValueChanged<String> onChanged;

  static const double height = 44;
  static const double radius = 12;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    const inset = (LnSize.minTouch - height) / 2;
    return SizedBox(
      height: LnSize.minTouch,
      child: Stack(
        children: [
          Positioned.fill(
            top: inset,
            bottom: inset,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: c.fill3,
                borderRadius: const BorderRadius.all(Radius.circular(radius)),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsetsDirectional.symmetric(
              horizontal: LnSpace.sm,
            ),
            child: Row(
              children: [
                Icon(FIcons.search, size: LnSize.tileIcon, color: c.fgMuted),
                const SizedBox(width: LnSpace.sm),
                Expanded(
                  child: TextField(
                    controller: controller,
                    autofocus: true,
                    expands: true,
                    maxLines: null,
                    textAlignVertical: TextAlignVertical.center,
                    onChanged: onChanged,
                    textInputAction: TextInputAction.search,
                    style: ln.text.body.copyWith(color: c.fg),
                    cursorColor: c.selection,
                    decoration: InputDecoration.collapsed(
                      hintText: hint,
                      hintStyle: ln.text.body.copyWith(color: c.fgSubtle),
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
