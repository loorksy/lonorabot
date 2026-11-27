// Voice notes from the composer: a long press anywhere on the empty composer records (≤ 2:00);
// slide toward the start to cancel, slide up to lock (hands-free); release (or «send» when
// locked) uploads the audio to `/artifacts/upload` with the conversation's `thread_id` and sends
// `{voice: {artifact_id, duration, peaks}}` through the conversation's SendMessageAction, as
// Lonora Web does (apps/web/src/conversation/Composer.tsx:513-533). The server transcribes the
// note into the message. A tap on the mic records hands-free at once (also the way for screen
// readers, which cannot hold). Voice notes never wait in the offline queue.
//
// While recording, the design kit's recording bar takes the composer pill's place: the cancel
// circle, the levels, the mm:ss timer, pause (locked) and the send disc.
import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/thread_actions.dart';
import 'voice_note_machine.dart';
import 'voice_strings.dart';

/// The microphone side of a voice note, behind an interface for tests.
abstract class VoiceNoteRecorder {
  /// granted / denied / permanently denied.
  Future<PermissionStatus> permission();
  Future<void> start(String path);
  Future<String?> stop();
  Future<void> cancel();
  Future<void> pause();
  Future<void> resume();

  /// Levels 0..1 every [VoiceNoteLimits.sample].
  Stream<double> levels();
  Future<void> dispose();
}

class RecordVoiceNoteRecorder implements VoiceNoteRecorder {
  final AudioRecorder _recorder = AudioRecorder();

  @override
  Future<PermissionStatus> permission() => Permission.microphone.request();

  /// AAC in MP4 (`audio/mp4`), mono, 32 kb/s: accepted by the server
  /// (`audio/webm|ogg|mp4|mpeg|wav`) and recorded by every Android version Lonora supports.
  @override
  Future<void> start(String path) => _recorder.start(
    const RecordConfig(
      encoder: AudioEncoder.aacLc,
      bitRate: 32000,
      sampleRate: 44100,
      numChannels: 1,
      echoCancel: true,
      noiseSuppress: true,
    ),
    path: path,
  );

  @override
  Future<String?> stop() => _recorder.stop();
  @override
  Future<void> cancel() => _recorder.cancel();
  @override
  Future<void> pause() => _recorder.pause();
  @override
  Future<void> resume() => _recorder.resume();
  @override
  Stream<double> levels() => _recorder
      .onAmplitudeChanged(VoiceNoteLimits.sample)
      .map((a) => levelFromDbfs(a.current));
  @override
  Future<void> dispose() => _recorder.dispose();
}

/// Uploads the recording and sends it; injectable for tests.
typedef VoiceNoteSender = Future<void> Function(
  BuildContext context, {
  required String threadId,
  required String path,
  required double seconds,
  required List<int> peaks,
});

Future<void> _sendVoiceNote(
  BuildContext context, {
  required String threadId,
  required String path,
  required double seconds,
  required List<int> peaks,
}) async {
  // The app store (not the context's): the conversation may close during the upload.
  final store = appStore;
  try {
    final row = asJson(
      await api.upload(
        '/artifacts/upload',
        filePath: path,
        fileName: 'voice-${DateTime.now().millisecondsSinceEpoch}.m4a',
        mimeType: 'audio/mp4',
        fields: {'thread_id': threadId},
      ),
    );
    final id = asString(row['id']);
    if (id == null) throw ApiError(status: 502, code: 'request_failed');
    await store.dispatchAndWait(
      SendMessageAction(threadId, {
        'voice': {
          'artifact_id': id,
          'duration': noteDuration(seconds),
          'peaks': peaks,
        },
      }),
    );
  } finally {
    unawaited(File(path).delete().catchError((Object _) => File(path)));
  }
}

/// The voice notes of one conversation's composer: the composer's hold ([holdToTalk]) or the mic's
/// tap ([tapStart]), the microphone, the clock and the levels, then the upload and the send.
/// Listeners hear every change (the recording bar redraws ten times a second while recording).
class VoiceNoteController extends ChangeNotifier {
  VoiceNoteController({required this.threadId, this.onRecordingChanged});

  final String threadId;

  /// The recording bar shows (true) or goes (false): the composer swaps its pill for it.
  final ValueChanged<bool>? onRecordingChanged;

  final VoiceNoteMachine machine = VoiceNoteMachine();
  VoiceNoteRecorder? _recorder;
  StreamSubscription<double>? _levels;
  Timer? _clock;
  BuildContext? _context;

  /// 100 ms ticks spent paused (the recorded length leaves them out).
  int _pausedTicks = 0;
  String? _path;
  bool _sending = false;
  bool _showing = false;
  bool _disposed = false;

  /// Bumped by every start: a start that resolves after its hold ended is dropped.
  int _press = 0;

  /// `recorder.start` is in flight: [_start] releases the recorder if the controller goes meanwhile.
  bool _opening = false;

  /// The note is uploading (the mic shows a spinner).
  bool get sending => _sending;

  /// The recording bar is up.
  bool get showing => _showing;

  /// The composer's context: toasts, direction and the send.
  void bind(BuildContext context) => _context = context;

  BuildContext? get _live {
    final c = _context;
    return c != null && c.mounted && !_disposed ? c : null;
  }

  bool get _rtl {
    final c = _live;
    return c != null && Directionality.of(c) == TextDirection.rtl;
  }

  /// The composer's press-to-talk, with the composer's hint while it is armed.
  ComposerHoldToTalk holdToTalk({String? placeholder}) => ComposerHoldToTalk(
    placeholder: placeholder,
    onStart: holdStart,
    onMove: holdMove,
    onEnd: holdEnd,
    onCancel: holdCancel,
  );

  /// The long press began: record with the finger down.
  void holdStart() {
    if (_sending || machine.phase != VoiceNotePhase.idle) return;
    _press++;
    machine.down();
    _apply(machine.holdElapsed());
  }

  /// The finger moved by [offset] from where the hold began (toward the start cancels, up locks).
  void holdMove(Offset offset) =>
      _apply(machine.move(offset.dx, offset.dy, rtl: _rtl));

  /// The finger lifted: send (or too short), unless the recording is locked.
  void holdEnd() => _apply(machine.release());

  /// The system took the gesture: an unlocked recording goes.
  void holdCancel() => _apply(machine.pointerLost());

  /// The mic's tap: a hands-free recording at once, with one light haptic (the composer's hold
  /// gives its own when it is recognised).
  void tapStart() {
    if (_sending || machine.phase != VoiceNotePhase.idle) return;
    _press++;
    HapticFeedback.lightImpact();
    _apply(machine.tapStart());
  }

  void delete() => _apply(machine.deleteTap());
  void pause() => _apply(machine.pauseTap());
  void send() => _apply(machine.sendTap());

  @override
  void dispose() {
    _disposed = true;
    _clock?.cancel();
    _levels?.cancel();
    // Leaving the conversation abandons a recording: nothing is ever sent.
    machine.deleteTap();
    final path = _path;
    _path = null;
    if (!_opening) unawaited(_release(_recorder, path));
    super.dispose();
  }

  /// Stops the microphone (cancel before dispose) and removes what it wrote.
  static Future<void> _release(
    VoiceNoteRecorder? recorder,
    String? path,
  ) async {
    try {
      await recorder?.cancel();
    } catch (_) {}
    try {
      await recorder?.dispose();
    } catch (_) {}
    if (path != null) _delete(path);
  }

  static void _delete(String path) =>
      unawaited(File(path).delete().catchError((Object _) => File(path)));

  void _apply(VoiceNoteEffect effect) {
    if (_disposed) return;
    switch (effect) {
      case VoiceNoteEffect.none:
        break;
      case VoiceNoteEffect.start:
        unawaited(_start());
      case VoiceNoteEffect.send:
        unawaited(_finishSend());
      case VoiceNoteEffect.discard:
        unawaited(_discard());
      case VoiceNoteEffect.tooShort:
        unawaited(_discard(quiet: true));
        _toast('vn_holdHint');
      case VoiceNoteEffect.tapHint:
        _toast('vn_holdHint');
      case VoiceNoteEffect.locked:
        HapticFeedback.selectionClick();
      case VoiceNoteEffect.pause:
        unawaited(_recorder?.pause());
      case VoiceNoteEffect.resume:
        unawaited(_recorder?.resume());
    }
    notifyListeners();
  }

  void _toast(String key) {
    final c = _live;
    if (c == null) return;
    registerVoiceStrings(c.l10n);
    LnToast.show(c, c.t(key), kind: LnToastKind.notice);
  }

  void _show(bool value) {
    if (_showing == value) return;
    _showing = value;
    if (!_disposed) onRecordingChanged?.call(value);
  }

  Future<void> _start() async {
    final press = _press;
    final recorder = _recorder ??= VoiceNoteButton.recorderFactory();
    _show(true);
    PermissionStatus status;
    try {
      status = await recorder.permission();
    } catch (_) {
      status = PermissionStatus.denied;
    }
    if (_disposed) return;
    if (!status.isGranted) {
      machine.deleteTap();
      _stopUi();
      final c = _context;
      if (c != null && c.mounted && !_disposed) {
        registerVoiceStrings(c.l10n);
        LnToast.show(
          c,
          c.t('vn_micDenied'),
          kind: LnToastKind.notice,
          action: status.isPermanentlyDenied
              ? (c.t('vc_openSettings'), () => unawaited(openAppSettings()))
              : null,
        );
      }
      return;
    }
    if (press != _press || !machine.recording) {
      _stopUi();
      return;
    }
    String path;
    _opening = true;
    try {
      final dir = await VoiceNoteButton.recordingsDir();
      path = '$dir/lonora-voice-${DateTime.now().millisecondsSinceEpoch}.m4a';
      await recorder.start(path);
    } catch (_) {
      _opening = false;
      if (_disposed) {
        unawaited(_release(recorder, null));
        return;
      }
      machine.deleteTap();
      _stopUi();
      _toast('vn_unavailable');
      return;
    }
    _opening = false;
    if (_disposed) {
      // The conversation closed while the microphone was opening.
      unawaited(_release(recorder, path));
      return;
    }
    _path = path;
    if (!machine.recording) {
      // Released or slid away while the microphone was opening.
      if (machine.phase == VoiceNotePhase.idle) await _discard(quiet: true);
      return;
    }
    _pausedTicks = 0;
    _levels = recorder.levels().listen((v) {
      machine.level(v);
      if (!_disposed) notifyListeners();
    });
    // The timer's own tick count is the clock: late callbacks still count whole periods.
    _clock = Timer.periodic(const Duration(milliseconds: 100), (timer) {
      if (machine.paused) _pausedTicks++;
      _apply(machine.tick((timer.tick - _pausedTicks) / 10));
    });
  }

  void _stopUi() {
    _clock?.cancel();
    _clock = null;
    _levels?.cancel();
    _levels = null;
    _show(false);
    if (!_disposed) notifyListeners();
  }

  Future<void> _discard({bool quiet = false}) async {
    if (!quiet) HapticFeedback.selectionClick();
    final path = _path;
    _path = null;
    _stopUi();
    try {
      await _recorder?.cancel();
    } catch (_) {}
    if (path != null) _delete(path);
  }

  Future<void> _finishSend() async {
    final seconds = machine.seconds;
    final peaks = voicePeaks(List.of(machine.levels));
    final written = _path;
    _path = null;
    _stopUi();
    String? path;
    try {
      path = await _recorder?.stop() ?? written;
    } catch (_) {
      path = written;
    }
    if (path == null) return;
    final c = _context;
    if (c == null || !c.mounted || _disposed) {
      _delete(path);
      return;
    }
    _sending = true;
    notifyListeners();
    try {
      await VoiceNoteButton.sender(
        c,
        threadId: threadId,
        path: path,
        seconds: seconds,
        peaks: peaks,
      );
    } on SessionRequestCancelled {
      // Signed out meanwhile: nothing to show.
    } on ApiError catch (e) {
      final c = _context;
      if (c != null && c.mounted && !_disposed) {
        LnToast.show(c, c.l10n.errorText(e.code), kind: LnToastKind.error);
      }
    } catch (_) {
      final c = _context;
      if (c != null && c.mounted && !_disposed) {
        LnToast.show(
          c,
          c.l10n.errorText('request_failed'),
          kind: LnToastKind.error,
        );
      }
    } finally {
      _sending = false;
      if (!_disposed) notifyListeners();
    }
  }
}

/// The composer's mic while its field is empty: a tap records hands-free (the long press belongs
/// to the composer's hold, which starts here too). A spinner while a note uploads.
class VoiceNoteButton extends StatelessWidget {
  const VoiceNoteButton({
    super.key,
    required this.controller,
    this.enabled = true,
  });

  final VoiceNoteController controller;
  final bool enabled;

  /// The microphone (replaced in tests).
  static VoiceNoteRecorder Function() recorderFactory =
      RecordVoiceNoteRecorder.new;

  /// Upload + send (replaced in tests).
  static VoiceNoteSender sender = _sendVoiceNote;

  /// Where recordings are written before the upload (replaced in tests).
  static Future<String> Function() recordingsDir = () async =>
      (await getTemporaryDirectory()).path;

  @override
  Widget build(BuildContext context) {
    registerVoiceStrings(context.l10n);
    final c = context.ln.colors;
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) => LnTappable(
        onTap: enabled && !controller.sending ? controller.tapStart : null,
        enabled: enabled,
        // The start of the recording is the haptic ([VoiceNoteController.tapStart]).
        haptic: false,
        semanticLabel: context.t('voiceNote'),
        semanticHint: context.t('vn_tapRecord'),
        excludeChildSemantics: true,
        child: SizedBox.square(
          dimension: LnSize.composerHeight - 2,
          child: Center(
            // 44 dp: the disc fills the composer's trailing slot, clear of the pill's 1 dp border.
            child: Container(
              width: LnSize.composerHeight - 4,
              height: LnSize.composerHeight - 4,
              decoration: BoxDecoration(
                color: c.surface,
                shape: BoxShape.circle,
              ),
              alignment: Alignment.center,
              child: controller.sending
                  ? LnSpinner(size: 18, color: c.fgWarm)
                  : Icon(
                      FIcons.mic,
                      size: LnSize.composerIcon,
                      color: enabled ? c.fgWarm : c.fgSubtle,
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The recording bar in the composer's place while [controller] records.
class VoiceNoteRecordingBar extends StatelessWidget {
  const VoiceNoteRecordingBar({super.key, required this.controller});

  final VoiceNoteController controller;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: controller,
    builder: (context, _) => VoiceNoteBar(
      machine: controller.machine,
      onDelete: controller.delete,
      onPause: controller.pause,
      onSend: controller.send,
    ),
  );
}

/// The recording bar for [machine] (pure: goldens render it directly): the design kit's
/// [ComposerRecordingBar] with Lonora's labels. Held, its hint says how to cancel and lock and the
/// cancel circle turns red past half the cancel slide; locked, the circles are buttons (✕ deletes,
/// pause, send).
class VoiceNoteBar extends StatelessWidget {
  const VoiceNoteBar({
    super.key,
    required this.machine,
    this.onDelete,
    this.onPause,
    this.onSend,
  });

  final VoiceNoteMachine machine;
  final VoidCallback? onDelete;
  final VoidCallback? onPause;
  final VoidCallback? onSend;

  @override
  Widget build(BuildContext context) {
    registerVoiceStrings(context.l10n);
    final l10n = context.l10n;
    final locked = machine.phase == VoiceNotePhase.locked;
    return ComposerRecordingBar(
      elapsed: Duration(milliseconds: (machine.seconds * 1000).round()),
      levels: machine.live,
      locked: locked,
      cancelArmed: !locked && machine.cancelProgress >= 0.5,
      hint: locked ? null : l10n.t('vn_slideHint'),
      paused: machine.paused,
      onCancel: onDelete,
      onPause: onPause,
      onSend: onSend,
      cancelLabel: l10n.t('vn_delete'),
      sendLabel: l10n.t('vn_send'),
      pauseLabel: l10n.t('vn_pause'),
      resumeLabel: l10n.t('vn_resume'),
      lengthLabel: l10n.t('vn_length'),
    );
  }
}
