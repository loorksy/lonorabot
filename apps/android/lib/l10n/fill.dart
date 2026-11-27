/// Placeholder filling, exactly as apps/mobile/lib/i18n.ts:986-996 `fill()`.
library;

import 'core/values.dart';

final RegExp _positional = RegExp(r'\{(\d+)\}');
final RegExp _named = RegExp(r'\{(\w+)\}');

/// Fills a label's placeholders as the TS `fill()` does.
///
/// Without [named] it is the positional form `fill(template, ...values)`: every `{0}`, `{1}` …
/// becomes its value from [positional], or '' when there is none. With [named] it is the
/// named form `fill(template, {…})`: every `{word}` (digits included) becomes its value or ''.
/// Given both, positional placeholders are filled first, then the named ones. Values print as
/// JavaScript's `String(value)` (`2.0` → «2»).
String fill(
  String template, [
  List<Object?>? positional,
  Map<String, Object?>? named,
]) {
  var text = template;
  if (named == null || positional != null) {
    final values = positional ?? const [];
    text = text.replaceAllMapped(_positional, (match) {
      final index = int.tryParse(match[1]!);
      return index != null && index < values.length
          ? jsString(values[index])
          : '';
    });
  }
  if (named != null) {
    text = text.replaceAllMapped(_named, (match) => jsString(named[match[1]]));
  }
  return text;
}
