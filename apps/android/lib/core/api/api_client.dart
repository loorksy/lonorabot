import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';

import 'api_error.dart';

/// Normalises a server address the way the Expo client does (apps/mobile/lib/api.ts:100-109):
/// http/https only, no credentials, query or fragment, trailing `/api` and `/` removed.
/// Returns null when the address is not usable.
String? normalizeServerUrl(String input) {
  var text = input.trim();
  if (text.isEmpty) return null;
  if (!text.contains('://')) text = 'https://$text';
  final uri = Uri.tryParse(text);
  if (uri == null ||
      !(uri.isScheme('http') || uri.isScheme('https')) ||
      uri.host.isEmpty) {
    return null;
  }
  if (uri.userInfo.isNotEmpty || uri.hasQuery || uri.hasFragment) return null;
  var path = uri.path;
  while (path.endsWith('/')) {
    path = path.substring(0, path.length - 1);
  }
  if (path.endsWith('/api')) path = path.substring(0, path.length - 4);
  while (path.endsWith('/')) {
    path = path.substring(0, path.length - 1);
  }
  return uri.replace(path: path).toString().replaceFirst(RegExp(r'\?$'), '');
}

/// Hosts where plain http is acceptable (connect-link rule, apps/mobile/lib/connect-link.ts).
bool isLocalHost(String host) {
  final h = host.toLowerCase();
  if (h == 'localhost' || h.endsWith('.local') || h == '[::1]' || h == '::1') {
    return true;
  }
  final parts = h.split('.').map(int.tryParse).toList();
  if (parts.length != 4 || parts.any((p) => p == null)) return false;
  final a = parts[0]!, b = parts[1]!;
  return a == 10 ||
      a == 127 ||
      (a == 172 && b >= 16 && b <= 31) ||
      (a == 192 && b == 168);
}

/// Whether the app may talk to [server]: https, or plain http only to a local address
/// ([isLocalHost], Expo's connect-link rule). Flutter's dart:io ignores
/// network_security_config.xml, so Dart enforces it.
bool serverAllowed(String server) {
  final uri = Uri.tryParse(server);
  if (uri == null) return false;
  return uri.isScheme('https') ||
      (uri.isScheme('http') && isLocalHost(uri.host));
}

/// The phone's refusal of a server that breaks [serverAllowed]. Status 0: refused before any
/// request, as Expo's `ApiError(code, 0)`.
ApiError httpsRequired() => ApiError(status: 0, code: 'auth_httpsRequired');

typedef UnauthorizedHandler = void Function();

/// The single HTTP client of the app. Every request carries the owner's bearer token and is
/// fenced by a session generation: signing out or changing server cancels everything in
/// flight, and late answers of an older generation are dropped as [SessionRequestCancelled].
class ApiClient {
  ApiClient({required String userAgent, this.onUnauthorized})
    : _dio = Dio(
        BaseOptions(
          connectTimeout: const Duration(seconds: 15),
          sendTimeout: const Duration(seconds: 30),
          receiveTimeout: const Duration(seconds: 30),
          responseType: ResponseType.json,
          validateStatus: (_) => true,
          headers: {
            HttpHeaders.userAgentHeader: userAgent,
            HttpHeaders.acceptHeader: 'application/json',
          },
        ),
      );

  final Dio _dio;
  UnauthorizedHandler? onUnauthorized;

  String? _server;
  String? _token;
  int _generation = 0;
  CancelToken _cancel = CancelToken();

  String? get server => _server;
  String? get token => _token;
  bool get hasSession => _server != null && _token != null;
  int get generation => _generation;

  /// Absolute URL of an API path (for WebSocket and media loaders). Every session request
  /// passes here, so a remote plain-http server is refused ([serverAllowed]).
  Uri resolve(String path, [Map<String, Object?>? query]) {
    final base = _server;
    if (base == null) throw ApiError.network('server_missing');
    if (!serverAllowed(base)) throw httpsRequired();
    final uri = Uri.parse('$base/api$path');
    if (query == null || query.isEmpty) return uri;
    return uri.replace(
      queryParameters: {
        for (final e in query.entries)
          if (e.value != null) e.key: '${e.value}',
      },
    );
  }

  Map<String, String> get authHeaders => {
    if (_token != null) HttpHeaders.authorizationHeader: 'Bearer $_token',
  };

  /// Switches server and/or token. Any change cancels in-flight requests of the old session.
  void configure({String? server, String? token}) {
    if (server == _server && token == _token) return;
    _server = server;
    _token = token;
    _bump();
  }

  void _bump() {
    _generation++;
    _cancel.cancel('session_changed');
    _cancel = CancelToken();
  }

  Future<dynamic> get(
    String path, {
    Map<String, Object?>? query,
    Duration? timeout,
  }) => _send('GET', path, query: query, timeout: timeout);
  Future<dynamic> post(String path, [Object? body]) =>
      _send('POST', path, body: body ?? const <String, Object?>{});
  Future<dynamic> put(String path, [Object? body]) =>
      _send('PUT', path, body: body ?? const <String, Object?>{});
  Future<dynamic> patch(String path, [Object? body]) =>
      _send('PATCH', path, body: body ?? const <String, Object?>{});
  Future<dynamic> delete(String path, {Map<String, Object?>? query}) =>
      _send('DELETE', path, query: query);

  /// Unauthenticated probe of another server (sign-in screen): `GET {server}/api/onboarding`.
  Future<dynamic> probe(
    String server,
    String path, {
    Object? body,
    String method = 'GET',
  }) async {
    if (!serverAllowed(server)) throw httpsRequired();
    try {
      final response = await _dio.request<dynamic>(
        '$server/api$path',
        data: body,
        options: Options(
          method: method,
          receiveTimeout: const Duration(seconds: 11),
          sendTimeout: const Duration(seconds: 11),
        ),
      );
      return _decode(response, path, authenticated: false);
    } on DioException catch (e) {
      throw _mapDio(e);
    }
  }

  Future<dynamic> _send(
    String method,
    String path, {
    Map<String, Object?>? query,
    Object? body,
    Duration? timeout,
  }) async {
    final generation = _generation;
    final cancel = _cancel;
    final uri = resolve(path, query);
    try {
      final response = await _dio.requestUri<dynamic>(
        uri,
        data: body,
        cancelToken: cancel,
        options: Options(
          method: method,
          headers: authHeaders,
          receiveTimeout: timeout,
        ),
      );
      if (generation != _generation) throw const SessionRequestCancelled();
      return _decode(response, path);
    } on DioException catch (e) {
      if (CancelToken.isCancel(e) || generation != _generation) {
        throw const SessionRequestCancelled();
      }
      throw _mapDio(e);
    }
  }

  dynamic _decode(
    Response<dynamic> response,
    String path, {
    bool authenticated = true,
  }) {
    final status = response.statusCode ?? 0;
    if (status >= 200 && status < 300) return response.data;
    final error = ApiError.fromResponse(
      status,
      response.data,
      retryAfterHeader: response.headers.value('retry-after'),
    );
    if (authenticated && status == 401 && !path.startsWith('/auth/')) {
      onUnauthorized?.call();
    }
    throw error;
  }

  ApiError _mapDio(DioException e) {
    final response = e.response;
    if (response != null && response.statusCode != null) {
      return ApiError.fromResponse(response.statusCode!, response.data);
    }
    return ApiError.network(switch (e.type) {
      DioExceptionType.connectionTimeout ||
      DioExceptionType.receiveTimeout ||
      DioExceptionType.sendTimeout => 'timeout',
      DioExceptionType.badCertificate => 'tls_failed',
      _ => 'network',
    });
  }

  /// Multipart upload to `/artifacts/upload` (or another upload route) with progress and cancel.
  Future<dynamic> upload(
    String path, {
    required String filePath,
    required String fileName,
    String? mimeType,
    Map<String, String> fields = const {},
    void Function(int sent, int total)? onProgress,
    CancelToken? cancelToken,
  }) async {
    final generation = _generation;
    final form = FormData.fromMap({
      ...fields,
      'file': await MultipartFile.fromFile(
        filePath,
        filename: fileName,
        contentType: mimeType == null ? null : DioMediaType.parse(mimeType),
      ),
    });
    final sessionCancel = _cancel;
    final token = cancelToken ?? CancelToken();
    final sub = sessionCancel.whenCancel.then(
      (_) => token.cancel('session_changed'),
    );
    try {
      final response = await _dio.requestUri<dynamic>(
        resolve(path),
        data: form,
        cancelToken: token,
        onSendProgress: onProgress,
        options: Options(
          method: 'POST',
          headers: authHeaders,
          sendTimeout: const Duration(minutes: 5),
          receiveTimeout: const Duration(minutes: 2),
        ),
      );
      if (generation != _generation) throw const SessionRequestCancelled();
      return _decode(response, path);
    } on DioException catch (e) {
      if (generation != _generation) throw const SessionRequestCancelled();
      if (CancelToken.isCancel(e)) {
        throw ApiError(status: null, code: 'upload_cancelled');
      }
      throw _mapDio(e);
    } finally {
      unawaited(sub);
    }
  }

  /// Authenticated bytes (artifact files, inline images). Optional on-disk target.
  Future<Uint8List> bytes(
    String path, {
    Map<String, Object?>? query,
    void Function(int, int)? onProgress,
  }) async {
    final generation = _generation;
    try {
      final response = await _dio.requestUri<List<int>>(
        resolve(path, query),
        cancelToken: _cancel,
        onReceiveProgress: onProgress,
        options: Options(
          method: 'GET',
          headers: authHeaders,
          responseType: ResponseType.bytes,
          receiveTimeout: const Duration(minutes: 3),
        ),
      );
      if (generation != _generation) throw const SessionRequestCancelled();
      final status = response.statusCode ?? 0;
      if (status < 200 || status >= 300) {
        throw ApiError.fromResponse(status, null);
      }
      final data = response.data ?? const <int>[];
      return data is Uint8List ? data : Uint8List.fromList(data);
    } on DioException catch (e) {
      if (CancelToken.isCancel(e) || generation != _generation) {
        throw const SessionRequestCancelled();
      }
      throw _mapDio(e);
    }
  }

  Future<void> downloadTo(
    String path,
    String savePath, {
    Map<String, Object?>? query,
    void Function(int, int)? onProgress,
  }) async {
    final generation = _generation;
    try {
      final response = await _dio.downloadUri(
        resolve(path, query),
        savePath,
        cancelToken: _cancel,
        onReceiveProgress: onProgress,
        options: Options(
          headers: authHeaders,
          receiveTimeout: const Duration(minutes: 5),
        ),
      );
      if (generation != _generation) throw const SessionRequestCancelled();
      final status = response.statusCode ?? 0;
      if (status < 200 || status >= 300) {
        throw ApiError.fromResponse(status, null);
      }
    } on DioException catch (e) {
      if (CancelToken.isCancel(e) || generation != _generation) {
        throw const SessionRequestCancelled();
      }
      throw _mapDio(e);
    }
  }
}
