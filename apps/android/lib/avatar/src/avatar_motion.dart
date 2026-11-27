// Port of packages/core/src/avatar-motion.ts:15-106 (`AvatarMotion`): the DOM-free sampler
// the native renderer drives once per frame. It retargets the glyph on screen, so a state,
// face or identity change morphs from wherever the particles currently are.
import 'avatar_state.dart';
import 'motion.dart';

class AvatarMotion {
  AvatarMotion([
    LonoraAvatarState state = LonoraAvatarState.waiting,
    String identity = '',
    String face = 'orb',
  ]) : _state = state,
       _identity = identity,
       _face = resolveAvatarFace(face) {
    _shown = poseAt(state, 0, identity: identity, face: _face);
    _plan = planMorph(_shown, _shown);
  }

  LonoraAvatarState _state;
  String _identity;
  String _face;
  double? _reactionTime;
  double _phase = 0;
  double _elapsed = AvatarMorph.seconds;
  late List<AvatarBar> _shown;
  List<AvatarBar>? _from;
  late MorphPlan _plan;

  LonoraAvatarState get state => _state;
  String get identity => _identity;
  String get face => _face;

  /// Starts the tap reaction (spin for `orb`, temperament for faces) while resting.
  void react() {
    if (_state == LonoraAvatarState.waiting) _reactionTime = 0;
  }

  void setIdentity(String identity) {
    if (identity == _identity) return;
    _identity = identity;
    if (_state != LonoraAvatarState.waiting) return;
    _retarget(poseAt(_state, _phase, identity: identity, face: _face));
  }

  void setFace(String face) {
    final next = resolveAvatarFace(face);
    if (next == _face) return;
    _face = next;
    if (_state != LonoraAvatarState.waiting) return;
    _retarget(poseAt(_state, _phase, identity: _identity, face: next));
  }

  void setState(LonoraAvatarState state) {
    if (state == _state) return;
    _state = state;
    _phase = 0;
    _retarget(poseAt(state, 0, identity: _identity, face: _face));
  }

  void _retarget(List<AvatarBar> target) {
    final from = [for (final bar in _shown) bar.copy()];
    _from = from;
    _elapsed = 0;
    _plan = planMorph(from, target);
  }

  /// Advances by [seconds] (capped at 0.1) and returns the particles to draw. [reduced]
  /// pins the reduced-motion poster: loop phase 0.3, no morph, no reaction.
  List<AvatarBar> frame(double seconds, {bool reduced = false}) {
    final dt = seconds.clamp(0.0, 0.1);
    final profile = avatarPersonality(_identity);
    final tempo = _state == LonoraAvatarState.waiting ? profile.tempo : 1.0;
    _phase = reduced
        ? 0.3
        : (_phase + (dt * tempo) / loopSeconds(_state)).remainder(1);
    _elapsed = reduced ? AvatarMorph.seconds : _elapsed + dt;
    if (reduced || _state != LonoraAvatarState.waiting) _reactionTime = null;
    if (_reactionTime != null) {
      _reactionTime = _reactionTime! + dt;
      if (_reactionTime! >= profile.spinSeconds) _reactionTime = null;
    }
    final reaction = _reactionTime == null
        ? 1.0
        : _reactionTime! / profile.spinSeconds;
    final target = poseAt(
      _state,
      _phase,
      identity: _identity,
      face: _face,
      reactionProgress: reaction,
    );
    final morphing = _elapsed < AvatarMorph.seconds;
    for (var i = 0; i < _shown.length; i++) {
      final bar = _shown[i], source = _from?[i];
      final t = morphSegment(
        morphing ? source : null,
        target,
        _plan,
        i,
        _elapsed,
        bar,
      );
      final end = target[_plan.perm[i]];
      bar
        ..r = source != null ? source.r + (end.r - source.r) * t : end.r
        ..g = source != null ? source.g + (end.g - source.g) * t : end.g
        ..b = source != null ? source.b + (end.b - source.b) * t : end.b;
    }
    return [for (final bar in _shown) bar.copy()];
  }
}
