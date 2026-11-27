// The routines list and a routine's detail. The rows are the kit's ScheduleCard («When» /
// «Agent will»); the detail actions are Pause/Resume · Edit schedule · Delete (confirmed), with
// Lonora's execution history (`GET /routines/{id}/history`, each run opens its conversation).
// «Run now» is not offered: Lonora has no routine endpoint that runs one now, and the client never
// posts `/runs` (lonora-api-contract §19). A fired one-shot is scheduled again instead. One agent's
// list also holds its conditional schedules, the price watches that wake it (apps/web
// SchedulesPages.tsx `ScheduleList`): pause/resume and «إلغاء المراقبة» (confirmed) through
// `POST /watches/{id}/control`; a watch carries no trading authority.
import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../agents/profile/agent_data.dart'
    show Watch, controlWatch, fetchWatches;
import '../agents/profile/agent_page.dart';
import '../settings/settings_common.dart';
import '../settings/settings_core_data.dart' show deviceTimeZone;
import 'routine_editor.dart';
import 'routines_data.dart';

/// «27 نوفمبر 2026 07:30».
String routineTime(DateTime? at, String lang) => at == null
    ? '—'
    : '${formatDate('d MMM y', lang, at)} ${clock(at.hour, at.minute)}';

/// A routine's status: done (fired one-shot), paused, or active with its next run.
String routineStatus(Routine r, L10n l10n) {
  if (r.fired) return l10n.t('oneShotDone');
  if (!r.enabled) return l10n.t('paused');
  return '${l10n.t('active')} · ${l10n.t('nextRun')}: ${routineTime(r.nextRunAt, l10n.lang)}';
}

/// The «When» line. A clock schedule runs in the routine's own time zone while its next and last
/// runs read in the device's time, so a routine kept in another zone names it.
String routineWhen(Routine r, L10n l10n, String? deviceZone) {
  final line = routineScheduleLine(r, l10n);
  final clockSchedule = r.runAt == null && (r.cron ?? '').trim().isNotEmpty;
  return clockSchedule && deviceZone != null && r.timezone != deviceZone
      ? '$line · ${ltr(r.timezone)}'
      : line;
}

/// The routines of one agent ([agentId]) or of every agent, with their actions. [header] is shown
/// above the cards; the empty state offers creating one.
class RoutineBoard extends StatefulWidget {
  const RoutineBoard({super.key, this.agentId, this.header = const []});

  final String? agentId;
  final List<Widget> header;

  @override
  State<RoutineBoard> createState() => RoutineBoardState();
}

class RoutineBoardState extends State<RoutineBoard> {
  List<Routine>? _routines;
  Object? _error;
  List<Watch>? _watches;
  Object? _watchError;
  String? _deviceZone;

  @override
  void initState() {
    super.initState();
    unawaited(reload());
    deviceTimeZone().then((zone) {
      if (mounted && zone != null) setState(() => _deviceZone = zone);
    });
  }

  Future<void> reload() async {
    final agentId = widget.agentId;
    await Future.wait([
      () async {
        try {
          final rows = await fetchRoutines(agentId: agentId);
          if (mounted) setState(() => (_routines = rows, _error = null));
        } catch (error) {
          if (error is! SessionRequestCancelled && mounted) {
            setState(() => _error = error);
          }
        }
      }(),
      if (agentId != null) _reloadWatches(agentId),
    ]);
  }

  Future<void> _reloadWatches(String agentId) async {
    try {
      final rows = await fetchWatches(agentId);
      if (mounted) setState(() => (_watches = rows, _watchError = null));
    } catch (error) {
      if (error is! SessionRequestCancelled && mounted) {
        setState(() => _watchError = error);
      }
    }
  }

  /// Pause, resume or stop (confirmed) one conditional schedule.
  Future<void> _watchMenu(Watch w) async {
    final l10n = context.l10n;
    final action = await showLnActionMenu<String>(
      context,
      actions: [
        if (w.on)
          LnMenuAction(
            label: l10n.t('pause'),
            icon: FIcons.pause,
            value: 'pause',
          )
        else
          LnMenuAction(
            label: l10n.t('resume'),
            icon: FIcons.play,
            value: 'resume',
          ),
        LnMenuAction(
          label: l10n.t('ag_watchCancel'),
          icon: FIcons.x,
          value: 'cancel',
          destructive: true,
        ),
      ],
    );
    if (action == null || !mounted) return;
    if (action == 'cancel') {
      final ok = await showLnConfirm(
        context,
        title: l10n.t('ag_watchCancelQ'),
        message: l10n.t('ag_watchCancelBody'),
        confirmLabel: l10n.t('ag_watchCancel'),
        cancelLabel: l10n.t('cancelAction'),
        destructive: true,
      );
      if (!ok || !mounted) return;
    }
    try {
      await controlWatch(w.id, action);
      if (!mounted) return;
      LnToast.show(
        context,
        l10n.t(switch (action) {
          'cancel' => 'ag_watchCancelled',
          'pause' => 'ag_watchPaused',
          _ => 'ag_watchResumed',
        }),
        kind: LnToastKind.positive,
      );
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    }
    final agentId = widget.agentId;
    if (agentId != null) await _reloadWatches(agentId);
  }

  List<Agent> get _agents => context.read().shell.orderedAgents;

  /// Opens the editor for a new routine.
  Future<void> create() async {
    final saved = await showRoutineEditor(
      context,
      agentId: widget.agentId,
      agents: _agents,
    );
    if (saved == true) await reload();
  }

  Future<void> _edit(Routine r, {bool reschedule = false}) async {
    final saved = await showRoutineEditor(
      context,
      routine: r,
      agents: _agents,
      reschedule: reschedule,
    );
    if (saved == true) await reload();
  }

  Future<void> _toggle(Routine r) async {
    final enabled = !r.enabled;
    setState(
      () => _routines = [
        for (final x in _routines ?? const <Routine>[])
          x.id == r.id ? x.copyWith(enabled: enabled) : x,
      ],
    );
    try {
      // Only the switch: the server keeps everything else as it is.
      await updateRoutine(r.id, {'enabled': enabled});
      if (!mounted) return;
      LnToast.show(
        context,
        context.t(enabled ? 'rt_resumedToast' : 'rt_pausedToast'),
        kind: LnToastKind.positive,
      );
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    }
    await reload();
  }

  Future<void> _delete(Routine r) async {
    final l10n = context.l10n;
    final ok = await showLnConfirm(
      context,
      title: l10n.t('rt_deleteQ'),
      message: l10n.t('rt_deleteBody'),
      confirmLabel: l10n.t('delete'),
      cancelLabel: l10n.t('cancelAction'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    try {
      await deleteRoutine(r.id);
      if (!mounted) return;
      LnToast.show(context, l10n.t('rt_deleted'), kind: LnToastKind.positive);
      await reload();
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    }
  }

  /// The detail actions: pause or resume (schedule again once fired), edit, delete.
  List<LnMenuAction<void>> _actions(Routine r) {
    final l10n = context.l10n;
    return [
      if (r.fired)
        LnMenuAction(
          label: l10n.t('rt_scheduleAgain'),
          icon: FIcons.calendarClock,
          onSelected: () => _edit(r, reschedule: true),
        )
      else
        LnMenuAction(
          label: l10n.t(r.enabled ? 'pause' : 'resume'),
          icon: r.enabled ? FIcons.pause : FIcons.play,
          onSelected: () => _toggle(r),
        ),
      LnMenuAction(
        label: l10n.t('rt_editSchedule'),
        icon: FIcons.pencil,
        onSelected: () => _edit(r),
      ),
      LnMenuAction(
        label: l10n.t('rt_deleteSchedule'),
        icon: FIcons.trash2,
        destructive: true,
        onSelected: () => _delete(r),
      ),
    ];
  }

  Future<void> _menu(Routine r) =>
      showLnActionMenu<void>(context, actions: _actions(r));

  Future<void> _detail(Routine r) async {
    final l10n = context.l10n;
    final agent = context.read().shell.agents[r.agentId];
    await showLnSheet<void>(
      context,
      maxHeightFraction: 0.92,
      title: isolate(r.displayTitle),
      builder: (sheet) => _RoutineDetail(
        routine: r,
        when: routineWhen(r, l10n, _deviceZone),
        agentName: agent?.name,
        actions: [
          for (final a in _actions(r))
            LnMenuAction<void>(
              label: a.label,
              icon: a.icon,
              destructive: a.destructive,
              onSelected: () {
                Navigator.of(sheet).pop();
                a.onSelected?.call();
              },
            ),
        ],
        onRun: (run) {
          Navigator.of(sheet).pop();
          context.go(Routes.thread(reportThread(run)));
        },
        lang: l10n.lang,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final routines = _routines;
    final agents = context.select((AppState s) => s.shell.agents);
    final width = MediaQuery.sizeOf(context).width - 2 * LnSpace.pageGutter;
    final now = DateTime.now();
    final watches = [
      for (final w in _watches ?? const <Watch>[])
        if (w.listed(now)) w,
    ];
    final watchError = _watchError;
    if (routines == null) {
      final error = _error;
      return ListView(
        children: [
          ...widget.header,
          if (error == null)
            const SettingsSkeleton(groups: [3, 3])
          else
            Padding(
              padding: const EdgeInsets.only(top: LnSpace.xxl),
              child: LoadFailure(error: error, onRetry: reload),
            ),
        ],
      );
    }
    return LnRefresh(
      onRefresh: reload,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.only(bottom: pageBottomPadding(context)),
        children: [
          ...widget.header,
          if (routines.isEmpty && watches.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: LnSpace.xxl),
              child: EmptyState(
                icon: FIcons.clock,
                title: l10n.t('emptyRoutines'),
                body: l10n.t('routineHint'),
                actionLabel: l10n.t('createRoutine'),
                onAction: create,
              ),
            )
          else
            for (final r in routines)
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(
                  LnSpace.pageGutter,
                  0,
                  LnSpace.pageGutter,
                  LnSpace.sm,
                ),
                child: LnTappable(
                  onTap: () => _detail(r),
                  semanticLabel: r.displayTitle,
                  child: ScheduleCard(
                    width: width,
                    icon: r.fired
                        ? FIcons.calendarCheck
                        : r.enabled
                        ? FIcons.clock
                        : FIcons.pause,
                    title: isolate(r.displayTitle),
                    menuLabel: l10n.t('more'),
                    onMenu: () => _menu(r),
                    fields: [
                      ScheduleField(
                        l10n.t('rt_when'),
                        routineWhen(r, l10n, _deviceZone),
                      ),
                      ScheduleField(
                        l10n.t('rt_agentWill'),
                        isolate(_preview(r.prompt)),
                      ),
                      if (widget.agentId == null)
                        ScheduleField(
                          l10n.t('rt_agent'),
                          isolate(agents[r.agentId]?.name ?? '—'),
                        ),
                      ScheduleField(
                        l10n.t('rt_status'),
                        routineStatus(r, l10n),
                      ),
                    ],
                  ),
                ),
              ),
          for (final w in watches)
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.pageGutter,
                0,
                LnSpace.pageGutter,
                LnSpace.sm,
              ),
              child: LnTappable(
                onTap: () => _watchMenu(w),
                semanticLabel: w.prompt,
                child: ScheduleCard(
                  width: width,
                  icon: w.on ? FIcons.radar : FIcons.pause,
                  title: isolate(w.prompt),
                  menuLabel: l10n.t('more'),
                  onMenu: () => _watchMenu(w),
                  fields: [
                    ScheduleField(
                      l10n.t('rt_when'),
                      '${l10n.t('rt_onCondition')} · ${watchCondition(w.payload, l10n.lang)}',
                    ),
                    ScheduleField(
                      l10n.t('rt_status'),
                      [
                        l10n.t(w.on ? 'active' : 'paused'),
                        watchUntil(w.payload, l10n.lang, now),
                      ].join(dotSeparator),
                    ),
                  ],
                ),
              ),
            ),
          if (watchError != null && _watches == null)
            SettingsNote(
              errorMessage(context, watchError) ?? l10n.t('request_failed'),
            ),
        ],
      ),
    );
  }

  static String _preview(String text) {
    final t = text.trim().replaceAll(RegExp(r'\s+'), ' ');
    final runes = t.runes.toList();
    return runes.length <= 140
        ? t
        : '${String.fromCharCodes(runes.take(140))}…';
  }
}

class _RoutineDetail extends StatefulWidget {
  const _RoutineDetail({
    required this.routine,
    required this.when,
    required this.agentName,
    required this.actions,
    required this.onRun,
    required this.lang,
  });

  final Routine routine;
  final String when;
  final String? agentName;
  final List<LnMenuAction<void>> actions;
  final ValueChanged<Run> onRun;
  final String lang;

  @override
  State<_RoutineDetail> createState() => _RoutineDetailState();
}

class _RoutineDetailState extends State<_RoutineDetail> {
  List<Run>? _runs;
  Object? _error;
  bool _loading = false;

  Future<void> _history() async {
    setState(() => _loading = true);
    try {
      final runs = await fetchRoutineHistory(widget.routine.id);
      if (mounted) setState(() => (_runs = runs, _error = null));
    } catch (error) {
      if (mounted) setState(() => _error = error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final ln = context.ln;
    final r = widget.routine;
    final runs = _runs;
    Widget fact(String label, String value) => Padding(
      padding: const EdgeInsets.only(bottom: LnSpace.sm),
      child: MergeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              label,
              style: ln.text.caption.copyWith(color: ln.colors.fgMuted),
            ),
            const SizedBox(height: 2),
            Text(value, style: ln.text.body),
          ],
        ),
      ),
    );
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          fact(l10n.t('rt_when'), widget.when),
          Padding(
            padding: const EdgeInsets.only(bottom: LnSpace.sm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  l10n.t('rt_agentWill'),
                  style: ln.text.caption.copyWith(color: ln.colors.fgMuted),
                ),
                const SizedBox(height: 2),
                ContentText(r.prompt.trim(), style: ln.text.body),
              ],
            ),
          ),
          if (widget.agentName != null)
            fact(l10n.t('rt_agent'), isolate(widget.agentName!)),
          fact(l10n.t('rt_status'), routineStatus(r, l10n)),
          fact(l10n.t('timezone'), ltr(r.timezone)),
          if (r.lastRunAt != null)
            fact(l10n.t('rt_lastRun'), routineTime(r.lastRunAt, widget.lang)),
          const SizedBox(height: LnSpace.xs),
          LnSection(
            padding: EdgeInsets.zero,
            children: [
              for (final a in widget.actions)
                LnListTile(
                  icon: a.icon,
                  title: a.label,
                  destructive: a.destructive,
                  showChevron: false,
                  onTap: a.onSelected,
                ),
            ],
          ),
          const SizedBox(height: LnSpace.lg),
          if (runs == null)
            BlockButton(
              label: l10n.t('history'),
              icon: FIcons.history,
              variant: BlockButtonVariant.secondary,
              loading: _loading,
              onPressed: _history,
            )
          else if (runs.isEmpty)
            Text(
              l10n.t('noHistory'),
              textAlign: TextAlign.center,
              style: ln.text.caption.copyWith(color: ln.colors.fgMuted),
            )
          else
            LnSection(
              title: l10n.t('history'),
              padding: EdgeInsets.zero,
              children: [
                for (final run in runs.take(30))
                  WrapTile(
                    icon: run.status == 'failed'
                        ? FIcons.circleAlert
                        : run.status == 'completed'
                        ? FIcons.circleCheck
                        : FIcons.loader,
                    title: routineTime(run.createdAt, widget.lang),
                    subtitle: runStatusText(run.status, widget.lang),
                    trailing: const TileChevron(),
                    onTap: () => widget.onRun(run),
                  ),
              ],
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: LnSpace.sm),
              child: Text(
                errorMessage(context, _error!) ?? l10n.t('request_failed'),
                style: ln.text.footnote.copyWith(color: ln.colors.error),
              ),
            ),
        ],
      ),
    );
  }
}
