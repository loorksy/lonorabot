// Exact decimals for the owner's orders. Prices and volumes travel as the server's decimal
// strings (lonora_contracts TradeRequest: Decimal > 0) and the executor compares them exactly
// (lonora_security.financial `validate_trade`): `(volume - volume_min) % volume_step` and
// `price % tick_size` must be exactly zero. A double would find 0.3 % 0.1 ≠ 0, so every check
// here works on a scaled integer.
import 'package:flutter/foundation.dart';

/// An exact non-negative decimal: [units] × 10^−[scale].
@immutable
class Dec implements Comparable<Dec> {
  const Dec._(this.units, this.scale);

  final BigInt units;
  final int scale;

  static final Dec zero = Dec._(BigInt.zero, 0);

  static final _plain = RegExp(r'^(\d*)(?:\.(\d*))?$');
  static final _server = RegExp(
    r'^([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$',
  );

  /// What the owner typed: ASCII, Arabic-Indic (٠–٩) or Eastern Arabic-Indic (۰–۹) digits,
  /// with «.» or «٫» as the decimal point. No sign, exponent or grouping: «,» and «٬» are
  /// refused (a thousands mark and a decimal comma cannot be told apart). Null when the text
  /// is not such a number.
  static Dec? parse(String text) {
    final ascii = asciiDigits(text.trim());
    final m = _plain.firstMatch(ascii);
    if (m == null) return null;
    final whole = m.group(1)!;
    final fraction = m.group(2) ?? '';
    if (whole.isEmpty && fraction.isEmpty) return null;
    return _of(whole, fraction);
  }

  /// A decimal the server sent (`"0.10"`, `2380.5`, `"1E-7"`); null when it is not one or is
  /// negative.
  static Dec? fromServer(Object? value) {
    if (value == null || value is bool) return null;
    final text = '$value'.trim();
    final m = _server.firstMatch(text);
    if (m == null || m.group(1) == '-') return null;
    var whole = m.group(2)!;
    var fraction = m.group(3) ?? '';
    if (whole.isEmpty && fraction.isEmpty) return null;
    final exponent = int.tryParse(m.group(4) ?? '0') ?? 0;
    if (exponent.abs() > 40) return null;
    if (exponent > 0) {
      final moved = fraction.padRight(exponent, '0');
      whole += moved.substring(0, exponent);
      fraction = moved.substring(exponent);
    } else if (exponent < 0) {
      final padded = whole.padLeft(-exponent, '0');
      fraction = padded.substring(padded.length + exponent) + fraction;
      whole = padded.substring(0, padded.length + exponent);
    }
    return _of(whole, fraction);
  }

  static Dec _of(String whole, String fraction) => Dec._(
    BigInt.parse('${whole.isEmpty ? '0' : whole}$fraction'),
    fraction.length,
  )._trimmed();

  /// Without trailing fractional zeros (2380.50 → 2380.5).
  Dec _trimmed() {
    var u = units, s = scale;
    final ten = BigInt.from(10);
    while (s > 0 && u % ten == BigInt.zero) {
      u = u ~/ ten;
      s--;
    }
    return Dec._(u, s);
  }

  static BigInt _pow10(int n) => BigInt.from(10).pow(n);

  BigInt _at(int s) => units * _pow10(s - scale);

  bool get isZero => units == BigInt.zero;
  bool get isPositive => units > BigInt.zero;

  Dec plus(Dec other) {
    final s = scale > other.scale ? scale : other.scale;
    return Dec._(_at(s) + other._at(s), s)._trimmed();
  }

  /// `this − other`, or null when negative (no negative decimal is ever needed here).
  Dec? minus(Dec other) {
    final s = scale > other.scale ? scale : other.scale;
    final d = _at(s) - other._at(s);
    return d.isNegative ? null : Dec._(d, s)._trimmed();
  }

  /// Whether this is a whole multiple of [step] (never for a zero step).
  bool multipleOf(Dec step) {
    if (step.isZero) return false;
    final s = scale > step.scale ? scale : step.scale;
    return _at(s) % step._at(s) == BigInt.zero;
  }

  @override
  int compareTo(Dec other) {
    final s = scale > other.scale ? scale : other.scale;
    return _at(s).compareTo(other._at(s));
  }

  bool operator <(Dec other) => compareTo(other) < 0;
  bool operator >(Dec other) => compareTo(other) > 0;
  bool operator <=(Dec other) => compareTo(other) <= 0;
  bool operator >=(Dec other) => compareTo(other) >= 0;

  @override
  bool operator ==(Object other) => other is Dec && compareTo(other) == 0;

  @override
  int get hashCode => Object.hash(_trimmed().units, _trimmed().scale);

  /// The canonical string sent to the server: ASCII digits, «.» only when there is a
  /// fraction, no trailing zeros, never an exponent (`0.0000001`, `2380.5`, `1`).
  @override
  String toString() {
    final digits = units.toString();
    if (scale == 0) return digits;
    final padded = digits.padLeft(scale + 1, '0');
    final cut = padded.length - scale;
    return '${padded.substring(0, cut)}.${padded.substring(cut)}';
  }
}

/// [text] with Arabic-Indic and Eastern Arabic-Indic digits as ASCII and «٫» as «.»; every
/// other character is left as it is.
String asciiDigits(String text) {
  final out = StringBuffer();
  for (final rune in text.runes) {
    if (rune >= 0x0660 && rune <= 0x0669) {
      out.writeCharCode(0x30 + rune - 0x0660);
    } else if (rune >= 0x06F0 && rune <= 0x06F9) {
      out.writeCharCode(0x30 + rune - 0x06F0);
    } else if (rune == 0x066B) {
      out.write('.');
    } else {
      out.writeCharCode(rune);
    }
  }
  return out.toString();
}
