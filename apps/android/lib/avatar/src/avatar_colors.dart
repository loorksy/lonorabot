// Shell palette and colour resolution.
//
// Port of packages/core/src/avatar-geometry.ts:227-414 (AVATAR_COLOR_LIST, AVATAR_COLORS,
// DEFAULT_AVATAR_COLOR, identityHash, seededRandom, resolveAvatarColor and helpers). The
// legacy shape paths of that file (js:16-225) are not used by the avatar and are not ported.
import 'dart:ui' show Color;

import 'motion.dart' show imul32;

/// One palette entry (`AvatarColorDef`). Colours are hex strings, as stored on agents.
class AvatarColor {
  const AvatarColor({
    required this.id,
    required this.name,
    required this.light,
    required this.dark,
    required this.eyeColor,
    required this.hex,
  });

  final String id;
  final String name;
  final String light;
  final String dark;
  final String eyeColor;

  /// The shell fill (what `Agent.color` stores).
  final String hex;

  /// [hex] as a [Color].
  Color get color => avatarHexColor(hex);
}

/// The eleven shell colours of the avatar studio, in order (avatar-geometry.ts:244-345).
const List<AvatarColor> avatarPalette = [
  AvatarColor(
    id: 'white',
    name: 'Staff White',
    light: '#FFFFFF',
    dark: '#CBD5E1',
    eyeColor: '#141414',
    hex: '#FFFFFF',
  ),
  AvatarColor(
    id: 'violet',
    name: 'Executive Violet',
    light: '#A97EFE',
    dark: '#7C3AED',
    eyeColor: '#FFFFFF',
    hex: '#8B5CF6',
  ),
  AvatarColor(
    id: 'green',
    name: 'Emerald',
    light: '#00C972',
    dark: '#059669',
    eyeColor: '#FFFFFF',
    hex: '#10B981',
  ),
  AvatarColor(
    id: 'orange',
    name: 'Forge Orange',
    light: '#FF781C',
    dark: '#EA580C',
    eyeColor: '#FFFFFF',
    hex: '#F97316',
  ),
  AvatarColor(
    id: 'cyan',
    name: 'Cyber Cyan',
    light: '#1CC3B0',
    dark: '#0284C7',
    eyeColor: '#FFFFFF',
    hex: '#06B6D4',
  ),
  AvatarColor(
    id: 'blue',
    name: 'Cobalt Blue',
    light: '#2A92FE',
    dark: '#1D4ED8',
    eyeColor: '#FFFFFF',
    hex: '#3B82F6',
  ),
  AvatarColor(
    id: 'yellow',
    name: 'Amber Gold',
    light: '#FFAF38',
    dark: '#D97706',
    eyeColor: '#141414',
    hex: '#EAB308',
  ),
  AvatarColor(
    id: 'brown',
    name: 'Caramel Bronze',
    light: '#A27952',
    dark: '#78350F',
    eyeColor: '#FFFFFF',
    hex: '#8D6E63',
  ),
  AvatarColor(
    id: 'red',
    name: 'Crimson Red',
    light: '#FF3E51',
    dark: '#BE123C',
    eyeColor: '#FFFFFF',
    hex: '#EF4444',
  ),
  AvatarColor(
    id: 'magenta',
    name: 'Neon Pink',
    light: '#FF5EB1',
    dark: '#BE185D',
    eyeColor: '#FFFFFF',
    hex: '#EC4899',
  ),
  AvatarColor(
    id: 'gray',
    name: 'Slate Silver',
    light: '#94A3B8',
    dark: '#475569',
    eyeColor: '#FFFFFF',
    hex: '#64748B',
  ),
];

/// Studio reset/fallback colour, Executive Violet (avatar-geometry.ts:349-351).
const String defaultAvatarColor = '#8B5CF6';

final RegExp _hexPattern = RegExp(
  r'^#(?:[0-9a-f]{3}|[0-9a-f]{6})$',
  caseSensitive: false,
);

/// `#rgb` / `#rrggbb` → opaque [Color]; anything else → [defaultAvatarColor].
Color avatarHexColor(String hex) {
  final value = _hexPattern.hasMatch(hex) ? _expandHex(hex) : '8B5CF6';
  return Color(0xFF000000 | int.parse(value, radix: 16));
}

/// FNV-1a over UTF-16 code units, unsigned (avatar-geometry.ts:353-359).
int identityHash(String value) {
  var hash = 2166136261;
  for (var index = 0; index < value.length; index += 1) {
    hash = imul32(hash ^ value.codeUnitAt(index), 16777619);
  }
  return hash;
}

/// mulberry32 generator (avatar-geometry.ts:361-369).
double Function() seededRandom(int seed) {
  var value = seed & 0xFFFFFFFF;
  return () {
    value = (value + 1831565813) & 0xFFFFFFFF;
    var next = imul32(value ^ (value >> 15), 1 | value);
    next = ((next + imul32(next ^ (next >> 7), 61 | next)) & 0xFFFFFFFF) ^ next;
    return (next ^ (next >> 14)) / 4294967296;
  };
}

/// The shell colour for an agent (avatar-geometry.ts:371-395): a palette id, name or hex;
/// else any custom `#rgb/#rrggbb`; else (empty or unrecognised) a palette colour picked
/// from a hash of [identity] — the same one web and Expo pick.
AvatarColor resolveAvatarColor(String identity, [String? explicitColor]) {
  if (explicitColor != null && explicitColor.isNotEmpty) {
    final clean = explicitColor.toLowerCase();
    for (final c in avatarPalette) {
      if (c.id == clean || c.name.toLowerCase() == clean) return c;
    }
    for (final c in avatarPalette) {
      if (c.hex.toLowerCase() == clean) return c;
    }
    if (_hexPattern.hasMatch(explicitColor)) {
      return AvatarColor(
        id: 'custom',
        name: 'Custom',
        light: explicitColor,
        dark: _darkenHex(explicitColor, 20),
        eyeColor: _isColorBright(explicitColor) ? '#141414' : '#FFFFFF',
        hex: explicitColor,
      );
    }
  }
  final seed = identityHash(identity) ^ imul32(1, 2654435769);
  final index = (seededRandom(seed ^ 2654435769)() * avatarPalette.length)
      .floor();
  return avatarPalette[index % avatarPalette.length];
}

String _expandHex(String hex) {
  final c = hex.replaceFirst('#', '');
  if (c.length == 3) return '${c[0]}${c[0]}${c[1]}${c[1]}${c[2]}${c[2]}';
  return c;
}

bool _isColorBright(String hex) {
  final c = _expandHex(hex);
  final r = int.tryParse(c.substring(0, 2), radix: 16) ?? 0;
  final g = int.tryParse(c.substring(2, 4), radix: 16) ?? 0;
  final b = int.tryParse(c.substring(4, 6), radix: 16) ?? 0;
  return (r * 299 + g * 587 + b * 114) / 1000 > 180;
}

String _darkenHex(String hex, double percent) {
  final n = int.parse(_expandHex(hex), radix: 16);
  final factor = 1 - percent / 100;
  final r = (((n >> 16) & 255) * factor).floor().clamp(0, 255);
  final g = (((n >> 8) & 255) * factor).floor().clamp(0, 255);
  final b = ((n & 255) * factor).floor().clamp(0, 255);
  return '#${((1 << 24) + (r << 16) + (g << 8) + b).toRadixString(16).substring(1)}';
}
