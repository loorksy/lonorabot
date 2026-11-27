import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../json.dart';

/// The signed-in session as stored on this phone. The bearer token is opaque and expiring
/// (24 h by default); it lives only in Android Keystore-backed secure storage.
class StoredSession {
  const StoredSession({
    required this.server,
    required this.token,
    required this.ownerId,
    required this.email,
    this.expiresAt,
  });

  final String server;
  final String token;
  final String ownerId;
  final String email;
  final DateTime? expiresAt;

  Json toJson() => {
    'server': server,
    'token': token,
    'owner_id': ownerId,
    'email': email,
    'expires_at': expiresAt?.toUtc().toIso8601String(),
  };

  static StoredSession? fromJson(Json json) {
    final server = asString(json['server']);
    final token = asString(json['token']);
    final owner = asString(json['owner_id']);
    if (server == null || token == null || owner == null) return null;
    return StoredSession(
      server: server,
      token: token,
      ownerId: owner,
      email: asStr(json['email']),
      expiresAt: asDate(json['expires_at']),
    );
  }
}

class SecureStore {
  SecureStore([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _sessionKey = 'lonora.session';
  static const _serverKey = 'lonora.server';
  static const _emailKey = 'lonora.email';

  Future<StoredSession?> readSession() async {
    try {
      return await readSessionNoRepair();
    } catch (_) {
      // A corrupted or unreadable entry (e.g. after a Keystore reset) means: sign in again.
      await _storage.delete(key: _sessionKey);
      return null;
    }
  }

  /// [readSession] without the repair, for the background check: an unreadable entry throws
  /// and stays, so a passing Keystore failure neither signs the owner out nor reads as "no
  /// session" (which would stop the check).
  Future<StoredSession?> readSessionNoRepair() async {
    final raw = await _storage.read(key: _sessionKey);
    if (raw == null) return null;
    return StoredSession.fromJson(asJson(jsonDecode(raw)));
  }

  Future<void> writeSession(StoredSession session) async {
    await _storage.write(key: _sessionKey, value: jsonEncode(session.toJson()));
    await _storage.write(key: _serverKey, value: session.server);
    await _storage.write(key: _emailKey, value: session.email);
  }

  Future<void> clearSession() => _storage.delete(key: _sessionKey);

  /// The last server and e-mail are kept after sign-out so signing in again is one step.
  Future<String?> lastServer() => _storage.read(key: _serverKey);
  Future<String?> lastEmail() => _storage.read(key: _emailKey);
  Future<void> rememberServer(String server) =>
      _storage.write(key: _serverKey, value: server);
}
