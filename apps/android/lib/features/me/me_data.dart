// Screen-local reads and writes of the owner's own records (Me tab, account and notification
// pages). Nothing else in the app needs them, so they are plain calls on `api`, not store state.
import 'package:flutter/foundation.dart';

import '../../app/services.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';

/// A device registered with the owner's passkey (`GET /owner/profile` → `devices`).
@immutable
class PasskeyDevice {
  const PasskeyDevice({required this.id, required this.name});
  final String id;
  final String name;
}

/// The parts of `GET /owner/profile` the Android settings read (lonora-api-contract §9):
/// name, form of address, reply language, the reach-me policy and the passkey devices.
@immutable
class OwnerProfileData {
  const OwnerProfileData({
    this.name,
    this.address,
    this.replyLanguage,
    this.reachMe = const {},
    this.devices = const [],
  });

  factory OwnerProfileData.fromJson(Json j) => OwnerProfileData(
    name: _text(j['name']),
    address: _text(j['address']),
    replyLanguage: _text(j['reply_language']),
    reachMe: asJson(j['reach_me']),
    devices: [
      for (final d in asJsonList(j['devices']))
        if (asString(d['id']) != null)
          PasskeyDevice(id: asStr(d['id']), name: asStr(d['name'])),
    ],
  );

  final String? name;
  final String? address;

  /// A BCP-47 tag; null follows the owner's latest message («تلقائي»).
  final String? replyLanguage;

  /// `IncomingCallPolicy` as the server sent it.
  final Json reachMe;
  final List<PasskeyDevice> devices;

  String get channel => asStr(reachMe['channel'], 'message');
  String? get deviceId => asString(reachMe['device_id']);
  int? get quietStartMinute => asInt(reachMe['quiet_start_minute']);
  int? get quietEndMinute => asInt(reachMe['quiet_end_minute']);
  bool get quiet => quietStartMinute != null && quietEndMinute != null;
  String get timeZone => asStr(reachMe['timezone'], 'UTC');

  static String? _text(Object? value) {
    final s = asString(value)?.trim();
    return s == null || s.isEmpty ? null : s;
  }
}

/// The name the Web shows for the owner (apps/web/src/shell/data.tsx `ownerDisplayName`):
/// form of address, else name, else the email's local part.
String ownerDisplayName(OwnerProfileData? profile, Owner owner) {
  final local = owner.email.split('@').first;
  return profile?.address ??
      profile?.name ??
      (local.isEmpty ? owner.email : local);
}

/// The owner's avatar letter: the name's first character, uppercased (Arabic stays as it is).
String ownerInitial(String name) {
  final it = name.runes.iterator;
  return it.moveNext() ? String.fromCharCode(it.current).toUpperCase() : '';
}

Future<OwnerProfileData> fetchOwnerProfile() async =>
    OwnerProfileData.fromJson(asJson(await api.get('/owner/profile')));

/// `PUT /owner/preferences`: only the fields sent change (routes/memory.py
/// `OwnerPreferencesUpdate`). Answers the whole profile.
Future<OwnerProfileData> saveOwnerPreferences(Json body) async =>
    OwnerProfileData.fromJson(
      asJson(await api.put('/owner/preferences', body)),
    );

/// The reach-me policy with [patch] applied, ready to send. The derived `enabled` flag is
/// never sent: the channel alone decides it (apps/mobile/lib/incoming-call.ts `reachMePayload`,
/// apps/web NotifyPages.tsx `save`).
Json reachMeWith(Json current, Json patch) =>
    {...current, ...patch}..remove('enabled');

/// `GET /usage/summary` (lonora-api-contract §13).
@immutable
class UsageSummary {
  const UsageSummary({
    required this.input,
    required this.output,
    required this.cached,
  });

  factory UsageSummary.fromJson(Json j) => UsageSummary(
    input: asInt(j['input_tokens']) ?? 0,
    output: asInt(j['output_tokens']) ?? 0,
    cached: asInt(j['cached_tokens']) ?? 0,
  );

  final int input;
  final int output;
  final int cached;
}

Future<UsageSummary> fetchUsageSummary() async =>
    UsageSummary.fromJson(asJson(await api.get('/usage/summary')));
