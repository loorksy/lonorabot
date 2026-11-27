/// Port of packages/core/src/agent-model.ts: the model card in an agent's settings (GET
/// /agents/{id}/model/summary JSON), token counts and usage lines.
library;

import 'package:intl/intl.dart';

import '../bidi.dart';
import '../fill.dart';
import 'chatgpt_plan.dart';
import 'core_tables.g.dart';
import 'text.dart';
import 'values.dart';

/// The model card's labels in [locale]'s language (agent-model.ts:62-64).
AgentModelText agentModelText(String locale) =>
    agentModelLabels[language(locale)]!;

/// A model's name as the owner recognizes it, isolated for Arabic text; null if none. [label]
/// is a ModelLabel JSON (agent-model.ts:70-74).
String? modelName(Map<String, Object?>? label) {
  final name = str(label?['name']) ?? str(label?['model']);
  return truthy(name) ? isolate(name!) : null;
}

const List<String> _compactEn = ['', 'K', 'M', 'B', 'T'];
const List<String> _compactAr = [
  '',
  '\u{a0}ألف',
  '\u{a0}مليون',
  '\u{a0}مليار',
  '\u{a0}ترليون',
];

/// A token count the owner can read at a glance ("12.3K", «12.3 ألف»): ICU's compact short
/// notation with one decimal at most, as `Intl.NumberFormat(…, {notation: "compact",
/// maximumFractionDigits: 1})` prints it for `ar` and `en` (agent-model.ts:76-82).
String tokenCount(num value, String locale) {
  final units = language(locale) == 'ar' ? _compactAr : _compactEn;
  final format = NumberFormat.decimalPattern('en')
    ..maximumFractionDigits = 1
    ..turnOffGrouping();
  var unit = 0;
  var scaled = value.abs().toDouble();
  while (unit < units.length - 1 && scaled >= 1000) {
    scaled /= 1000;
    unit++;
  }
  // A value that rounds up to the next unit reads in that unit (999,999 → «1M»).
  if (unit < units.length - 1 && (scaled * 10).round() / 10 >= 1000) {
    scaled /= 1000;
    unit++;
  }
  return '${value < 0 ? '-' : ''}${format.format(scaled)}${units[unit]}';
}

/// One agent's usage line, or the "no use" line; never a cap (agent-model.ts:84-100).
String usageLine(Map<String, Object?> usage, num days, String locale) {
  final text = agentModelText(locale);
  final numbers = NumberFormat.decimalPattern(language(locale));
  final count = numbers.format(days);
  if (!truthy(usage['requests'])) {
    return fill(text.noUsage, null, {'days': count});
  }
  final input = isolate(tokenCount(number(usage['input_tokens']) ?? 0, locale));
  final output = isolate(
    tokenCount(number(usage['output_tokens']) ?? 0, locale),
  );
  final requests = isolate(numbers.format(number(usage['requests']) ?? 0));
  return '${fill(text.usageDays, null, {'days': count})}: ${fill(text.usageLine, null, {'input': input, 'output': output, 'requests': requests})}';
}

/// Whether the agent answers on a model someone set rather than the owner's default
/// (agent-model.ts:102-106).
bool offersDefaultModel(Map<String, Object?> summary) =>
    obj(obj(summary['record'])['preference'])['primary'] != null;

/// Whether the agent answers on the owner's ChatGPT plan (agent-model.ts:108-112).
bool usesChatGptPlan(Map<String, Object?> summary) =>
    obj(summary['current'])['provider'] == chatgptProvider;

/// The model card's summary lines in an agent's settings (agent-model.ts:114-124).
List<String> agentModelLines(Map<String, Object?> summary, String locale) {
  final text = agentModelText(locale);
  final record = obj(summary['record']);
  final current = summary['current'] is Map ? obj(summary['current']) : null;
  final lines = [
    '${text.answering}: ${modelName(current) ?? text.defaultModel}',
  ];
  if (usesChatGptPlan(summary)) lines.add(chatgptText(locale).usingPlan);
  if (truthy(record['chosen_by']) &&
      truthy(obj(record['preference'])['primary'])) {
    lines.add(
      record['chosen_by'] == 'owner' ? text.chosenByYou : text.inherited,
    );
  }
  final usage = obj(summary['usage']);
  lines.add(usageLine(usage, number(usage['days']) ?? 0, locale));
  return lines;
}
