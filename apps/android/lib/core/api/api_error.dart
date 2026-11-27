import '../json.dart';

/// An error answered by the Lonora API (`{code, request_id}` envelope) or a transport failure.
///
/// [status] is null when no HTTP answer arrived at all (offline, DNS, TLS, timeout): that is
/// what the outbox treats as "the API never saw it".
class ApiError implements Exception {
  ApiError({
    required this.status,
    required this.code,
    this.requestId,
    this.retryAfter,
    this.fields = const [],
    this.body,
  });

  final int? status;
  final String code;
  final String? requestId;
  final Duration? retryAfter;
  final List<Json> fields;
  final Json? body;

  bool get isNetwork => status == null;
  bool get isUnauthorized => status == 401;
  bool get isConflict => status == 409;
  bool get isNotFound => status == 404;

  /// Whether the Lonora API itself answered (see apps/mobile/lib/outgoing-messages.ts
  /// `serverAnswered`): no response, or a proxy's bare 502/504 without a Lonora code, means
  /// the API never saw the request.
  bool get serverAnswered =>
      status != null &&
      !((status == 502 || status == 504) && code == 'request_failed');

  factory ApiError.fromResponse(
    int status,
    Object? data, {
    String? retryAfterHeader,
  }) {
    final json = asJson(data);
    final code =
        asString(json['code']) ??
        (json['error'] == 'maintenance'
            ? 'maintenance'
            : _fallbackCode(status));
    final retrySeconds =
        asInt(json['retry_after_seconds']) ??
        int.tryParse(retryAfterHeader ?? '');
    return ApiError(
      status: status,
      code: code,
      requestId: asString(json['request_id']),
      retryAfter: retrySeconds == null ? null : Duration(seconds: retrySeconds),
      fields: asJsonList(json['fields']),
      body: json.isEmpty ? null : json,
    );
  }

  factory ApiError.network([String code = 'network']) =>
      ApiError(status: null, code: code);

  static String _fallbackCode(int status) => switch (status) {
    401 => 'unauthorized',
    404 => 'endpoint_not_found',
    413 => 'request_body_too_large',
    429 => 'rate_limited',
    _ => 'request_failed',
  };

  @override
  String toString() =>
      'ApiError($status, $code${requestId == null ? '' : ', $requestId'})';
}

/// Thrown for requests the session itself cancelled (sign-out, server change). Never shown.
class SessionRequestCancelled implements Exception {
  const SessionRequestCancelled();
  @override
  String toString() => 'SessionRequestCancelled';
}
