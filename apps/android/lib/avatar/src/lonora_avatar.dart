// The Lonora agent avatar widget: port of apps/mobile/components/bot-avatar.tsx.
import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' show FlutterView;

import 'package:flutter/material.dart' show Theme;
import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';

import '../../design/tokens.dart';
import 'avatar_colors.dart';
import 'avatar_faces.dart';
import 'avatar_motion.dart';
import 'avatar_painter.dart';
import 'avatar_state.dart';
import 'motion.dart';

/// The agent's own avatar: a glossy sphere in the agent colour with a dark visor showing
/// the animated glyph (four signal bars at rest, the chosen face, or a state glyph).
///
/// * [agentId] seeds the personality (idle gaze, tempo, spin) and, when [color] is empty
///   or unknown, the shell colour — the same ones web and Expo derive.
/// * [face] is `Agent.avatar` (`orb` or one of the `face-*` ids; unknown → `orb`).
/// * [color] is `Agent.color`: a palette id/name/hex or any `#rgb/#rrggbb`.
/// * [animate] runs a ≤ 30 fps ticker only while visible, foregrounded, inside an enabled
///   [TickerMode] and with animations allowed; otherwise a static poster frame is drawn
///   (use `animate: false` in long lists).
/// * A touch pokes the visor and, at rest, spins the signals / plays the face reaction. It
///   never claims the gesture, so a surrounding row still receives its tap. [onTap] is
///   optional and, when set, makes the avatar itself tappable.
class LonoraAvatar extends StatefulWidget {
  const LonoraAvatar({
    super.key,
    required this.agentId,
    this.face,
    this.color,
    this.state = LonoraAvatarState.idle,
    this.size = 44,
    this.tradesOnItsOwn = false,
    this.animate = true,
    this.onTap,
  });

  final String agentId;
  final String? face;
  final String? color;
  final LonoraAvatarState state;
  final double size;
  final bool tradesOnItsOwn;
  final bool animate;
  final VoidCallback? onTap;

  @override
  State<LonoraAvatar> createState() => _LonoraAvatarWidgetState();
}

/// Frames closer than this are skipped: 30 fps on 60/90/120 Hz displays.
const Duration _frameInterval = Duration(milliseconds: 30);
const Duration _offscreenPoll = Duration(milliseconds: 500);

class _LonoraAvatarWidgetState extends State<LonoraAvatar>
    with SingleTickerProviderStateMixin {
  late final AvatarMotion _motion;
  late final AvatarScene _scene;
  late final Ticker _ticker;
  late final AppLifecycleListener _lifecycle;
  Timer? _offscreen;
  bool _foreground = true;
  bool _reduced = false;
  bool _started = false;
  FlutterView? _view;

  Duration? _previous;
  double _elapsed = 0;
  double _idleEpoch = 0;
  double? _tapSpin;
  ({double x, double y, double until})? _pointer;

  String get _face => resolveAvatarFace(widget.face);
  bool get _animating => widget.animate && !_reduced;

  @override
  void initState() {
    super.initState();
    _motion = AvatarMotion(widget.state, widget.agentId, _face);
    _scene = AvatarScene(
      bars: _motion.frame(0, reduced: !widget.animate),
      shell: resolveAvatarColor(widget.agentId, widget.color).color,
    );
    _ticker = createTicker(_tick);
    final lifecycle = SchedulerBinding.instance.lifecycleState;
    _foreground = lifecycle == null || lifecycle == AppLifecycleState.resumed;
    _lifecycle = AppLifecycleListener(onStateChange: _onLifecycle);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _view = View.maybeOf(context);
    final reduced = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    if (!_started || reduced != _reduced) {
      _started = true;
      _reduced = reduced;
      _restart();
    }
  }

  @override
  void didUpdateWidget(LonoraAvatar old) {
    super.didUpdateWidget(old);
    if (old.color != widget.color || old.agentId != widget.agentId) {
      _scene.shell = resolveAvatarColor(widget.agentId, widget.color).color;
    }
    if (resolveAvatarFace(old.face) != _face) {
      _motion.setFace(_face);
      _scene.bars = _motion.frame(0, reduced: !_animating);
    }
    if (old.state != widget.state ||
        old.agentId != widget.agentId ||
        old.animate != widget.animate) {
      _restart();
    } else {
      _syncScene();
      _scene.notify();
    }
  }

  @override
  void dispose() {
    _offscreen?.cancel();
    _lifecycle.dispose();
    _ticker.dispose();
    _scene.dispose();
    super.dispose();
  }

  /// bot-avatar.tsx:91-153 effect: retarget the sampler, reset idle/tap timing, draw the
  /// first frame and (re)start the loop when animating.
  void _restart() {
    _motion.setIdentity(widget.agentId);
    _motion.setState(widget.state);
    _idleEpoch = _elapsed;
    _tapSpin = null;
    _scene.bars = _motion.frame(0, reduced: !_animating);
    if (!_animating) {
      _scene
        ..gazeX = 0
        ..gazeY = 0
        ..poke = 0
        ..yaw = 0;
    }
    _syncScene();
    _scene.notify();
    _syncTicker();
  }

  void _syncScene() {
    _scene
      ..moving = _animating
      ..goo = widget.size >= 48
      ..facial = widget.state == LonoraAvatarState.waiting && _face != 'orb';
    if (!_animating) {
      _scene
        ..barScale = 1
        ..barOffsetY = 0
        ..barTilt = 0;
    }
  }

  void _onLifecycle(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    _syncTicker();
  }

  void _syncTicker() {
    final run = _animating && _foreground;
    if (run && !_ticker.isActive && _offscreen == null) {
      _previous = null;
      _ticker.start();
    } else if (!run) {
      _offscreen?.cancel();
      _offscreen = null;
      if (_ticker.isActive) _ticker.stop();
    }
  }

  bool _onScreen() {
    final box = context.findRenderObject();
    final view = _view;
    if (box is! RenderBox || !box.attached || !box.hasSize || view == null) {
      return true;
    }
    final rect = MatrixUtils.transformRect(
      box.getTransformTo(null),
      Offset.zero & box.size,
    );
    return rect.overlaps(
      Offset.zero & (view.physicalSize / view.devicePixelRatio),
    );
  }

  /// Off screen the ticker stops and a cheap timer checks back, so a cached list row
  /// does not keep the engine producing frames.
  void _pauseOffscreen() {
    _ticker.stop();
    _offscreen = Timer.periodic(_offscreenPoll, (timer) {
      if (!mounted || !_onScreen()) return;
      timer.cancel();
      _offscreen = null;
      _syncTicker();
    });
  }

  /// One animation frame (bot-avatar.tsx:107-148).
  void _tick(Duration now) {
    final previous = _previous;
    if (previous != null && now - previous < _frameInterval) return;
    if (!_onScreen()) {
      _pauseOffscreen();
      return;
    }
    final dt = previous == null
        ? 0.0
        : math.min((now - previous).inMicroseconds / 1e6, 0.1);
    _previous = now;
    _elapsed += dt;
    final face = _face, waiting = widget.state == LonoraAvatarState.waiting;
    _scene.bars = _motion.frame(dt);
    final idle = waiting
        ? idleAvatarPose(_elapsed - _idleEpoch, widget.agentId, face)
        : (
            gazeX: math.sin(now.inMicroseconds / 1000 / 2400) * 0.4,
            gazeY: 0.0,
            yaw: 0.0,
          );
    var yaw = idle.yaw;
    var reaction = faceReaction(1, 'face-smile');
    final tapSpin = _tapSpin;
    if (waiting && tapSpin != null) {
      final spinSeconds = avatarPersonality(widget.agentId).spinSeconds;
      final progress = math.min(1.0, (_elapsed - tapSpin) / spinSeconds);
      reaction = faceReaction(progress, face, widget.agentId);
      yaw = reaction.yaw;
      if (progress >= 1) {
        _tapSpin = null;
        // Start the next idle cycle facing forward after a requested turn.
        _idleEpoch = _elapsed;
      }
    }
    final pointer = _pointer,
        aimed = pointer != null && _elapsed < pointer.until;
    _scene
      ..gazeX = ((aimed ? pointer.x : idle.gazeX) + reaction.gazeX).clamp(
        -1.0,
        1.0,
      )
      ..gazeY = ((aimed ? pointer.y : idle.gazeY) + reaction.gazeY).clamp(
        -1.0,
        1.0,
      )
      ..yaw = yaw
      ..barScale = reaction.scale
      ..barOffsetY = reaction.offsetY
      ..barTilt = reaction.tilt
      ..poke = _scene.poke < 0.005 ? 0 : _scene.poke * math.exp(-dt * 12)
      ..notify();
  }

  void _aim(Offset local) {
    if (!_animating) return;
    final size = widget.size;
    _pointer = (
      x: ((local.dx / size - 0.5) * 2).clamp(-1.0, 1.0),
      y: ((local.dy / size - 0.5) * 1.6).clamp(-0.8, 0.8),
      until: _elapsed + 1.5,
    );
  }

  void _react(PointerDownEvent event) {
    if (!_animating) return;
    _aim(event.localPosition);
    _scene.poke = 0.8;
    if (widget.state == LonoraAvatarState.waiting) {
      _tapSpin = _elapsed;
      _motion.react();
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = widget.size;
    Widget avatar = Stack(
      clipBehavior: Clip.none,
      children: [
        Positioned.fill(
          child: RepaintBoundary(
            child: CustomPaint(painter: AvatarPainter(_scene)),
          ),
        ),
        if (widget.tradesOnItsOwn) ...[
          const Positioned(
            left: -3,
            top: -3,
            right: -3,
            bottom: -3,
            child: IgnorePointer(
              child: CustomPaint(painter: AvatarRingPainter()),
            ),
          ),
          _crown(context, math.max(12.0, size * 0.34)),
        ],
      ],
    );
    avatar = Listener(
      behavior: HitTestBehavior.opaque,
      onPointerDown: _react,
      onPointerMove: (event) => _aim(event.localPosition),
      child: SizedBox.square(dimension: size, child: avatar),
    );
    if (widget.onTap != null) {
      avatar = GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: widget.onTap,
        child: avatar,
      );
    }
    return avatar;
  }

  /// Crown at right −3 / top −4 of the ring box, which itself is inset −3.
  Widget _crown(BuildContext context, double crownSize) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Positioned(
      right: -6,
      top: -7,
      width: crownSize,
      height: crownSize,
      child: Semantics(
        label: avatarIsArabic(context) ? 'يتداول بنفسه' : 'Trades on its own',
        child: IgnorePointer(
          child: CustomPaint(
            painter: AvatarCrownPainter(
              dark ? LnPalette.dark.bg : LnPalette.light.bg,
            ),
          ),
        ),
      ),
    );
  }
}
