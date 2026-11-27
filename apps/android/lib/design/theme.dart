// Lonora theme: typography, the inherited LnTheme, and the forui/Material themes derived from LnPalette.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:forui/forui.dart';

import 'tokens.dart';

/// Text roles. No style names a font family, so text uses the platform default (Roboto on Android),
/// with the system fallback for Arabic and other scripts. Every style centres its glyphs in the
/// line box (`leadingDistribution: even`), so taller scripts such as Arabic grow evenly above and
/// below instead of being pushed into the next line.
@immutable
class LnTextStyles {
  const LnTextStyles({
    required this.largeTitle,
    required this.display,
    required this.headline,
    required this.title,
    required this.body,
    required this.button,
    required this.caption,
    required this.captionStrong,
    required this.footnote,
    required this.footnoteStrong,
    required this.small,
    required this.smallStrong,
    required this.micro,
  });

  /// Builds the scale in [color] (normally `palette.fg`).
  ///
  /// [fontFamily] and [fontFamilyFallback] are empty in the app (Android picks its system font and
  /// resolves missing glyphs itself). Tests pass explicit families because the test engine has neither.
  factory LnTextStyles.standard({
    required Color color,
    String? fontFamily,
    List<String> fontFamilyFallback = const [],
  }) {
    TextStyle s(
      double size,
      double? lineHeight,
      FontWeight weight,
      double tracking,
    ) => TextStyle(
      inherit: false,
      fontFamily: fontFamily,
      fontFamilyFallback: fontFamilyFallback,
      fontSize: size,
      height: lineHeight == null ? null : lineHeight / size,
      fontWeight: weight,
      letterSpacing: tracking,
      color: color,
      leadingDistribution: TextLeadingDistribution.even,
      textBaseline: TextBaseline.alphabetic,
      decoration: TextDecoration.none,
    );
    return LnTextStyles(
      largeTitle: s(24, 32, FontWeight.w700, 0),
      display: s(20, 24, FontWeight.w700, 0),
      headline: s(18, 22, FontWeight.w600, 0),
      title: s(16, 24, FontWeight.w500, 0.5),
      body: s(16, 24, FontWeight.w400, 0.5),
      button: s(16, 24, FontWeight.w500, 0.5),
      caption: s(14, 20, FontWeight.w400, 0.25),
      captionStrong: s(14, 20, FontWeight.w500, 0.25),
      footnote: s(13, 18, FontWeight.w400, 0.3),
      footnoteStrong: s(13, 18, FontWeight.w500, 0.3),
      small: s(12, 16, FontWeight.w400, 0.4),
      smallStrong: s(12, 16, FontWeight.w500, 0.4),
      // 12 dp line height: a Lonora choice for one-line badges.
      micro: s(10, 12, FontWeight.w500, 0),
    );
  }

  /// 24/32 w700: large page titles.
  final TextStyle largeTitle;

  /// 20/24 w700: tab-root titles ("Explore"), sheet titles.
  final TextStyle display;

  /// 18/22 w600: section and card headlines.
  final TextStyle headline;

  /// 16/24 w500 +0.5: list titles, card titles, chip name.
  final TextStyle title;

  /// 16/24 w400 +0.5: message text, card values, field text.
  final TextStyle body;

  /// 16/24 w500 +0.5: block-button labels.
  final TextStyle button;

  /// 14/20 w400 +0.25: previews, timestamps, inline event rows.
  final TextStyle caption;

  /// 14/20 w500 +0.25.
  final TextStyle captionStrong;

  /// 13/18 w400 +0.3: secondary metadata.
  final TextStyle footnote;

  /// 13/18 w500 +0.3.
  final TextStyle footnoteStrong;

  /// 12/16 w400 +0.4: badges, helper text.
  final TextStyle small;

  /// 12/16 w500 +0.4: unread counts.
  final TextStyle smallStrong;

  /// 10 w500: badge counts.
  final TextStyle micro;

  LnTextStyles lerp(LnTextStyles other, double t) => LnTextStyles(
    largeTitle: TextStyle.lerp(largeTitle, other.largeTitle, t)!,
    display: TextStyle.lerp(display, other.display, t)!,
    headline: TextStyle.lerp(headline, other.headline, t)!,
    title: TextStyle.lerp(title, other.title, t)!,
    body: TextStyle.lerp(body, other.body, t)!,
    button: TextStyle.lerp(button, other.button, t)!,
    caption: TextStyle.lerp(caption, other.caption, t)!,
    captionStrong: TextStyle.lerp(captionStrong, other.captionStrong, t)!,
    footnote: TextStyle.lerp(footnote, other.footnote, t)!,
    footnoteStrong: TextStyle.lerp(footnoteStrong, other.footnoteStrong, t)!,
    small: TextStyle.lerp(small, other.small, t)!,
    smallStrong: TextStyle.lerp(smallStrong, other.smallStrong, t)!,
    micro: TextStyle.lerp(micro, other.micro, t)!,
  );
}

/// Everything a Lonora component needs to paint itself.
@immutable
class LnThemeData {
  const LnThemeData({required this.colors, required this.text});

  factory LnThemeData.fromPalette(
    LnPalette colors, {
    String? fontFamily,
    List<String> fontFamilyFallback = const [],
  }) => LnThemeData(
    colors: colors,
    text: LnTextStyles.standard(
      color: colors.fg,
      fontFamily: fontFamily,
      fontFamilyFallback: fontFamilyFallback,
    ),
  );

  static final light = LnThemeData.fromPalette(LnPalette.light);
  static final dark = LnThemeData.fromPalette(LnPalette.dark);

  final LnPalette colors;
  final LnTextStyles text;

  bool get isDark => colors.isDark;

  /// Shadow for floating chrome (header circles, capsule, composer, tab bar).
  List<BoxShadow> get chromeShadow =>
      isDark ? LnShadow.darkChrome : LnShadow.chrome;

  /// Shadow for bordered cards (action, schedule cards).
  List<BoxShadow> get cardShadow => isDark ? LnShadow.darkCard : LnShadow.card;

  /// Opaque equivalent of a translucent [fill] over the canvas.
  Color opaque(Color fill) => Color.alphaBlend(fill, colors.bg);
}

/// Provides [LnThemeData] to the subtree and sets matching ambient text and icon defaults.
class LnTheme extends InheritedWidget {
  LnTheme({super.key, required this.data, required Widget child})
    : super(
        child: _LnAmbient(data: data, child: child),
      );

  final LnThemeData data;

  /// The nearest [LnThemeData], or the light/dark default for the platform brightness.
  static LnThemeData of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<LnTheme>();
    if (scope != null) return scope.data;
    final brightness =
        MediaQuery.maybePlatformBrightnessOf(context) ?? Brightness.light;
    return brightness == Brightness.dark ? LnThemeData.dark : LnThemeData.light;
  }

  @override
  bool updateShouldNotify(LnTheme oldWidget) => data != oldWidget.data;
}

class _LnAmbient extends StatelessWidget {
  const _LnAmbient({required this.data, required this.child});

  final LnThemeData data;
  final Widget child;

  @override
  Widget build(BuildContext context) => DefaultTextStyle(
    style: data.text.body,
    textHeightBehavior: const TextHeightBehavior(
      leadingDistribution: TextLeadingDistribution.even,
    ),
    child: IconTheme(
      data: IconThemeData(color: data.colors.fg, size: LnSize.chromeIcon),
      child: child,
    ),
  );
}

extension LnThemeContext on BuildContext {
  LnThemeData get ln => LnTheme.of(this);
}

/// Edge-to-edge system bars: transparent, with icons contrasting the canvas.
SystemUiOverlayStyle lnSystemOverlayStyle(LnPalette p) => SystemUiOverlayStyle(
  statusBarColor: const Color(0x00000000),
  systemNavigationBarColor: const Color(0x00000000),
  systemNavigationBarDividerColor: const Color(0x00000000),
  systemNavigationBarContrastEnforced: false,
  systemStatusBarContrastEnforced: false,
  statusBarIconBrightness: p.isDark ? Brightness.light : Brightness.dark,
  statusBarBrightness: p.brightness,
  systemNavigationBarIconBrightness: p.isDark
      ? Brightness.light
      : Brightness.dark,
);

/// forui colours for Lonora. forui 0.15's roles are filled with Lonora's neutrals: primary = the
/// strong button ink, secondary = the 6 % secondary-button fill, muted = the 4 % fill, border = the 6 %
/// border, barrier = the overlay scrim. secondary and border are solid over the page (forui derives
/// its disabled colours from them by replacing their alpha); [lnForuiTheme] draws the enabled
/// secondary fill, dividers and field borders with the translucent tokens instead, so they also read
/// on a raised card.
FColors lnForuiColors(LnPalette p) {
  Color solid(Color c) => Color.alphaBlend(c, p.bg);
  return FColors(
    brightness: p.brightness,
    systemOverlayStyle: lnSystemOverlayStyle(p),
    barrier: p.scrim,
    background: p.bg,
    foreground: p.fg,
    primary: p.fgStrong,
    primaryForeground: p.isDark
        ? const Color(0xFF000000)
        : const Color(0xFFFFFFFF),
    secondary: solid(p.fill3),
    secondaryForeground: p.fg,
    muted: solid(p.fill1),
    mutedForeground: p.fgMuted,
    destructive: p.error,
    destructiveForeground: p.onAccent,
    error: p.error,
    errorForeground: p.onAccent,
    border: solid(p.border),
  );
}

/// forui typography on the [LnTextStyles] scale: xs 12/16 +0.4, sm 14/20 +0.25,
/// base 16/24 +0.5, lg 18/22, xl 20/24. Larger sizes keep forui's metrics. No font family is set, so the
/// platform default applies (tests pass [fontFamily]).
FTypography lnForuiTypography(
  FColors colors, {
  String? fontFamily,
  List<String> fontFamilyFallback = const [],
}) {
  // forui needs a non-empty family; Android's `sans-serif` is the platform default the styles resolve to.
  final base = FTypography.inherit(
    colors: colors,
    defaultFontFamily: fontFamily ?? 'sans-serif',
  );
  TextStyle f(TextStyle s) => TextStyle(
    inherit: s.inherit,
    color: s.color,
    fontSize: s.fontSize,
    height: s.height,
    letterSpacing: s.letterSpacing,
    fontWeight: s.fontWeight,
    fontFamily: fontFamily,
    fontFamilyFallback: fontFamilyFallback,
    leadingDistribution: TextLeadingDistribution.even,
  );
  return base.copyWith(
    xs: f(base.xs.copyWith(height: 16 / 12, letterSpacing: 0.4)),
    sm: f(base.sm.copyWith(height: 20 / 14, letterSpacing: 0.25)),
    base: f(base.base.copyWith(height: 24 / 16, letterSpacing: 0.5)),
    lg: f(base.lg.copyWith(height: 22 / 18, letterSpacing: 0)),
    xl: f(base.xl.copyWith(height: 24 / 20, letterSpacing: 0)),
    xl2: f(base.xl2),
    xl3: f(base.xl3),
    xl4: f(base.xl4),
    xl5: f(base.xl5),
    xl6: f(base.xl6),
    xl7: f(base.xl7),
    xl8: f(base.xl8),
  );
}

/// The forui 0.15 theme for Lonora: forui's defaults derived from [lnForuiColors]/[lnForuiTypography],
/// with these style overrides:
/// * radius 24 (cards; the composer and block buttons are 48 dp stadiums);
/// * the card shadow ([LnShadow.card]) and 24 dp chrome icons in the ink;
/// * 16 dp page gutter;
/// * block buttons 48 dp tall whose disabled (consumed, e.g. "Approved") look is the 6 % fill
///   (#F0F0F0 in light) with a tertiary-ink label;
/// * the secondary-button fill, dividers and field borders kept translucent (black 6 % in light,
///   white 6 % in dark), so on a #1F1F1F dark card they composite to ≈#2C2C2C instead of an
///   opaque #222222;
/// * a dark off switch with a visible track and thumb (Lonora-specific);
/// * toasts at the top on the inverse surface ([LnPalette.inverseSurface]).
FThemeData lnForuiTheme(
  LnPalette p, {
  String? fontFamily,
  List<String> fontFamilyFallback = const [],
}) {
  final colors = lnForuiColors(p);
  final typography = lnForuiTypography(
    colors,
    fontFamily: fontFamily,
    fontFamilyFallback: fontFamilyFallback,
  );
  final base = FStyle.inherit(colors: colors, typography: typography);
  const radius = BorderRadius.all(Radius.circular(LnRadius.card));
  final style = FStyle(
    formFieldStyle: base.formFieldStyle,
    focusedOutlineStyle: base.focusedOutlineStyle,
    iconStyle: IconThemeData(color: p.fg, size: LnSize.chromeIcon),
    tappableStyle: base.tappableStyle,
    borderRadius: radius,
    borderWidth: 1,
    pagePadding: const EdgeInsets.symmetric(
      horizontal: LnSpace.pageGutter,
      vertical: LnSpace.xs,
    ),
    shadow: p.isDark ? LnShadow.darkCard : LnShadow.card,
  );

  final buttons = FButtonStyles.inherit(
    colors: colors,
    typography: typography,
    style: style,
  );
  FButtonStyle block(FButtonStyle s, {Color? fill}) => s.copyWith(
    decoration: FWidgetStateMap({
      WidgetState.disabled: BoxDecoration(color: p.fill3, borderRadius: radius),
      WidgetState.hovered | WidgetState.pressed: s.decoration.resolve({
        WidgetState.pressed,
      }),
      WidgetState.any: s.decoration.resolve({}).copyWith(color: fill),
    }),
    contentStyle: (cs) => cs.copyWith(
      textStyle: FWidgetStateMap({
        WidgetState.disabled: cs.textStyle
            .resolve({})
            .copyWith(color: p.fgSubtle),
        WidgetState.any: cs.textStyle.resolve({}),
      }),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
    ),
  );

  final toaster = FToasterStyle.inherit(
    colors: colors,
    typography: typography,
    style: style,
  );

  final dividers = FDividerStyles.inherit(colors: colors, style: style);
  final textField = FTextFieldStyle.inherit(
    colors: colors,
    typography: typography,
    style: style,
  );
  final fieldBorder = textField.border.resolve({});
  final switches = FSwitchStyle.inherit(colors: colors, style: style);

  return FThemeData(
    debugLabel: p.isDark ? 'Lonora Dark' : 'Lonora Light',
    colors: colors,
    typography: typography,
    style: style,
    buttonStyles: FButtonStyles(
      primary: block(buttons.primary),
      secondary: block(buttons.secondary, fill: p.fill3),
      destructive: block(buttons.destructive),
      outline: block(buttons.outline),
      ghost: buttons.ghost,
    ),
    dividerStyles: FDividerStyles(
      horizontalStyle: dividers.horizontalStyle.copyWith(color: p.border),
      verticalStyle: dividers.verticalStyle.copyWith(color: p.border),
    ),
    textFieldStyle: textField.copyWith(
      border: FWidgetStateMap({
        WidgetState.error: textField.border.resolve({WidgetState.error}),
        WidgetState.disabled: textField.border.resolve({WidgetState.disabled}),
        WidgetState.focused: textField.border.resolve({WidgetState.focused}),
        WidgetState.any: fieldBorder.copyWith(
          borderSide: fieldBorder.borderSide.copyWith(color: p.border),
        ),
      }),
    ),
    // forui's dark off switch is a #141414 thumb on a #222222 track (≈1.15:1 on the page): the
    // track takes the tertiary ink and the thumb the ink, as forui's on switch inverts them.
    switchStyle: p.isDark
        ? switches.copyWith(
            trackColor: switches.trackColor.replaceFirstWhere(
              {},
              (_) => p.fgSubtle,
            ),
            thumbColor: FWidgetStateMap({
              WidgetState.disabled | WidgetState.selected: colors.background,
              WidgetState.any: p.fg,
            }),
          )
        : switches,
    toasterStyle: toaster.copyWith(
      toastAlignment: FToastAlignment.topCenter,
      toastStyle: (ts) => ts.copyWith(
        decoration: BoxDecoration(
          color: p.inverseSurface,
          borderRadius: radius,
          boxShadow: LnShadow.darkChrome,
        ),
        iconStyle: IconThemeData(color: p.onInverse, size: 18),
        titleTextStyle: typography.sm.copyWith(
          color: p.onInverse,
          fontWeight: FontWeight.w500,
        ),
        descriptionTextStyle: typography.sm.copyWith(color: p.onInverseMuted),
      ),
    ),
  );
}

/// Material 3 theme for the parts of the app that still use Material widgets (text fields, sheets,
/// selection handles, page transitions). Neutral so no default Material look leaks into Lonora screens.
ThemeData lnMaterialTheme(
  LnPalette p, {
  String? fontFamily,
  List<String> fontFamilyFallback = const [],
}) {
  final text = LnTextStyles.standard(
    color: p.fg,
    fontFamily: fontFamily,
    fontFamilyFallback: fontFamilyFallback,
  );
  final scheme = ColorScheme(
    brightness: p.brightness,
    primary: p.brand,
    onPrimary: p.onAccent,
    primaryContainer: Color.alphaBlend(p.brand.withValues(alpha: 0.16), p.bg),
    onPrimaryContainer: p.fg,
    secondary: p.fgStrong,
    onSecondary: p.bg,
    tertiary: p.userBubble,
    onTertiary: p.onUserBubble,
    error: p.error,
    onError: p.onAccent,
    surface: p.bg,
    onSurface: p.fg,
    onSurfaceVariant: p.fgMuted,
    surfaceContainerLowest: p.bg,
    surfaceContainerLow: p.surface,
    surfaceContainer: Color.alphaBlend(p.fill1, p.bg),
    surfaceContainerHigh: Color.alphaBlend(p.fill2, p.bg),
    surfaceContainerHighest: Color.alphaBlend(p.fill3, p.bg),
    outline: Color.alphaBlend(p.border, p.bg),
    outlineVariant: Color.alphaBlend(p.fill3, p.bg),
    shadow: const Color(0xFF000000),
    scrim: p.scrim,
    inverseSurface: p.fgStrong,
    onInverseSurface: p.bg,
    inversePrimary: p.brand,
    surfaceTint: const Color(0x00000000),
  );

  TextStyle m(TextStyle s) => s.copyWith(inherit: true);
  final textTheme = TextTheme(
    displayLarge: m(text.display.copyWith(fontSize: 34, height: 40 / 34)),
    displayMedium: m(text.display.copyWith(fontSize: 28, height: 34 / 28)),
    displaySmall: m(text.largeTitle),
    headlineLarge: m(text.largeTitle),
    headlineMedium: m(text.display.copyWith(fontSize: 22, height: 28 / 22)),
    headlineSmall: m(text.headline),
    titleLarge: m(text.display),
    titleMedium: m(text.title),
    titleSmall: m(text.captionStrong),
    bodyLarge: m(text.body),
    bodyMedium: m(text.caption),
    bodySmall: m(text.small),
    labelLarge: m(text.button),
    labelMedium: m(text.captionStrong),
    labelSmall: m(text.smallStrong),
  );

  return ThemeData(
    useMaterial3: true,
    brightness: p.brightness,
    colorScheme: scheme,
    fontFamily: fontFamily,
    fontFamilyFallback: fontFamilyFallback,
    textTheme: textTheme,
    primaryTextTheme: textTheme,
    scaffoldBackgroundColor: p.bg,
    canvasColor: p.bg,
    cardColor: p.surface,
    dividerColor: Color.alphaBlend(p.fill3, p.bg),
    disabledColor: p.fgSubtle,
    hintColor: p.fgSubtle,
    splashFactory: NoSplash.splashFactory,
    splashColor: const Color(0x00000000),
    highlightColor: const Color(0x00000000),
    hoverColor: p.fill1,
    focusColor: p.fill2,
    materialTapTargetSize: MaterialTapTargetSize.padded,
    visualDensity: VisualDensity.standard,
    iconTheme: IconThemeData(color: p.fg, size: LnSize.chromeIcon),
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: p.brand,
      selectionColor: p.brand.withValues(alpha: 0.28),
      selectionHandleColor: p.brand,
    ),
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: {
        TargetPlatform.android: PredictiveBackPageTransitionsBuilder(),
      },
    ),
    appBarTheme: AppBarThemeData(
      backgroundColor: p.bg,
      foregroundColor: p.fg,
      surfaceTintColor: const Color(0x00000000),
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: true,
      systemOverlayStyle: lnSystemOverlayStyle(p),
      titleTextStyle: text.title,
      iconTheme: IconThemeData(color: p.fg, size: LnSize.chromeIcon),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      // Material sheets have no backdrop blur, so they use the opaque surface instead of the sheet fill.
      backgroundColor: p.surface,
      modalBackgroundColor: p.surface,
      surfaceTintColor: const Color(0x00000000),
      modalBarrierColor: p.scrim,
      elevation: 0,
      modalElevation: 0,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(LnRadius.sheet),
        ),
      ),
      clipBehavior: Clip.antiAlias,
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: p.popover,
      surfaceTintColor: const Color(0x00000000),
      elevation: 0,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(LnRadius.card)),
      ),
      barrierColor: p.scrim,
      titleTextStyle: text.title,
      contentTextStyle: text.body.copyWith(color: p.fgMuted),
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: p.popover,
      surfaceTintColor: const Color(0x00000000),
      elevation: 0,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(16)),
      ),
      textStyle: text.body,
    ),
    dividerTheme: DividerThemeData(
      color: Color.alphaBlend(p.fill3, p.bg),
      thickness: 1,
      space: 1,
    ),
    inputDecorationTheme: InputDecorationThemeData(
      filled: true,
      fillColor: p.fill1,
      hintStyle: text.body.copyWith(color: p.fgSubtle),
      border: const OutlineInputBorder(
        borderSide: BorderSide.none,
        borderRadius: BorderRadius.all(Radius.circular(LnRadius.field)),
      ),
      contentPadding: const EdgeInsetsDirectional.symmetric(
        horizontal: 16,
        vertical: 13,
      ),
    ),
    scrollbarTheme: ScrollbarThemeData(
      thumbColor: WidgetStatePropertyAll(p.fgSubtle.withValues(alpha: 0.5)),
      radius: const Radius.circular(4),
      thickness: const WidgetStatePropertyAll(4),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      color: p.fgMuted,
      circularTrackColor: p.fill3,
    ),
  );
}
