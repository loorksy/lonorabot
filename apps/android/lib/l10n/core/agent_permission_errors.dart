/// Port of packages/core/src/agent-permission-errors.ts.
library;

import 'core_tables.g.dart';

/// Shared human explanations of an agent-permission refusal; null for other codes so callers
/// keep their normal handling (agent-permission-errors.ts:50-54).
String? agentPermissionError(String? code, String locale) {
  final category = code == null ? null : agentPermissionCategories[code];
  return category == null
      ? null
      : agentPermissionMessages[category]!.pick(locale);
}
