// The composer field's controller: it paints the committed @mentions and the typed «/» command
// over the text without changing it (apps/web/src/conversation/Composer.tsx `ta-mirror`, CSS
// conversation.css `.ta-mirror mark`), so the caret and the text stay the owner's.
import 'package:flutter/widgets.dart';

import 'composer_assist.dart';

class ComposerTextController extends TextEditingController {
  ComposerTextController({super.text});

  /// The committed mentions (offsets in [text]).
  List<MentionRange> mentions = const [];

  /// Where the typed command spans in [text], when the message is one.
  (int, int)? command;

  /// The mention mark's and the command mark's fills (set by the composer from its theme).
  Color? mentionFill;
  Color? commandFill;

  @override
  TextSpan buildTextSpan({
    required BuildContext context,
    TextStyle? style,
    required bool withComposing,
  }) {
    final value = this.value;
    final text = value.text;
    final marks = <(int, int, Color)>[
      if (command case (final s, final e)? when commandFill != null)
        (s, e, commandFill!),
      if (mentionFill != null)
        for (final (s, e) in _marked(text)) (s, e, mentionFill!),
    ];
    if (marks.isEmpty) {
      return super.buildTextSpan(
        context: context,
        style: style,
        withComposing: withComposing,
      );
    }
    final composing = withComposing && value.isComposingRangeValid
        ? value.composing
        : null;
    final cuts = <int>{0, text.length};
    for (final (s, e, _) in marks) {
      cuts
        ..add(s.clamp(0, text.length))
        ..add(e.clamp(0, text.length));
    }
    if (composing != null) {
      cuts
        ..add(composing.start)
        ..add(composing.end);
    }
    final points = cuts.toList()..sort();
    final children = <TextSpan>[];
    for (var i = 0; i + 1 < points.length; i++) {
      final a = points[i];
      final b = points[i + 1];
      if (a >= b) continue;
      Color? fill;
      for (final (s, e, color) in marks) {
        if (a >= s && b <= e) fill = color;
      }
      final underline =
          composing != null && a >= composing.start && b <= composing.end;
      children.add(
        TextSpan(
          text: text.substring(a, b),
          style: fill == null && !underline
              ? null
              : TextStyle(
                  backgroundColor: fill,
                  decoration: underline ? TextDecoration.underline : null,
                ),
        ),
      );
    }
    return TextSpan(style: style, children: children);
  }

  /// The committed tokens still spelled as committed.
  List<(int, int)> _marked(String text) {
    final out = <(int, int)>[];
    var at = 0;
    for (final s in mentionSegments(text, mentions)) {
      if (s.mark) out.add((at, at + s.text.length));
      at += s.text.length;
    }
    return out;
  }
}
