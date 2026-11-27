import 'package:flutter/material.dart'
    show InputDecoration, Material, MaterialType, TextField;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../l10n/format.dart' show voiceClock;
import '../theme.dart';
import '../tokens.dart';
import 'glyphs.dart';
import 'icons.dart';
import 'tappable.dart';

/// The message composer pill: min 48 dp, radius 24 (a stadium on one line, a rounded rect as it grows
/// to [maxLines]), surface fill, hairline border, chrome shadow. Leading "+" and trailing mic (or the
/// caller's [micButton]); the mic turns into a 32 dp send disc when the field has text (or
/// [sendWithoutText]), or a stop disc while [running] with an empty field. Optional [attachments] sit
/// above the field inside the pill; a [replyBar] is its own pill 7 dp above it.
///
/// With [holdToTalk], an empty, unfocused composer is a press-to-talk surface: a long press anywhere
/// on the pill starts a hold (see [ComposerHoldToTalk]) and a tap on the field focuses it.
///
/// Pure UI: the caller owns [controller] and reacts to the callbacks. Lay it out with the 20 dp chrome
/// gutter (`EdgeInsetsDirectional.symmetric(horizontal: LnSpace.chromeGutter)`).
class Composer extends StatefulWidget {
  const Composer({
    super.key,
    required this.controller,
    required this.placeholder,
    this.focusNode,
    this.onSend,
    this.onAttach,
    this.onMic,
    this.onStop,
    this.running = false,
    this.enabled = true,
    this.inputEnabled,
    this.sendEnabled = true,
    this.maxLines = 6,
    this.attachments,
    this.replyBar,
    this.attachLabel = 'Add attachment',
    this.micLabel = 'Voice input',
    this.sendLabel = 'Send',
    this.stopLabel = 'Stop',
    this.micButton,
    this.sendWithoutText = false,
    this.holdToTalk,
    this.recordingBar,
  });

  final TextEditingController controller;
  final String placeholder;
  final FocusNode? focusNode;

  /// Called with the trimmed text when the send disc is tapped.
  final ValueChanged<String>? onSend;
  final VoidCallback? onAttach;

  /// Mic tap; the mic is hidden when null and the field is empty (the send disc shows disabled).
  final VoidCallback? onMic;
  final VoidCallback? onStop;

  /// The caller's own mic for the trailing slot (e.g. a hold-to-record voice-note button), shown
  /// instead of the default mic when the field is empty; it handles its own gestures and semantics.
  /// A disabled composer shows its own inert mic instead. With [holdToTalk], pass a plain tap target
  /// here (or [onMic]): a long press on it starts the composer's hold.
  final Widget? micButton;

  /// Attachments are ready to go on their own: an empty field shows the enabled send disc, and
  /// [onSend] receives ''.
  final bool sendWithoutText;

  /// The agent is working: an empty field shows the stop disc.
  final bool running;

  /// False for read-only conversations: the field and buttons are inert.
  final bool enabled;

  /// False makes only the field and «+» inert (e.g. while recording a voice note); the trailing slot
  /// still follows [enabled]. Defaults to [enabled]; a false [enabled] wins. A hold already under
  /// way keeps reporting until the finger lifts.
  final bool? inputEnabled;

  /// False shows the send disc in its disabled colours (e.g. offline).
  final bool sendEnabled;
  final int maxLines;

  /// Row of [ComposerAttachmentChip]s shown above the field.
  final Widget? attachments;

  /// A [ComposerReplyBar] (reply or edit preview), drawn as its own pill 7 dp above the composer.
  final Widget? replyBar;

  final String attachLabel;
  final String micLabel;
  final String sendLabel;
  final String stopLabel;

  /// Press-to-talk on the empty, unfocused composer; null keeps the plain composer.
  final ComposerHoldToTalk? holdToTalk;

  /// While a voice note records: the [ComposerRecordingBar] drawn in place of the pill,
  /// bottom-aligned with it (its hint stands above). The pill stays mounted underneath, hidden,
  /// inert and out of the semantics tree, so a hold that started on it keeps reporting
  /// [ComposerHoldToTalk.onMove], [ComposerHoldToTalk.onEnd] and [ComposerHoldToTalk.onCancel]
  /// until the finger lifts; no new hold starts while it shows. Show the bar here rather than in
  /// place of the [Composer]: a removed composer takes its long press with it and the hold never
  /// ends.
  final Widget? recordingBar;

  /// The reply bar's distance above the composer (dp).
  static const double replyGap = 7;

  @override
  State<Composer> createState() => _ComposerState();
}

class _ComposerState extends State<Composer> {
  FocusNode? _ownFocus;
  bool _holding = false;

  FocusNode get _focus => widget.focusNode ?? (_ownFocus ??= FocusNode());

  /// Whether the text was empty at the last change: an empty ↔ non-empty change arms or disarms
  /// the hold, whoever changed the text.
  late bool _wasEmpty;

  @override
  void initState() {
    super.initState();
    _focus.addListener(_rebuild);
    widget.controller.addListener(_textChanged);
    _wasEmpty = widget.controller.text.isEmpty;
  }

  @override
  void didUpdateWidget(Composer old) {
    super.didUpdateWidget(old);
    final oldFocus = old.focusNode ?? _ownFocus;
    if (oldFocus != _focus) {
      oldFocus?.removeListener(_rebuild);
      _focus.addListener(_rebuild);
    }
    if (old.controller != widget.controller) {
      old.controller.removeListener(_textChanged);
      widget.controller.addListener(_textChanged);
    }
    _wasEmpty = widget.controller.text.isEmpty;
  }

  @override
  void dispose() {
    _focus.removeListener(_rebuild);
    widget.controller.removeListener(_textChanged);
    _ownFocus?.dispose();
    super.dispose();
  }

  void _rebuild() => setState(() {});

  void _textChanged() {
    final empty = widget.controller.text.isEmpty;
    if (empty != _wasEmpty && widget.holdToTalk != null) setState(() {});
    _wasEmpty = empty;
  }

  bool get _input => widget.enabled && (widget.inputEnabled ?? true);

  /// A hold can start: hold-to-talk is on, nothing records yet, the field is empty, unfocused and
  /// enabled.
  bool get _armed =>
      widget.holdToTalk != null &&
      widget.recordingBar == null &&
      _input &&
      widget.controller.text.isEmpty &&
      !_focus.hasFocus;

  void _holdStart(LongPressStartDetails details) {
    _holding = true;
    HapticFeedback.mediumImpact();
    widget.holdToTalk?.onStart?.call();
  }

  void _holdMove(LongPressMoveUpdateDetails details) {
    if (_holding) widget.holdToTalk?.onMove?.call(details.offsetFromOrigin);
  }

  void _holdEnd(LongPressEndDetails details) {
    if (!_holding) return;
    setState(() => _holding = false);
    widget.holdToTalk?.onEnd?.call();
  }

  void _holdCancel() {
    if (!_holding) return;
    setState(() => _holding = false);
    widget.holdToTalk?.onCancel?.call();
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final input = _input;
    final armed = _armed;
    final hold = armed || _holding;
    final placeholder = armed
        ? widget.holdToTalk!.placeholder ?? widget.placeholder
        : widget.placeholder;
    Widget pill = Container(
      constraints: const BoxConstraints(minHeight: LnSize.composerHeight),
      decoration: BoxDecoration(
        color: c.surface,
        borderRadius: const BorderRadius.all(
          Radius.circular(LnSize.composerHeight / 2),
        ),
        border: Border.all(color: c.border),
        boxShadow: ln.chromeShadow,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.attachments != null)
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(8, 8, 8, 0),
              child: widget.attachments,
            ),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              _ComposerIconButton(
                label: widget.attachLabel,
                onTap: input ? widget.onAttach : null,
                child: Icon(
                  FIcons.plus,
                  size: LnSize.composerIcon,
                  color: c.fgWarm,
                ),
              ),
              Expanded(
                child: Padding(
                  // 1 dp border on each side: one body line centred in the 46 dp inner height.
                  padding: EdgeInsets.symmetric(
                    vertical:
                        (LnSize.composerHeight -
                            2 -
                            ln.text.body.fontSize! * ln.text.body.height!) /
                        2,
                  ),
                  child: Stack(
                    children: [
                      // Material TextField (not forui's FTextField, see LnTextField) with the
                      // composer look.
                      Material(
                        type: MaterialType.transparency,
                        child: TextField(
                          controller: widget.controller,
                          focusNode: _focus,
                          enabled: input,
                          minLines: 1,
                          maxLines: widget.maxLines,
                          keyboardType: TextInputType.multiline,
                          textInputAction: TextInputAction.newline,
                          textCapitalization: TextCapitalization.sentences,
                          style: ln.text.body.copyWith(
                            color: input ? c.fg : c.fgSubtle,
                          ),
                          cursorColor: c.brand,
                          cursorWidth: 2,
                          cursorRadius: const Radius.circular(1),
                          keyboardAppearance: c.brightness,
                          decoration: InputDecoration.collapsed(
                            hintText: placeholder,
                            hintStyle: ln.text.body.copyWith(color: c.fgSubtle),
                          ),
                        ),
                      ),
                      // Armed: the field takes no long press of its own (no paste menu); a tap
                      // focuses it, a long press falls to the pill's hold.
                      if (armed)
                        Positioned.fill(
                          child: GestureDetector(
                            behavior: HitTestBehavior.opaque,
                            excludeFromSemantics: true,
                            onTap: _focus.requestFocus,
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              ValueListenableBuilder<TextEditingValue>(
                valueListenable: widget.controller,
                builder: (context, value, _) {
                  final hasText = value.text.trim().isNotEmpty;
                  final _TrailingMode mode;
                  if (hasText || widget.sendWithoutText) {
                    mode = _TrailingMode.send;
                  } else if (widget.running) {
                    mode = _TrailingMode.stop;
                  } else if (widget.onMic != null || widget.micButton != null) {
                    mode = _TrailingMode.mic;
                  } else {
                    mode = _TrailingMode.sendIdle;
                  }
                  return _Trailing(
                    mode: mode,
                    enabled: widget.enabled,
                    sendEnabled: widget.sendEnabled,
                    onMic: widget.onMic,
                    micButton: widget.micButton,
                    onStop: widget.onStop,
                    onSend: widget.onSend == null
                        ? null
                        : () => widget.onSend!(value.text.trim()),
                    micLabel: widget.micLabel,
                    sendLabel: widget.sendLabel,
                    stopLabel: widget.stopLabel,
                  );
                },
              ),
            ],
          ),
        ],
      ),
    );
    if (widget.recordingBar != null) {
      pill = Stack(
        alignment: Alignment.bottomCenter,
        children: [
          Visibility(
            visible: false,
            maintainState: true,
            maintainAnimation: true,
            maintainSize: true,
            child: pill,
          ),
          widget.recordingBar!,
        ],
      );
    }
    if (widget.holdToTalk != null) {
      // Not announced: a screen reader's long-press action would start and end the hold at once.
      // Screen-reader users record with the mic ([onMic] / [micButton]).
      pill = GestureDetector(
        excludeFromSemantics: true,
        onLongPressStart: hold ? _holdStart : null,
        onLongPressMoveUpdate: hold ? _holdMove : null,
        onLongPressEnd: hold ? _holdEnd : null,
        onLongPressCancel: hold ? _holdCancel : null,
        child: pill,
      );
    }
    if (widget.replyBar == null) return pill;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        widget.replyBar!,
        const SizedBox(height: Composer.replyGap),
        pill,
      ],
    );
  }
}

/// Press-to-talk on an empty, unfocused [Composer]: a long press anywhere on its pill starts a hold
/// that reports until the finger lifts; a tap on the field focuses it (the keyboard opens and
/// [placeholder] gives way to the composer's own).
@immutable
class ComposerHoldToTalk {
  const ComposerHoldToTalk({
    this.placeholder,
    this.onStart,
    this.onMove,
    this.onEnd,
    this.onCancel,
  });

  /// The field's hint while a hold can start ("Press and hold to talk, tap to type"); the
  /// composer's placeholder when null.
  final String? placeholder;

  /// The long press was recognised (after a medium haptic): start recording.
  final VoidCallback? onStart;

  /// The finger moved: its offset from where the hold started, in logical pixels on the screen's
  /// axes (+x right, +y down), e.g. toward the start to cancel, up to lock.
  final ValueChanged<Offset>? onMove;

  /// The finger lifted.
  final VoidCallback? onEnd;

  /// The system took the gesture away (another route, an incoming call).
  final VoidCallback? onCancel;
}

enum _TrailingMode { mic, send, sendIdle, stop }

class _Trailing extends StatelessWidget {
  const _Trailing({
    required this.mode,
    required this.enabled,
    required this.sendEnabled,
    required this.onMic,
    required this.micButton,
    required this.onStop,
    required this.onSend,
    required this.micLabel,
    required this.sendLabel,
    required this.stopLabel,
  });

  final _TrailingMode mode;
  final bool enabled;
  final bool sendEnabled;
  final VoidCallback? onMic;
  final Widget? micButton;
  final VoidCallback? onStop;
  final VoidCallback? onSend;
  final String micLabel;
  final String sendLabel;
  final String stopLabel;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final Widget child = switch (mode) {
      _TrailingMode.mic when micButton != null && enabled => SizedBox.square(
        key: const ValueKey('mic'),
        dimension: LnSize.composerHeight - 2,
        child: Center(child: micButton),
      ),
      _TrailingMode.mic => _ComposerIconButton(
        key: const ValueKey('mic'),
        label: micLabel,
        onTap: enabled ? onMic : null,
        child: Icon(FIcons.mic, size: LnSize.composerIcon, color: c.fgWarm),
      ),
      _TrailingMode.send || _TrailingMode.sendIdle => _ComposerIconButton(
        key: const ValueKey('send'),
        label: sendLabel,
        onTap: enabled && sendEnabled && mode == _TrailingMode.send
            ? onSend
            : null,
        child: SendDisc(
          enabled: enabled && sendEnabled && mode == _TrailingMode.send,
        ),
      ),
      _TrailingMode.stop => _ComposerIconButton(
        key: const ValueKey('stop'),
        label: stopLabel,
        onTap: enabled ? onStop : null,
        child: const SendDisc(stop: true),
      ),
    };
    return AnimatedSwitcher(
      duration: LnMotion.fast,
      switchInCurve: LnMotion.emphasized,
      switchOutCurve: Curves.easeIn,
      transitionBuilder: (child, animation) => FadeTransition(
        opacity: animation,
        child: ScaleTransition(
          scale: Tween<double>(begin: 0.6, end: 1).animate(animation),
          child: child,
        ),
      ),
      child: child,
    );
  }
}

/// The 36 dp send disc (fgStrong disc + arrow), its disabled look, or the stop variant.
class SendDisc extends StatelessWidget {
  const SendDisc({super.key, this.enabled = true, this.stop = false});

  final bool enabled;
  final bool stop;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final on = enabled || stop;
    return AnimatedContainer(
      duration: LnMotion.fast,
      width: LnSize.sendButton,
      height: LnSize.sendButton,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: on ? c.sendDisc : c.sendDisabledDisc,
      ),
      alignment: Alignment.center,
      child: LnGlyph(
        stop ? LnGlyphs.stop : LnGlyphs.sendArrow,
        size: 20,
        color: on ? c.sendArrow : c.sendDisabledArrow,
      ),
    );
  }
}

class _ComposerIconButton extends StatelessWidget {
  const _ComposerIconButton({
    super.key,
    required this.label,
    required this.onTap,
    required this.child,
  });

  final String label;
  final VoidCallback? onTap;
  final Widget child;

  @override
  Widget build(BuildContext context) => LnTappable(
    onTap: onTap,
    enabled: onTap != null,
    haptic: true,
    semanticLabel: label,
    excludeChildSemantics: true,
    child: SizedBox.square(
      dimension: LnSize.composerHeight - 2,
      child: Center(
        child: SizedBox.square(
          dimension: LnSize.composerButton,
          child: Center(child: child),
        ),
      ),
    ),
  );
}

/// Reply / edit preview: its own pill (min 48 dp, the composer's surface, hairline and shadow) that
/// the [Composer] draws 7 dp above itself. A 2 × 16 dp quote bar at the start, the quoted [text] on
/// one 16 dp line, both in [LnPalette.fgMuted], and a ✕ at the end. An optional [title] line above
/// the text ([icon] and the title, 12 dp) names the mode, e.g. "Editing message"; leave it null for
/// a plain reply.
class ComposerReplyBar extends StatelessWidget {
  const ComposerReplyBar({
    super.key,
    this.title,
    required this.text,
    this.onClose,
    this.icon = LnIcons.reply,
    this.closeLabel = 'Cancel reply',
  });

  /// "Editing message"; null shows the quote alone.
  final String? title;
  final String text;
  final VoidCallback? onClose;

  /// Leads the [title] line.
  final IconData icon;
  final String closeLabel;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    // A DecoratedBox, not a Container: the ✕ is a whole 48 dp target at the end edge (the hairline
    // paints under it).
    return DecoratedBox(
      decoration: BoxDecoration(
        color: c.surface,
        borderRadius: const BorderRadius.all(
          Radius.circular(LnSize.composerHeight / 2),
        ),
        border: Border.all(color: c.border),
        boxShadow: ln.chromeShadow,
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: LnSize.composerHeight),
        child: Padding(
          padding: EdgeInsetsDirectional.only(
            start: LnSpace.md,
            end: onClose == null ? LnSpace.md : 0,
          ),
          child: Row(
            children: [
              Container(
                width: 2,
                height: 16,
                decoration: BoxDecoration(
                  color: c.fgMuted,
                  borderRadius: const BorderRadius.all(Radius.circular(1)),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (title != null)
                      Row(
                        children: [
                          Icon(icon, size: 14, color: c.fgMuted),
                          const SizedBox(width: 4),
                          Flexible(
                            child: Text(
                              title!,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: ln.text.smallStrong.copyWith(
                                color: c.fgMuted,
                              ),
                            ),
                          ),
                        ],
                      ),
                    Text(
                      text,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: ln.text.body.copyWith(color: c.fgMuted),
                    ),
                  ],
                ),
              ),
              if (onClose != null)
                LnTappable(
                  onTap: onClose,
                  semanticLabel: closeLabel,
                  excludeChildSemantics: true,
                  child: SizedBox.square(
                    dimension: LnSize.minTouch,
                    child: Icon(
                      FIcons.x,
                      size: LnSize.chromeIcon,
                      color: c.fgMuted,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Attachment chip inside the composer (file/photo name, optional upload progress, remove button).
class ComposerAttachmentChip extends StatelessWidget {
  const ComposerAttachmentChip({
    super.key,
    required this.label,
    this.icon = FIcons.file,
    this.thumbnail,
    this.progress,
    this.failed = false,
    this.onRemove,
    this.removeLabel = 'Remove attachment',
  });

  final String label;
  final IconData icon;

  /// Image thumbnail replacing the icon tile.
  final Widget? thumbnail;

  /// Upload progress 0..1; null when done.
  final double? progress;
  final bool failed;
  final VoidCallback? onRemove;
  final String removeLabel;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Container(
      height: 48,
      constraints: const BoxConstraints(maxWidth: 220),
      padding: const EdgeInsetsDirectional.fromSTEB(6, 6, 2, 6),
      decoration: BoxDecoration(
        color: c.fill1,
        borderRadius: const BorderRadius.all(Radius.circular(14)),
        border: failed
            ? Border.all(color: c.error.withValues(alpha: 0.5))
            : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          ClipRRect(
            borderRadius: const BorderRadius.all(Radius.circular(9)),
            child: SizedBox.square(
              dimension: 36,
              child:
                  thumbnail ??
                  ColoredBox(
                    color: c.surface,
                    child: Icon(
                      failed ? FIcons.circleAlert : icon,
                      size: 18,
                      color: failed ? c.error : c.fgMuted,
                    ),
                  ),
            ),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: ln.text.captionStrong.copyWith(color: c.fg),
                ),
                if (progress != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: ClipRRect(
                      borderRadius: const BorderRadius.all(Radius.circular(2)),
                      child: SizedBox(
                        height: 3,
                        width: 96,
                        child: Stack(
                          children: [
                            ColoredBox(
                              color: c.fill3,
                              child: const SizedBox.expand(),
                            ),
                            FractionallySizedBox(
                              alignment: AlignmentDirectional.centerStart,
                              widthFactor: progress!.clamp(0, 1),
                              child: ColoredBox(color: c.brand),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          if (onRemove != null)
            LnTappable(
              onTap: onRemove,
              semanticLabel: removeLabel,
              excludeChildSemantics: true,
              child: SizedBox(
                width: 32,
                height: 36,
                child: Icon(FIcons.x, size: 16, color: c.fgMuted),
              ),
            ),
        ],
      ),
    );
  }
}

/// The recording look that stands in for the [Composer]'s pill while a voice note records: an
/// optional [hint] line centred 8 dp above a 48 dp pill with the composer's surface, hairline and
/// shadow. From the start: a Ø36 cancel circle (✕ on [LnPalette.fill1]; [LnPalette.error] while
/// [cancelArmed]), the [levels] (bars for heard levels, dots for the rest, newest at the end), the
/// [elapsed] time as Latin mm:ss («00:05», [voiceClock]) in [LnPalette.fgMuted], an optional pause
/// button ([onPause], locked only) and a Ø36 send disc in the selection colour with a white arrow.
/// Each circle sits centred in a 48 dp touch target that spans the pill's height.
///
/// While holding, the circles are the targets the finger moves to (not tappable); once [locked],
/// [onCancel] and [onSend] make them buttons. Pass it as [Composer.recordingBar]: the composer
/// stays mounted underneath, so the hold that started the recording keeps reporting until the
/// finger lifts (a composer swapped out for the bar would drop the hold).
class ComposerRecordingBar extends StatelessWidget {
  const ComposerRecordingBar({
    super.key,
    required this.elapsed,
    this.levels = const [],
    this.locked = false,
    this.cancelArmed = false,
    this.hint,
    this.onCancel,
    this.onSend,
    this.onPause,
    this.paused = false,
    this.cancelLabel = 'Cancel recording',
    this.sendLabel = 'Send voice note',
    this.pauseLabel = 'Pause',
    this.resumeLabel = 'Resume',
    this.lengthLabel = 'Recording length',
  });

  final Duration elapsed;

  /// Levels 0..1, oldest first; the newest sits at the end.
  final List<double> levels;

  /// Hands-free: the circles are buttons and the pause button shows.
  final bool locked;

  /// The finger is over the cancel circle: lifting it cancels.
  final bool cancelArmed;

  /// The caller's instruction above the pill («ارفع إصبعك للإلغاء», «‹ Slide to cancel»).
  final String? hint;
  final VoidCallback? onCancel;
  final VoidCallback? onSend;

  /// Pause or resume (Lonora-specific); shown only when [locked].
  final VoidCallback? onPause;
  final bool paused;

  final String cancelLabel;
  final String sendLabel;
  final String pauseLabel;
  final String resumeLabel;

  /// Names the timer for screen readers; its value is the mm:ss text.
  final String lengthLabel;

  static const double circle = LnSize.sendButton;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final time = voiceClock(elapsed.inSeconds, twoDigitMinutes: true);
    Widget slot({
      required String label,
      required VoidCallback? onTap,
      required Widget child,
    }) => LnTappable(
      onTap: locked ? onTap : null,
      enabled: locked && onTap != null,
      haptic: true,
      semanticLabel: label,
      excludeChildSemantics: true,
      child: SizedBox.square(
        dimension: LnSize.minTouch,
        child: Center(child: child),
      ),
    );
    // A DecoratedBox, not a Container: the row spans the full 48 dp (the hairline paints under
    // its edges), so the end slots are whole 48 dp targets.
    final pill = DecoratedBox(
      decoration: BoxDecoration(
        color: c.surface,
        borderRadius: const BorderRadius.all(
          Radius.circular(LnSize.composerHeight / 2),
        ),
        border: Border.all(color: c.border),
        boxShadow: ln.chromeShadow,
      ),
      child: SizedBox(
        height: LnSize.composerHeight,
        child: Row(
          children: [
            slot(
              label: cancelLabel,
              onTap: onCancel,
              child: AnimatedContainer(
                duration: LnMotion.fast,
                width: circle,
                height: circle,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: cancelArmed ? c.error : c.fill1,
                ),
                child: Icon(
                  FIcons.x,
                  size: LnSize.composerIcon,
                  color: cancelArmed ? c.onAccent : c.fg,
                ),
              ),
            ),
            const SizedBox(width: LnSpace.xxs),
            Expanded(
              child: ExcludeSemantics(
                child: SizedBox(
                  height: 24,
                  child: CustomPaint(
                    painter: _LevelsPainter(
                      levels: levels,
                      color: c.fgMuted,
                      rtl: Directionality.of(context) == TextDirection.rtl,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: LnSpace.sm),
            Semantics(
              label: lengthLabel,
              value: time,
              child: ExcludeSemantics(
                child: Text(
                  time,
                  textDirection: TextDirection.ltr,
                  style: ln.text.body.copyWith(
                    color: c.fgMuted,
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
              ),
            ),
            if (locked && onPause != null)
              slot(
                label: paused ? resumeLabel : pauseLabel,
                onTap: onPause,
                child: Icon(
                  paused ? FIcons.mic : FIcons.pause,
                  size: LnSize.composerIcon,
                  color: c.fgWarm,
                ),
              )
            else
              const SizedBox(width: LnSpace.xxs),
            slot(
              label: sendLabel,
              onTap: onSend,
              child: Container(
                width: circle,
                height: circle,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: c.selection,
                ),
                child: LnGlyph(
                  LnGlyphs.sendArrow,
                  size: LnSize.composerIcon,
                  color: c.onAccent,
                ),
              ),
            ),
          ],
        ),
      ),
    );
    if (hint == null) return pill;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          hint!,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          textAlign: TextAlign.center,
          style: ln.text.caption.copyWith(color: c.fgSubtle),
        ),
        const SizedBox(height: LnSpace.xs),
        pill,
      ],
    );
  }
}

/// Level bars (3 dp wide, 5 dp pitch, 3–24 dp tall) for the heard levels at the end side, 3 dp dots
/// for the room not yet filled.
class _LevelsPainter extends CustomPainter {
  _LevelsPainter({
    required this.levels,
    required this.color,
    required this.rtl,
  });

  final List<double> levels;
  final Color color;
  final bool rtl;

  static const double pitch = 5;
  static const double bar = 3;

  @override
  void paint(Canvas canvas, Size size) {
    final n = (size.width / pitch).floor();
    if (n <= 0) return;
    final paint = Paint()
      ..color = color
      ..isAntiAlias = true;
    final shown = levels.length > n
        ? levels.sublist(levels.length - n)
        : levels;
    final empty = n - shown.length;
    final midY = size.height / 2;
    for (var i = 0; i < n; i++) {
      // Slot i counted from the start; the newest level fills the last slot.
      final x = (rtl ? n - 1 - i : i) * pitch + (pitch - bar) / 2 + bar / 2;
      if (i < empty) {
        canvas.drawCircle(Offset(x, midY), bar / 2, paint);
      } else {
        final level = shown[i - empty].clamp(0.0, 1.0);
        final h = bar + level * (size.height - bar);
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromCenter(center: Offset(x, midY), width: bar, height: h),
            const Radius.circular(bar / 2),
          ),
          paint,
        );
      }
    }
  }

  @override
  bool shouldRepaint(_LevelsPainter old) =>
      old.levels != levels || old.color != color || old.rtl != rtl;
}
