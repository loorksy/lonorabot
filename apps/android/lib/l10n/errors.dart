/// The owner text of an API error code, with the Expo app's lookup order.
library;

import 'core/agent_permission_errors.dart';
import 'core/financial_boundary.dart';
import 'core/owner_actions.dart';
import 'core/owner_profile.dart';

/// The text for an `ApiError.code` (apps/mobile/lib/session.tsx:192-209 `errorText`):
/// `agentPermissionError` → `financialBoundaryError` → `ownerActionError` (with the ChatGPT
/// sign-in errors) → `ownerProfileError` → the app label with the same key → [fallback] →
/// the `request_failed` label. A null [code] means no HTTP answer arrived: the `network`
/// label. [label] and [hasLabel] read the app catalog in [locale].
///
/// A request the session itself cancelled is never shown; callers skip it before asking.
String errorTextFor(
  String? code,
  String locale, {
  required String Function(String key) label,
  required bool Function(String key) hasLabel,
  String? fallback,
}) {
  if (code == null) return label('network');
  return agentPermissionError(code, locale) ??
      financialBoundaryError(code, locale) ??
      ownerActionError(code, locale) ??
      ownerProfileError(code, locale) ??
      (hasLabel(code) ? label(code) : fallback ?? label('request_failed'));
}
