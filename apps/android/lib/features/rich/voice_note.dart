// An owner voice note (`rich_content` voice part, server-written): play / pause, the 44-bar
// waveform the server stored (filled as it plays), and the length as m:ss. The audio is the
// voice artifact, read through the owner session (never a credential in a URL) into the
// app's cache and played with just_audio. Its transcript is the message's own text.
import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:just_audio/just_audio.dart';

import '../../design/design.dart';
import '../../l10n/l10n.dart';
import 'artifact_image.dart';
import 'rich_parts.dart';

class VoiceNoteView extends StatefulWidget {
  const VoiceNoteView({
    super.key,
    required this.part,
    this.onUserBubble = false,
  });

  final VoicePart part;
  final bool onUserBubble;

  @override
  State<VoiceNoteView> createState() => _VoiceNoteViewState();
}

class _VoiceNoteViewState extends State<VoiceNoteView> {
  /// Only one voice note plays at a time.
  static _VoiceNoteViewState? _active;

  AudioPlayer? _player;
  StreamSubscription<PlayerState>? _stateSub;
  StreamSubscription<Duration>? _positionSub;
  bool _playing = false;
  bool _loading = false;
  bool _failed = false;
  Duration _position = Duration.zero;

  @override
  void dispose() {
    if (identical(_active, this)) _active = null;
    _stateSub?.cancel();
    _positionSub?.cancel();
    _player?.dispose();
    super.dispose();
  }

  Future<void> _toggle() async {
    // One load at a time: a second tap while the first is still starting does nothing.
    if (_loading) return;
    unawaited(HapticFeedback.selectionClick());
    final player = _player;
    if (player != null && _playing) {
      await player.pause();
      return;
    }
    if (player == null) {
      setState(() {
        _loading = true;
        _failed = false;
      });
    }
    if (!identical(_active, this)) {
      final previous = _active;
      _active = this;
      await previous?._player?.pause();
    }
    if (player != null) {
      if (player.processingState == ProcessingState.completed) {
        await player.seek(Duration.zero);
      }
      unawaited(player.play());
      return;
    }
    AudioPlayer? created;
    try {
      final bytes = await ArtifactBytesCache.load(widget.part.artifactId);
      final file = await ArtifactBytesCache.voiceFile(widget.part.artifactId);
      if (!file.existsSync() || file.lengthSync() != bytes.length) {
        await file.writeAsBytes(bytes, flush: true);
      }
      created = AudioPlayer();
      await created.setFilePath(file.path);
      if (!mounted) {
        await created.dispose();
        return;
      }
      _player = created;
      _stateSub = created.playerStateStream.listen((s) {
        if (!mounted) return;
        final done = s.processingState == ProcessingState.completed;
        setState(() {
          _playing = s.playing && !done;
          if (done) _position = Duration.zero;
        });
      });
      _positionSub = created.positionStream.listen((p) {
        if (mounted) setState(() => _position = p);
      });
      setState(() => _loading = false);
      // Another note may have started while this one loaded.
      if (identical(_active, this)) unawaited(created.play());
    } catch (_) {
      if (created != null && !identical(_player, created)) {
        unawaited(created.dispose());
      }
      if (mounted) {
        setState(() {
          _loading = false;
          _failed = true;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final onUser = widget.onUserBubble;
    final ink = onUser ? c.onUserBubble : c.fg;
    final dim = onUser ? c.onUserBubble.withValues(alpha: 0.45) : c.fgSubtle;
    final total = widget.part.duration;
    final progress = total <= 0
        ? 0.0
        : (_position.inMilliseconds / 1000 / total).clamp(0.0, 1.0);
    final shown = _playing || _position > Duration.zero
        ? voiceClock(_position.inMilliseconds / 1000)
        : voiceClock(total);
    final label = '${context.t('voiceNote')} · ${voiceClock(total)}';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            // A 36 dp disc inside a 48 dp hit area.
            LnTappable(
              onTap: _loading ? null : _toggle,
              semanticLabel: _playing
                  ? context.t('pause')
                  : context.t('rich_play'),
              semanticHint: label,
              excludeChildSemantics: true,
              child: SizedBox.square(
                dimension: 48,
                child: Center(
                  child: Container(
                    width: 36,
                    height: 36,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: onUser ? c.onUserBubble : c.fgStrong,
                      shape: BoxShape.circle,
                    ),
                    child: _loading
                        ? LnSpinner(
                            size: 16,
                            color: onUser ? c.userBubble : c.bg,
                          )
                        : Icon(
                            _playing ? FIcons.pause : FIcons.play,
                            size: 18,
                            color: onUser ? c.userBubble : c.bg,
                          ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 4),
            ExcludeSemantics(
              child: SizedBox(
                width: 44 * 3.0,
                height: 28,
                child: CustomPaint(
                  painter: _WavePainter(
                    peaks: widget.part.peaks,
                    progress: progress,
                    played: ink,
                    rest: dim,
                    rtl: Directionality.of(context) == TextDirection.rtl,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 10),
            Text(
              ltr(shown),
              style: ln.text.footnote.copyWith(
                color: ink,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ],
        ),
        if (_failed || widget.part.transcriptStatus != 'done')
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              _failed
                  ? context.t('rich_voiceFailed')
                  : widget.part.transcriptStatus == 'failed'
                  ? context.t('rich_transcriptFailed')
                  : context.t('rich_transcribing'),
              style: ln.text.small.copyWith(
                color: onUser
                    ? c.onUserBubble.withValues(alpha: 0.75)
                    : c.fgMuted,
              ),
            ),
          ),
      ],
    );
  }
}

class _WavePainter extends CustomPainter {
  _WavePainter({
    required this.peaks,
    required this.progress,
    required this.played,
    required this.rest,
    required this.rtl,
  });

  final List<int> peaks;
  final double progress;
  final Color played;
  final Color rest;
  final bool rtl;

  @override
  void paint(Canvas canvas, Size size) {
    if (peaks.isEmpty) return;
    final pitch = size.width / peaks.length;
    final bar = pitch * 0.6;
    final paint = Paint()
      ..strokeCap = StrokeCap.round
      ..strokeWidth = bar;
    for (var i = 0; i < peaks.length; i++) {
      final h = (peaks[i].clamp(0, 100) / 100) * (size.height - bar) + bar;
      final index = rtl ? peaks.length - 1 - i : i;
      final x = index * pitch + pitch / 2;
      paint.color = (i + 0.5) / peaks.length <= progress ? played : rest;
      canvas.drawLine(
        Offset(x, (size.height - h) / 2 + bar / 2),
        Offset(x, (size.height + h) / 2 - bar / 2),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_WavePainter old) =>
      old.progress != progress ||
      old.played != played ||
      old.rest != rest ||
      old.rtl != rtl ||
      !identical(old.peaks, peaks);
}
