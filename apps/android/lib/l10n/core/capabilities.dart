/// Port of packages/core/src/capabilities.ts: the Capabilities view's lines (GET
/// /capabilities JSON), built only from server facts; names, domains and repositories are
/// isolated so they keep their order inside Arabic text.
library;

import '../bidi.dart';
import '../format.dart';
import 'core_tables.g.dart';
import 'text.dart';
import 'values.dart';

/// The Capabilities labels in [locale]'s language (capabilities.ts:157-159).
CapabilityText capabilityText(String locale) =>
    capabilityLabels[language(locale)]!;

String _dot(List<String?> parts) =>
    parts.where((part) => part != null && part.isNotEmpty).join(dotSeparator);

String? _day(Object? value, String locale) {
  if (!truthy(value)) return null;
  final date = parseDate(value);
  if (date == null) return null;
  return isolate(formatDate('MMMd', language(locale), date));
}

String? _waitingWrites(
  Object? tier,
  List<Object?> writes,
  CapabilityText text,
) => tier == 'read' && writes.isNotEmpty
    ? '${isolate('${writes.length}')} ${text.needWrites}'
    : null;

/// One trusted source: what it is, who added it, its tier and when it was last used
/// (capabilities.ts:184-201).
String sourceLine(Map<String, Object?> source, String locale) {
  final text = capabilityText(locale);
  final kind = str(source['kind']) ?? '';
  final labelValue = str(source['label']);
  final label = kind == 'github'
      ? null
      : truthy(labelValue)
      ? isolate(labelValue!)
      : text.unnamed;
  final used = _day(source['last_used_at'], locale);
  final server = kind == 'mcp_server';
  final needsReview = truthy(source['needs_review']);
  final tools = list(source['tools']);
  return _dot([
    label != null ? '${text[kind] ?? ''}: $label' : text[kind],
    text[str(source['added_via']) ?? ''],
    server && needsReview ? text.needsReview : null,
    server && !needsReview ? text[str(source['effect_tier']) ?? ''] : null,
    server && tools.isNotEmpty
        ? '${isolate('${tools.length}')} ${text.tools}'
        : null,
    server
        ? _waitingWrites(
            source['effect_tier'],
            list(source['write_tools']),
            text,
          )
        : null,
    used != null ? '${text.lastUsed} $used' : null,
    truthy(source['active']) ? null : text.removedState,
  ]);
}

/// One skill: title, version, agent, origin and state (capabilities.ts:203-216).
String skillLine(Map<String, Object?> skill, String locale) {
  final text = capabilityText(locale);
  final repository = str(skill['repository']);
  final provenance = str(skill['provenance']) ?? '';
  final origin = provenance == 'external'
      ? '${text.external} ${truthy(repository) ? isolate(repository!) : 'GitHub'}'
      : text[provenance];
  final version = str(skill['version']);
  final agent = str(skill['agent_name']);
  return _dot([
    isolate(str(skill['title']) ?? str(skill['skill_id']) ?? ''),
    truthy(version) ? isolate(version!) : null,
    truthy(agent) ? isolate(agent!) : null,
    origin,
    truthy(skill['undone'])
        ? text.undone
        : truthy(skill['enabled'])
        ? text.on
        : text.off,
  ]);
}

/// The server's own title of a tool, from the server's own keys only
/// (capabilities.ts:218-222).
String? toolTitle(Map<String, Object?> titles, String name) =>
    str(titles[name]);

/// One MCP server: name, trust, waiting writes, blocked tools, state and last use
/// (capabilities.ts:224-241).
String serverLine(Map<String, Object?> server, String locale) {
  final text = capabilityText(locale);
  final used = _day(server['last_used_at'], locale);
  final name = str(server['name']);
  final tier = str(server['trusted_tier']);
  final blocked = list(server['blocked_tools']);
  return _dot([
    truthy(name) ? isolate(name!) : text.unnamed,
    truthy(tier)
        ? '${text[tier!] ?? ''}$dotSeparator${isolate('${list(server['trusted_tools']).length}')} ${text.tools}'
        : truthy(server['operator_declared'])
        ? text.operator
        : text.notTrusted,
    _waitingWrites(tier, list(server['write_tools']), text),
    blocked.isNotEmpty
        ? '${isolate('${blocked.length}')} ${text.blocked}'
        : null,
    truthy(server['enabled']) ? text.on : text.off,
    used != null ? '${text.lastUsed} $used' : null,
  ]);
}

/// One integration or feed (capabilities.ts:243-252).
String integrationLine(Map<String, Object?> item, String locale) {
  final text = capabilityText(locale);
  final name = str(item['name']);
  final domain = str(item['domain']);
  final deliver = str(item['deliver_to_agent_name']);
  return _dot([
    text[str(item['type']) ?? ''],
    truthy(name) ? isolate(name!) : null,
    truthy(domain) ? isolate(domain!) : null,
    truthy(deliver) ? '${text.deliversTo} ${isolate(deliver!)}' : null,
    truthy(item['enabled']) ? text.on : text.off,
  ]);
}

/// A built-in capability and its state (capabilities.ts:254-257).
String builtInLine(Map<String, Object?> item, String locale) {
  final text = capabilityText(locale);
  final capability = text[str(item['capability']) ?? ''] ?? '';
  return '$capability: ${text[str(item['state']) ?? ''] ?? ''}';
}
