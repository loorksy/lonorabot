// Golden/widget harness of the platform package: the app's localisation and themes with real
// fonts around a single page, a store, and the four variants.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/voice/voice_strings.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/platform/platform_strings.dart';
import 'package:lonora/state/app_state.dart';

import '../design/fonts.dart';
import '../design/harness.dart';

late L10n platformL10n;

Future<void> setUpPlatformTests() async {
  await loadAppFonts();
  platformL10n = await L10n.load();
  registerPlatformStrings(platformL10n);
  registerVoiceStrings(platformL10n);
}

const platformVariants = [
  (dark: false, locale: 'ar', name: 'light_ar'),
  (dark: true, locale: 'ar', name: 'dark_ar'),
  (dark: false, locale: 'en', name: 'light_en'),
  (dark: true, locale: 'en', name: 'dark_en'),
];

/// Golden viewport (393 × 852 dp, DPR 2) with a 24 dp status bar.
void setPlatformViewport(WidgetTester tester) {
  setGoldenViewport(tester);
  tester.view.padding = const FakeViewPadding(top: 48);
  tester.view.viewPadding = const FakeViewPadding(top: 48);
}

Widget platformApp({
  required Store<AppState> store,
  required Widget home,
  bool dark = false,
  String locale = 'ar',
}) {
  platformL10n.setLocale(Locale(locale));
  final palette = dark ? LnPalette.dark : LnPalette.light;
  return StoreProvider<AppState>(
    store: store,
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      locale: Locale(locale),
      supportedLocales: L10n.supportedLocales,
      localizationsDelegates: [
        platformL10n.delegate,
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
      builder: (context, child) => LnTheme(
        data: testTheme(dark ? Brightness.dark : Brightness.light),
        child: FTheme(
          data: lnForuiTheme(
            palette,
            fontFamily: testFontFamily,
            fontFamilyFallback: testFontFallback,
          ),
          child: FToaster(child: child ?? const SizedBox.shrink()),
        ),
      ),
      home: home,
    ),
  );
}

/// A plain page behind overlays (so banners are seen over content, as in the app).
class BackdropPage extends StatelessWidget {
  const BackdropPage({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return ColoredBox(
      color: c.bg,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Padding(
            padding: EdgeInsets.only(
              top: MediaQuery.paddingOf(context).top + 120,
              left: LnSpace.pageGutter,
              right: LnSpace.pageGutter,
            ),
            child: Column(
              children: [
                for (var i = 0; i < 9; i++)
                  Padding(
                    padding: const EdgeInsets.only(bottom: LnSpace.sm),
                    child: Row(
                      children: [
                        Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: c.fill4,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: LnSpace.sm),
                        Expanded(
                          child: Container(
                            height: 14,
                            decoration: BoxDecoration(
                              color: c.fill3,
                              borderRadius: BorderRadius.circular(7),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          ...children,
        ],
      ),
    );
  }
}
