// The call UI: a full-screen call page on a soft vertical gradient with the agent's avatar on two
// rings that swell with the voice level, «Calling…» → the connected timer → «Call ended»
// (apps/mobile/components/voice-overlay.tsx), error states with Retry, the conversation's trade
// approvals under the controls (the fixed card: only the owner's tap on it decides), three Ø72
// controls Speaker · End call · Mute, and the ⌄ circle that minimizes it. Minimized, the call is a
// pill at the top that brings it back.
import 'dart:async';
import 'dart:math' as math;

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
    final connectedAt = s.connectedAt;
    final clock = s.phase == CallPhase.connected && connectedAt != null
        ? callClock(now.difference(connectedAt))
        : (s.phase == CallPhase.ended && s.endedAfter != null
              ? callClock(s.endedAfter!)
              : null);
    final ended = s.phase == CallPhase.ended || s.phase == CallPhase.failed;
    final top = MediaQuery.paddingOf(context).top;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final level = s.phase == CallPhase.connected && (!s.muted || s.speaking)
        ? s.level.clamp(0.0, 1.0)
        : 0.0;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [c.profileTop, c.profileBottom],
        ),
      ),
      child: Padding(
        padding: EdgeInsets.only(top: top, bottom: bottom),
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(14, 10, 14, 0),
              child: Row(
                children: [
                  _MinimizeCircle(
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
              child: SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(
                  LnSpace.pageGutter,
                  _avatarLead(context, top),
                  LnSpace.pageGutter,
                  LnSpace.lg,
                ),
                child: Column(
                  children: [
                    Semantics(
                      label: callStatus(l10n, s),
                      child: _AvatarRings(
                        level: ended ? 0 : level,
                        animate: animate,
                        child: LonoraAvatar(
                          agentId: agent?.id ?? s.agentId ?? 'lonora',
                          face: agent?.avatar,
                          color: agent?.color,
                          tradesOnItsOwn: agent?.tradesOnItsOwn ?? false,
                          state: callAvatarState(s),
                          size: _AvatarRings.avatar,
                          animate: animate,
                        ),
                      ),
                    ),
                    // The name sits on the rings' lower edge, 8 dp under the avatar.
                    const SizedBox(height: LnSpace.xs),
                    Text(
                      name,
                      textAlign: TextAlign.center,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: ln.text.headline.copyWith(color: c.fg),
                    ),
                    const SizedBox(height: LnSpace.xxs),
                    Semantics(
                      liveRegion: true,
                      child: Text(
                        callStatus(l10n, s),
                        textAlign: TextAlign.center,
                        style: ln.text.caption.copyWith(color: c.fgMuted),
                      ),
                    ),
                    if (s.error != null) ...[
                      const SizedBox(height: LnSpace.xxl),
                      _CallError(
                        text: l10n.errorText(s.error),
                        onRetry: s.canRetry && !s.openSettings ? onRetry : null,
                        onOpenSettings: s.openSettings ? onOpenSettings : null,
                      ),
                    ],
                    if (approvals != null) ...[
                      const SizedBox(height: LnSpace.lg),
                      approvals!,
                    ],
                  ],
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
                  : Center(
                      // Three controls at a 104 dp pitch, centred (narrower on a narrow screen).
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(
                          maxWidth: 3 * _CallControl.pitch,
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // The label names the control; on/off is the filled disc and
                            // Semantics.toggled. Minimize is the ⌄ circle above.
                            Expanded(
                              child: _CallControl(
                                icon: FIcons.volume2,
                                label: l10n.t('vc_speaker'),
                                semantics: l10n.t('vc_speaker'),
                                toggled: s.speaker,
                                onTap: s.phase == CallPhase.ending
                                    ? null
                                    : onSpeaker,
                              ),
                            ),
                            Expanded(
                              child: _CallControl(
                                icon: FIcons.phoneOff,
                                label: l10n.t('vc_end'),
                                semantics: l10n.t('endCall'),
                                destructive: true,
                                onTap: s.phase == CallPhase.ending
                                    ? null
                                    : onEnd,
                              ),
                            ),
                            Expanded(
                              child: _CallControl(
                                icon: s.muted ? FIcons.micOff : FIcons.mic,
                                label: s.muted
                                    ? l10n.t('vc_unmute')
                                    : l10n.t('vc_mute'),
                                semantics: l10n.t(
                                  s.muted ? 'unmuteCall' : 'muteCall',
                                ),
                                toggled: s.muted,
                                onTap: s.phase == CallPhase.ending
                                    ? null
                                    : onMute,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  /// The header row: 10 dp, then the ⌄ circle's 48 dp target.
  static const double _headerExtent = 10 + _MinimizeCircle.target;

  /// Space above the avatar: the rings' centre at 29 % of the screen's height (the page's upper
  /// third), never so high that the outer ring reaches the header row.
  static double _avatarLead(BuildContext context, double top) => math.max(
    (_AvatarRings.outer - _AvatarRings.avatar) / 2 + LnSpace.xs,
    MediaQuery.sizeOf(context).height * 0.29 -
        top -
        _headerExtent -
        _AvatarRings.avatar / 2,
  );
}

/// The ⌄ circle that minimizes the call: the header circle (Ø44 in a 48 dp target) raised over
/// the page's gradient. In dark the chrome circle's fill would melt into the gradient's top, so
/// the disc is the ink at 11 % over it; light keeps the chrome circle.
class _MinimizeCircle extends StatelessWidget {
  const _MinimizeCircle({required this.semanticLabel, this.onTap});

  /// The touch target around the Ø44 disc.
  static const double target = 48;

  final String semanticLabel;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: onTap,
      haptic: true,
      semanticLabel: semanticLabel,
      excludeChildSemantics: true,
      child: SizedBox.square(
        dimension: target,
        child: Center(
          child: Container(
            width: LnSize.headerCircle,
            height: LnSize.headerCircle,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: c.isDark ? c.fg.withValues(alpha: 0.11) : c.chromeCircle,
              border: c.isDark ? null : Border.fromBorderSide(ln.chromeRim),
              boxShadow: c.isDark ? null : ln.chromeShadow,
            ),
            child: Icon(
              FIcons.chevronDown,
              size: LnSize.chromeIcon,
              color: c.fg,
            ),
          ),
        ),
      ),
    );
  }
}

/// The avatar (80 dp) on two rings (119 and 163 dp, 10 % and 4 % of the ink) that swell with the
/// voice [level]; still with reduced motion or [animate] off. The box is the avatar's: the rings
/// overflow it.
class _AvatarRings extends StatelessWidget {
  const _AvatarRings({
    required this.level,
    required this.animate,
    required this.child,
  });

  final double level;
  final bool animate;
  final Widget child;

  static const double avatar = 80;
  static const double inner = 119;
  static const double outer = 163;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final still =
        !animate || (MediaQuery.maybeDisableAnimationsOf(context) ?? false);
    final swell = still ? 0.0 : level;
    Widget ring(double size, double alpha, double grow) => AnimatedScale(
      scale: 1 + swell * grow,
      duration: const Duration(milliseconds: 140),
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: c.fg.withValues(alpha: alpha),
        ),
      ),
    );
    // The rings spread beyond the avatar's box: what follows (the name) lies on the outer one.
    return SizedBox.square(
      dimension: avatar,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          OverflowBox(
            maxWidth: outer,
            maxHeight: outer,
            child: Stack(
              alignment: Alignment.center,
              children: [ring(outer, 0.04, 0.10), ring(inner, 0.10, 0.06)],
            ),
          ),
          child,
        ],
      ),
    );
  }
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

/// One of the call controls: a 72 dp disc with its label below, as wide as its slot.
class _CallControl extends StatelessWidget {
  const _CallControl({
    required this.icon,
    required this.label,
    required this.semantics,
    this.onTap,
    this.toggled = false,
    this.destructive = false,
  });

  /// Centre to centre of two controls (their row's slots).
  static const double pitch = 104;

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
        : c.surface;
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
          width: double.infinity,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 72,
                height: 72,
                decoration: BoxDecoration(color: fill, shape: BoxShape.circle),
                alignment: Alignment.center,
                child: Icon(icon, size: 28, color: ink),
              ),
              const SizedBox(height: LnSpace.xs),
              Text(
                label,
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: ln.text.caption.copyWith(color: c.fgMuted),
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
