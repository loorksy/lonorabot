import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart' show SelectionArea;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../cards/cards_actions.dart' show SideKeys;
import '../cards/peer_card.dart';
import '../conversation/composer_assist.dart'
    show mentionNamesKey, mentionPattern;
import 'genui/ui_card.dart';
import 'markdown_view.dart';
import 'markdown_parse.dart' show sanitizeLink;
import 'rich_parts.dart';
import 'rich_strings.dart';
import 'visual/visual_view.dart';
import 'voice_note.dart';

/// Renders a message's body: `content` Markdown plus every `rich_content.parts[]` part
/// (text, ui v2 GenUI documents with actions, legacy v1 visual documents, voice, call,
/// command), and the live streaming preview of a reply (`streaming: true`).
///
/// * Agent text is Lonora Markdown; the owner's own words stay plain text with tappable
///   links (web/Expo `plainTextLinkParts`): Markdown marks stay characters.
/// * Rich content is validated fail closed: one malformed part and the message reads as its
///   plain `content`.
/// * A message whose rich content has `ui` parts is not wrapped in a bubble by the
///   conversation: its text parts are drawn here in agent bubbles and its cards as cards.
/// * A message that belongs to a peer exchange (`ThreadState.side['peer_messages']`) is
///   drawn as that exchange (who asked whom, the text, the status).
/// * «@name» of the conversation's agents (the group's members, or every agent in a direct chat)
///   and «@الكل» are marked in the text (apps/web/src/conversation/Markdown.tsx `.mention`).
/// * While [streaming], each rich partial tree replaces the previous one, the growing text
///   keeps its finished blocks, and the typing dots follow the text.
///
/// Additive options: [selectable] (default false: the bubble owns long-press; the
/// "Select text" sheet passes true) and [onCallBack] (a call log's tap).
final Expando<Map<String, Json>> _peerIndexes = Expando('peer-index');

/// [peersByMessage] of a thread's stored peer list, built once per list (every message's
/// selector reads it on each store change).
Map<String, Json> _peerIndex(Object? peers) {
  if (peers is! List || peers.isEmpty) return const {};
  return _peerIndexes[peers] ??= peersByMessage(asJsonList(peers));
}

class RichContentView extends StatelessWidget {
  const RichContentView({
    super.key,
    required this.threadId,
    required this.text,
    this.richContent,
    this.message,
    this.streaming = false,
    this.onUserBubble = false,
    this.selectable = false,
    this.onCallBack,
  });

  final String threadId;
  final String text;
  final Json? richContent;

  /// The canonical message, when this is not a live preview (needed for GenUI submits).
  final Message? message;
  final bool streaming;
  final bool onUserBubble;
  final bool selectable;
  final VoidCallback? onCallBack;

  /// Whether the conversation draws this rich content without a bubble (it has cards).
  static bool drawsOwnBubbles(Json? richContent) =>
      asJsonList(richContent?['parts']).any((p) => p['type'] == 'ui');

  @override
  Widget build(BuildContext context) {
    registerRichStrings(context.l10n);
    final m = message;
    if (m != null && !onUserBubble) {
      final peer = context.select(
        (AppState s) =>
            _peerIndex(s.thread(threadId).side[SideKeys.peerMessages])[m.id],
      );
      if (peer != null) {
        final runId = asString(asJson(peer['payload'])['run_id']);
        final runStatus = context.select(
          (AppState s) =>
              runId == null ? null : s.thread(threadId).runs[runId]?.status,
        );
        return PeerExchangeView(message: m, peer: peer, runStatus: runStatus);
      }
    }
    final bare = !onUserBubble && drawsOwnBubbles(richContent);
    final parts = validateRichContent(richContent);
    final names = context.select((AppState s) => _mentionNames(s, threadId));
    final mentions = mentionPattern(
      names.isEmpty ? const [] : names.split('\n'),
    );
    Widget prose(String value, {required bool last, Key? key}) =>
        _text(context, value, last: last, key: key, mentions: mentions);
    final children = <Widget>[];
    if (parts == null) {
      children.add(prose(_plainBody(text), last: true));
    } else {
      var drewText = false;
      for (var i = 0; i < parts.length; i++) {
        final part = parts[i];
        final last = i == parts.length - 1;
        switch (part) {
          case TextPart(:final text):
            if (text.trim().isEmpty) continue;
            drewText = true;
            children.add(prose(text, last: last, key: ValueKey('t$i')));
          case CardPart(:final card):
            children.add(
              _CardWidth(
                key: ValueKey('ui$i'),
                child: UiCardView(
                  part: card,
                  index: i,
                  threadId: threadId,
                  messageId: streaming ? null : m?.id,
                ),
              ),
            );
          case VisualPart(:final document):
            children.add(
              _CardWidth(
                key: ValueKey('v$i'),
                child: LnCardSurface(
                  child: VisualDocumentView(
                    document: document,
                    threadId: threadId,
                    messageId: m?.id,
                    index: i,
                  ),
                ),
              ),
            );
          case VoicePart():
            children.add(
              VoiceNoteView(
                key: ValueKey('voice$i'),
                part: part,
                onUserBubble: onUserBubble,
              ),
            );
            // The transcript is the message's text.
            if (text.trim().isNotEmpty && part.transcriptStatus == 'done') {
              children.add(prose(text, last: last));
              drewText = true;
            }
          case CallPart():
            children.add(CallLogRow(part: part, onCallBack: onCallBack));
            drewText = true;
          case CommandPart():
            children.add(CommandChip(part: part, onUserBubble: onUserBubble));
            // After the chip, only the words after the command.
            final argument = part.argument.isNotEmpty
                ? part.argument
                : part.name == 'summary'
                ? context.t('cmdSummaryOf')
                : '';
            if (argument.isNotEmpty) {
              children.add(prose(argument, last: last));
            }
            drewText = true;
        }
      }
      if (!drewText &&
          !parts.any((p) => p is TextPart) &&
          text.trim().isNotEmpty) {
        // A card-only reply keeps its lead text (content holds the lead and the fallback).
        if (!parts.any((p) => p is CardPart || p is VisualPart)) {
          children.insert(0, prose(text, last: false));
        }
      }
    }
    if (streaming) {
      children.add(_Typing(threadId: threadId, empty: children.isEmpty));
    }
    if (children.isEmpty) return const SizedBox.shrink();
    if (children.length == 1 && !bare) return children.first;
    return Column(
      crossAxisAlignment: onUserBubble
          ? CrossAxisAlignment.end
          : CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < children.length; i++) ...[
          if (i > 0)
            SizedBox(height: bare ? LnSpace.sameSenderGap : LnSpace.xs),
          children[i],
        ],
      ],
    );
  }

  /// A colleague's result reaches the conversation inside a machine wrapper agents read;
  /// the owner sees only the result.
  String _plainBody(String value) => peerOutcome(value).body;

  /// The names [threadId]'s messages mark as mentions (a string: selectors compare it). Every
  /// bubble asks on every store change (each streaming delta): the string is built again only
  /// when the agents or the group change.
  static String _mentionNames(AppState s, String threadId) {
    final groupId =
        s.threads[threadId]?.thread?.groupId ??
        (s.threads[threadId]?.thread == null
            ? s.shell.entryFor(threadId)?.groupId
            : null);
    final agents = s.shell.agents;
    final group = groupId == null ? null : s.shell.groups[groupId];
    final last = _lastNames;
    if (last != null &&
        identical(last.agents, agents) &&
        identical(last.group, group)) {
      return last.names;
    }
    final names = mentionNamesKey(agents, group);
    _lastNames = (agents: agents, group: group, names: names);
    return names;
  }

  static ({Map<String, Agent> agents, Group? group, String names})? _lastNames;

  Widget _text(
    BuildContext context,
    String value, {
    required bool last,
    Key? key,
    RegExp? mentions,
  }) {
    final Widget body = onUserBubble
        ? OwnerText(value, selectable: selectable, mentions: mentions)
        : MarkdownView(
            value,
            selectable: selectable,
            streaming: streaming && last,
            mentions: mentions,
          );
    final bare = !onUserBubble && drawsOwnBubbles(richContent);
    return KeyedSubtree(
      key: key,
      child: bare
          ? MessageBubble(sender: BubbleSender.agent, child: body)
          : body,
    );
  }
}

/// A rich card's width: min(315, 80 % of the screen), or wider on a narrow phone when the card
/// needs it.
class _CardWidth extends StatelessWidget {
  const _CardWidth({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final screen = MediaQuery.sizeOf(context).width;
    return ConstrainedBox(
      constraints: BoxConstraints(
        maxWidth: (screen - 2 * LnSpace.pageGutter).clamp(0, 400).toDouble(),
        minWidth: ActionCard.widthFor(screen),
      ),
      child: child,
    );
  }
}

/// The owner's own words: plain text, with http(s) links tappable (no Markdown) and the
/// [mentions] marked.
class OwnerText extends StatefulWidget {
  const OwnerText(
    this.text, {
    super.key,
    this.selectable = false,
    this.mentions,
  });
  final String text;
  final bool selectable;

  /// «@name» of the conversation's agents ([mentionPattern]; group 1 is the name).
  final RegExp? mentions;

  @override
  State<OwnerText> createState() => _OwnerTextState();
}

class _OwnerTextState extends State<OwnerText> {
  final List<TapGestureRecognizer> _taps = [];

  @override
  void dispose() {
    for (final t in _taps) {
      t.dispose();
    }
    super.dispose();
  }

  static const String _url = r'https?://[^\s<]+[^\s<.,،)]';
  static final RegExp _links = RegExp('($_url)');
  static final Expando<RegExp> _withMentions = Expando('owner-mentions');

  /// Links (group 1) and, when given, mentions.
  static RegExp _pattern(RegExp? mentions) => mentions == null
      ? _links
      : _withMentions[mentions] ??= RegExp('($_url)|${mentions.pattern}');

  @override
  Widget build(BuildContext context) {
    for (final t in _taps) {
      t.dispose();
    }
    _taps.clear();
    final spans = <InlineSpan>[];
    var last = 0;
    // The mark takes the surrounding text colour (white in the owner's bubble).
    final ink =
        DefaultTextStyle.of(context).style.color ?? context.ln.colors.fg;
    for (final m in _pattern(widget.mentions).allMatches(widget.text)) {
      if (m.start > last) {
        spans.add(TextSpan(text: widget.text.substring(last, m.start)));
      }
      if (m[1] == null) {
        spans.add(
          TextSpan(
            text: m[0],
            style: TextStyle(
              fontWeight: FontWeight.w600,
              backgroundColor: ink.withValues(alpha: 0.2),
            ),
          ),
        );
        last = m.end;
        continue;
      }
      final href = sanitizeLink(m[0]!);
      final tap = TapGestureRecognizer()
        ..onTap = () {
          if (href != null) openLink(context, href);
        };
      _taps.add(tap);
      spans.add(
        TextSpan(
          text: ltr(m[0]!),
          // The underline takes the surrounding text colour: white in the owner's bubble,
          // the body colour in the Select text sheet.
          style: const TextStyle(decoration: TextDecoration.underline),
          recognizer: tap,
        ),
      );
      last = m.end;
    }
    if (last < widget.text.length) {
      spans.add(TextSpan(text: widget.text.substring(last)));
    }
    final dir = textDirectionFor(widget.text, Directionality.of(context));
    final text = Text.rich(TextSpan(children: spans), textDirection: dir);
    return widget.selectable ? SelectionArea(child: text) : text;
  }
}

/// The / command an owner message is (server-written): «/مهمة», «/بحث», or the skill's name.
class CommandChip extends StatelessWidget {
  const CommandChip({super.key, required this.part, this.onUserBubble = false});
  final CommandPart part;
  final bool onUserBubble;

  static const Map<String, String> _labels = {
    'task': 'cmdTask',
    'search': 'cmdSearch',
    'summary': 'cmdSummary',
    'skill': 'cmdSkill',
  };

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final name = part.name == 'skill' && (part.skillName ?? '').isNotEmpty
        ? part.skillName!
        : context.t(_labels[part.name] ?? 'cmdSkill');
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: ShapeDecoration(
        color: onUserBubble ? c.onUserBubble.withValues(alpha: 0.2) : c.fill3,
        shape: const StadiumBorder(),
      ),
      child: Text(
        // RLM: in Arabic the «/» stays before the name, read from the right.
        '${rtl ? '\u200f/' : '/'}$name',
        style: ln.text.smallStrong.copyWith(
          color: onUserBubble ? c.onUserBubble : c.fgMuted,
        ),
      ),
    );
  }
}

/// A call log (server-written system message): «مكالمة صوتية · m:ss» or «مكالمة صوتية
/// فائتة», as an inline event row; a tap calls the agent back when the conversation offers it.
class CallLogRow extends StatelessWidget {
  const CallLogRow({super.key, required this.part, this.onCallBack});
  final CallPart part;
  final VoidCallback? onCallBack;

  @override
  Widget build(BuildContext context) {
    final label = part.missed
        ? context.t('missedVoiceCall')
        : context.t('voiceCall');
    final detail = part.missed
        ? (onCallBack == null ? null : context.t('tapToCallBack'))
        : voiceClock(part.durationSeconds);
    return InlineEventRow(
      icon: Icon(
        part.missed
            ? FIcons.phoneMissed
            : part.direction == 'incoming'
            ? FIcons.phoneIncoming
            : FIcons.phoneOutgoing,
      ),
      label: label,
      detail: detail,
      emphasized: !part.missed,
      alignment: InlineEventAlignment.start,
      showChevron: onCallBack != null,
      onTap: onCallBack,
    );
  }
}

/// Typing dots after the streaming text (or alone before any text arrives).
class _Typing extends StatelessWidget {
  const _Typing({required this.threadId, required this.empty});
  final String threadId;
  final bool empty;

  @override
  Widget build(BuildContext context) {
    final name = context.select((AppState s) {
      final agentId = s.thread(threadId).thread?.agentId;
      return agentId == null ? null : s.shell.agents[agentId]?.name;
    });
    final label = name == null ? null : context.t('isTyping', [name]);
    return Padding(
      padding: EdgeInsets.only(top: empty ? 4 : 2, bottom: empty ? 2 : 0),
      child: TypingDots(
        dotSize: empty ? 8 : 6,
        gap: empty ? 5 : 4,
        bounce: empty ? 6 : 4,
        semanticLabel: label,
      ),
    );
  }
}
