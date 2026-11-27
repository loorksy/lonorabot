import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../theme.dart';
import '../tokens.dart';
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
/// 24 (single-line bubbles are full stadiums), padding 16 × 11.5, max width min(313, 80 % of the screen),
/// no border or shadow. Provide [text] or a custom [child].
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
  }) : assert(text != null || child != null);

  const MessageBubble.user(
    String this.text, {
    super.key,
    this.quote,
    this.editedLabel,
    this.footer,
    this.onLongPress,
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

  bool get isUser => sender == BubbleSender.user;

  /// min(313, 80 % of [screenWidth]).
  static double maxWidthFor(double screenWidth) =>
      math.min(LnSize.bubbleMaxWidth, screenWidth * LnSize.bubbleMaxFraction);

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
      decoration: BoxDecoration(
        color: bg,
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.bubble)),
      ),
      child: DefaultTextStyle(style: style, child: content),
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

    return Semantics(
      label: semanticLabel,
      container: true,
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

/// Vertical rhythm between consecutive messages: 7 dp within a sender, 16 dp at a sender change.
abstract final class BubbleGroup {
  static double gap({required bool sameSender}) =>
      sameSender ? LnSpace.sameSenderGap : LnSpace.senderChangeGap;

  static Widget spacer({required bool sameSender}) =>
      SizedBox(height: gap(sameSender: sameSender));

  /// Padding that aligns a bubble to its side at the 16 dp page gutter.
  static const EdgeInsetsDirectional gutter = EdgeInsetsDirectional.symmetric(
    horizontal: LnSpace.pageGutter,
  );
}

/// Centred day label between message groups ("Today", "Nov 22") in the secondary ink, like
/// timestamps.
class DateSeparator extends StatelessWidget {
  const DateSeparator({
    super.key,
    required this.label,
    this.bottom = LnSpace.md,
  });

  final String label;

  /// Space below the label (16 dp above it); less when the next row brings its own touch band.
  final double bottom;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    return Semantics(
      header: true,
      child: Padding(
        padding: EdgeInsets.only(top: LnSpace.md, bottom: bottom),
        child: Center(
          child: Text(
            label,
            style: ln.text.captionStrong.copyWith(color: ln.colors.fgMuted),
          ),
        ),
      ),
    );
  }
}
