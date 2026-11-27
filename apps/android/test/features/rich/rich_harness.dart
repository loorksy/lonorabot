// Test harness for the rich-content and card widgets: the app's theme stack (Material → forui →
// LnTheme, as test/design/harness.dart builds it), the real Lonora catalogs in Arabic or
// English with the app's localization delegates, and a redux store.
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart';

L10n? _l10n;
bool _mono = false;

/// Android resolves the `monospace` family to its system mono font; the test engine has none,
/// so the Flutter SDK's Roboto Mono (shipped with DevTools) stands in for it.
Future<void> loadMonospaceFont() async {
  if (_mono) return;
  _mono = true;
  final root = Platform.environment['FLUTTER_ROOT'] ?? '/opt/flutter';
  final loader = FontLoader('monospace');
  for (final weight in ['Regular', 'Medium', 'Bold']) {
    final file = File(
      '$root/bin/cache/dart-sdk/bin/resources/devtools/assets/fonts/Roboto_Mono/RobotoMono-$weight.ttf',
    );
    if (file.existsSync()) {
      loader.addFont(
        Future.value(ByteData.sublistView(file.readAsBytesSync())),
      );
    }
  }
  await loader.load();
}

/// The real catalogs (assets/l10n), loaded once.
Future<L10n> loadTestL10n() async => _l10n ??= await L10n.load();

/// A signed-in state with [agents] and one thread.
AppState signedInState({
  Map<String, Agent> agents = const {},
  Map<String, ThreadState> threads = const {},
}) => AppState(
  session: const SessionState(
    status: SessionStatus.signedIn,
    server: 'http://127.0.0.1:8840',
    owner: Owner(id: 'owner-1', email: 'owner@example.com'),
  ),
  shell: ShellState(agents: agents, agentOrder: agents.keys.toList()),
  threads: threads,
);

Widget richTestApp({
  required Widget child,
  required L10n l10n,
  required Store<AppState> store,
  Brightness brightness = Brightness.light,
  String locale = 'ar',
}) {
  final palette = brightness == Brightness.dark
      ? LnPalette.dark
      : LnPalette.light;
  l10n.setLocale(Locale(locale));
  return StoreProvider<AppState>(
    store: store,
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      locale: Locale(locale),
      supportedLocales: L10n.supportedLocales,
      localizationsDelegates: [
        l10n.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        ...FLocalizations.localizationsDelegates,
      ],
      theme: lnMaterialTheme(
        palette,
        fontFamily: testFontFamily,
        fontFamilyFallback: testFontFallback,
      ),
      builder: (context, app) => FTheme(
        data: lnForuiTheme(
          palette,
          fontFamily: testFontFamily,
          fontFamilyFallback: testFontFallback,
        ),
        child: LnTheme(
          data: testTheme(brightness),
          child: FToaster(child: app!),
        ),
      ),
      home: Builder(
        builder: (context) => ColoredBox(
          color: context.ln.colors.bg,
          child: SafeArea(child: child),
        ),
      ),
    ),
  );
}

/// The four golden variants: light/dark × ar/en.
const goldenVariants = [
  (Brightness.light, 'ar'),
  (Brightness.dark, 'ar'),
  (Brightness.light, 'en'),
  (Brightness.dark, 'en'),
];

String variantName(Brightness b, String locale) =>
    '${b == Brightness.dark ? 'dark' : 'light'}_$locale';

/// Pumps a few frames (spinners and typing dots never settle).
Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 6; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}
