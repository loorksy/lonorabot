// The voice-note recorder's gestures and limits, a port of Lonora Web's recorder
// (apps/web/src/conversation/Composer.tsx `useVoiceRecorder`, Voice.tsx `VOICE`/`voicePeaks`):
// hold to record (the composer's long press, or the mic's 350 ms hold in the pure machine); slide
// 110 dp toward the start to cancel, 70 dp up to lock; release sends; a tap on the mic records
// hands-free at once; at most 2:00 (then it sends by itself); under 0.7 s is too short. Pure and
// unit-tested; the controller drives the recorder from the effects it returns.
import 'dart:math' as math;

abstract final class VoiceNoteLimits {
  static const hold = Duration(milliseconds: 350);
  static const cancel = 110.0;
  static const lock = 70.0;

  /// A press that moves this far before the hold is a scroll, not a recording.
  static const slop = 12.0;
  static const minSeconds = 0.7;
  static const maxSeconds = 120.0;
  static const bars = 44;
  static const liveBars = 32;
  static const sample = Duration(milliseconds: 70);
}

/// 44 peaks, 0..100, normalised to the loudest sample (`voicePeaks`).
List<int> voicePeaks(List<double> levels, [int n = VoiceNoteLimits.bars]) {
  if (levels.isEmpty) return List.filled(n, 15);
  final out = <double>[];
  for (var i = 0; i < n; i++) {
    final a = (i * levels.length) ~/ n;
    final b = math.max(a + 1, ((i + 1) * levels.length) ~/ n);
    var m = 0.0;
    for (var k = a; k < b && k < levels.length; k++) {
      m = math.max(m, levels[k]);
    }
    out.add(m);
  }
  final top = math.max(out.reduce(math.max), 0.01);
  return [for (final v in out) (math.max(0.08, v / top) * 100).round()];
}

/// A microphone level (0..1) from the recorder's amplitude in dBFS (−160..0): −50 dB and
/// below is silence, the last 50 dB map linearly.
double levelFromDbfs(double dbfs) {
  if (dbfs.isNaN || dbfs.isInfinite) return 0;
  return ((dbfs + 50) / 50).clamp(0.0, 1.0);
}

/// The duration the server receives: seconds with one decimal.
double noteDuration(double seconds) => (seconds * 10).roundToDouble() / 10;

enum VoiceNotePhase {
  idle,

  /// The finger is down; the hold has not elapsed yet.
  pressing,

  /// Recording with the finger down (slide to cancel or lock).
  recording,

  /// Recording hands-free (delete · pause · send).
  locked,
}

enum VoiceNoteEffect {
  none,

  /// Start the microphone (hold elapsed).
  start,

  /// Stop and send the note.
  send,

  /// Stop and drop the recording (slid away, deleted, or the pointer was lost).
  discard,

  /// Released before 0.7 s: drop it and remind how the mic works.
  tooShort,

  /// A tap without a hold: remind how the mic works.
  tapHint,

  /// Slid up: the recording continues without the finger.
  locked,
  pause,
  resume,
}

class VoiceNoteMachine {
  VoiceNotePhase phase = VoiceNotePhase.idle;

  /// Seconds recorded (pauses excluded), fed by [tick].
  double seconds = 0;
  bool paused = false;

  /// Distance slid toward the start (cancel) and up (lock), in dp, while recording.
  double toward = 0;
  double up = 0;
  final List<double> levels = [];

  bool get recording =>
      phase == VoiceNotePhase.recording || phase == VoiceNotePhase.locked;

  /// Whether the slide is horizontal (cancel) rather than vertical (lock).
  bool get horizontal => toward >= up;

  double get cancelProgress => (toward / VoiceNoteLimits.cancel).clamp(0, 1);
  double get lockProgress =>
      horizontal ? 0 : (up / VoiceNoteLimits.lock).clamp(0, 1);

  VoiceNoteEffect down() {
    if (phase != VoiceNotePhase.idle) return VoiceNoteEffect.none;
    _reset();
    phase = VoiceNotePhase.pressing;
    return VoiceNoteEffect.none;
  }

  /// The mic's tap (or a screen reader's activation): a hands-free recording at once.
  VoiceNoteEffect tapStart() {
    if (phase != VoiceNotePhase.idle) return VoiceNoteEffect.none;
    _reset();
    phase = VoiceNotePhase.locked;
    return VoiceNoteEffect.start;
  }

  VoiceNoteEffect holdElapsed() {
    if (phase != VoiceNotePhase.pressing) return VoiceNoteEffect.none;
    phase = VoiceNotePhase.recording;
    return VoiceNoteEffect.start;
  }

  /// The pointer moved by ([dx], [dy]) since it went down; [rtl] mirrors the cancel side.
  VoiceNoteEffect move(double dx, double dy, {required bool rtl}) {
    switch (phase) {
      case VoiceNotePhase.pressing:
        if (math.sqrt(dx * dx + dy * dy) > VoiceNoteLimits.slop) {
          phase = VoiceNotePhase.idle;
        }
        return VoiceNoteEffect.none;
      case VoiceNotePhase.recording:
        toward = math.max(0, rtl ? dx : -dx);
        up = math.max(0, -dy);
        if (horizontal && toward >= VoiceNoteLimits.cancel) {
          return _finish(send: false);
        }
        if (!horizontal && up >= VoiceNoteLimits.lock) {
          phase = VoiceNotePhase.locked;
          toward = 0;
          up = 0;
          return VoiceNoteEffect.locked;
        }
        return VoiceNoteEffect.none;
      case VoiceNotePhase.idle:
      case VoiceNotePhase.locked:
        return VoiceNoteEffect.none;
    }
  }

  VoiceNoteEffect release() => switch (phase) {
    VoiceNotePhase.pressing => _tap(),
    VoiceNotePhase.recording => _finish(send: true),
    _ => VoiceNoteEffect.none,
  };

  VoiceNoteEffect _tap() {
    phase = VoiceNotePhase.idle;
    return VoiceNoteEffect.tapHint;
  }

  /// The pointer was taken away (a scroll, the system): a recording that is not locked goes.
  VoiceNoteEffect pointerLost() => switch (phase) {
    VoiceNotePhase.pressing => _idle(),
    VoiceNotePhase.recording => _finish(send: false),
    _ => VoiceNoteEffect.none,
  };

  VoiceNoteEffect _idle() {
    phase = VoiceNotePhase.idle;
    return VoiceNoteEffect.none;
  }

  /// [elapsed] seconds recorded so far; at 2:00 the note sends itself.
  VoiceNoteEffect tick(double elapsed) {
    if (!recording) return VoiceNoteEffect.none;
    seconds = elapsed;
    if (elapsed >= VoiceNoteLimits.maxSeconds) return _finish(send: true);
    return VoiceNoteEffect.none;
  }

  void level(double value) {
    if (recording && !paused) levels.add(value.clamp(0.0, 1.0));
  }

  /// The locked bar's buttons.
  VoiceNoteEffect sendTap() => phase == VoiceNotePhase.locked
      ? _finish(send: true)
      : VoiceNoteEffect.none;
  VoiceNoteEffect deleteTap() =>
      recording ? _finish(send: false) : VoiceNoteEffect.none;
  VoiceNoteEffect pauseTap() {
    if (phase != VoiceNotePhase.locked) return VoiceNoteEffect.none;
    paused = !paused;
    return paused ? VoiceNoteEffect.pause : VoiceNoteEffect.resume;
  }

  VoiceNoteEffect _finish({required bool send}) {
    phase = VoiceNotePhase.idle;
    toward = 0;
    up = 0;
    if (!send) return VoiceNoteEffect.discard;
    return seconds >= VoiceNoteLimits.minSeconds
        ? VoiceNoteEffect.send
        : VoiceNoteEffect.tooShort;
  }

  void _reset() {
    seconds = 0;
    paused = false;
    toward = 0;
    up = 0;
    levels.clear();
  }

  /// The last [VoiceNoteLimits.liveBars] levels for the live waveform.
  List<double> get live => levels.length <= VoiceNoteLimits.liveBars
      ? List.unmodifiable(levels)
      : List.unmodifiable(
          levels.sublist(levels.length - VoiceNoteLimits.liveBars),
        );
}
