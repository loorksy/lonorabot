// Screen-local reads of the core settings pages (lonora-api-contract §13, §17.1, §3.1).
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../../app/services.dart';
import '../../core/json.dart';
import '../../state/actions/prefs_actions.dart' show platformChannel;

/// `GET/PUT /attention/policy`: what raises an alert. `locale` also picks the push language.
@immutable
class AttentionPolicy {
  const AttentionPolicy({
    required this.opportunities,
    required this.informational,
    required this.locale,
  });

  factory AttentionPolicy.fromJson(Json j) => AttentionPolicy(
    opportunities: asBool(j['opportunities'], true),
    informational: asBool(j['informational']),
    locale: asStr(j['locale'], 'ar'),
  );

  final bool opportunities;
  final bool informational;
  final String locale;

  Json toJson() => {
    'opportunities': opportunities,
    'informational': informational,
    'locale': locale,
  };
}

Future<AttentionPolicy> fetchAttentionPolicy() async =>
    AttentionPolicy.fromJson(asJson(await api.get('/attention/policy')));

Future<AttentionPolicy> saveAttentionPolicy(AttentionPolicy policy) async =>
    AttentionPolicy.fromJson(
      asJson(await api.put('/attention/policy', policy.toJson())),
    );

/// `GET /agents/notifications`: each agent's delivery rules by agent id (`in_app`, `calls`,
/// `daily_limit`); an agent without saved rules is absent and alerts.
Future<Json> fetchAgentAlertRules() async =>
    asJson(await api.get('/agents/notifications'));

/// `GET /voice/status`: whether GPT-Live has a server-side OpenAI credential, and its model.
@immutable
class VoiceStatus {
  const VoiceStatus({required this.configured, this.model, this.transport});

  factory VoiceStatus.fromJson(Json j) => VoiceStatus(
    configured: asBool(j['transport_configured']),
    model: asString(j['model']),
    transport: asString(j['transport']),
  );

  final bool configured;
  final String? model;
  final String? transport;
}

Future<VoiceStatus> fetchVoiceStatus() async =>
    VoiceStatus.fromJson(asJson(await api.get('/voice/status')));

/// `GET /version`: the server's version and web build id.
@immutable
class ServerVersion {
  const ServerVersion({required this.version, this.build});

  factory ServerVersion.fromJson(Json j) =>
      ServerVersion(version: asStr(j['version']), build: asString(j['build']));

  final String version;
  final String? build;

  /// «0.2.0» or «0.2.0 · 1a2b3c4» (the Web shows the first 7 characters of the build).
  String get label {
    final b = build;
    if (b == null || b.isEmpty) return version;
    return '$version · ${b.length > 7 ? b.substring(0, 7) : b}';
  }
}

Future<ServerVersion> fetchServerVersion() async =>
    ServerVersion.fromJson(asJson(await api.get('/version')));

/// The phone's IANA time zone, for quiet hours. Asks the platform channel's `timeZone` method;
/// null when the host does not answer it (then the policy's stored zone is kept).
Future<String?> deviceTimeZone() async {
  try {
    final zone = await platformChannel.invokeMethod<String>('timeZone');
    return zone == null || zone.isEmpty ? null : zone;
  } on PlatformException {
    return null;
  } on MissingPluginException {
    return null;
  }
}
