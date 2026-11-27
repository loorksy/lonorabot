import 'dart:math' as math;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../theme.dart';
import '../tokens.dart';
import 'icons.dart';
import 'tappable.dart';

enum BubbleSender { user, agent }

/// A quoted message shown at the top of a reply bubble.
@immutable
class BubbleQuote {
  const BubbleQuote({required this.author, required this.text});

  final String author;
  final String text;
}

/// Chat bubble. User bubbles are blue and end-aligned, agent bubbles neutral and start-aligned. Radius
/// 24 (single-line bubbles are full stadiums), padding 16 × 12, max width min(313, 78 % of the screen),
/// no border or shadow. Text is 16/24; the first line's ascent and the last line's descent keep the
/// font's own height, so n lines are n·24 + 18.75 dp tall in Roboto (one line: the 44 dp minimum).
/// Within a run of one sender's bubbles, [joinTop] and [joinBottom] narrow the corners on the
/// sender's side to 5 dp. Provide [text] or a custom [child].
class MessageBubble extends StatelessWidget {
  const MessageBubble({
    super.key,
    required this.sender,
    this.text,
    this.child,
    this.quote,
    this.editedLabel,
    this.footer,
    this.onTap,
    this.onLongPress,
    this.semanticLabel,
    this.maxWidth,
    this.joinTop = false,
    this.joinBottom = false,
    this.onSwipeReply,
    this.replyLabel,
  }) : assert(text != null || child != null);

  const MessageBubble.user(
    String this.text, {
    super.key,
    this.quote,
    this.editedLabel,
    this.footer,
    this.onLongPress,
    this.joinTop = false,
    this.joinBottom = false,
    this.onSwipeReply,
    this.replyLabel,
  }) : sender = BubbleSender.user,
       child = null,
       onTap = null,
       semanticLabel = null,
       maxWidth = null;

  const MessageBubble.agent(
    String this.text, {
    super.key,
    this.quote,
    this.editedLabel,
    this.footer,
    this.onLongPress,
    this.joinTop = false,
    this.joinBottom = false,
    this.onSwipeReply,
    this.replyLabel,
  }) : sender = BubbleSender.agent,
       child = null,
       onTap = null,
       semanticLabel = null,
       maxWidth = null;

  final BubbleSender sender;
  final String? text;

  /// Custom content (markdown, attachments). Inherits the bubble's text style.
  final Widget? child;
  final BubbleQuote? quote;

  /// Localised "edited" mark shown after the content.
  final String? editedLabel;

  /// Below-bubble slot aligned with the bubble (reactions, delivery state).
  final Widget? footer;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final String? semanticLabel;

  /// Overrides the default max width.
  final double? maxWidth;

  /// The previous bubble of this sender's run sits [LnSpace.bubbleRunGap] above: the top corner on
  /// the sender's side narrows to [LnRadius.bubbleJoin].
  final bool joinTop;

  /// The next bubble of this sender's run sits right below: the bottom corner on the sender's side
  /// narrows to [LnRadius.bubbleJoin].
  final bool joinBottom;

  /// Swipe to reply: dragging the bubble toward the end side past 64 dp calls this when released.
  /// A reply arrow fades in at the vacated start side, a light haptic marks the threshold and the
  /// bubble springs back. Screen readers get the same as the custom action [replyLabel].
  final VoidCallback? onSwipeReply;

  /// Name of the reply action for screen readers («رد»); required with [onSwipeReply].
  final String? replyLabel;

  bool get isUser => sender == BubbleSender.user;

  /// min(313, 78 % of [screenWidth]).
  static double maxWidthFor(double screenWidth) =>
      math.min(LnSize.bubbleMaxWidth, screenWidth * LnSize.bubbleMaxFraction);

  /// Lines of 24 dp whose first ascent and last descent keep the font's height.
  static const textHeightBehavior = TextHeightBehavior(
    applyHeightToFirstAscent: false,
    applyHeightToLastDescent: false,
    leadingDistribution: TextLeadingDistribution.even,
  );

  BorderRadiusDirectional get _radius {
    const full = Radius.circular(LnRadius.bubble);
    const joined = Radius.circular(LnRadius.bubbleJoin);
    final top = joinTop ? joined : full;
    final bottom = joinBottom ? joined : full;
    return isUser
        ? BorderRadiusDirectional.only(
            topStart: full,
            bottomStart: full,
            topEnd: top,
            bottomEnd: bottom,
          )
        : BorderRadiusDirectional.only(
            topStart: top,
            bottomStart: bottom,
            topEnd: full,
            bottomEnd: full,
          );
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final bg = isUser ? c.userBubble : c.agentBubble;
    final fg = isUser ? c.onUserBubble : c.onAgentBubble;
    final style = ln.text.body.copyWith(color: fg);
    final limit = maxWidth ?? maxWidthFor(MediaQuery.sizeOf(context).width);

    Widget content = child ?? Text(text!);
    if (editedLabel != null) {
      content = Wrap(
        crossAxisAlignment: WrapCrossAlignment.end,
        alignment: WrapAlignment.end,
        spacing: 6,
        children: [
          content,
          Padding(
            padding: const EdgeInsets.only(bottom: 1.5),
            child: Text(
              editedLabel!,
              style: ln.text.small.copyWith(color: fg.withValues(alpha: 0.6)),
            ),
          ),
        ],
      );
    }
    if (quote != null) {
      content = Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _QuoteHeader(quote: quote!, onUser: isUser),
          const SizedBox(height: 6),
          content,
        ],
      );
    }

    Widget bubble = Container(
      constraints: BoxConstraints(maxWidth: limit, minHeight: 44),
      padding: const EdgeInsetsDirectional.symmetric(
        horizontal: LnSize.bubblePadH,
        vertical: LnSize.bubblePadV,
      ),
      decoration: BoxDecoration(color: bg, borderRadius: _radius),
      child: DefaultTextStyle(
        style: style,
        textHeightBehavior: textHeightBehavior,
        child: content,
      ),
    );

    if (onTap != null || onLongPress != null) {
      bubble = LnTappable(
        onTap: onTap,
        onLongPress: onLongPress,
        haptic: true,
        pressScale: 0.98,
        pressOpacity: 1,
        child: bubble,
      );
    }

    if (onSwipeReply != null) {
      bubble = _SwipeToReply(onReply: onSwipeReply!, child: bubble);
    }

    return Semantics(
      label: semanticLabel,
      container: true,
      customSemanticsActions: onSwipeReply == null
          ? null
          : {
              CustomSemanticsAction(label: replyLabel ?? 'Reply'):
                  onSwipeReply!,
            },
      child: Column(
        crossAxisAlignment: isUser
            ? CrossAxisAlignment.end
            : CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          bubble,
          if (footer != null)
            Padding(
              padding: const EdgeInsetsDirectional.only(top: 4),
              child: footer,
            ),
        ],
      ),
    );
  }
}

/// Horizontal drag toward the end side that reveals a reply arrow at the start side.
class _SwipeToReply extends StatefulWidget {
  const _SwipeToReply({required this.onReply, required this.child});

  final VoidCallback onReply;
  final Widget child;

  /// Release past this distance replies.
  static const double threshold = 64;

  /// The drag meets resistance past [threshold] and stops here.
  static const double limit = 80;

  @override
  State<_SwipeToReply> createState() => _SwipeToReplyState();
}

class _SwipeToReplyState extends State<_SwipeToReply>
    with SingleTickerProviderStateMixin {
  late final AnimationController _offset = AnimationController(
    vsync: this,
    upperBound: _SwipeToReply.limit,
    duration: LnMotion.slow,
  );
  bool _armed = false;

  @override
  void dispose() {
    _offset.dispose();
    super.dispose();
  }

  void _update(DragUpdateDetails details) {
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final delta = (details.primaryDelta ?? 0) * (rtl ? -1 : 1);
    final past = _offset.value >= _SwipeToReply.threshold && delta > 0;
    _offset.value = (_offset.value + (past ? delta * 0.3 : delta)).clamp(
      0,
      _SwipeToReply.limit,
    );
    final armed = _offset.value >= _SwipeToReply.threshold;
    if (armed && !_armed) HapticFeedback.lightImpact();
    _armed = armed;
  }

  void _release() {
    if (_armed) widget.onReply();
    _armed = false;
    _offset.animateBack(0, curve: LnMotion.emphasized);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final rtl = Directionality.of(context) == TextDirection.rtl;
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onHorizontalDragUpdate: _update,
      onHorizontalDragEnd: (_) => _release(),
      onHorizontalDragCancel: _release,
      child: AnimatedBuilder(
        animation: _offset,
        child: widget.child,
        builder: (context, child) {
          final x = _offset.value;
          final shown = (x / _SwipeToReply.threshold).clamp(0.0, 1.0);
          return Stack(
            clipBehavior: Clip.none,
            children: [
              if (x > 0)
                PositionedDirectional(
                  start: 0,
                  top: 0,
                  bottom: 0,
                  child: ExcludeSemantics(
                    child: Center(
                      child: Opacity(
                        opacity: shown,
                        child: Transform.scale(
                          scale: 0.6 + 0.4 * shown,
                          child: Icon(
                            LnIcons.reply,
                            size: 24,
                            color: c.fgMuted,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              Transform.translate(
                offset: Offset(rtl ? -x : x, 0),
                child: child,
              ),
            ],
          );
        },
      ),
    );
  }
}

class _QuoteHeader extends StatelessWidget {
  const _QuoteHeader({required this.quote, required this.onUser});

  final BubbleQuote quote;
  final bool onUser;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final accent = onUser ? c.onUserBubble : c.brand;
    final muted = onUser ? c.onUserBubble.withValues(alpha: 0.78) : c.fgMuted;
    return Container(
      padding: const EdgeInsetsDirectional.fromSTEB(10, 6, 10, 6),
      decoration: BoxDecoration(
        color: onUser ? const Color(0x26FFFFFF) : c.fill2,
        borderRadius: const BorderRadius.all(Radius.circular(10)),
        border: BorderDirectional(start: BorderSide(color: accent, width: 3)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            quote.author,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: ln.text.captionStrong.copyWith(color: accent),
          ),
          Text(
            quote.text,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: ln.text.caption.copyWith(color: muted),
          ),
        ],
      ),
    );
  }
}

/// Vertical rhythm between consecutive messages: 4 dp between two bubbles of one sender's run
/// ([bubbleRun]; join their corners with [MessageBubble.joinTop]/[MessageBubble.joinBottom]), 7 dp
/// between other items of one sender, 16 dp at a sender change.
abstract final class BubbleGroup {
  static double gap({required bool sameSender, bool bubbleRun = false}) =>
      !sameSender
      ? LnSpace.senderChangeGap
      : bubbleRun
      ? LnSpace.bubbleRunGap
      : LnSpace.sameSenderGap;

  static Widget spacer({required bool sameSender, bool bubbleRun = false}) =>
      SizedBox(
        height: gap(sameSender: sameSender, bubbleRun: bubbleRun),
      );

  /// Padding that aligns a bubble to its side at the 16 dp page gutter.
  static const EdgeInsetsDirectional gutter = EdgeInsetsDirectional.symmetric(
    horizontal: LnSpace.pageGutter,
  );
}

/// Centred time label between message groups («٨:٥٦ ص», «٢٤ نوفمبر ٧:٥٤ م»): a 13/18 footnote in
/// the secondary ink, 28 dp below the previous message and 16 dp above the next.
class DateSeparator extends StatelessWidget {
  const DateSeparator({
    super.key,
    required this.label,
    this.top = 28,
    this.bottom = LnSpace.md,
  });

  final String label;

  /// Space above the label.
  final double top;

  /// Space below the label; less when the next row brings its own touch band.
  final double bottom;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    return Semantics(
      header: true,
      child: Padding(
        padding: EdgeInsets.only(top: top, bottom: bottom),
        child: Center(
          child: Text(
            label,
            style: ln.text.footnote.copyWith(color: ln.colors.fgMuted),
          ),
        ),
      ),
    );
  }
}
