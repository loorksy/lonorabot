import 'dart:async';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart' show SelectionArea;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/deep_links.dart';
import '../../app/routes.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import 'artifact_image.dart';
import 'code_block.dart';
import 'markdown_parse.dart';
import 'rich_strings.dart';

/// Renders Lonora Markdown (agent replies) in the conversation's visual language: the 16/24 body
/// style, per-paragraph reading direction, Lonora's link rules, code blocks with highlighting
/// and copy, scrollable tables, quotes, lists and task lists, and artifact images.
///
/// [selectable] wraps the text in a [SelectionArea]. A bubble that owns a long-press menu
/// passes false (text is then selected from the message menu instead).
///
/// [streaming] (additive): the text is a live reply that grows; its finished blocks are parsed
/// once and the growing tail again, and an open code fence draws as code without re-flowing.
class MarkdownView extends StatefulWidget {
  const MarkdownView(
    this.text, {
    super.key,
    this.style,
    this.selectable = true,
    this.onUserBubble = false,
    this.streaming = false,
  });

  final String text;
  final TextStyle? style;
  final bool selectable;

  /// True when drawn on the owner's blue bubble (inverted link/code colours).
  final bool onUserBubble;
  final bool streaming;

  @override
  State<MarkdownView> createState() => _MarkdownViewState();
}

class _MarkdownViewState extends State<MarkdownView> {
  final List<TapGestureRecognizer> _recognizers = [];

  @override
  void dispose() {
    _disposeRecognizers();
    super.dispose();
  }

  void _disposeRecognizers() {
    for (final r in _recognizers) {
      r.dispose();
    }
    _recognizers.clear();
  }

  @override
  Widget build(BuildContext context) {
    registerRichStrings(context.l10n);
    _disposeRecognizers();
    final blocks = parseMarkdown(widget.text, streaming: widget.streaming);
    final ui = Directionality.of(context);
    final direction = textDirectionFor(widget.text, ui);
    final ink = _Ink.of(context, widget.onUserBubble, widget.style);
    final builder = _BlockBuilder(
      context: context,
      ink: ink,
      direction: direction,
      recognizers: _recognizers,
      onUserBubble: widget.onUserBubble,
    );
    final children = <Widget>[
      for (var i = 0; i < blocks.length; i++)
        KeyedSubtree(
          key: ValueKey('md$i'),
          child: Padding(
            padding: EdgeInsets.only(top: i == 0 ? 0 : _gapBefore(blocks[i])),
            child: builder.block(blocks[i]),
          ),
        ),
    ];
    final scrolls = blocks.any(_scrolls);
    Widget body = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: children,
    );
    // A short message hugs its text (a bubble only as wide as its words); tables and code
    // take the full width and scroll sideways.
    if (!scrolls && widget.text.length < 2000) {
      body = IntrinsicWidth(child: body);
    }
    body = DefaultTextStyle.merge(style: ink.body, child: body);
    if (widget.selectable) body = SelectionArea(child: body);
    return body;
  }

  double _gapBefore(MdBlock block) => switch (block) {
    MdHeading() => 12,
    MdCode() || MdTable() => 10,
    _ => 8,
  };

  static bool _scrolls(MdBlock block) => switch (block) {
    MdCode() || MdTable() => true,
    MdParagraph(:final inlines) => inlines.any((i) => i is MdImage),
    MdQuote(:final blocks) => blocks.any(_scrolls),
    MdList(:final items) => items.any((i) => i.blocks.any(_scrolls)),
    _ => false,
  };
}

/// The colours of one MarkdownView (agent bubble, owner bubble, or plain surface).
class _Ink {
  const _Ink({
    required this.body,
    required this.fg,
    required this.muted,
    required this.link,
    required this.codeFill,
    required this.rule,
    required this.ln,
  });

  factory _Ink.of(BuildContext context, bool onUser, TextStyle? style) {
    final ln = context.ln;
    final c = ln.colors;
    final ambient = DefaultTextStyle.of(context).style;
    final base = ln.text.body
        .copyWith(
          fontFamily: ambient.fontFamily,
          fontFamilyFallback: ambient.fontFamilyFallback,
          color: onUser ? c.onUserBubble : (ambient.color ?? c.fg),
        )
        .merge(style);
    final fg = base.color ?? c.fg;
    return _Ink(
      body: base,
      fg: fg,
      muted: onUser ? c.onUserBubble.withValues(alpha: 0.75) : c.fgMuted,
      link: onUser ? c.onUserBubble : c.selection,
      codeFill: onUser ? c.onUserBubble.withValues(alpha: 0.2) : c.fill4,
      rule: onUser ? c.onUserBubble.withValues(alpha: 0.3) : c.border,
      ln: ln,
    );
  }

  final TextStyle body;
  final Color fg;
  final Color muted;
  final Color link;
  final Color codeFill;
  final Color rule;
  final LnThemeData ln;
}

class _BlockBuilder {
  _BlockBuilder({
    required this.context,
    required this.ink,
    required this.direction,
    required this.recognizers,
    required this.onUserBubble,
  });

  final BuildContext context;
  final _Ink ink;
  final TextDirection direction;
  final List<TapGestureRecognizer> recognizers;
  final bool onUserBubble;

  TextDirection _dirOf(String text) => readingDirection(text) ?? direction;

  TextStyle _heading(int level) {
    final t = ink.ln.text;
    final s = switch (level) {
      1 => t.display,
      2 => t.headline,
      _ => t.title.copyWith(fontWeight: FontWeight.w600),
    };
    return s.copyWith(
      color: ink.fg,
      fontFamily: ink.body.fontFamily,
      fontFamilyFallback: ink.body.fontFamilyFallback,
    );
  }

  Widget block(MdBlock block) {
    switch (block) {
      case MdParagraph(:final inlines):
        final images = inlines.whereType<MdImage>().toList();
        final onlyImages =
            images.isNotEmpty &&
            inlines.every(
              (i) => i is MdImage || (i is MdText && i.text.trim().isEmpty),
            );
        if (onlyImages) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (var i = 0; i < images.length; i++) ...[
                if (i > 0) const SizedBox(height: LnSpace.xs),
                _blockImage(images[i]),
              ],
            ],
          );
        }
        return _text(inlines, ink.body);
      case MdHeading(:final level, :final inlines):
        return Semantics(header: true, child: _text(inlines, _heading(level)));
      case MdCode(:final code, :final language, :final open):
        return CodeBlockView(
          code: code,
          language: language,
          open: open,
          onUserBubble: onUserBubble,
        );
      case MdQuote(:final blocks):
        return Container(
          padding: const EdgeInsetsDirectional.only(start: 12),
          decoration: BoxDecoration(
            border: BorderDirectional(
              start: BorderSide(
                color: ink.muted.withValues(alpha: 0.5),
                width: 3,
              ),
            ),
          ),
          child: DefaultTextStyle.merge(
            style: TextStyle(color: ink.muted),
            child: _column(blocks, muted: true),
          ),
        );
      case MdList():
        return _list(block, 0);
      case MdTable():
        return _table(block);
      case MdRule():
        return Container(height: 1, color: ink.rule);
    }
  }

  Widget _column(List<MdBlock> blocks, {bool muted = false}) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    mainAxisSize: MainAxisSize.min,
    children: [
      for (var i = 0; i < blocks.length; i++) ...[
        if (i > 0) const SizedBox(height: 6),
        muted && blocks[i] is MdParagraph
            ? _text(
                (blocks[i] as MdParagraph).inlines,
                ink.body.copyWith(color: ink.muted),
              )
            : block(blocks[i]),
      ],
    ],
  );

  Widget _list(MdList list, int depth) {
    final children = <Widget>[];
    for (var i = 0; i < list.items.length; i++) {
      final item = list.items[i];
      final text = item.blocks.map(blockText).join(' ');
      final dir = _dirOf(text);
      final Widget marker;
      if (item.checked != null) {
        marker = Padding(
          padding: const EdgeInsets.only(top: 3),
          child: Icon(
            item.checked! ? FIcons.squareCheck : FIcons.square,
            size: 18,
            color: item.checked! ? ink.fg : ink.muted,
          ),
        );
      } else {
        marker = Text(
          list.ordered ? '${list.start + i}.' : (depth.isEven ? '•' : '◦'),
          style: ink.body.copyWith(color: ink.muted),
        );
      }
      children.add(
        Padding(
          padding: EdgeInsets.only(top: i == 0 ? 0 : 4),
          child: Directionality(
            textDirection: dir,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ConstrainedBox(
                  constraints: const BoxConstraints(minWidth: 18),
                  child: marker,
                ),
                const SizedBox(width: 8),
                Flexible(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      for (var b = 0; b < item.blocks.length; b++) ...[
                        if (b > 0) const SizedBox(height: 4),
                        item.blocks[b] is MdList
                            ? _list(item.blocks[b] as MdList, depth + 1)
                            : item.checked == true &&
                                  item.blocks[b] is MdParagraph
                            ? _text(
                                (item.blocks[b] as MdParagraph).inlines,
                                ink.body.copyWith(color: ink.muted),
                              )
                            : block(item.blocks[b]),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: children,
    );
  }

  Widget _table(MdTable table) {
    final columns = table.header.length;
    final c = ink.ln.colors;
    TextAlign alignOf(int i) =>
        switch (i < table.align.length ? table.align[i] : MdAlign.start) {
          MdAlign.center => TextAlign.center,
          MdAlign.end => TextAlign.end,
          MdAlign.start => TextAlign.start,
        };
    Widget cell(List<MdInline> inlines, int i, {bool head = false}) =>
        ConstrainedBox(
          constraints: const BoxConstraints(minWidth: 64, maxWidth: 240),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: _text(
              inlines,
              (head ? ink.ln.text.captionStrong : ink.ln.text.caption).copyWith(
                color: ink.fg,
                fontFamily: ink.body.fontFamily,
                fontFamilyFallback: ink.body.fontFamilyFallback,
              ),
              align: alignOf(i),
            ),
          ),
        );
    final rows = <TableRow>[
      TableRow(
        decoration: BoxDecoration(
          color: onUserBubble ? c.onUserBubble.withValues(alpha: 0.1) : c.fill2,
        ),
        children: [
          for (var i = 0; i < columns; i++)
            cell(table.header[i], i, head: true),
        ],
      ),
      for (final row in table.rows)
        TableRow(
          decoration: BoxDecoration(
            border: Border(top: BorderSide(color: ink.rule)),
          ),
          children: [
            for (var i = 0; i < columns; i++)
              cell(i < row.length ? row[i] : const [], i),
          ],
        ),
    ];
    final tableDir = _dirOf(table.header.map(inlineText).join(' '));
    // The table hugs its columns at the reading start and scrolls sideways when wider.
    return Directionality(
      textDirection: tableDir,
      child: Align(
        alignment: AlignmentDirectional.centerStart,
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Container(
            decoration: BoxDecoration(
              borderRadius: const BorderRadius.all(
                Radius.circular(LnRadius.field),
              ),
              border: Border.all(color: ink.rule),
            ),
            child: ClipRRect(
              borderRadius: const BorderRadius.all(
                Radius.circular(LnRadius.field - 1),
              ),
              child: Table(
                defaultColumnWidth: const IntrinsicColumnWidth(),
                defaultVerticalAlignment: TableCellVerticalAlignment.top,
                children: rows,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _blockImage(MdImage image) {
    final id = artifactIdOf(image.src);
    if (id != null) {
      return ArtifactImage(
        artifactId: id,
        label: image.alt.isEmpty ? null : image.alt,
      );
    }
    return _text([image], ink.body);
  }

  Widget _text(List<MdInline> inlines, TextStyle style, {TextAlign? align}) {
    final plain = inlineText(inlines);
    final dir = _dirOf(plain);
    return Text.rich(
      TextSpan(
        style: style,
        children: [for (final i in inlines) _span(i, style)],
      ),
      textDirection: dir,
      textAlign: align ?? TextAlign.start,
    );
  }

  InlineSpan _span(MdInline inline, TextStyle style) {
    switch (inline) {
      case MdBreak():
        return const TextSpan(text: '\n');
      case MdImage(:final src, :final alt):
        final label = alt.isEmpty ? context.t('rich_openImage') : alt;
        final target = sanitizeLink(src);
        return TextSpan(
          text: '[$label]',
          style: TextStyle(color: ink.link),
          recognizer: target == null ? null : _tap(target),
        );
      case MdText(:final text, :final href):
        var s = const TextStyle();
        if (inline.has(MdStyle.bold)) {
          s = s.copyWith(fontWeight: FontWeight.w600);
        }
        if (inline.has(MdStyle.italic)) {
          s = s.copyWith(fontStyle: FontStyle.italic);
        }
        final decorations = <TextDecoration>[
          if (inline.has(MdStyle.strike)) TextDecoration.lineThrough,
          if (href != null) TextDecoration.underline,
        ];
        if (decorations.isNotEmpty) {
          s = s.copyWith(
            decoration: TextDecoration.combine(decorations),
            decorationColor: href != null ? ink.link : ink.fg,
          );
        }
        if (href != null) s = s.copyWith(color: ink.link);
        var shown = text;
        if (inline.has(MdStyle.code)) {
          final size = style.fontSize ?? 16;
          s =
              codeTextStyle(
                style,
                size: size - 2,
                height: size * (style.height ?? 1.5),
              ).copyWith(
                backgroundColor: ink.codeFill,
                color: href != null ? ink.link : null,
                fontWeight: s.fontWeight,
              );
          shown = ltr(text);
        } else {
          // A signed number keeps its sign on its left in Arabic (isolated left to right).
          shown = text.replaceAllMapped(
            signedNumber,
            (m) => '${m[1]}\u2066${m[2]}\u2069',
          );
        }
        return TextSpan(
          text: shown,
          style: s,
          recognizer: href == null ? null : _tap(href),
          mouseCursor: href == null ? null : SystemMouseCursors.click,
        );
    }
  }

  TapGestureRecognizer _tap(String href) {
    final r = TapGestureRecognizer()..onTap = () => openLink(context, href);
    recognizers.add(r);
    return r;
  }
}

/// Opens a message link on an explicit tap: `lonora://` thread/agent links and the
/// `/charts?…` chart links route in the app (never `lonora://connect`, which would change
/// the server); http(s), mailto and tel open outside the app.
Future<void> openLink(BuildContext context, String href) async {
  final target = sanitizeLink(href);
  if (target == null) return;
  final uri = Uri.tryParse(target);
  if (uri == null) return;
  final router = GoRouter.maybeOf(context);
  if (uri.scheme == 'lonora') {
    if (uri.host == 'connect') return;
    if (uri.host == 'artifact' && uri.pathSegments.isNotEmpty) {
      await router?.push(Routes.artifact(uri.pathSegments.first));
      return;
    }
    final location = DeepLinks.locationFor(uri);
    if (location != null) await router?.push(location);
    return;
  }
  if (!uri.hasScheme) {
    // In-app relative links the agents write: chart links and files (after `..` is
    // resolved, so `/charts/../connect` never reaches another screen).
    final local = uri.normalizePath();
    final first = local.pathSegments.firstOrNull;
    if (!uri.hasAuthority && (first == 'charts' || first == 'files')) {
      await router?.push(local.toString());
    }
    return;
  }
  unawaited(HapticFeedback.selectionClick());
  try {
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  } catch (_) {
    // No app on this device opens it.
  }
}
