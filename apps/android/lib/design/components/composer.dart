import 'package:flutter/material.dart'
    show InputDecoration, Material, MaterialType, TextField;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../theme.dart';
import '../tokens.dart';
import 'glyphs.dart';
import 'icons.dart';
import 'tappable.dart';

/// The message composer pill: min 48 dp, radius 24 (a stadium on one line, a rounded rect as it grows
/// to [maxLines]), surface fill, hairline border, chrome shadow. Leading "+" and trailing mic (or the
/// caller's [micButton]); the mic turns into a 32 dp send disc when the field has text (or
/// [sendWithoutText]), or a stop disc while [running] with an empty field. Optional [attachments] and
/// [replyBar] rows sit above the field inside the pill.
///
/// Pure UI: the caller owns [controller] and reacts to the callbacks. Lay it out with the 20 dp chrome
/// gutter (`EdgeInsetsDirectional.symmetric(horizontal: LnSpace.chromeGutter)`).
class Composer extends StatelessWidget {
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
  /// A disabled composer shows its own inert mic instead.
  final Widget? micButton;

  /// Attachments are ready to go on their own: an empty field shows the enabled send disc, and
  /// [onSend] receives ''.
  final bool sendWithoutText;

  /// The agent is working: an empty field shows the stop disc.
  final bool running;

  /// False for read-only conversations: the field and buttons are inert.
  final bool enabled;

  /// False makes only the field and «+» inert (e.g. while recording a voice note); the trailing slot
  /// still follows [enabled]. Defaults to [enabled]; a false [enabled] wins.
  final bool? inputEnabled;

  /// False shows the send disc in its disabled colours (e.g. offline).
  final bool sendEnabled;
  final int maxLines;

  /// Row of [ComposerAttachmentChip]s shown above the field.
  final Widget? attachments;

  /// A [ComposerReplyBar] (reply or edit preview) shown above the field.
  final Widget? replyBar;

  final String attachLabel;
  final String micLabel;
  final String sendLabel;
  final String stopLabel;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final input = enabled && (inputEnabled ?? true);
    return Container(
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
          if (replyBar != null)
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(8, 8, 8, 0),
              child: replyBar,
            ),
          if (attachments != null)
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(8, 8, 8, 0),
              child: attachments,
            ),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              _ComposerIconButton(
                label: attachLabel,
                onTap: input ? onAttach : null,
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
                  // Material TextField (not forui's FTextField, see LnTextField) with the composer look.
                  child: Material(
                    type: MaterialType.transparency,
                    child: TextField(
                      controller: controller,
                      focusNode: focusNode,
                      enabled: input,
                      minLines: 1,
                      maxLines: maxLines,
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
                ),
              ),
              ValueListenableBuilder<TextEditingValue>(
                valueListenable: controller,
                builder: (context, value, _) {
                  final hasText = value.text.trim().isNotEmpty;
                  final _TrailingMode mode;
                  if (hasText || sendWithoutText) {
                    mode = _TrailingMode.send;
                  } else if (running) {
                    mode = _TrailingMode.stop;
                  } else if (onMic != null || micButton != null) {
                    mode = _TrailingMode.mic;
                  } else {
                    mode = _TrailingMode.sendIdle;
                  }
                  return _Trailing(
                    mode: mode,
                    enabled: enabled,
                    sendEnabled: sendEnabled,
                    onMic: onMic,
                    micButton: micButton,
                    onStop: onStop,
                    onSend: onSend == null
                        ? null
                        : () => onSend!(value.text.trim()),
                    micLabel: micLabel,
                    sendLabel: sendLabel,
                    stopLabel: stopLabel,
                  );
                },
              ),
            ],
          ),
        ],
      ),
    );
  }
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

/// Reply / edit preview shown inside the composer above the field.
class ComposerReplyBar extends StatelessWidget {
  const ComposerReplyBar({
    super.key,
    required this.title,
    required this.text,
    this.onClose,
    this.icon = LnIcons.reply,
    this.closeLabel = 'Cancel reply',
  });

  /// "Replying to Travel desk" / "Editing message".
  final String title;
  final String text;
  final VoidCallback? onClose;
  final IconData icon;
  final String closeLabel;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Container(
      padding: const EdgeInsetsDirectional.fromSTEB(12, 8, 4, 8),
      decoration: BoxDecoration(
        color: c.fill1,
        borderRadius: const BorderRadius.all(Radius.circular(16)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 18, color: c.brand),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: ln.text.captionStrong.copyWith(color: c.brand),
                ),
                Text(
                  text,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: ln.text.caption.copyWith(color: c.fgMuted),
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
                dimension: 40,
                child: Icon(FIcons.x, size: 18, color: c.fgMuted),
              ),
            ),
        ],
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
