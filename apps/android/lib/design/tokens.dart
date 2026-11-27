// Design tokens for Lonora Android: colours, spacing, radii, sizes, shadows and motion (dp).
// theme.dart maps them onto forui and Material; anything not set here keeps the forui default.
import 'package:flutter/widgets.dart';

/// Colour roles. Neutral fills are foreground-at-alpha so the same token works in both themes.
@immutable
class LnPalette {
  const LnPalette({
    required this.brightness,
    required this.bg,
    required this.fg,
    required this.fgWarm,
    required this.fgStrong,
    required this.fgMuted,
    required this.fgSubtle,
    required this.chevron,
    required this.fill1,
    required this.fill2,
    required this.fill3,
    required this.fill4,
    required this.tabHighlight,
    required this.border,
    required this.surface,
    required this.sheet,
    required this.popover,
    required this.barSurface,
    required this.userBubble,
    required this.onUserBubble,
    required this.agentBubble,
    required this.onAgentBubble,
    required this.sendDisc,
    required this.sendArrow,
    required this.sendDisabledDisc,
    required this.sendDisabledArrow,
    required this.brand,
    required this.selection,
    required this.warning,
    required this.success,
    required this.error,
    required this.attention,
    required this.pending,
    required this.positive,
    required this.negative,
    required this.scrim,
    required this.onAccent,
    required this.link,
    required this.inverseSurface,
    required this.onInverse,
    required this.onInverseMuted,
    required this.inverseFill,
    required this.toastAction,
    required this.segmentedSelected,
    required this.successText,
    required this.positiveText,
  });

  final Brightness brightness;
  final Color bg;
  final Color fg;
  final Color fgWarm;
  final Color fgStrong;
  final Color fgMuted;
  final Color fgSubtle;
  final Color chevron;

  /// Black (light) or white (dark) at 4 / 5 / 6 / 7 %.
  final Color fill1;
  final Color fill2;
  final Color fill3;
  final Color fill4;

  /// Selected-tab highlight in the floating tab bar (opaque #EDEDED in light).
  final Color tabHighlight;
  final Color border;

  /// Raised surfaces: header circles, chips, cards, composer.
  final Color surface;

  /// Bottom-sheet fill: 60 % surface, meant to sit on a backdrop blur.
  final Color sheet;
  final Color popover;

  /// Floating tab bar and action circle: an opaque elevated surface (no backdrop blur on Android).
  final Color barSurface;

  final Color userBubble;
  final Color onUserBubble;
  final Color agentBubble;
  final Color onAgentBubble;

  final Color sendDisc;
  final Color sendArrow;
  final Color sendDisabledDisc;
  final Color sendDisabledArrow;

  final Color brand;
  final Color selection;
  final Color warning;
  final Color success;
  final Color error;
  final Color attention;
  final Color pending;

  /// Market direction (Lonora-specific; kept distinct from the user-bubble blue and error red).
  final Color positive;
  final Color negative;

  final Color scrim;

  /// Ink on saturated fills: brand, success, error, selection (unread pill, initials on brand, the
  /// End-call button). Fixed white in both modes.
  final Color onAccent;

  /// Blue text and icons (links).
  final Color link;

  /// The toast's dark stadium (heads-up banner, incoming call, offline strip). Lonora-specific: an
  /// inverse surface in both modes, near-black in light and #3A3A3C in dark.
  final Color inverseSurface;

  /// Ink on [inverseSurface]: fixed white.
  final Color onInverse;

  /// Secondary ink on [inverseSurface]. Lonora-specific: 70 % white ([inkWhiteMuted] is 60 %).
  final Color onInverseMuted;

  /// A quiet fill (pill, button) on [inverseSurface] or another dark tinted surface. Lonora-specific.
  final Color inverseFill;

  /// The toast's action label. Lonora-specific.
  final Color toastAction;

  /// Selected segment of a segmented control: white in light, 24 % white over the track in dark.
  final Color segmentedSelected;

  /// [success] and [positive] as small text: [success] is a function colour (status dots, icons)
  /// and Lonora's market green is too light for text in light mode. Lonora-specific: the same hues
  /// darkened to ≥ 4.5:1 on white and on the #F2F2F2 tile; dark mode keeps the base colours.
  final Color successText;
  final Color positiveText;

  /// Selected reaction chip under a message (the owner's own reaction). Lonora-specific.
  Color get reactionSelected =>
      selection.withValues(alpha: isDark ? 0.28 : 0.14);

  /// Border of [reactionSelected]. Lonora-specific.
  Color get reactionSelectedBorder => selection.withValues(alpha: 0.5);

  /// Brief highlight on a message the conversation jumped to. Lonora-specific.
  Color get jumpFlash => selection.withValues(alpha: 0.12);

  /// Fixed white inks for text and icons on images and tinted surfaces, the same in both modes:
  /// primary, secondary (60 %) and tertiary (30 %).
  static const inkWhite = Color(0xFFFFFFFF);
  static const inkWhiteMuted = Color(0x99FFFFFF);
  static const inkWhiteSubtle = Color(0x4DFFFFFF);

  /// Opacity of a disabled control drawn in its normal colours. Lonora-specific.
  static const disabledOpacity = 0.45;

  bool get isDark => brightness == Brightness.dark;

  static const light = LnPalette(
    brightness: Brightness.light,
    bg: Color(0xFFFFFFFF),
    fg: Color(0xFF1F1F1F),
    fgWarm: Color(0xFF34322D),
    fgStrong: Color(0xFF141414),
    // 60 % / 30 % of the ink (secondary / tertiary text and icons).
    fgMuted: Color(0x991F1F1F),
    fgSubtle: Color(0x4D1F1F1F),
    chevron: Color(0x991F1F1F),
    fill1: Color(0x0A000000),
    fill2: Color(0x0D000000),
    fill3: Color(0x0F000000),
    fill4: Color(0x12000000),
    tabHighlight: Color(0xFFEDEDED),
    border: Color(0x0F000000),
    surface: Color(0xFFFFFFFF),
    sheet: Color(0x99FFFFFF),
    popover: Color(0xFFFFFFFF),
    barSurface: Color(0xFFFFFFFF),
    userBubble: Color(0xFF2276EC),
    onUserBubble: Color(0xFFFFFFFF),
    agentBubble: Color(0xFFF5F5F5),
    onAgentBubble: Color(0xFF34322D),
    sendDisc: Color(0xFF111111),
    sendArrow: Color(0xFFFFFFFF),
    sendDisabledDisc: Color(0x1F37352F),
    sendDisabledArrow: Color(0xFFC7C7C6),
    brand: Color(0xFF7776EE),
    selection: Color(0xFF2276EC),
    warning: Color(0xFFE59900),
    success: Color(0xFF25BA3B),
    error: Color(0xFFFA3D43),
    attention: Color(0xFFFF6438),
    pending: Color(0xFFFFBF36),
    positive: Color(0xFF1FA971),
    negative: Color(0xFFE5484D),
    scrim: Color(0x33000000),
    onAccent: Color(0xFFFFFFFF),
    link: Color(0xFF2276EC),
    inverseSurface: Color(0xF2141414),
    onInverse: Color(0xFFFFFFFF),
    onInverseMuted: Color(0xB3FFFFFF),
    inverseFill: Color(0x26FFFFFF),
    toastAction: Color(0xFFB4B3FF),
    segmentedSelected: Color(0xFFFFFFFF),
    successText: Color(0xFF197E28),
    positiveText: Color(0xFF177C53),
  );

  static const dark = LnPalette(
    brightness: Brightness.dark,
    bg: Color(0xFF141414),
    fg: Color(0xFFFFFFFF),
    fgWarm: Color(0xFFDADADA),
    fgStrong: Color(0xFFFFFFFF),
    fgMuted: Color(0x99FFFFFF),
    fgSubtle: Color(0x4DFFFFFF),
    chevron: Color(0x99FFFFFF),
    fill1: Color(0x0AFFFFFF),
    fill2: Color(0x0DFFFFFF),
    fill3: Color(0x0FFFFFFF),
    fill4: Color(0x12FFFFFF),
    tabHighlight: Color(0x0AFFFFFF),
    border: Color(0x0FFFFFFF),
    surface: Color(0xFF1F1F1F),
    sheet: Color(0x991F1F1F),
    popover: Color(0xFF1F1F1F),
    barSurface: Color(0xFF1F1F1F),
    userBubble: Color(0xFF347ADB),
    onUserBubble: Color(0xFFFFFFFF),
    agentBubble: Color(0xFF292929),
    onAgentBubble: Color(0xFFDADADA),
    sendDisc: Color(0xE6FFFFFF),
    sendArrow: Color(0xFF000000),
    sendDisabledDisc: Color(0x1FFFFFFF),
    sendDisabledArrow: Color(0xFFC7C7C6),
    brand: Color(0xFF8D8CF5),
    selection: Color(0xFF347ADB),
    warning: Color(0xFFF5B734),
    success: Color(0xFF5EB92D),
    error: Color(0xFFEA454A),
    attention: Color(0xFFFF7A52),
    pending: Color(0xFFFFC24D),
    positive: Color(0xFF2FD39A),
    negative: Color(0xFFFF6369),
    scrim: Color(0x7A000000),
    onAccent: Color(0xFFFFFFFF),
    link: Color(0xFF69A4F8),
    inverseSurface: Color(0xFF3A3A3C),
    onInverse: Color(0xFFFFFFFF),
    onInverseMuted: Color(0xB3FFFFFF),
    inverseFill: Color(0x26FFFFFF),
    // As light: the brand (#8D8CF5) reads only 3.9:1 on the #3A3A3C toast; this tint 5.9:1.
    toastAction: Color(0xFFB4B3FF),
    segmentedSelected: Color(0x3DFFFFFF),
    successText: Color(0xFF5EB92D),
    positiveText: Color(0xFF2FD39A),
  );
}

/// The five agent palettes. Only the profile-hub gradient is a token so far ([hubStart] → [hubEnd],
/// the same in both modes).
enum LnAgentPalette {
  blue(hubStart: Color(0xFF143352), hubEnd: Color(0xFF183D62)),
  red(hubStart: Color(0xFF422424), hubEnd: Color(0xFF502B2B)),
  yellow(hubStart: Color(0xFF453021), hubEnd: Color(0xFF533A28)),
  brown(hubStart: Color(0xFF3B322B), hubEnd: Color(0xFF473C34)),
  gray(hubStart: Color(0xFF333333), hubEnd: Color(0xFF3D3D3D));

  const LnAgentPalette({required this.hubStart, required this.hubEnd});

  final Color hubStart;
  final Color hubEnd;
}

/// Spacing scale and layout constants (dp).
abstract final class LnSpace {
  static const double xxs = 4;
  static const double xs = 8;
  static const double sm = 12;
  static const double md = 16;
  static const double lg = 20;
  static const double xl = 24;
  static const double xxl = 32;

  static const double pageGutter = 16;
  static const double chromeGutter = 20;
  static const double listInset = 24;

  /// Avatar → text gap in list rows (24 dp inset + 44 dp avatar + 15 dp: text starts at 83 dp).
  static const double listTextGap = 15;

  /// Gap between consecutive items from the same sender (bubble → bubble or card).
  static const double sameSenderGap = 7;
  static const double senderChangeGap = 16;

  /// Composer ↔ tab bar.
  static const double composerToBar = 7;

  /// Floating tab bar: `SafeArea(minimum: fromLTRB(21, 6, 21, 12))` around a `Row(spacing: 8)` of the
  /// pill and the action circle. The bottom value is a minimum; a taller system inset wins.
  static const double tabBarGutter = 21;
  static const double tabBarSpacing = 8;
  static const double chromeBottom = 12;

  /// Inner padding of bordered cards; inset of block buttons inside cards.
  static const double cardPadding = 16;
  static const double cardButtonInset = 12;

  /// Explore tile grid gap.
  static const double tileGap = 8;
}

abstract final class LnRadius {
  /// Bubble corners (single-line bubbles are full stadiums either way).
  static const double bubble = 24;

  /// Explore tiles and recommendation cards.
  static const double tile = 24;
  static const double card = 24;
  static const double iconTile = 8;

  /// Top corners only.
  static const double sheet = 38;
  static const double field = 14;
  static const double image = 16;
  static const double stadium = 999;
  static const double tabHighlight = 100;
}

abstract final class LnSize {
  static const double headerCircle = 44;
  static const double chromeIcon = 24;
  static const double composerIcon = 20;

  /// Circular composer button (attach, mic) around a [composerIcon].
  static const double composerButton = 36;
  static const double toolIcon = 18;
  static const double avatarList = 44;
  static const double avatarHeader = 48;
  static const double avatarGroup = 28;

  /// Chat-header name pill.
  static const double chipHeight = 32;
  static const double composerHeight = 48;

  /// The pill takes the width left by the gutters, the 8 dp spacing and the action circle (W − 112).
  static const double tabBarHeight = 62;
  static const EdgeInsets tabBarPadding = EdgeInsets.fromLTRB(9, 4, 9, 4);
  static const double tabItemHeight = 54;

  /// The selection highlight extends this far beyond each side of its tab.
  static const double tabIndicatorOutset = 6;

  /// 54 dp disc plus 4 dp padding.
  static const double actionCircle = 62;
  static const double actionCirclePadding = 4;
  static const double blockButton = 48;
  static const double sendButton = 36;
  static const double listRow = 66;
  static const double bubbleMaxWidth = 313;
  static const double cardMaxWidth = 315;
  static const double headerBarHeight = 64;
  static const double bubbleMaxFraction = 0.8;
  static const double bubblePadH = 16;
  static const double bubblePadV = 12;

  /// Permission-card illustration band.
  static const double illustrationHeader = 110;
  static const double iconTile = 40;
  static const double exploreTile = 144;
  static const double wideTileWidth = 296;
  static const double wideTileHeight = 128;
  static const double recIllustration = 32;
  static const double jumpButton = 40;

  /// Minimum touch target (Android accessibility guideline). Where a visual is smaller, the visual
  /// keeps its size and the hit area grows around it.
  static const double minTouch = 48;

  /// Emoji in the message menu's quick-reaction strip, and in the reactions list. Lonora-specific.
  static const double reactionPickerEmoji = 26;
  static const double reactionListEmoji = 24;
}

abstract final class LnShadow {
  /// Header circles, name pill, composer, tab bar: a soft ramp below the chrome edges, black 4 %,
  /// σ ≈ 7.5 dp, y 4.
  static const chrome = [
    BoxShadow(color: Color(0x0A000000), blurRadius: 12, offset: Offset(0, 4)),
  ];

  /// Bordered conversation cards (same ramp, slightly tighter).
  static const card = [
    BoxShadow(color: Color(0x0A000000), blurRadius: 10, offset: Offset(0, 4)),
  ];
  static const darkChrome = [
    BoxShadow(color: Color(0x40000000), blurRadius: 10, offset: Offset(0, 4)),
  ];
  static const darkCard = [
    BoxShadow(color: Color(0x33000000), blurRadius: 6, offset: Offset(0, 3)),
  ];
  static const sheet = [
    BoxShadow(color: Color(0x14000000), blurRadius: 24, offset: Offset(0, -2)),
  ];
}

/// Motion. Press feedback is an opacity fade without scale (pressed opacity 0.4, 120 ms down / 180 ms up,
/// as Flutter's `CupertinoButton`).
abstract final class LnMotion {
  static const pressScale = 1.0;
  static const pressOpacity = 0.4;
  static const pressDown = Duration(milliseconds: 120);
  static const pressUp = Duration(milliseconds: 180);
  static const pressDownCurve = Curves.easeInOutCubicEmphasized;
  static const pressUpCurve = Curves.easeOutCubic;

  /// Optional "pop" press for a button that should bounce.
  static const popScale = 0.82;
  static const popCurve = Cubic(0.45, 1.45, 0.8, 1);
  static const popDuration = Duration(milliseconds: 150);

  static const fast = Duration(milliseconds: 120);
  static const medium = Duration(milliseconds: 180);
  static const slow = Duration(milliseconds: 300);
  static const emphasized = Curves.easeOutCubic;
  static const standard = Curves.easeInOutCubic;

  static const tabIndicator = Duration(milliseconds: 180);
  static const drawer = Duration(milliseconds: 320);
  static const typingLoop = Duration(milliseconds: 1050);
  static const typingStagger = Duration(milliseconds: 83);
}
