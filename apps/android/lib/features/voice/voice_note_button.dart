// The composer's trailing mic: hold to record a voice note (≤ 2:00), slide toward the start
// to cancel, slide up to lock; release (or «send» when locked) uploads the audio to
// `/artifacts/upload` with the conversation's `thread_id` and sends
// `{voice: {artifact_id, duration, peaks}}` through the conversation's SendMessageAction, as
// Lonora Web does (apps/web/src/conversation/Composer.tsx:513-533). The server transcribes
// the note into the message. Voice notes never wait in the offline queue.
//
// The recording bar takes the composer pill's geometry
// (48 dp stadium, surface, hairline border, chrome shadow) over the composer while recording.
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

class VoiceNoteButton extends StatefulWidget {
  const VoiceNoteButton({
    super.key,
    required this.threadId,
    this.enabled = true,
    this.onRecordingChanged,
  });

  final String threadId;
  final bool enabled;

  /// Lets the composer hide its text field while recording.
  final ValueChanged<bool>? onRecordingChanged;

  /// The microphone (replaced in tests).
  static VoiceNoteRecorder Function() recorderFactory =
      RecordVoiceNoteRecorder.new;

  /// Upload + send (replaced in tests).
  static VoiceNoteSender sender = _sendVoiceNote;

  /// Where recordings are written before the upload (replaced in tests).
  static Future<String> Function() recordingsDir = () async =>
      (await getTemporaryDirectory()).path;

  @override
  State<VoiceNoteButton> createState() => _VoiceNoteButtonState();
}

class _VoiceNoteButtonState extends State<VoiceNoteButton> {
  final VoiceNoteMachine _machine = VoiceNoteMachine();
  VoiceNoteRecorder? _recorder;
  StreamSubscription<double>? _levels;
  Timer? _hold;
  Timer? _clock;

  /// 100 ms ticks spent paused (the recorded length leaves them out).
  int _pausedTicks = 0;
  Offset? _origin;
  String? _path;
  OverlayEntry? _bar;
  bool _sending = false;

  /// Bumped by every press: a start that resolves after its press ended is dropped.
  int _press = 0;

  /// `recorder.start` is in flight: [_start] releases the recorder if the button goes meanwhile.
  bool _opening = false;

  /// The bar follows the mic: the composer moves when the keyboard closes under the finger.
  final LayerLink _link = LayerLink();

  @override
  void dispose() {
    _hold?.cancel();
    _clock?.cancel();
    _levels?.cancel();
    _removeBar();
    // Leaving the conversation abandons a recording: nothing is ever sent.
    final wasRecording = _machine.recording;
    _machine.deleteTap();
    if (wasRecording) {
      // Told after this frame: the composer's setState cannot run while the tree is locked.
      final changed = widget.onRecordingChanged;
      if (changed != null) {
        WidgetsBinding.instance.addPostFrameCallback((_) => changed(false));
      }
    }
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

  bool get _rtl => Directionality.of(context) == TextDirection.rtl;

  void _apply(VoiceNoteEffect effect) {
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
    _bar?.markNeedsBuild();
    if (mounted) setState(() {});
  }

  void _toast(String key) {
    if (!mounted) return;
    registerVoiceStrings(context.l10n);
    LnToast.show(context, context.t(key), kind: LnToastKind.notice);
  }

  void _down(PointerDownEvent event) {
    if (!widget.enabled || _sending || _machine.phase != VoiceNotePhase.idle) {
      return;
    }
    _press++;
    _origin = event.position;
    _apply(_machine.down());
    _hold = Timer(VoiceNoteLimits.hold, () => _apply(_machine.holdElapsed()));
  }

  void _move(PointerMoveEvent event) {
    final origin = _origin;
    if (origin == null) return;
    final d = event.position - origin;
    final before = _machine.phase;
    _apply(_machine.move(d.dx, d.dy, rtl: _rtl));
    if (before == VoiceNotePhase.pressing &&
        _machine.phase == VoiceNotePhase.idle) {
      _hold?.cancel();
    }
  }

  void _up(PointerUpEvent event) {
    _hold?.cancel();
    _origin = null;
    _apply(_machine.release());
  }

  void _cancel(PointerCancelEvent event) {
    _hold?.cancel();
    _origin = null;
    _apply(_machine.pointerLost());
  }

  Future<void> _start() async {
    final press = _press;
    HapticFeedback.lightImpact();
    final recorder = _recorder ??= VoiceNoteButton.recorderFactory();
    widget.onRecordingChanged?.call(true);
    _showBar();
    PermissionStatus status;
    try {
      status = await recorder.permission();
    } catch (_) {
      status = PermissionStatus.denied;
    }
    if (!mounted) return;
    if (!status.isGranted) {
      _machine.deleteTap();
      _stopUi();
      registerVoiceStrings(context.l10n);
      LnToast.show(
        context,
        context.t('vn_micDenied'),
        kind: LnToastKind.notice,
        action: status.isPermanentlyDenied
            ? (context.t('vc_openSettings'), () => unawaited(openAppSettings()))
            : null,
      );
      return;
    }
    if (press != _press || !_machine.recording) {
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
      if (!mounted) {
        unawaited(_release(recorder, null));
        return;
      }
      _machine.deleteTap();
      _stopUi();
      _toast('vn_unavailable');
      return;
    }
    _opening = false;
    if (!mounted) {
      // The conversation closed while the microphone was opening.
      unawaited(_release(recorder, path));
      return;
    }
    _path = path;
    if (!_machine.recording) {
      // Released or slid away while the microphone was opening.
      if (_machine.phase == VoiceNotePhase.idle) await _discard(quiet: true);
      return;
    }
    _pausedTicks = 0;
    _levels = recorder.levels().listen((v) {
      _machine.level(v);
      _bar?.markNeedsBuild();
    });
    // The timer's own tick count is the clock: late callbacks still count whole periods.
    _clock = Timer.periodic(const Duration(milliseconds: 100), (timer) {
      if (_machine.paused) _pausedTicks++;
      _apply(_machine.tick((timer.tick - _pausedTicks) / 10));
    });
  }

  void _stopUi() {
    _clock?.cancel();
    _clock = null;
    _levels?.cancel();
    _levels = null;
    _removeBar();
    if (!mounted) return;
    widget.onRecordingChanged?.call(false);
    setState(() {});
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
    final seconds = _machine.seconds;
    final peaks = voicePeaks(List.of(_machine.levels));
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
    if (!mounted) {
      _delete(path);
      return;
    }
    setState(() => _sending = true);
    try {
      await VoiceNoteButton.sender(
        context,
        threadId: widget.threadId,
        path: path,
        seconds: seconds,
        peaks: peaks,
      );
    } on SessionRequestCancelled {
      // Signed out meanwhile: nothing to show.
    } on ApiError catch (e) {
      if (mounted) {
        LnToast.show(
          context,
          context.l10n.errorText(e.code),
          kind: LnToastKind.error,
        );
      }
    } catch (_) {
      if (mounted) {
        LnToast.show(
          context,
          context.l10n.errorText('request_failed'),
          kind: LnToastKind.error,
        );
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  /// The mic's rect in the overlay, as laid out now.
  Rect? _micRect(RenderBox overlayBox) {
    if (!mounted) return null;
    final box = context.findRenderObject() as RenderBox?;
    if (box == null || !box.attached || !box.hasSize) return null;
    return box.localToGlobal(Offset.zero, ancestor: overlayBox) & box.size;
  }

  void _showBar() {
    if (_bar != null) return;
    final overlay = Overlay.maybeOf(context);
    final overlayBox = overlay?.context.findRenderObject() as RenderBox?;
    if (overlay == null || overlayBox == null) return;
    final first = _micRect(overlayBox);
    if (first == null) return;
    final entry = OverlayEntry(
      builder: (_) => _RecordingLayer(
        link: _link,
        // Only the mic's horizontal place sizes the bar (the keyboard moves it vertically,
        // and the followers track that).
        anchor: _micRect(overlayBox) ?? first,
        overlaySize: overlayBox.size,
        rtl: _rtl,
        machine: _machine,
        theme: context.ln,
        l10n: context.l10n,
        onDelete: () => _apply(_machine.deleteTap()),
        onPause: () => _apply(_machine.pauseTap()),
        onSend: () => _apply(_machine.sendTap()),
      ),
    );
    _bar = entry;
    overlay.insert(entry);
  }

  void _removeBar() {
    _bar?.remove();
    _bar = null;
  }

  @override
  Widget build(BuildContext context) {
    registerVoiceStrings(context.l10n);
    final ln = context.ln;
    final c = ln.colors;
    final active = _machine.phase == VoiceNotePhase.recording;
    final mic = Semantics(
      button: true,
      enabled: widget.enabled,
      label: context.t('voiceNote'),
      hint: context.t('vn_hold'),
      child: Listener(
        onPointerDown: _down,
        onPointerMove: _move,
        onPointerUp: _up,
        onPointerCancel: _cancel,
        behavior: HitTestBehavior.opaque,
        child: SizedBox.square(
          dimension: LnSize.composerHeight - 2,
          child: Center(
            child: AnimatedOpacity(
              duration: LnMotion.fast,
              opacity: _machine.phase == VoiceNotePhase.pressing
                  ? LnMotion.pressOpacity
                  : 1,
              // 44 dp: the disc fills the composer's trailing slot, clear of the pill's 1 dp
              // border.
              child: Container(
                width: LnSize.composerHeight - 4,
                height: LnSize.composerHeight - 4,
                decoration: BoxDecoration(
                  color: active ? c.error : c.surface,
                  shape: BoxShape.circle,
                ),
                alignment: Alignment.center,
                child: _sending
                    ? LnSpinner(size: 18, color: c.fgWarm)
                    : Icon(
                        FIcons.mic,
                        size: LnSize.composerIcon,
                        color: active
                            ? c.onAccent
                            : (widget.enabled ? c.fgWarm : c.fgSubtle),
                      ),
              ),
            ),
          ),
        ),
      ),
    );
    return CompositedTransformTarget(link: _link, child: mic);
  }
}

/// The recording bar over the composer, the lock above the mic, and (locked) its buttons.
class _RecordingLayer extends StatelessWidget {
  const _RecordingLayer({
    required this.link,
    required this.anchor,
    required this.overlaySize,
    required this.rtl,
    required this.machine,
    required this.theme,
    required this.l10n,
    required this.onDelete,
    required this.onPause,
    required this.onSend,
  });

  /// The mic's place: the followers stay on it while the composer moves.
  final LayerLink link;

  /// The mic's rect in the overlay (its horizontal place sizes the bar).
  final Rect anchor;
  final Size overlaySize;
  final bool rtl;
  final VoiceNoteMachine machine;
  final LnThemeData theme;
  final L10n l10n;
  final VoidCallback onDelete;
  final VoidCallback onPause;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    // The pill spans from the chrome gutter to the mic's outer edge (+1 dp border), its
    // bottom 1 dp under the mic's; the lock stands 48 dp above the mic.
    const gutter = LnSpace.chromeGutter;
    final width = rtl
        ? overlaySize.width - gutter - anchor.left + 1
        : anchor.right + 1 - gutter;
    final end = rtl ? Alignment.bottomLeft : Alignment.bottomRight;
    return Directionality(
      textDirection: rtl ? TextDirection.rtl : TextDirection.ltr,
      child: LnTheme(
        data: theme,
        child: Stack(
          children: [
            Positioned(
              left: 0,
              top: 0,
              child: CompositedTransformFollower(
                link: link,
                showWhenUnlinked: false,
                targetAnchor: end,
                followerAnchor: end,
                offset: Offset(rtl ? -1 : 1, 1),
                child: SizedBox(
                  width: width < 0 ? 0 : width,
                  height: LnSize.composerHeight,
                  child: VoiceNoteBar(
                    machine: machine,
                    onDelete: onDelete,
                    onPause: onPause,
                    onSend: onSend,
                  ),
                ),
              ),
            ),
            if (machine.phase == VoiceNotePhase.recording)
              Positioned(
                left: 0,
                top: 0,
                child: CompositedTransformFollower(
                  link: link,
                  showWhenUnlinked: false,
                  targetAnchor: Alignment.topCenter,
                  followerAnchor: Alignment.bottomCenter,
                  offset: Offset(0, -48 - machine.lockProgress * 24),
                  child: IgnorePointer(child: _LockHint(theme: theme)),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// The bar's content (pure: goldens render it directly).
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
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final locked = machine.phase == VoiceNotePhase.locked;
    final time = voiceClock(machine.seconds);
    return Container(
      decoration: BoxDecoration(
        color: c.surface,
        borderRadius: const BorderRadius.all(
          Radius.circular(LnSize.composerHeight / 2),
        ),
        border: Border.all(color: c.border),
        boxShadow: ln.chromeShadow,
      ),
      child: Row(
        children: [
          if (locked)
            _BarButton(
              icon: FIcons.trash2,
              label: l10n.t('vn_delete'),
              color: c.error,
              onTap: onDelete,
            )
          else
            const SizedBox(width: LnSpace.md),
          _RecDot(color: c.error, paused: machine.paused),
          const SizedBox(width: LnSpace.xs),
          Semantics(
            label: l10n.t('vn_length'),
            value: time,
            child: ExcludeSemantics(
              child: Text(
                ltr(time),
                style: ln.text.captionStrong.copyWith(
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ),
          ),
          const SizedBox(width: LnSpace.sm),
          Expanded(
            child: locked
                ? _LiveWave(levels: machine.live, color: c.fg)
                : _SlideHint(
                    text: l10n.t('vn_slideCancel'),
                    progress: machine.cancelProgress,
                    color: c.fgMuted,
                    style: ln.text.footnote,
                  ),
          ),
          if (locked) ...[
            _BarButton(
              icon: machine.paused ? FIcons.mic : FIcons.pause,
              label: l10n.t(machine.paused ? 'vn_resume' : 'vn_pause'),
              color: c.fgWarm,
              onTap: onPause,
            ),
            LnTappable(
              onTap: onSend,
              haptic: true,
              semanticLabel: l10n.t('vn_send'),
              excludeChildSemantics: true,
              child: const SizedBox.square(
                dimension: LnSize.composerHeight - 2,
                child: Center(child: SendDisc()),
              ),
            ),
          ] else
            const SizedBox(width: LnSize.composerHeight + LnSpace.xs),
        ],
      ),
    );
  }
}

class _BarButton extends StatelessWidget {
  const _BarButton({
    required this.icon,
    required this.label,
    required this.color,
    this.onTap,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => LnTappable(
    onTap: onTap,
    haptic: true,
    semanticLabel: label,
    excludeChildSemantics: true,
    child: SizedBox.square(
      dimension: LnSize.composerHeight - 2,
      child: Icon(icon, size: LnSize.composerIcon, color: color),
    ),
  );
}

/// The blinking red dot of a running recording (steady while paused).
class _RecDot extends StatefulWidget {
  const _RecDot({required this.color, required this.paused});

  final Color color;
  final bool paused;

  @override
  State<_RecDot> createState() => _RecDotState();
}

class _RecDotState extends State<_RecDot> with SingleTickerProviderStateMixin {
  late final AnimationController _blink = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );

  @override
  void initState() {
    super.initState();
    _sync();
  }

  @override
  void didUpdateWidget(_RecDot old) {
    super.didUpdateWidget(old);
    _sync();
  }

  void _sync() {
    final reduced = WidgetsBinding
        .instance
        .platformDispatcher
        .accessibilityFeatures
        .disableAnimations;
    if (widget.paused || reduced) {
      _blink.stop();
      _blink.value = 1;
    } else if (!_blink.isAnimating) {
      _blink.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _blink.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(
    opacity: Tween(begin: 0.25, end: 1.0).animate(_blink),
    child: Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(color: widget.color, shape: BoxShape.circle),
    ),
  );
}

/// «‹ Slide to cancel», fading as the finger travels toward the start.
class _SlideHint extends StatelessWidget {
  const _SlideHint({
    required this.text,
    required this.progress,
    required this.color,
    required this.style,
  });

  final String text;
  final double progress;
  final Color color;
  final TextStyle style;

  @override
  Widget build(BuildContext context) {
    final rtl = Directionality.of(context) == TextDirection.rtl;
    return Opacity(
      opacity: (1 - progress).clamp(0.2, 1.0),
      child: Transform.translate(
        offset: Offset((rtl ? 1 : -1) * progress * 40, 0),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Points toward the start (forui's Lucide chevrons mirror themselves in RTL).
            Icon(FIcons.chevronLeft, size: 16, color: color),
            const SizedBox(width: 2),
            Flexible(
              child: Text(
                text,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: style.copyWith(color: color),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The live waveform: the last 32 levels, newest at the end.
class _LiveWave extends StatelessWidget {
  const _LiveWave({required this.levels, required this.color});

  final List<double> levels;
  final Color color;

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: SizedBox(
      height: 28,
      child: LayoutBuilder(
        builder: (context, box) {
          const n = VoiceNoteLimits.liveBars;
          final pad = n - levels.length;
          final each = box.maxWidth / n;
          return Row(
            children: [
              for (var i = 0; i < n; i++)
                SizedBox(
                  width: each,
                  child: Center(
                    child: Container(
                      width: (each * 0.5).clamp(1.5, 3.0),
                      height: i < pad ? 3 : 4 + levels[i - pad] * 24,
                      decoration: BoxDecoration(
                        color: i < pad ? color.withValues(alpha: 0.25) : color,
                        borderRadius: const BorderRadius.all(
                          Radius.circular(2),
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    ),
  );
}

/// The lock above the mic while recording (slide up to lock).
class _LockHint extends StatelessWidget {
  const _LockHint({required this.theme});

  final LnThemeData theme;

  @override
  Widget build(BuildContext context) {
    final c = theme.colors;
    return Container(
      width: 40,
      height: 72,
      decoration: ShapeDecoration(
        color: c.surface,
        shape: StadiumBorder(side: BorderSide(color: c.border)),
        shadows: theme.chromeShadow,
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          Icon(FIcons.lock, size: 18, color: c.fgWarm),
          Icon(FIcons.chevronUp, size: 16, color: c.fgMuted),
        ],
      ),
    );
  }
}
