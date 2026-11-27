/// Lonora's words on Android: the Expo app's own catalogs (assets/l10n/{ar,en}.json, made by
/// tool/i18n/port_i18n.mjs), Arabic first (default `ar`, right to left) with English.
///
/// ```dart
/// final l10n = await L10n.load();                 // once, before runApp
/// MaterialApp(locale: l10n.locale, localizationsDelegates: [l10n.delegate, ...]);
/// context.t('sh_unreadN', const [], {'count': 3}); // «3 غير مقروءة»
/// ```
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import 'core/time_separators.dart';
import 'errors.dart';
import 'fill.dart';
import 'format.dart';
import 'plurals.dart' as plurals;

export 'attention.dart';
export 'bidi.dart';
export 'core/core.dart';
export 'errors.dart';
export 'fill.dart';
export 'format.dart';
export 'plurals.dart';

/// The app's labels in Arabic and English, the current locale, and the Expo app's helpers
/// bound to it.
class L10n {
  /// Catalogs given directly (tests, previews). The app uses [load].
  L10n({
    required Map<String, String> ar,
    required Map<String, String> en,
    Locale locale = defaultLocale,
  }) : _catalogs = {'ar': Map.of(ar), 'en': Map.of(en)},
       _locale = ValueNotifier(normalize(locale));

  /// Arabic is the default and first language.
  static const Locale defaultLocale = Locale('ar');
  static const List<Locale> supportedLocales = [Locale('ar'), Locale('en')];

  static const String arAsset = 'assets/l10n/ar.json';
  static const String enAsset = 'assets/l10n/en.json';

  static L10n? _instance;

  /// The instance [load] made, for code without a BuildContext.
  static L10n get instance =>
      _instance ?? (throw StateError('L10n.load() has not run yet'));
  static set instance(L10n value) => _instance = value;

  /// Loads both catalogs and the date symbols, once at startup, and makes the result
  /// [instance]. [locale] is the saved choice (the app store keeps it), `ar` by default.
  static Future<L10n> load({
    AssetBundle? bundle,
    Locale locale = defaultLocale,
  }) async {
    final assets = bundle ?? rootBundle;
    final texts = await Future.wait([
      assets.loadString(arAsset),
      assets.loadString(enAsset),
    ]);
    await ensureDateFormatting();
    Map<String, String> read(String text) =>
        (jsonDecode(text) as Map<String, dynamic>).cast<String, String>();
    return _instance = L10n(
      ar: read(texts[0]),
      en: read(texts[1]),
      locale: locale,
    );
  }

  /// `ar` for any Arabic locale, otherwise `en`.
  static Locale normalize(Locale locale) =>
      locale.languageCode.toLowerCase().startsWith('ar')
      ? const Locale('ar')
      : const Locale('en');

  final Map<String, Map<String, String>> _catalogs;
  final ValueNotifier<Locale> _locale;
  final Set<String> _missing = {};

  /// The current locale, `ar` or `en`.
  Locale get locale => _locale.value;

  /// Notifies when the locale changes (the app rebuilds with it).
  ValueListenable<Locale> get localeListenable => _locale;

  /// `ar` or `en`: the `locale` the TS functions take.
  String get lang => _locale.value.languageCode;

  /// Arabic reads right to left (the TS `rtl = locale === "ar"`).
  bool get isRtl => lang == 'ar';
  TextDirection get textDirection =>
      isRtl ? TextDirection.rtl : TextDirection.ltr;

  /// Switches the language; persisting the choice is the app store's job.
  void setLocale(Locale locale) => _locale.value = normalize(locale);

  /// The delegate to give MaterialApp (with the Global*Localizations delegates).
  LocalizationsDelegate<L10n> get delegate => L10nDelegate(this);

  /// Whether the catalog has [key] (in either language).
  bool has(String key) =>
      _catalogs['ar']!.containsKey(key) || _catalogs['en']!.containsKey(key);

  /// Every key, in source order.
  Iterable<String> get keys => _catalogs['en']!.keys;

  /// The raw label of [key] in [language] (`ar` or `en`, default the current one): a key
  /// missing there reads in English, a key missing everywhere reads as itself, and both are
  /// reported in debug builds.
  String translate(String key, [String? language]) {
    final lang = language ?? this.lang;
    final own = _catalogs[lang]?[key];
    if (own != null) return own;
    final english = _catalogs['en']![key];
    assert(() {
      if (_missing.add('$lang:$key')) {
        debugPrint(
          english == null
              ? 'L10n: missing key "$key"'
              : 'L10n: "$key" has no $lang text; showing English',
        );
      }
      return true;
    }());
    return english ?? key;
  }

  /// The keys looked up and not found, as `lang:key` (debug builds only).
  @visibleForTesting
  Set<String> get debugMissingKeys => Set.unmodifiable(_missing);

  /// The label of [key] in the current language with its `{0}` `{1}` … filled from
  /// [positional] and its `{name}` placeholders from [named], as the TS `fill()`.
  String t(
    String key, [
    List<Object?> positional = const [],
    Map<String, Object?> named = const {},
  ]) {
    final template = translate(key);
    if (positional.isEmpty && named.isEmpty) return template;
    return fill(
      template,
      positional.isEmpty ? null : positional,
      named.isEmpty ? null : named,
    );
  }

  /// Adds a feature's own labels, as `'key': ['ar text', 'en text']`, for Android-only UI.
  /// Lonora's existing labels are never replaced: reuse them instead (a different text for
  /// an existing key fails an assert in debug builds and is ignored).
  void register(Map<String, List<String>> table) {
    for (final MapEntry(:key, :value) in table.entries) {
      if (value.length != 2) {
        throw ArgumentError.value(value, key, 'expected [ar, en]');
      }
      final ar = _catalogs['ar']!;
      final en = _catalogs['en']!;
      if (ar.containsKey(key) || en.containsKey(key)) {
        assert(
          ar[key] == value[0] && en[key] == value[1],
          'L10n.register: "$key" is already a label with other words',
        );
        continue;
      }
      ar[key] = value[0];
      en[key] = value[1];
    }
  }

  /// The owner text of an API error code; null [code] (no HTTP answer) reads `network`. See
  /// [errorTextFor] for the order.
  String errorText(String? code, {String? fallback}) => errorTextFor(
    code,
    lang,
    label: translate,
    hasLabel: has,
    fallback: fallback,
  );

  /// A conversation's time separator: «اليوم 9:05 ص», «أمس …», a weekday or a date.
  String timeSeparator(Object createdAt, {DateTime? now}) =>
      formatTimeSeparator(
        createdAt,
        lang,
        today: translate('today'),
        yesterday: translate('yesterday'),
        now: now,
      );

  /// «محادثة واحدة», «محادثتان», «3 محادثات», «11 محادثة».
  String chatsWord(int count) => plurals.chatsWord(lang, count);

  /// «وكيل واحد», «وكيلان», «3 وكلاء», «11 وكيلًا», «100 وكيل».
  String agentsWord(int count) => plurals.agentsWord(lang, count);

  /// The toast after the offline queue went out by itself.
  String waitingSentText(int count) => plurals.waitingSentText(lang, count);

  /// The offline strip's queued count ('' when nothing waits).
  String networkWaitingText(int count) =>
      plurals.networkWaitingText(lang, count);
}

/// Gives [L10n] to the widget tree and keeps its locale in step with the app's.
class L10nDelegate extends LocalizationsDelegate<L10n> {
  const L10nDelegate(this.l10n);

  final L10n l10n;

  @override
  bool isSupported(Locale locale) {
    final code = locale.languageCode.toLowerCase();
    return code == 'ar' || code == 'en';
  }

  @override
  Future<L10n> load(Locale locale) {
    l10n.setLocale(locale);
    return SynchronousFuture(l10n);
  }

  @override
  bool shouldReload(L10nDelegate old) => old.l10n != l10n;
}

/// `context.l10n` and `context.t(…)`.
extension L10nContext on BuildContext {
  /// The tree's [L10n] (rebuilding this widget when the locale changes), else [L10n.instance].
  L10n get l10n => Localizations.of<L10n>(this, L10n) ?? L10n.instance;

  /// [L10n.t] in this context.
  String t(
    String key, [
    List<Object?> positional = const [],
    Map<String, Object?> named = const {},
  ]) => l10n.t(key, positional, named);
}
