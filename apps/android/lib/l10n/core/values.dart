/// Reading the server's JSON the way the TS ports do (JS truthiness and `String(value)`).
library;

/// A JSON object, or an empty one for anything else (the TS `record()` / optional chaining).
Map<String, Object?> obj(Object? value) =>
    value is Map ? value.cast<String, Object?>() : const <String, Object?>{};

/// A string field, or null when it is missing or not a string.
String? str(Object? value) => value is String ? value : null;

/// A list field, or an empty list.
List<Object?> list(Object? value) => value is List ? value : const [];

/// The strings of a list field.
List<String> strings(Object? value) => list(value).whereType<String>().toList();

/// JavaScript truthiness: null, false, 0, NaN and '' are false.
bool truthy(Object? value) {
  if (value == null || value == false) return false;
  if (value is num) return value != 0 && !value.isNaN;
  if (value is String) return value.isNotEmpty;
  return true;
}

/// A number field (JSON ints and doubles), or null.
num? number(Object? value) => value is num ? value : null;

/// `String(value)` as JavaScript prints it: integral doubles without «.0», null as ''.
String jsString(Object? value) {
  if (value == null) return '';
  if (value is double) {
    if (value.isNaN) return 'NaN';
    if (value.isInfinite) return value > 0 ? 'Infinity' : '-Infinity';
    if (value == value.truncateToDouble() && value.abs() < 1e21) {
      return value.toInt().toString();
    }
  }
  return value.toString();
}

/// `Date.parse` / `new Date(iso).getTime()`: milliseconds, or NaN when it does not parse.
double parseTime(Object? value) {
  if (value is DateTime) return value.millisecondsSinceEpoch.toDouble();
  final date = value is String ? DateTime.tryParse(value) : null;
  return date == null ? double.nan : date.millisecondsSinceEpoch.toDouble();
}

/// `new Date(value)` as a local date, or null when it is not a valid date.
DateTime? parseDate(Object? value) {
  if (value is DateTime) return value.toLocal();
  final date = value is String ? DateTime.tryParse(value) : null;
  return date?.toLocal();
}
