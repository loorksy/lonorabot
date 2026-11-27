/// Port of the text of packages/core/src/chatgpt-plan.ts (Sign in with ChatGPT): its labels,
/// the providers-list row, sign-out and plan-limit lines and the sign-in's errors.
library;

import '../bidi.dart';
import 'core_tables.g.dart';
import 'text.dart';
import 'values.dart';

/// The ChatGPT plan's provider id (chatgpt-plan.ts:16-17).
const String chatgptProvider = 'openai_chatgpt';

/// ChatGPT settings › Usage (chatgpt-plan.ts:18-19).
const String manageUsageUrl = 'https://chatgpt.com/settings/usage';

/// The plan's labels in [locale]'s language (chatgpt-plan.ts:78-80).
ChatGptText chatgptText(String locale) => chatgptLabels[language(locale)]!;

/// A Secret card that signs in with ChatGPT instead of taking a key; [card] is the
/// OwnerAction JSON (chatgpt-plan.ts:91-99).
bool isChatGptCard(Map<String, Object?> card) {
  final secret = obj(obj(card['facts'])['secret']);
  return card['kind'] == 'secret' &&
      secret['connect'] == 'model_provider' &&
      obj(secret['details'])['provider'] == chatgptProvider;
}

/// "Signing in as …" once an attempt continues a registered account; null for a new one
/// (chatgpt-plan.ts:122-128).
String? continuingAsLine(String? account, String locale) =>
    account == null || account.isEmpty
    ? null
    : chatgptText(locale).continuingAs
          .replaceFirst('{account}', isolate(account));

/// The providers list's ChatGPT row: its line and whether Sign out is offered; null when
/// there is nothing to show. [status] is the `GET /providers` ChatGPT status JSON
/// (chatgpt-plan.ts:157-170).
({String line, bool signOut})? chatgptRow(
  Map<String, Object?>? status,
  String locale,
) {
  if (status == null) return null;
  final text = chatgptText(locale);
  final signOut = truthy(status['signed_in']);
  if (truthy(status['plan'])) return (line: text.usingPlan, signOut: signOut);
  if (truthy(status['sign_in_again'])) {
    return (line: text.signInAgain, signOut: signOut);
  }
  if (signOut) return (line: text.planNotUsed, signOut: signOut);
  return null;
}

/// What sign-out did: confirmed at OpenAI, or only on the owner's server. [result] is the
/// sign-out JSON (`signed_out`, `revoked`) (chatgpt-plan.ts:172-176).
String signOutLine(Map<String, Object?> result, String locale) {
  final text = chatgptText(locale);
  return truthy(result['revoked'])
      ? text.signedOut
      : text.revocationUnconfirmed;
}

/// A run that failed on the ChatGPT plan's own limit (chatgpt-plan.ts:178-183).
bool planLimitReached(Map<String, Object?>? failure) =>
    failure?['family'] == 'quota' && failure?['provider'] == chatgptProvider;

/// Owner text for a sign-in refusal; null if the code is not one (chatgpt-plan.ts:244-248).
String? chatgptError(String? code, String locale) =>
    code == null || code.isEmpty ? null : chatgptErrors[code]?.pick(locale);
