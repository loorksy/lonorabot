import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_highlighter/themes/atom-one-dark.dart';
import 'package:flutter_highlighter/themes/github.dart';
import 'package:forui/forui.dart' show FIcons;
// The highlighter engine is flutter_highlighter's own dependency (same pinned version); its
// widget is not used because it is not selectable and paints its own background.
import 'package:highlighter/highlighter.dart' show highlight, Node;

import '../../design/design.dart';
import '../../l10n/l10n.dart';

/// The monospace style for code, falling back to the ambient families (tests, missing glyphs).
TextStyle codeTextStyle(
  TextStyle base, {
  double size = 13,
  double height = 20,
}) => base.copyWith(
  fontFamily: 'monospace',
  fontFamilyFallback: [?base.fontFamily, ...?base.fontFamilyFallback],
  fontSize: size,
  height: height / size,
  letterSpacing: 0,
  fontWeight: FontWeight.w400,
);

final _spanCache = <String, List<TextSpan>>{};

List<TextSpan> _highlighted(String code, String language, bool dark) {
  final key = '$dark\u0000$language\u0000$code';
  final hit = _spanCache.remove(key);
  if (hit != null) return _spanCache[key] = hit;
  final theme = dark ? atomOneDarkTheme : githubTheme;
  List<TextSpan> spans;
  try {
    final nodes = highlight.parse(code, language: language).nodes ?? const [];
    spans = _convert(nodes, theme);
  } catch (_) {
    spans = [TextSpan(text: code)];
  }
  _spanCache[key] = spans;
  if (_spanCache.length > 64) _spanCache.remove(_spanCache.keys.first);
  return spans;
}

List<TextSpan> _convert(List<Node> nodes, Map<String, TextStyle> theme) {
  TextStyle? styleOf(String? name) {
    final s = name == null ? null : theme[name];
    // Colour, weight and slant only: the block's own size, font and background stay.
    return s == null
        ? null
        : TextStyle(
            color: s.color,
            fontWeight: s.fontWeight,
            fontStyle: s.fontStyle,
          );
  }

  TextSpan walk(Node node) {
    if (node.value != null) {
      return TextSpan(text: node.value, style: styleOf(node.className));
    }
    return TextSpan(
      style: styleOf(node.className),
      children: [
        for (final child in node.children ?? const <Node>[]) walk(child),
      ],
    );
  }

  return [for (final node in nodes) walk(node)];
}

/// A fenced code block: the language and a copy button above monospace, left-to-right code
/// that scrolls sideways (web `CodeBlock`, «نسخ الكود»; mobile `markdown.tsx` code blocks).
/// Highlighting waits until the fence is closed, so a streaming block never re-flows.
class CodeBlockView extends StatelessWidget {
  const CodeBlockView({
    super.key,
    required this.code,
    this.language = '',
    this.open = false,
    this.onUserBubble = false,
  });

  final String code;
  final String language;
  final bool open;
  final bool onUserBubble;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final base = DefaultTextStyle.of(context).style;
    final ink = onUserBubble ? c.onUserBubble : c.fg;
    final muted = onUserBubble
        ? c.onUserBubble.withValues(alpha: 0.75)
        : c.fgMuted;
    final fill = onUserBubble
        ? c.onUserBubble.withValues(alpha: 0.15)
        : c.fill2;
    final style = codeTextStyle(base).copyWith(color: ink);
    final lang = language.trim();
    final spans = open || onUserBubble || lang.isEmpty
        ? [TextSpan(text: code)]
        : _highlighted(code, lang.toLowerCase(), c.isDark);
    return Container(
      decoration: BoxDecoration(
        color: fill,
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.field)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(14, 0, 0, 0),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    lang.isEmpty ? context.t('rich_code') : lang,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: ln.text.small.copyWith(color: muted),
                  ),
                ),
                LnTappable(
                  onTap: () => _copy(context),
                  semanticLabel: context.t('rich_copyCode'),
                  excludeChildSemantics: true,
                  child: SizedBox.square(
                    dimension: 48,
                    child: Icon(FIcons.copy, size: 16, color: muted),
                  ),
                ),
              ],
            ),
          ),
          // Code reads left to right in both languages and scrolls from its left edge.
          Directionality(
            textDirection: TextDirection.ltr,
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
              child: Text.rich(
                TextSpan(style: style, children: spans),
                softWrap: false,
                textDirection: TextDirection.ltr,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _copy(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: code));
    unawaited(HapticFeedback.selectionClick());
    if (!context.mounted) return;
    try {
      LnToast.show(context, context.t('copied'), kind: LnToastKind.positive);
    } catch (_) {
      // No toaster above this context (previews, tests).
    }
  }
}
