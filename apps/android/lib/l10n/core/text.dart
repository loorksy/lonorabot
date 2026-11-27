/// The shared shape of @lonora/core text: one sentence in English and Arabic.
library;

/// The language a @lonora/core module answers in: Arabic for any `ar*` locale, else English
/// (every module's `language(locale)`, e.g. packages/core/src/financial-boundary.ts:50-52).
String language(String locale) => locale.startsWith('ar') ? 'ar' : 'en';

/// `{ en, ar }` of a @lonora/core table (the TS `Text` type).
class CoreText {
  const CoreText({required this.en, required this.ar});

  final String en;
  final String ar;

  /// The text in [locale]'s language (the TS `pick`).
  String pick(String locale) => language(locale) == 'ar' ? ar : en;
}
