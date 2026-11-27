/// Port of packages/core/src/owner-profile.ts: the owner profile's vocabulary (reach-me
/// channels, reply languages, revision authors) and its error texts.
library;

import 'core_tables.g.dart';
import 'values.dart';

/// The reach-me channels in the offered order (owner-profile.ts:9-10).
const List<String> reachMeChannels = ['notify', 'message', 'call'];

/// The reply languages in the offered order (owner-profile.ts:11-12).
const List<String> replyLanguages = ['auto', 'ar', 'en'];

/// Every [ownerProfileLabel] key (owner-profile.ts:219).
final List<String> ownerProfileLabelKeys = List.unmodifiable(
  ownerProfileLabels.keys,
);

/// A profile label by key (`title`, `reachMe`, `saved`, …) (owner-profile.ts:170-172).
String ownerProfileLabel(String key, String locale) =>
    ownerProfileLabels[key]!.pick(locale);

/// «أرسل لي تنبيهًا» / "Notify me" … (owner-profile.ts:174-176).
String reachMeLabel(String channel, String locale) =>
    reachMeChannelTexts[channel]!.pick(locale);

/// What a reach-me channel does (owner-profile.ts:178-180).
String reachMeHint(String channel, String locale) =>
    reachMeHintTexts[channel]!.pick(locale);

/// A reply language in words. The offered choices are Lonora's words; any other BCP-47 tag an
/// agent saved is shown as the tag itself (owner-profile.ts:182-190; the TS names it with
/// `Intl.DisplayNames`, which Flutter does not have, and returns the tag when that fails).
String replyLanguageLabel(String language, String locale) =>
    replyLanguageTexts[language]?.pick(locale) ?? language;

/// A preference field's name, or null for an unknown field (owner-profile.ts:192-195).
String? preferenceFieldLabel(String field, String locale) =>
    preferenceFieldTexts[field]?.pick(locale);

/// A recorded preference value in plain words; device identifiers are never shown
/// (owner-profile.ts:197-211).
String preferenceValueText(String field, Object? value, String locale) {
  String label(String key) => ownerProfileLabels[key]!.pick(locale);
  if (field == 'quiet_hours') {
    return value is String && value.isNotEmpty
        ? value.replaceFirst('-', ' – ')
        : label('off');
  }
  if (value == null || value == '') return label('notSet');
  if (value is bool) return label(value ? 'on' : 'off');
  if (field == 'reach_me' && value is String) {
    final channel = reachMeChannelTexts[value];
    if (channel != null) return channel.pick(locale);
    if (value == 'activity') return reachMeActivityOnly.pick(locale);
  }
  if (field == 'reply_language' && value is String) {
    return replyLanguageLabel(value, locale);
  }
  return jsString(value);
}

/// Owner text for a profile or memory error code, or null for other codes
/// (owner-profile.ts:213-217).
String? ownerProfileError(String? code, String locale) =>
    code == null ? null : ownerProfileErrors[code]?.pick(locale);
