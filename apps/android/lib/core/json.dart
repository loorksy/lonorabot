/// Tolerant readers for server JSON. The server is the system of record; the client never
/// invents values, it only reads what is there and keeps unknown fields in `raw`.
typedef Json = Map<String, dynamic>;

Json asJson(Object? value) =>
    value is Map ? value.cast<String, dynamic>() : <String, dynamic>{};

List<Json> asJsonList(Object? value) => value is List
    ? value.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList()
    : const [];

List<String> asStringList(Object? value) => value is List
    ? value.whereType<String>().toList(growable: false)
    : const [];

String? asString(Object? value) => value is String ? value : null;

String asStr(Object? value, [String fallback = '']) =>
    value is String ? value : fallback;

int? asInt(Object? value) => switch (value) {
  final int v => v,
  final double v when v == v.roundToDouble() => v.toInt(),
  final String v => int.tryParse(v),
  _ => null,
};

double? asDouble(Object? value) => switch (value) {
  final num v => v.toDouble(),
  final String v => double.tryParse(v),
  _ => null,
};

bool asBool(Object? value, [bool fallback = false]) =>
    value is bool ? value : fallback;

DateTime? asDate(Object? value) =>
    value is String ? DateTime.tryParse(value)?.toLocal() : null;
