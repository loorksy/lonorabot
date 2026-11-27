// Lonora's Markdown dialect for agent text, parsed into a small block model the renderer draws.
//
// The dialect is the union of what apps/web draws (`conversation/Markdown.tsx` md/mdInline and
// `@lonora/chat-ui` ChatMarkdown = GitHub-flavoured Markdown without HTML) and apps/mobile
// (`components/markdown.tsx`): paragraphs, headings, **bold**, _em_, ~~strike~~, `code`,
// fenced code with a language, lists (nested, ordered, task lists), quotes, tables, rules,
// links (http/https/mailto/tel, in-app `lonora://` and the `/charts?` chart links), bare URLs,
// and images (artifact images draw; remote images never fetch on their own). HTML is never
// interpreted. Lonora has no maths notation, so `$…$` stays text.
//
// Streaming: the stable prefix (complete blocks before the last blank line outside a fence) is
// parsed once and cached; only the growing tail is parsed again on each delta, and an
// unterminated fence is closed (chat-ui `closeUnterminatedFence`) so code never re-flows.

import 'package:markdown/markdown.dart' as md;

/// A signed number keeps its sign on its left in Arabic (packages/core/src/plain-line.ts:23).
final RegExp signedNumber = RegExp(
  r'(^|[\s(\[«:،|·])([+\-−][$€£]?\d[\d,]*(?:\.\d+)?%?)',
);

/// Inline styles of a run.
abstract final class MdStyle {
  static const int bold = 1;
  static const int italic = 2;
  static const int strike = 4;
  static const int code = 8;
}

sealed class MdInline {
  const MdInline();
}

/// A run of text with one style and optional link.
class MdText extends MdInline {
  const MdText(this.text, {this.style = 0, this.href});
  final String text;
  final int style;
  final String? href;

  bool has(int flag) => style & flag != 0;
}

class MdBreak extends MdInline {
  const MdBreak();
}

class MdImage extends MdInline {
  const MdImage({required this.src, required this.alt});
  final String src;
  final String alt;
}

sealed class MdBlock {
  const MdBlock();
}

class MdParagraph extends MdBlock {
  const MdParagraph(this.inlines);
  final List<MdInline> inlines;
}

class MdHeading extends MdBlock {
  const MdHeading(this.level, this.inlines);
  final int level;
  final List<MdInline> inlines;
}

class MdCode extends MdBlock {
  const MdCode({required this.code, this.language = '', this.open = false});
  final String code;
  final String language;

  /// Still being written (an unterminated fence while streaming).
  final bool open;
}

class MdQuote extends MdBlock {
  const MdQuote(this.blocks);
  final List<MdBlock> blocks;
}

class MdListItem {
  const MdListItem(this.blocks, {this.checked});
  final List<MdBlock> blocks;

  /// A task-list item: true / false; null for a plain item.
  final bool? checked;
}

class MdList extends MdBlock {
  const MdList({required this.ordered, required this.items, this.start = 1});
  final bool ordered;
  final int start;
  final List<MdListItem> items;
}

enum MdAlign { start, center, end }

class MdTable extends MdBlock {
  const MdTable({
    required this.header,
    required this.rows,
    required this.align,
  });
  final List<List<MdInline>> header;
  final List<List<List<MdInline>>> rows;
  final List<MdAlign> align;
}

class MdRule extends MdBlock {
  const MdRule();
}

/// Plain text of inline runs (direction detection, copy, semantics).
String inlineText(List<MdInline> inlines) => inlines
    .map(
      (i) => switch (i) {
        MdText(:final text) => text,
        MdBreak() => '\n',
        MdImage(:final alt) => alt,
      },
    )
    .join();

/// Plain text of a block.
String blockText(MdBlock block) => switch (block) {
  MdParagraph(:final inlines) ||
  MdHeading(:final inlines) => inlineText(inlines),
  MdCode(:final code) => code,
  MdQuote(:final blocks) => blocks.map(blockText).join('\n'),
  MdList(:final items) =>
    items.map((i) => i.blocks.map(blockText).join('\n')).join('\n'),
  MdTable(:final header, :final rows) => [
    header.map(inlineText).join('\t'),
    for (final row in rows) row.map(inlineText).join('\t'),
  ].join('\n'),
  MdRule() => '',
};

/// Safe link targets (chat-ui `sanitizeMarkdownUrl` with relative links), plus `lonora:`.
String? sanitizeLink(String url) {
  final value = url.trim();
  final protocol = RegExp(
    r'^([a-z][a-z\d+.-]*):',
    caseSensitive: false,
  ).firstMatch(value)?[1]?.toLowerCase();
  if (protocol != null) {
    return const {'http', 'https', 'mailto', 'tel', 'lonora'}.contains(protocol)
        ? value
        : null;
  }
  if (value.startsWith('/') || value.startsWith('#')) return value;
  return null;
}

final RegExp _fence = RegExp(r'^ {0,3}(`{3,}|~{3,})');

/// Closes an unterminated fence so a streaming code block renders as code
/// (chat-ui `closeUnterminatedFence`). Returns the text and whether a fence was open.
(String, bool) closeUnterminatedFence(String text) {
  String? open;
  for (final line in text.split('\n')) {
    final m = _fence.firstMatch(line);
    if (m == null) continue;
    final marker = m[1]!;
    if (open == null) {
      open = marker;
    } else if (marker[0] == open[0] &&
        marker.length >= open.length &&
        line.trim() == marker) {
      open = null;
    }
  }
  if (open == null) return (text, false);
  return ('$text${text.endsWith('\n') ? '' : '\n'}$open', true);
}

/// Where the stable prefix ends: after the last blank line that is outside a fence and
/// followed by more text. Blocks before it cannot change as the reply grows.
int stableSplit(String text) {
  var inFence = false;
  String? marker;
  var split = 0;
  var offset = 0;
  final lines = text.split('\n');
  for (var i = 0; i < lines.length; i++) {
    final line = lines[i];
    final m = _fence.firstMatch(line);
    if (m != null) {
      if (!inFence) {
        inFence = true;
        marker = m[1];
      } else if (m[1]![0] == marker![0] && line.trim() == m[1]) {
        inFence = false;
      }
    }
    offset += line.length + 1;
    if (!inFence &&
        line.trim().isEmpty &&
        i < lines.length - 1 &&
        offset < text.length) {
      // A table or list could continue across one blank line only for loose lists; a blank
      // line followed by an indented line keeps the list open.
      final next = lines[i + 1];
      if (next.isNotEmpty && !next.startsWith(' ') && !next.startsWith('\t')) {
        split = offset;
      }
    }
  }
  return split;
}

final md.ExtensionSet _lonora = md.ExtensionSet(
  const [
    md.FencedCodeBlockSyntax(),
    md.TableSyntax(),
    md.UnorderedListWithCheckboxSyntax(),
    md.OrderedListWithCheckboxSyntax(),
  ],
  [md.StrikethroughSyntax(), md.AutolinkExtensionSyntax()],
);

List<md.Node> _parseNodes(String text) {
  final document = md.Document(
    extensionSet: _lonora,
    encodeHtml: false,
    withDefaultInlineSyntaxes: true,
  );
  return document.parse(text);
}

class _Converter {
  List<MdBlock> blocks(List<md.Node> nodes) {
    final out = <MdBlock>[];
    final loose = <MdInline>[];
    void flush() {
      if (loose.isEmpty) return;
      out.add(MdParagraph(List.of(loose)));
      loose.clear();
    }

    for (final node in nodes) {
      final block = _block(node);
      if (block != null) {
        flush();
        out.add(block);
      } else {
        loose.addAll(inlines([node]));
      }
    }
    flush();
    return out;
  }

  MdBlock? _block(md.Node node) {
    if (node is! md.Element) return null;
    final children = node.children ?? const <md.Node>[];
    switch (node.tag) {
      case 'p':
        return MdParagraph(inlines(children));
      case 'h1' || 'h2' || 'h3' || 'h4' || 'h5' || 'h6':
        return MdHeading(int.parse(node.tag.substring(1)), inlines(children));
      case 'pre':
        final code = children.whereType<md.Element>().firstOrNull;
        final language = (code?.attributes['class'] ?? '').replaceFirst(
          'language-',
          '',
        );
        var text = (code ?? node).textContent;
        if (text.endsWith('\n')) text = text.substring(0, text.length - 1);
        return MdCode(code: text, language: language);
      case 'blockquote':
        return MdQuote(blocks(children));
      case 'ul' || 'ol':
        return MdList(
          ordered: node.tag == 'ol',
          start: int.tryParse(node.attributes['start'] ?? '') ?? 1,
          items: [
            for (final li in children.whereType<md.Element>())
              _item(li.children ?? const []),
          ],
        );
      case 'table':
        final rows = <md.Element>[];
        for (final section in children.whereType<md.Element>()) {
          if (section.tag == 'tr') {
            rows.add(section);
          } else {
            rows.addAll((section.children ?? const []).whereType<md.Element>());
          }
        }
        if (rows.isEmpty) return null;
        final head =
            rows.first.children?.whereType<md.Element>().toList() ?? [];
        return MdTable(
          header: [for (final cell in head) inlines(cell.children ?? const [])],
          align: [
            for (final cell in head)
              switch (cell.attributes['align']) {
                'center' => MdAlign.center,
                'right' => MdAlign.end,
                _ => MdAlign.start,
              },
          ],
          rows: [
            for (final row in rows.skip(1))
              [
                for (final cell
                    in (row.children ?? const []).whereType<md.Element>())
                  inlines(cell.children ?? const []),
              ],
          ],
        );
      case 'hr':
        return const MdRule();
    }
    return null;
  }

  MdListItem _item(List<md.Node> nodes) {
    bool? checked;
    final rest = <md.Node>[];
    void take(List<md.Node> list) {
      for (final n in list) {
        if (checked == null &&
            n is md.Element &&
            n.tag == 'input' &&
            n.attributes['type'] == 'checkbox') {
          checked = n.attributes['checked'] == 'true';
        } else {
          rest.add(n);
        }
      }
    }

    // The checkbox is the first child of the item or of its first paragraph.
    final first = nodes.firstOrNull;
    if (first is md.Element && first.tag == 'p') {
      final kids = first.children ?? const <md.Node>[];
      final head = kids.firstOrNull;
      if (head is md.Element && head.tag == 'input') {
        checked = head.attributes['checked'] == 'true';
        rest.add(md.Element('p', kids.skip(1).toList()));
        rest.addAll(nodes.skip(1));
        return MdListItem(blocks(rest), checked: checked);
      }
    }
    take(nodes);
    return MdListItem(blocks(rest), checked: checked);
  }

  List<MdInline> inlines(List<md.Node> nodes, [int style = 0, String? href]) {
    final out = <MdInline>[];
    for (final node in nodes) {
      if (node is md.Text) {
        out.add(MdText(_unescape(node.text), style: style, href: href));
        continue;
      }
      if (node is! md.Element) continue;
      final children = node.children ?? const <md.Node>[];
      switch (node.tag) {
        case 'strong':
          out.addAll(inlines(children, style | MdStyle.bold, href));
        case 'em':
          out.addAll(inlines(children, style | MdStyle.italic, href));
        case 'del':
          out.addAll(inlines(children, style | MdStyle.strike, href));
        case 'code':
          out.add(
            MdText(
              _unescape(node.textContent),
              style: style | MdStyle.code,
              href: href,
            ),
          );
        case 'br':
          out.add(const MdBreak());
        case 'a':
          final target = sanitizeLink(node.attributes['href'] ?? '');
          out.addAll(inlines(children, style, target ?? href));
        case 'img':
          out.add(
            MdImage(
              src: node.attributes['src'] ?? '',
              alt: node.attributes['alt'] ?? '',
            ),
          );
        default:
          out.addAll(inlines(children, style, href));
      }
    }
    return _merge(out);
  }

  /// Adjacent runs with the same style and link become one (fewer spans).
  List<MdInline> _merge(List<MdInline> runs) {
    final out = <MdInline>[];
    for (final run in runs) {
      final last = out.lastOrNull;
      if (run is MdText &&
          last is MdText &&
          last.style == run.style &&
          last.href == run.href) {
        out[out.length - 1] = MdText(
          last.text + run.text,
          style: run.style,
          href: run.href,
        );
      } else {
        out.add(run);
      }
    }
    return out;
  }
}

String _unescape(String text) => text
    .replaceAll('&amp;', '&')
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&quot;', '"')
    .replaceAll('&#39;', "'");

/// A small LRU so a rebuilt message never parses again.
class _Lru<V> {
  _Lru(this.capacity);
  final int capacity;
  final _map = <String, V>{};

  V? get(String key) {
    final value = _map.remove(key);
    if (value != null) _map[key] = value;
    return value;
  }

  void put(String key, V value) {
    _map.remove(key);
    _map[key] = value;
    if (_map.length > capacity) _map.remove(_map.keys.first);
  }
}

final _Lru<List<MdBlock>> _blockCache = _Lru(96);

List<MdBlock> _parseCached(String text) {
  final cached = _blockCache.get(text);
  if (cached != null) return cached;
  final blocks = _Converter().blocks(_parseNodes(text));
  _blockCache.put(text, blocks);
  return blocks;
}

/// Parses [text]. While [streaming], the stable prefix is parsed once (cached) and only the
/// tail again; an unterminated fence renders as an open code block.
List<MdBlock> parseMarkdown(String text, {bool streaming = false}) {
  final source = text.replaceAll('\r', '');
  if (!streaming) return _parseCached(source);
  final split = stableSplit(source);
  final head = split > 0
      ? _parseCached(source.substring(0, split))
      : const <MdBlock>[];
  final (tail, open) = closeUnterminatedFence(source.substring(split));
  final tailBlocks = _Converter().blocks(_parseNodes(tail));
  if (open && tailBlocks.isNotEmpty && tailBlocks.last is MdCode) {
    final last = tailBlocks.last as MdCode;
    tailBlocks[tailBlocks.length - 1] = MdCode(
      code: last.code,
      language: last.language,
      open: true,
    );
  }
  return [...head, ...tailBlocks];
}

/// The artifact id an image source names (`lonora://artifact/<id>`, `/files/<id>`,
/// `/artifacts/<id>[/file]`, `artifact:<id>` or a bare id), else null.
String? artifactIdOf(String src) {
  final m = RegExp(
    r'^(?:lonora://artifact/|/files/|/api/artifacts/|/artifacts/|artifact:)?'
    r'([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})(?:/file)?(?:\?.*)?$',
    caseSensitive: false,
  ).firstMatch(src.trim());
  return m?[1];
}
