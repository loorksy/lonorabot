import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/features/voice/voice_note_machine.dart';

void main() {
  group('VoiceNoteMachine', () {
    late VoiceNoteMachine m;
    setUp(() => m = VoiceNoteMachine());

    VoiceNoteEffect startRecording() {
      m.down();
      return m.holdElapsed();
    }

    test('a hold starts recording; release sends what is long enough', () {
      expect(m.down(), VoiceNoteEffect.none);
      expect(m.phase, VoiceNotePhase.pressing);
      expect(m.holdElapsed(), VoiceNoteEffect.start);
      expect(m.phase, VoiceNotePhase.recording);
      m.tick(3.2);
      expect(m.release(), VoiceNoteEffect.send);
      expect(m.phase, VoiceNotePhase.idle);
      expect(m.seconds, 3.2);
    });

    test('a tap (released before the hold) is a hint, not a recording', () {
      m.down();
      expect(m.release(), VoiceNoteEffect.tapHint);
      expect(m.holdElapsed(), VoiceNoteEffect.none);
    });

    test('a press that moves before the hold is a scroll', () {
      m.down();
      m.move(0, -13, rtl: false);
      expect(m.phase, VoiceNotePhase.idle);
      expect(m.holdElapsed(), VoiceNoteEffect.none);
    });

    test('released under 0.7 s is too short', () {
      startRecording();
      m.tick(0.5);
      expect(m.release(), VoiceNoteEffect.tooShort);
    });

    test('sliding 110 dp toward the start cancels (mirrored in RTL)', () {
      startRecording();
      m.tick(2);
      expect(m.move(-60, 0, rtl: false), VoiceNoteEffect.none);
      expect(m.cancelProgress, closeTo(60 / 110, 1e-9));
      expect(m.move(-110, -5, rtl: false), VoiceNoteEffect.discard);
      expect(m.phase, VoiceNotePhase.idle);

      startRecording();
      expect(m.move(-200, 0, rtl: true), VoiceNoteEffect.none);
      expect(m.move(110, 0, rtl: true), VoiceNoteEffect.discard);
    });

    test('sliding 70 dp up locks; then delete, pause and send', () {
      startRecording();
      m.tick(1);
      expect(m.move(-10, -40, rtl: false), VoiceNoteEffect.none);
      expect(m.lockProgress, closeTo(40 / 70, 1e-9));
      expect(m.move(-10, -70, rtl: false), VoiceNoteEffect.locked);
      expect(m.phase, VoiceNotePhase.locked);
      // The finger leaves: the recording continues.
      expect(m.release(), VoiceNoteEffect.none);
      expect(m.pointerLost(), VoiceNoteEffect.none);
      expect(m.pauseTap(), VoiceNoteEffect.pause);
      m.level(0.9);
      expect(m.levels, isEmpty, reason: 'paused: no levels');
      expect(m.pauseTap(), VoiceNoteEffect.resume);
      m.tick(4);
      expect(m.sendTap(), VoiceNoteEffect.send);

      startRecording();
      m.move(0, -80, rtl: false);
      expect(m.deleteTap(), VoiceNoteEffect.discard);
    });

    test('a lost pointer drops an unlocked recording', () {
      startRecording();
      m.tick(5);
      expect(m.pointerLost(), VoiceNoteEffect.discard);
    });

    test('at 2:00 the note sends itself', () {
      startRecording();
      expect(m.tick(119.9), VoiceNoteEffect.none);
      expect(m.tick(120), VoiceNoteEffect.send);
      expect(m.phase, VoiceNotePhase.idle);
    });

    test('live levels keep the last 32', () {
      startRecording();
      for (var i = 0; i < 40; i++) {
        m.level(i / 40);
      }
      expect(m.live, hasLength(VoiceNoteLimits.liveBars));
      expect(m.live.last, closeTo(39 / 40, 1e-9));
      expect(m.levels, hasLength(40));
    });
  });

  group('voicePeaks', () {
    test('44 peaks, 0..100, normalised to the loudest', () {
      final peaks = voicePeaks([for (var i = 0; i < 100; i++) i / 100]);
      expect(peaks, hasLength(44));
      expect(peaks.last, 100);
      expect(peaks.every((p) => p >= 8 && p <= 100), isTrue);
    });

    test('no levels: a flat line of 15; silence floors at 8', () {
      expect(voicePeaks(const []), List.filled(44, 15));
      expect(voicePeaks(const [0, 0, 0]), List.filled(44, 8));
    });

    test('fewer levels than bars repeat each sample (as Web)', () {
      final peaks = voicePeaks(const [0.5, 1.0]);
      expect(peaks.first, 50);
      expect(peaks.last, 100);
    });
  });

  test('levelFromDbfs and noteDuration', () {
    expect(levelFromDbfs(-160), 0);
    expect(levelFromDbfs(0), 1);
    expect(levelFromDbfs(-25), 0.5);
    expect(levelFromDbfs(double.negativeInfinity), 0);
    expect(noteDuration(12.345), 12.3);
    expect(noteDuration(0.96), 1.0);
  });
}
