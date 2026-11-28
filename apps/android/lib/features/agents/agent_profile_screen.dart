// «ملف الوكيل» (/agent/:id): the agent's hub: hero, Configuration rows, Schedules and a manage
// menu, composed from the kit. The whole page sits on one screen-fixed vertical gradient
// ([LnPalette.profileTop] → [LnPalette.profileBottom]) and its lists are flat rows on it.
// Capabilities follow Lonora's other clients (apps/web/src/shell/agent/AgentPage.tsx,
// apps/mobile/app/bot-settings.tsx): Message, Call (only when GPT-Live is set up, otherwise it
// explains), Settings; memory, skills, routines, files, charts; for a trading agent its Mandate
// (read-only here, changed in settings through the Mandate card) and its watches (pause, resume,
// cancel); stop / turn on; delete (confirmed, the server's refusal shown).
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart' show Scaffold;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart' hide liveAvatarState;
import '../../state/actions/base.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/actions/thread_actions.dart';
import '../../state/app_state.dart';
import '../../state/realtime.dart';
import '../routines/routines_data.dart';
import '../routines/routines_strings.dart';
import '../trading/trading_strings.dart';
import '../settings/settings_common.dart'
    show
        LnRefresh,
        LoadFailure,
        SettingsSkeleton,
        SettingsNote,
        WrapTile,
        errorMessage,
        showErrorToast;
import '../settings/settings_core_data.dart' show fetchVoiceStatus;
import '../voice/voice_api.dart';
import 'profile/agent_data.dart';
import 'profile/agent_hub.dart';
import 'profile/agent_page.dart';
import 'profile/agent_strings.dart';
import 'settings/avatar_editor.dart';

class AgentProfileScreen extends StatefulWidget {
  const AgentProfileScreen({super.key, required this.agentId});
  final String agentId;

  @override
  State<AgentProfileScreen> createState() => _AgentProfileScreenState();
}

class _AgentProfileScreenState extends State<AgentProfileScreen> {
  Json? _live;
  bool? _voiceReady;
  List<Routine>? _routines;
  Object? _routinesError;
  List<Watch>? _watches;
  Object? _watchError;
  Object? _agentError;
  bool _busy = false;

  StreamSubscription<LonoraEvent>? _events;
  Timer? _debounce;

  String get _id => widget.agentId;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    // The agent's own activity (runs, watches, cards) refreshes its live state.
    _events = realtime.events
        .where((e) => e.agentId == _id && !e.isStreamChunk)
        .listen((_) {
          _debounce?.cancel();
          _debounce = Timer(const Duration(milliseconds: 800), () {
            if (mounted) unawaited(_load());
          });
        });
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _events?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    var agent = context.read().shell.agents[_id];
    if (agent == null) {
      try {
        agent = await fetchAgent(_id);
        if (!mounted) return;
        context.dispatch(UpsertAgentAction(agent));
      } catch (error) {
        if (error is SessionRequestCancelled) return;
        if (mounted) setState(() => _agentError = error);
        return;
      }
    }
    if (mounted && _agentError != null) setState(() => _agentError = null);
    final trader = isTrader(agent);
    await Future.wait([
      _quiet(() async => _live = await fetchAgentState(_id)),
      _quiet(() async => _voiceReady = (await fetchVoiceStatus()).configured),
      fetchRoutines(agentId: _id).then(
        (rows) {
          _routines = rows;
          _routinesError = null;
        },
        onError: (Object e) {
          if (e is! SessionRequestCancelled) _routinesError = e;
        },
      ),
      if (trader) _loadWatches(),
    ]);
    // Lonora shows its Trading section once /state says an account is connected
    // (apps/web AgentPage.tsx: `trader = isTrader(agent) || hasMode`).
    if (!trader && _hasMode(agent, _live)) await _loadWatches();
    if (mounted) setState(() {});
  }

  Future<void> _loadWatches() => fetchWatches(_id).then(
    (rows) {
      _watches = rows;
      _watchError = null;
    },
    onError: (Object e) {
      if (e is! SessionRequestCancelled) _watchError = e;
    },
  );

  /// Whether the agent shows a trading mode, from its live state.
  static bool _hasMode(Agent agent, Json? live) {
    final readiness = asJson(live?['trading_readiness']);
    return showsTradingControl(
      agent,
      hasTradingAccount: readiness['has_trading_account'] is bool
          ? readiness['has_trading_account'] as bool
          : null,
    );
  }

  /// A side read whose failure leaves its section as it was.
  Future<void> _quiet(Future<void> Function() read) async {
    try {
      await read();
    } catch (_) {}
  }

  Future<void> _message(Agent agent) async {
    final ensure = EnsureAgentThreadAction(agent.id);
    await context.dispatchAndWait(ensure);
    if (!mounted) return;
    final id = ensure.threadId;
    if (ensure.status.originalError != null || id == null) {
      showErrorToast(context, ensure.status.originalError ?? 'request_failed');
      return;
    }
    context.go(Routes.thread(id));
  }

  Future<void> _call(Agent agent) async {
    final l10n = context.l10n;
    if (_voiceReady == false) {
      await showLnSheet<void>(
        context,
        title: l10n.t('ag_callsNotSetUp'),
        builder: (sheet) => Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              l10n.t('ag_callsNeedProvider'),
              style: sheet.ln.text.body.copyWith(
                color: sheet.ln.colors.fgMuted,
              ),
            ),
            const SizedBox(height: LnSpace.lg),
            BlockButton(
              label: l10n.t('ag_openVoiceSettings'),
              onPressed: () {
                Navigator.of(sheet).pop();
                context.push(Routes.voice);
              },
            ),
          ],
        ),
      );
      return;
    }
    if (agent.paused) {
      LnToast.show(context, l10n.t('agent_paused'), kind: LnToastKind.notice);
      return;
    }
    final ensure = EnsureAgentThreadAction(agent.id);
    await context.dispatchAndWait(ensure);
    if (!mounted) return;
    final id = ensure.threadId;
    if (ensure.status.originalError != null || id == null) {
      showErrorToast(context, ensure.status.originalError ?? 'request_failed');
      return;
    }
    await VoiceCalls.start(context, agentId: agent.id, threadId: id);
  }

  Future<void> _togglePause(Agent agent) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final updated = await patchAgent(agent.id, {'paused': !agent.paused});
      if (!mounted) return;
      context.dispatch(UpsertAgentAction(updated));
      LnToast.show(
        context,
        context.t(updated.paused ? 'ag_agentPaused' : 'ag_agentResumed'),
        kind: LnToastKind.positive,
      );
      unawaited(_load());
    } catch (error) {
      // The server refuses some pauses (Lonora, a trading agent's own): its words, in a toast.
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete(Agent agent) async {
    final l10n = context.l10n;
    final ok = await showLnConfirm(
      context,
      title: l10n.t('ag_deleteAgentQ', [agent.name]),
      message: l10n.t('ag_deleteAgentBody'),
      confirmLabel: l10n.t('delete'),
      cancelLabel: l10n.t('cancelAction'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() => _busy = true);
    try {
      await deleteAgent(agent.id);
      if (!mounted) return;
      LnToast.show(
        context,
        l10n.t('ag_agentDeleted'),
        kind: LnToastKind.positive,
      );
      unawaited(context.dispatchAndWait(RefreshShellAction()));
      context.go(Routes.agents);
    } catch (error) {
      // e.g. the personal agent, or a trade whose broker result is not confirmed yet.
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  Future<void> _watchAction(Watch watch) async {
    final l10n = context.l10n;
    final action = await showLnActionMenu<String>(
      context,
      actions: [
        if (watch.paused)
          LnMenuAction(
            label: l10n.t('resume'),
            icon: FIcons.play,
            value: 'resume',
          )
        else
          LnMenuAction(
            label: l10n.t('pause'),
            icon: FIcons.pause,
            value: 'pause',
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
        confirmLabel: l10n.t('cancel'),
        cancelLabel: l10n.t('cancelAction'),
        destructive: true,
      );
      if (!ok || !mounted) return;
    }
    try {
      await controlWatch(watch.id, action);
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
      unawaited(_load());
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    }
  }

  Future<void> _menu(Agent agent) async {
    final l10n = context.l10n;
    await showLnActionMenu<void>(
      context,
      actions: [
        LnMenuAction(
          label: l10n.t('agentSettings'),
          icon: FIcons.settings,
          onSelected: () => context.push(Routes.agentSettings(agent.id)),
        ),
        if (!agent.isPersonal) ...[
          LnMenuAction(
            label: l10n.t(agent.paused ? 'ag_resumeAgent' : 'ag_pauseAgent'),
            icon: agent.paused ? FIcons.play : FIcons.pause,
            onSelected: () => _togglePause(agent),
          ),
          LnMenuAction(
            label: l10n.t('ag_deleteAgent'),
            icon: FIcons.trash2,
            destructive: true,
            onSelected: () => _delete(agent),
          ),
        ],
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    registerAgentStrings(l10n);
    registerRoutinesStrings(l10n);
    registerTradingStrings(l10n);
    final ln = context.ln;
    final agent = context.select((AppState s) => s.shell.agents[_id]);
    final running = context.select(
      (AppState s) => s.shell.runs.any((r) => r.agentId == _id && r.isActive),
    );

    if (agent == null) {
      final error = _agentError;
      // Loading, failed or missing: the same surface as the loaded page, so it does not flash.
      return DecoratedBox(
        decoration: _profileFill(ln.colors),
        child: AgentPage(
          title: '',
          background: const Color(0x00000000),
          body: error == null
              ? const SettingsSkeleton(groups: [5, 3])
              : error is ApiError && error.isNotFound
              ? EmptyState(icon: FIcons.userX, title: l10n.t('agentMissing'))
              : LoadFailure(error: error, onRetry: _load),
        ),
      );
    }

    // On the dark profile gradient the circles take the translucent fill the hub's own circles
    // use; light keeps the white circles.
    final circleFill = ln.colors.isDark ? ln.colors.fill4 : null;
    final header = ScreenHeader(
      leading: CircleIconButton(
        icon: const Icon(FIcons.chevronLeft),
        semanticLabel: l10n.t('back'),
        fill: circleFill,
        onTap: () => leaveTo(context, Routes.agents),
      ),
      trailing: CircleIconButton(
        icon: const Icon(FIcons.ellipsis),
        fill: circleFill,
        semanticLabel: l10n.t('actions'),
        onTap: _busy ? null : () => _menu(agent),
      ),
    );

    final live = _live;
    final readiness = asJson(live?['trading_readiness']);
    final hasMode = _hasMode(agent, live);
    final trader = isTrader(agent) || hasMode;
    final status = hubStatusOf(agent, live, running: running);
    final words = agentStatusText(l10n.lang);
    final line = live == null || agent.paused
        ? ''
        : agentStatusLine(live, l10n.lang, DateTime.now());
    final statusLabel = switch (status) {
      HubStatus.paused => l10n.t('paused'),
      HubStatus.working when line.isEmpty || line == words.idle =>
        words.working,
      _ => line.isEmpty ? words.idle : line,
    };
    final avatarState = agent.paused
        ? LonoraAvatarState.sleeping
        : running
        ? LonoraAvatarState.working
        : liveAvatarState(
            state: asString(live?['state']),
            phase: asString(live?['phase']),
          );
    final animate = !(MediaQuery.maybeDisableAnimationsOf(context) ?? false);

    final hero = AgentHero(
      agent: agent,
      avatarState: avatarState,
      status: status,
      statusLabel: statusLabel,
      role: agentRoleLine(l10n, agent),
      topPadding: ScreenHeader.heightOf(context) + LnSpace.xs,
      animate: animate,
      onEditAvatar: () => showAvatarEditor(context, agent),
      actions: [
        HubAction(
          icon: FIcons.messageCircle,
          label: l10n.t('ag_message'),
          onTap: () => _message(agent),
        ),
        HubAction(
          icon: FIcons.phone,
          label: l10n.t('ag_call'),
          enabled: _voiceReady != false && !agent.paused,
          onTap: () => _call(agent),
        ),
        HubAction(
          icon: FIcons.settings,
          label: l10n.t('ag_settings'),
          onTap: () => context.push(Routes.agentSettings(agent.id)),
        ),
      ],
    );

    final firstInstruction = agent.instructions
        .split('\n')
        .map((l) => l.trim())
        .firstWhere((l) => l.isNotEmpty, orElse: () => '');
    final routines = _routines;
    final watches = (_watches ?? const <Watch>[])
        .where((w) => w.shown)
        .toList();

    final sections = <Widget>[
      const SizedBox(height: LnSpace.md),
      LnSection(
        flat: true,
        title: l10n.t('ag_configuration'),
        children: [
          WrapTile(
            icon: FIcons.scrollText,
            title: l10n.t('instructions'),
            subtitle: firstInstruction.isEmpty
                ? null
                : isolate(firstInstruction),
            trailing: const TileChevron(),
            onTap: () => context.push(Routes.agentInstructions(agent.id)),
          ),
          WrapTile(
            icon: FIcons.brain,
            title: l10n.t('ag_memoryTab'),
            subtitle: l10n.t('memoryHint'),
            trailing: const TileChevron(),
            onTap: () => context.push(Routes.agentMemory(agent.id)),
          ),
          WrapTile(
            icon: FIcons.layers,
            title: l10n.t('skills'),
            subtitle: l10n.t('skillsHint'),
            trailing: const TileChevron(),
            onTap: () => context.push(Routes.agentSkills(agent.id)),
          ),
          // The agent's files (apps/web AgentPage.tsx: `/app/artifacts?agent=`).
          WrapTile(
            icon: FIcons.folder,
            title: l10n.t('sh_sFiles'),
            trailing: const TileChevron(),
            onTap: () => context.push(Routes.artifacts(agentId: agent.id)),
          ),
          WrapTile(
            icon: FIcons.chartCandlestick,
            title: l10n.t('charts'),
            trailing: const TileChevron(),
            onTap: () => context.push(Routes.charts(agentId: agent.id)),
          ),
          // «الصفقات» (apps/web AgentPage.tsx: `trader || agent.trading_symbol`).
          if (trader || (agent.tradingSymbol ?? '').isNotEmpty)
            WrapTile(
              icon: FIcons.chartLine,
              title: l10n.t('tr_title'),
              trailing: const TileChevron(),
              onTap: () => context.push(Routes.agentTrades(agent.id)),
            ),
        ],
      ),
      const SizedBox(height: LnSpace.lg),
      LnSection(
        flat: true,
        title: l10n.t('routines'),
        children: [
          for (final r in (routines ?? const <Routine>[]).take(3))
            WrapTile(
              icon: FIcons.clock,
              title: isolate(r.displayTitle),
              subtitle: [
                routineScheduleLine(r, l10n),
                if (r.fired)
                  l10n.t('oneShotDone')
                else if (!r.enabled)
                  l10n.t('paused'),
              ].join(dotSeparator),
              onTap: () => context.push(Routes.routines(agentId: agent.id)),
            ),
          // «Create routine» only once the list is known to be empty; a failed read says so and
          // leads to the routines page (its own retry).
          WrapTile(
            icon: routines != null && routines.isEmpty
                ? FIcons.plus
                : LnIcons.listChecks,
            title: routines != null && routines.isEmpty
                ? l10n.t('createRoutine')
                : l10n.t('ag_viewAll'),
            subtitle: routines != null && routines.isNotEmpty
                ? l10n.t('ag_routinesCount', [routines.length])
                : routines == null && _routinesError != null
                ? errorMessage(context, _routinesError!) ??
                      l10n.t('request_failed')
                : null,
            trailing: const TileChevron(),
            onTap: () => context.push(Routes.routines(agentId: agent.id)),
          ),
        ],
      ),
      if (trader) ...[
        const SizedBox(height: LnSpace.lg),
        LnSection(
          flat: true,
          title: l10n.t('ag_trading'),
          footer: hasMode ? l10n.t('ag_mandateInSettings') : null,
          children: [
            if (hasMode)
              WrapTile(
                icon: agent.tradingMode == 'full'
                    ? FIcons.triangleAlert
                    : FIcons.shieldCheck,
                title:
                    mandateLine(agent.tradingMode, l10n.lang) ??
                    l10n.t('ag_modeUnknown'),
                subtitle: tradingSubLine(
                  asInt(readiness['unresolved_count']),
                  agent.tradingMode,
                  l10n.lang,
                ),
                trailing: const TileChevron(),
                onTap: () => context.push(Routes.agentSettings(agent.id)),
              ),
            WrapTile(
              icon: FIcons.chartLine,
              title: l10n.t('ag_tradingAccount'),
              subtitle: (agent.tradingAccountId ?? '').isEmpty
                  ? l10n.t(
                      readiness['has_trading_account'] == true
                          ? 'ag_noAccountChosen'
                          : 'ag_noAccountLinked',
                    )
                  : ltr(agent.tradingSymbol ?? ''),
              trailing: const TileChevron(),
              onTap: () => context.push(Routes.agentSettings(agent.id)),
            ),
          ],
        ),
        const SizedBox(height: LnSpace.lg),
        if (_watchError != null && _watches == null)
          SettingsNote(
            errorMessage(context, _watchError!) ?? l10n.t('request_failed'),
          )
        else if (_watches != null && watches.isEmpty)
          SettingsNote(l10n.t('ag_noWatches'))
        else if (watches.isNotEmpty)
          LnSection(
            flat: true,
            title: l10n.t('ag_watches'),
            children: [
              for (final w in watches)
                WrapTile(
                  icon: w.paused ? FIcons.pause : FIcons.radar,
                  title: watchCondition(w.payload, l10n.lang),
                  subtitle: [
                    watchUntil(w.payload, l10n.lang, DateTime.now()),
                    if (w.paused) l10n.t('ag_watchPausedNow'),
                  ].join(dotSeparator),
                  trailing: Icon(FIcons.ellipsis, color: ln.colors.fgMuted),
                  onTap: () => _watchAction(w),
                ),
            ],
          ),
      ],
      if (!agent.isPersonal) ...[
        const SizedBox(height: LnSpace.xl),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
          child: BlockButton(
            label: l10n.t(agent.paused ? 'ag_resumeAgent' : 'ag_pauseAgent'),
            icon: agent.paused ? FIcons.play : FIcons.pause,
            loading: _busy,
            variant: agent.paused
                ? BlockButtonVariant.primary
                : BlockButtonVariant.secondary,
            onPressed: () => _togglePause(agent),
          ),
        ),
      ],
      SizedBox(height: pageBottomPadding(context)),
    ];

    return Scaffold(
      backgroundColor: ln.colors.profileBottom,
      body: Stack(
        children: [
          // Screen-fixed: the rows scroll over it.
          Positioned.fill(
            child: DecoratedBox(decoration: _profileFill(ln.colors)),
          ),
          LnRefresh(
            onRefresh: _load,
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: EdgeInsets.zero,
              children: [hero, ...sections],
            ),
          ),
          Positioned(left: 0, right: 0, top: 0, child: header),
        ],
      ),
    );
  }
}

/// The profile's screen-fixed fill: [LnPalette.profileTop] → [LnPalette.profileBottom].
BoxDecoration _profileFill(LnPalette c) => BoxDecoration(
  gradient: LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [c.profileTop, c.profileBottom],
  ),
);
