// «ما يعمل الآن»: tile groups, chips, pill buttons and the kit's states. Lonora's counterpart of
// apps/mobile app/(settings)/running.tsx and apps/web RunningPage.tsx (every workspace process with
// the agent that started it, Stop per process and Stop all, the stale/unknown banners, a 4 s
// refresh while open and on top) with the agents' runs in progress on top, live from the event feed
// and stopped with `POST /runs/{id}/cancel` (the conversation's Stop). Nothing here starts a run.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons, FTile, FTileMixin;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/api/api_error.dart';
import '../../core/models/models.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../../state/realtime.dart';
import 'integrations/ext_common.dart';
import 'running/running_data.dart';
import 'settings_common.dart';

class RunningScreen extends StatefulWidget {
  const RunningScreen({super.key});

  /// How often the open screen asks again (the Gateway lists the workspace every 10 s).
  static const refreshEvery = Duration(seconds: 4);

  @override
  State<RunningScreen> createState() => _RunningScreenState();
}

class _RunningScreenState extends State<RunningScreen>
    with WidgetsBindingObserver, CoverAware {
  WorkspaceRunning? _view;
  Object? _error;

  /// Taps not yet seen in a server answer (each answer says what is being stopped).
  Set<String> _asked = {};
  final Set<String> _stoppingRuns = {};
  Timer? _timer;
  Timer? _runsDebounce;
  StreamSubscription<LonoraEvent>? _events;
  bool _foreground = true;

  /// Only the latest workspace answer is shown; a tick waits for the one in flight.
  int _serial = 0;
  int _reading = 0;

  /// A run event arrived while the page was covered: the runs are read once it is back.
  bool _runsStale = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_loadWorkspace());
    _timer = Timer.periodic(RunningScreen.refreshEvery, (_) {
      // Paused while the app is in the background or another page covers this one.
      if (_foreground && onTop && _reading == 0) unawaited(_loadWorkspace());
    });
    try {
      _events = realtime.events.listen((e) {
        if (!e.kind.startsWith('run.') || e.isStreamChunk) return;
        _runsDebounce?.cancel();
        _runsDebounce = Timer(const Duration(milliseconds: 500), () {
          if (onTop) {
            unawaited(_refreshRuns());
          } else {
            _runsStale = true;
          }
        });
      });
    } catch (_) {
      // No realtime controller (previews): the runs come from the shell snapshot.
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => _refreshRuns());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    _runsDebounce?.cancel();
    unawaited(_events?.cancel());
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    if (_foreground && onTop) unawaited(_loadWorkspace());
  }

  @override
  void onUncovered() {
    unawaited(_loadWorkspace());
    if (_runsStale) {
      _runsStale = false;
      unawaited(_refreshRuns());
    }
  }

  /// Reads the workspace. [pulled]: the owner pulled to refresh, so a failure with the last
  /// list still on screen is said in a toast (a tick that fails stays quiet; the next one
  /// asks again).
  Future<void> _loadWorkspace({bool pulled = false}) async {
    final mine = ++_serial;
    _reading++;
    try {
      final view = await fetchWorkspaceRunning();
      if (!mounted || mine != _serial) return;
      setState(() {
        _view = view;
        _asked = {};
        _error = null;
      });
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (!mounted || mine != _serial) return;
      if (_view == null) {
        setState(() => _error = e);
      } else if (pulled) {
        showErrorToast(context, e);
      }
    } finally {
      _reading--;
    }
  }

  Future<void> _refresh() =>
      Future.wait([_loadWorkspace(pulled: true), _refreshRuns()]);

  Future<void> _send(Future<void> Function() request, String mark) async {
    // An answer already on its way predates this tap: it must not clear the mark.
    _serial++;
    setState(() => _asked = {..._asked, mark});
    try {
      await request();
      if (mounted) LnToast.show(context, context.t('running_stopping'));
      await _loadWorkspace();
    } catch (e) {
      if (!mounted) return;
      setState(() => _asked = {..._asked}..remove(mark));
      showErrorToast(context, e);
    }
  }

  Future<void> _stopAll() async {
    final ok = await showLnConfirm(
      context,
      title: context.t('rn_stopAllQ'),
      message: context.t('rn_stopAllBody'),
      confirmLabel: context.t('running_stopAll'),
      cancelLabel: context.t('sh_cancel'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    await _send(stopAllProcesses, 'all');
  }

  Future<void> _stopRun(Run run) async {
    setState(() => _stoppingRuns.add(run.id));
    final action = StopRunAction(run.id);
    await context.dispatchAndWait(action);
    if (!mounted) return;
    setState(() => _stoppingRuns.remove(run.id));
    final error = action.error;
    if (error != null) showErrorToast(context, error);
  }

  Future<void> _refreshRuns() async {
    if (mounted) await context.dispatchAndWait(RefreshOwnerRunsAction());
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final runs = runsInProgress(context.select((AppState s) => s.shell.runs));
    final agents = context.select((AppState s) => s.shell.agents);
    final view = _view;
    final processes = view?.processes ?? const <WorkspaceProcess>[];
    final stopAll = (view?.stoppingAll ?? false) || _asked.contains('all');
    final stale = view?.stale ?? false;

    final workspace = <Widget>[];
    if (view == null) {
      workspace.add(
        _error == null
            ? const SettingsSkeleton(groups: [2])
            : ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 280),
                child: LoadFailure(error: _error!, onRetry: _loadWorkspace),
              ),
      );
    } else {
      if (stale && view.listedAt != null) {
        workspace.add(
          _Banner(
            text: context.t('running_stale', [
              context.l10n.timeSeparator(view.listedAt!),
            ]),
          ),
        );
      }
      if (view.listedAt == null) {
        workspace.add(_Banner(text: context.t('running_unknown')));
      } else if (processes.isEmpty) {
        workspace.add(
          LnSection(
            title: context.t('rn_workspace'),
            children: [
              WrapTile(
                icon: FIcons.circleCheck,
                title: context.t('running_empty'),
              ),
            ],
          ),
        );
      }
      for (final MapEntry(key: _, value: own) in view.byAgent.entries) {
        workspace
          ..add(
            LnSection(
              title: isolate(own.first.agentName),
              children: [
                for (final p in own)
                  _ProcessTile(
                    process: p,
                    stopping: p.stopping || stopAll || _asked.contains(p.key),
                    stale: stale,
                    onStop: () => _send(() => stopProcess(p), p.key),
                  ),
              ],
            ),
          )
          ..add(const SectionGap());
      }
      if (processes.isNotEmpty || view.listedAt != null) {
        workspace.add(
          Gutter(
            bottom: LnSpace.md,
            child: BlockButton(
              label: context.t(
                stopAll ? 'running_stoppingAll' : 'running_stopAll',
              ),
              icon: FIcons.circleStop,
              variant: BlockButtonVariant.destructive,
              onPressed: processes.isEmpty || stopAll || stale
                  ? null
                  : _stopAll,
            ),
          ),
        );
      }
    }

    return SettingsPageScaffold(
      title: context.t('running_title'),
      onRefresh: _refresh,
      children: [
        LnSection(
          title: context.t('rn_agentsAtWork'),
          footer: runs.isEmpty ? null : context.t('rn_runsNote'),
          children: [
            if (runs.isEmpty)
              WrapTile(icon: FIcons.moon, title: context.t('rn_noAgentWorking'))
            else
              for (final run in runs)
                _RunTile(
                  run: run,
                  agent: agents[run.agentId],
                  stopping: _stoppingRuns.contains(run.id),
                  onStop: () => _stopRun(run),
                  onOpen: () => context.push(Routes.thread(run.threadId)),
                ),
          ],
        ),
        const SectionGap(),
        ...workspace,
        SettingsNote(context.t('running_note')),
      ],
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Gutter(
      bottom: LnSpace.md,
      child: Semantics(
        liveRegion: true,
        child: Container(
          padding: const EdgeInsets.all(LnSpace.sm),
          decoration: BoxDecoration(
            color: c.fill2,
            borderRadius: const BorderRadius.all(
              Radius.circular(LnRadius.field),
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(FIcons.clock, size: 18, color: c.fgMuted),
              const SizedBox(width: LnSpace.xs),
              Expanded(
                child: Text(
                  text,
                  style: ln.text.footnote.copyWith(color: c.fg),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// One agent run in progress: the agent, what it is doing, since when; Stop.
class _RunTile extends StatelessWidget with FTileMixin {
  const _RunTile({
    required this.run,
    required this.agent,
    required this.stopping,
    required this.onStop,
    required this.onOpen,
  });

  final Run run;
  final Agent? agent;
  final bool stopping;
  final VoidCallback onStop;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final a = agent;
    final phase = turnActivity(run.raw, const []).phase;
    final activity = context.l10n.has('activity_$phase')
        ? context.t('activity_$phase')
        : context.t('activity_preparing');
    final since = run.createdAt == null
        ? null
        : context.l10n.timeSeparator(run.createdAt!);
    final name = a?.name ?? 'Lonora';
    // The row opens the conversation; Stop is the pill's own button node.
    return FTile(
      onPress: onOpen,
      prefix: a == null
          ? const Icon(FIcons.bot)
          : LonoraAvatar(
              agentId: a.id,
              face: a.avatar,
              color: a.color,
              tradesOnItsOwn: a.tradesOnItsOwn,
              state: run.waiting
                  ? LonoraAvatarState.waiting
                  : LonoraAvatarState.working,
              size: 32,
              animate: false,
            ),
      title: Text(isolate(name), maxLines: 1),
      subtitle: Text([activity, ?since].join(dotSeparator), maxLines: 2),
      suffix: stopping
          ? StatusChip(
              label: context.t('running_stopping'),
              kind: StatusChipKind.waiting,
            )
          : PillButton(
              label: context.t('running_stop'),
              semanticLabel: context.t('running_stopOne', [isolate(name)]),
              destructive: true,
              onTap: onStop,
            ),
    );
  }
}

/// One workspace process: its command (left to right), its start; Stop.
class _ProcessTile extends StatelessWidget with FTileMixin {
  const _ProcessTile({
    required this.process,
    required this.stopping,
    required this.stale,
    required this.onStop,
  });

  final WorkspaceProcess process;
  final bool stopping;
  final bool stale;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final p = process;
    final command = p.command.isEmpty
        ? context.t('running_noCommand')
        : ltr(p.command);
    return FTile(
      prefix: const Icon(FIcons.cpu),
      title: Text(command, maxLines: 2),
      subtitle: p.startedAt == null
          ? null
          : Text(
              context.t('running_started', [
                // Mid-sentence: «Started today 11:02 AM».
                formatTimeSeparator(
                  p.startedAt!,
                  context.l10n.lang,
                  today: context.t('today').toLowerCase(),
                  yesterday: context.t('yesterday').toLowerCase(),
                ),
              ]),
            ),
      suffix: stopping
          ? StatusChip(
              label: context.t('running_stopping'),
              kind: StatusChipKind.waiting,
            )
          : PillButton(
              label: context.t('running_stop'),
              semanticLabel: context.t('running_stopOne', [p.command]),
              destructive: true,
              onTap: stale ? null : onStop,
            ),
    );
  }
}
