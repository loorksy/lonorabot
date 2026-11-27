// The call UI: a full-screen call page with the agent's large avatar, «Calling…» → the connected
// timer → «Call ended», the level meter in the agent's colour
// (apps/mobile/components/voice-overlay.tsx), error states with Retry, the conversation's trade
// approvals under the controls (the fixed card: only the owner's tap on it decides), and four
// controls Speaker · Mute · End call · Minimize. Minimized, the call is a pill at the top that
// brings it back.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:permission_handler/permission_handler.dart'
    show openAppSettings;

import '../../app/router.dart' show rootNavigatorKey;
import '../../avatar/avatar.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/app_state.dart';
import '../cards/trade_approval_card.dart';
import 'voice_api.dart';
import 'voice_strings.dart';

/// «00:12», «12:05», «1:02:03».
String callClock(Duration d) {
  final s = d.inSeconds < 0 ? 0 : d.inSeconds;
  String two(int v) => v.toString().padLeft(2, '0');
  final h = s ~/ 3600;
  return h > 0
      ? '$h:${two(s ~/ 60 % 60)}:${two(s % 60)}'
      : '${two(s ~/ 60)}:${two(s % 60)}';
}

/// The status line under the agent's name.
String callStatus(L10n l10n, VoiceCallState s) => switch (s.phase) {
  CallPhase.calling => l10n.t('vc_calling'),
  CallPhase.connected =>
    s.muted
        ? l10n.t('vc_micMuted')
        : s.speaking
        ? l10n.t('callSpeaking')
        : l10n.t('vc_listeningToYou'),
  CallPhase.ending => l10n.t('vc_ending'),
  // A call that never connected did not «end»: its error card says what happened.
  CallPhase.failed => s.connectedAt == null ? '' : l10n.t('vc_callEnded'),
  CallPhase.ended || CallPhase.idle => l10n.t('vc_callEnded'),
};

LonoraAvatarState callAvatarState(VoiceCallState s) => avatarStateFor(
  error: s.phase == CallPhase.failed,
  voice: AvatarVoice(
    connected: s.phase == CallPhase.connected,
    speaking: s.speaking,
    muted: s.muted,
    ending: s.phase == CallPhase.ending || s.phase == CallPhase.ended,
  ),
);

/// The call page's content for [state] (pure: goldens render it directly).
class VoiceCallView extends StatelessWidget {
  const VoiceCallView({
    super.key,
    required this.state,
    required this.agent,
    required this.now,
    this.onMinimize,
    this.onEnd,
    this.onMute,
    this.onSpeaker,
    this.onRetry,
    this.onClose,
    this.onOpenSettings,
    this.approvals,
    this.animate = true,
  });

  final VoiceCallState state;
  final Agent? agent;
  final DateTime now;
  final VoidCallback? onMinimize;
  final VoidCallback? onEnd;
  final VoidCallback? onMute;
  final VoidCallback? onSpeaker;
  final VoidCallback? onRetry;
  final VoidCallback? onClose;
  final VoidCallback? onOpenSettings;

  /// The approval cards under the controls (built by the page; null in goldens).
  final Widget? approvals;
  final bool animate;

  @override
  Widget build(BuildContext context) {
    registerVoiceStrings(context.l10n);
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final s = state;
    final name = agent?.name ?? 'Lonora';
    final color = avatarHexColor(
      resolveAvatarColor(agent?.id ?? s.agentId ?? 'lonora', agent?.color).hex,
    );
    final connectedAt = s.connectedAt;
    final clock = s.phase == CallPhase.connected && connectedAt != null
        ? callClock(now.difference(connectedAt))
        : (s.phase == CallPhase.ended && s.endedAfter != null
              ? callClock(s.endedAfter!)
              : null);
    final ended = s.phase == CallPhase.ended || s.phase == CallPhase.failed;
    final top = MediaQuery.paddingOf(context).top;
    final bottom = MediaQuery.paddingOf(context).bottom;
    return ColoredBox(
      color: c.bg,
      child: Padding(
        padding: EdgeInsets.only(top: top, bottom: bottom),
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(14, 10, 14, 0),
              child: Row(
                children: [
                  CircleIconButton(
                    icon: const Icon(FIcons.chevronDown),
                    semanticLabel: l10n.t('minimizeCall'),
                    onTap: onMinimize,
                  ),
                  Expanded(
                    child: Text(
                      clock == null
                          ? l10n.t('voiceCall')
                          : '${l10n.t('voiceCall')} · ${ltr(clock)}',
                      textAlign: TextAlign.center,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: ln.text.footnoteStrong.copyWith(color: c.fgMuted),
                    ),
                  ),
                  const SizedBox(width: 48),
                ],
              ),
            ),
            Expanded(
              child: LayoutBuilder(
                builder: (context, box) => SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(
                    horizontal: LnSpace.pageGutter,
                  ),
                  child: ConstrainedBox(
                    constraints: BoxConstraints(minHeight: box.maxHeight),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const SizedBox(height: LnSpace.lg),
                        Semantics(
                          label: callStatus(l10n, s),
                          child: Transform.scale(
                            scale: 1 + s.level.clamp(0.0, 1.0) * 0.12,
                            child: LonoraAvatar(
                              agentId: agent?.id ?? s.agentId ?? 'lonora',
                              face: agent?.avatar,
                              color: agent?.color,
                              tradesOnItsOwn: agent?.tradesOnItsOwn ?? false,
                              state: callAvatarState(s),
                              size: 132,
                              animate: animate,
                            ),
                          ),
                        ),
                        const SizedBox(height: LnSpace.xl),
                        Text(
                          name,
                          textAlign: TextAlign.center,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: ln.text.largeTitle,
                        ),
                        const SizedBox(height: LnSpace.xxs),
                        Semantics(
                          liveRegion: true,
                          child: Text(
                            callStatus(l10n, s),
                            textAlign: TextAlign.center,
                            style: ln.text.body.copyWith(color: c.fgMuted),
                          ),
                        ),
                        const SizedBox(height: LnSpace.lg),
                        if (!ended)
                          _LevelMeter(
                            level: s.phase == CallPhase.connected && !s.muted
                                ? s.level
                                : (s.phase == CallPhase.connected && s.speaking
                                      ? s.level
                                      : 0),
                            color: color,
                          ),
                        if (s.error != null) ...[
                          const SizedBox(height: LnSpace.lg),
                          _CallError(
                            text: l10n.errorText(s.error),
                            onRetry: s.canRetry && !s.openSettings
                                ? onRetry
                                : null,
                            onOpenSettings: s.openSettings
                                ? onOpenSettings
                                : null,
                          ),
                        ],
                        if (approvals != null) ...[
                          const SizedBox(height: LnSpace.lg),
                          approvals!,
                        ],
                        const SizedBox(height: LnSpace.lg),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.pageGutter,
                LnSpace.sm,
                LnSpace.pageGutter,
                LnSpace.xl,
              ),
              child: ended
                  ? BlockButton(label: l10n.t('close'), onPressed: onClose)
                  : Row(
                      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // The label names the control; on/off is the filled disc and
                        // Semantics.toggled.
                        _CallControl(
                          icon: FIcons.volume2,
                          label: l10n.t('vc_speaker'),
                          semantics: l10n.t('vc_speaker'),
                          toggled: s.speaker,
                          onTap: s.phase == CallPhase.ending ? null : onSpeaker,
                        ),
                        _CallControl(
                          icon: s.muted ? FIcons.micOff : FIcons.mic,
                          label: s.muted
                              ? l10n.t('vc_unmute')
                              : l10n.t('vc_mute'),
                          semantics: l10n.t(
                            s.muted ? 'unmuteCall' : 'muteCall',
                          ),
                          toggled: s.muted,
                          onTap: s.phase == CallPhase.ending ? null : onMute,
                        ),
                        _CallControl(
                          icon: FIcons.phoneOff,
                          label: l10n.t('vc_end'),
                          semantics: l10n.t('endCall'),
                          destructive: true,
                          onTap: s.phase == CallPhase.ending ? null : onEnd,
                        ),
                        _CallControl(
                          icon: FIcons.minimize2,
                          label: l10n.t('vc_minimize'),
                          semantics: l10n.t('minimizeCall'),
                          onTap: onMinimize,
                        ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Seven bars in the agent's colour (voice-overlay.tsx:110-127).
class _LevelMeter extends StatelessWidget {
  const _LevelMeter({required this.level, required this.color});

  final double level;
  final Color color;

  static const _factors = [0.3, 0.7, 0.5, 1.0, 0.6, 0.85, 0.4];

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: SizedBox(
      height: 38,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final f in _factors)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 1.5),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 140),
                width: 4,
                height: 4 + level.clamp(0.0, 1.0) * f * 30,
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: const BorderRadius.all(Radius.circular(4)),
                ),
              ),
            ),
        ],
      ),
    ),
  );
}

class _CallError extends StatelessWidget {
  const _CallError({required this.text, this.onRetry, this.onOpenSettings});

  final String text;
  final VoidCallback? onRetry;
  final VoidCallback? onOpenSettings;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    return Container(
      width: double.infinity,
      constraints: const BoxConstraints(maxWidth: LnSize.cardMaxWidth + 40),
      padding: const EdgeInsets.all(LnSpace.cardPadding),
      decoration: BoxDecoration(
        color: Color.alphaBlend(c.error.withValues(alpha: 0.08), c.bg),
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.card)),
        border: Border.all(color: c.error.withValues(alpha: 0.24)),
      ),
      child: Semantics(
        liveRegion: true,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              text,
              textAlign: TextAlign.center,
              style: ln.text.caption.copyWith(color: c.fg),
            ),
            if (onRetry != null || onOpenSettings != null) ...[
              const SizedBox(height: LnSpace.sm),
              BlockButton(
                label: l10n.t(
                  onOpenSettings != null ? 'vc_openSettings' : 'retry',
                ),
                variant: BlockButtonVariant.secondary,
                onPressed: onOpenSettings ?? onRetry,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// One of the call controls: a 64 dp disc with its label below.
class _CallControl extends StatelessWidget {
  const _CallControl({
    required this.icon,
    required this.label,
    required this.semantics,
    this.onTap,
    this.toggled = false,
    this.destructive = false,
  });

  final IconData icon;
  final String label;
  final String semantics;
  final VoidCallback? onTap;
  final bool toggled;
  final bool destructive;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final fill = destructive
        ? c.error
        : toggled
        ? c.fgStrong
        : ln.opaque(c.fill4);
    final ink = destructive
        ? c.onAccent
        : toggled
        ? c.bg
        : c.fg;
    return Semantics(
      toggled: destructive ? null : toggled,
      child: LnTappable(
        onTap: onTap,
        enabled: onTap != null,
        haptic: true,
        semanticLabel: semantics,
        excludeChildSemantics: true,
        child: SizedBox(
          width: 76,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(color: fill, shape: BoxShape.circle),
                alignment: Alignment.center,
                child: Icon(icon, size: 26, color: ink),
              ),
              const SizedBox(height: LnSpace.xs),
              Text(
                label,
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: ln.text.small.copyWith(color: c.fgMuted),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The minimized call: a pill at the top with the agent, the timer and the phone glyph.
class CallPill extends StatelessWidget {
  const CallPill({
    super.key,
    required this.state,
    required this.agent,
    required this.now,
    this.onTap,
  });

  final VoiceCallState state;
  final Agent? agent;
  final DateTime now;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    registerVoiceStrings(context.l10n);
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final connectedAt = state.connectedAt;
    final line = state.phase == CallPhase.connected && connectedAt != null
        ? ltr(callClock(now.difference(connectedAt)))
        : callStatus(l10n, state);
    final name = agent?.name ?? 'Lonora';
    return LnTappable(
      onTap: onTap,
      haptic: true,
      semanticLabel: '${l10n.t('vc_returnToCall')}: $name',
      excludeChildSemantics: true,
      child: SizedBox(
        height: 48,
        child: Center(
          child: Container(
            height: 40,
            constraints: const BoxConstraints(maxWidth: 260),
            padding: const EdgeInsetsDirectional.fromSTEB(4, 4, 14, 4),
            decoration: ShapeDecoration(
              color: c.success,
              shape: const StadiumBorder(),
              shadows: ln.chromeShadow,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                ClipOval(
                  child: ColoredBox(
                    color: c.surface,
                    child: LonoraAvatar(
                      agentId: agent?.id ?? state.agentId ?? 'lonora',
                      face: agent?.avatar,
                      color: agent?.color,
                      tradesOnItsOwn: agent?.tradesOnItsOwn ?? false,
                      state: callAvatarState(state),
                      size: 32,
                      animate: false,
                    ),
                  ),
                ),
                const SizedBox(width: LnSpace.xs),
                Flexible(
                  child: Text(
                    name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: ln.text.footnoteStrong.copyWith(color: c.onAccent),
                  ),
                ),
                const SizedBox(width: LnSpace.xs),
                Text(
                  line,
                  maxLines: 1,
                  style: ln.text.footnote.copyWith(
                    color: c.onAccent.withValues(alpha: 0.9),
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
                const SizedBox(width: LnSpace.xs),
                Icon(
                  state.muted ? FIcons.micOff : FIcons.phone,
                  size: 16,
                  color: c.onAccent,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Ticks once a second while the call is connected (the timers).
class _Ticker extends StatefulWidget {
  const _Ticker({required this.running, required this.builder});

  final bool running;
  final Widget Function(BuildContext context, DateTime now) builder;

  @override
  State<_Ticker> createState() => _TickerState();
}

class _TickerState extends State<_Ticker> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _sync();
  }

  @override
  void didUpdateWidget(_Ticker old) {
    super.didUpdateWidget(old);
    _sync();
  }

  void _sync() {
    if (widget.running && _timer == null) {
      _timer = Timer.periodic(
        const Duration(seconds: 1),
        (_) => setState(() {}),
      );
    } else if (!widget.running) {
      _timer?.cancel();
      _timer = null;
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.builder(context, DateTime.now());
}

/// The call page as a route on the root navigator (back minimizes the call).
class _CallPage extends StatefulWidget {
  const _CallPage({required this.controller, required this.onGone});

  final VoiceCallController controller;

  /// The page left the navigator (popped, or removed when the router replaced the stack).
  final VoidCallback onGone;

  @override
  State<_CallPage> createState() => _CallPageState();
}

class _CallPageState extends State<_CallPage> {
  @override
  void dispose() {
    final gone = widget.onGone;
    scheduleMicrotask(gone);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    return PopScope(
      canPop: true,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) controller.leavePage();
      },
      child: ListenableBuilder(
        listenable: controller,
        builder: (context, _) {
          final s = controller.state;
          final agent = context.getSelect<AppState, Agent?>(
            (st) => st.shell.agents[s.agentId],
          );
          final threadId = s.threadId;
          return AnnotatedRegion<SystemUiOverlayStyle>(
            value: context.ln.isDark
                ? SystemUiOverlayStyle.light
                : SystemUiOverlayStyle.dark,
            child: _Ticker(
              running: s.phase == CallPhase.connected,
              builder: (context, now) => VoiceCallView(
                state: s,
                agent: agent,
                now: now,
                onMinimize: controller.minimize,
                onEnd: () => unawaited(controller.end()),
                onMute: () => unawaited(controller.toggleMute()),
                onSpeaker: () => unawaited(controller.toggleSpeaker()),
                onRetry: () => unawaited(controller.retry()),
                onClose: controller.dismiss,
                onOpenSettings: () => unawaited(openAppSettings()),
                approvals: threadId == null || s.approvalIds.isEmpty
                    ? null
                    : Column(
                        children: [
                          for (final id in s.approvalIds)
                            Padding(
                              padding: const EdgeInsets.only(
                                bottom: LnSpace.sm,
                              ),
                              child: TradeApprovalCardView(
                                threadId: threadId,
                                approvalId: id,
                              ),
                            ),
                        ],
                      ),
              ),
            ),
          );
        },
      ),
    );
  }
}

/// Shows the call: pushes the call page on the root navigator while the call is expanded and
/// draws the pill while it is minimized. Lives in [PlatformOverlayHost]'s stack.
class CallPresenter extends StatefulWidget {
  const CallPresenter({super.key, required this.controller});

  final VoiceCallController controller;

  @override
  State<CallPresenter> createState() => _CallPresenterState();
}

class _CallPresenterState extends State<CallPresenter> {
  Route<void>? _route;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_sync);
    WidgetsBinding.instance.addPostFrameCallback((_) => _sync());
  }

  @override
  void dispose() {
    widget.controller.removeListener(_sync);
    super.dispose();
  }

  void _sync() {
    if (!mounted) return;
    final s = widget.controller.state;
    final wantPage = s.visible && !s.minimized;
    final route = _route;
    if (wantPage && route == null) {
      final navigator = rootNavigatorKey.currentState;
      if (navigator == null) return;
      late final PageRouteBuilder<void> page;
      void gone() {
        if (_route != page) return;
        _route = null;
        widget.controller.leavePage();
      }

      page = PageRouteBuilder<void>(
        opaque: true,
        transitionDuration: LnMotion.slow,
        reverseTransitionDuration: LnMotion.medium,
        pageBuilder: (_, _, _) =>
            _CallPage(controller: widget.controller, onGone: gone),
        transitionsBuilder: (_, animation, _, child) => SlideTransition(
          position: Tween(begin: const Offset(0, 1), end: Offset.zero).animate(
            CurvedAnimation(parent: animation, curve: LnMotion.emphasized),
          ),
          child: child,
        ),
      );
      _route = page;
      unawaited(navigator.push(page).whenComplete(gone));
    } else if (!wantPage && route != null) {
      _route = null;
      if (route.isActive) route.navigator?.removeRoute(route);
    }
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.controller.state;
    if (!s.visible || !s.minimized) return const SizedBox.shrink();
    final agent = context.getSelect<AppState, Agent?>(
      (st) => st.shell.agents[s.agentId],
    );
    return Positioned(
      top: MediaQuery.paddingOf(context).top + 2,
      left: 0,
      right: 0,
      child: Center(
        child: _Ticker(
          running: s.phase == CallPhase.connected,
          builder: (context, now) => CallPill(
            state: s,
            agent: agent,
            now: now,
            onTap: widget.controller.expand,
          ),
        ),
      ),
    );
  }
}
