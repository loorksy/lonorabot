// Lonora for Android's own release manifest (sideloaded installs): parsing, safety checks and
// version comparison. Pure, unit-tested.
//
// The manifest URL is a build-time `--dart-define=LONORA_UPDATE_MANIFEST=https://…`; without it
// sideloaded builds never look for updates. Expected JSON:
//
//   {"package": "ai.lonora.android", "version_name": "1.2.0", "version_code": 12,
//    "url": "https://…/lonora-android-1.2.0.apk", "notes": {"ar": "…", "en": "…"}}
//
// The Expo companion's `/download/lonora.apk` is a different app (`ai.lonora.mobile`): a
// manifest that points there, or names another package, is refused.
import '../../core/json.dart';

/// Numeric parts of a version name: `1.10.2-beta+7` → [1, 10, 2].
List<int> versionParts(String name) {
  final core = name.trim().split(RegExp(r'[+\-\s]')).first;
  return [
    for (final part in core.split('.'))
      int.tryParse(RegExp(r'^\d+').stringMatch(part) ?? '') ?? 0,
  ];
}

/// Compares two version names part by part (missing parts are 0): <0, 0 or >0.
int compareVersionNames(String a, String b) {
  final x = versionParts(a), y = versionParts(b);
  final n = x.length > y.length ? x.length : y.length;
  for (var i = 0; i < n; i++) {
    final d = (i < x.length ? x[i] : 0) - (i < y.length ? y[i] : 0);
    if (d != 0) return d;
  }
  return 0;
}

/// Whether [candidate] is newer than the running build: by version code when both have one,
/// else by version name.
bool isNewerVersion({
  required String candidateName,
  required int candidateCode,
  required String currentName,
  required int currentCode,
}) {
  if (candidateCode > 0 && currentCode > 0 && candidateCode != currentCode) {
    return candidateCode > currentCode;
  }
  return compareVersionNames(candidateName, currentName) > 0;
}

/// The Expo companion app; its APK must never be offered as this app's update.
const expoCompanionPackage = 'ai.lonora.mobile';

class ReleaseManifest {
  const ReleaseManifest({
    required this.versionName,
    required this.versionCode,
    required this.url,
    this.notes,
    this.package,
  });

  final String versionName;
  final int versionCode;
  final Uri url;
  final String? notes;
  final String? package;

  /// Null when the manifest is unusable or unsafe for [appPackage]; [lang] picks the notes.
  static ReleaseManifest? parse(
    Object? value, {
    required String appPackage,
    String lang = 'ar',
  }) {
    final j = asJson(value);
    if (j.isEmpty) return null;
    final package = asString(j['package']) ?? asString(j['application_id']);
    if (package != null && package != appPackage) return null;
    final name =
        asString(j['version_name']) ??
        asString(j['versionName']) ??
        asString(j['version']) ??
        '';
    final code =
        asInt(j['version_code']) ??
        asInt(j['versionCode']) ??
        asInt(j['build']) ??
        0;
    if (name.isEmpty && code <= 0) return null;
    final raw =
        asString(j['url']) ??
        asString(j['download_url']) ??
        asString(j['apk']) ??
        '';
    final url = Uri.tryParse(raw.trim());
    if (url == null || !url.isScheme('https') || url.host.isEmpty) return null;
    if (url.userInfo.isNotEmpty) return null;
    final path = url.path.toLowerCase();
    if (path.endsWith('/download/lonora.apk') ||
        path.contains(expoCompanionPackage)) {
      return null;
    }
    final notesValue = j['notes'] ?? j['release_notes'];
    final notes = notesValue is String
        ? notesValue
        : asString(asJson(notesValue)[lang]) ??
              asString(asJson(notesValue)['en']);
    return ReleaseManifest(
      versionName: name,
      versionCode: code,
      url: url,
      notes: notes == null || notes.trim().isEmpty ? null : notes.trim(),
      package: package,
    );
  }
}

/// How this build was installed, from the installer package name.
String distributionChannel(String? installer) {
  if (installer == 'com.android.vending' ||
      installer == 'com.google.android.feedback') {
    return 'play';
  }
  const direct = {
    'com.google.android.packageinstaller',
    'com.android.packageinstaller',
    'com.android.shell',
    'com.samsung.android.packageinstaller',
  };
  if (installer == null || installer.isEmpty || direct.contains(installer)) {
    return 'direct';
  }
  // Another store keeps it up to date; Lonora offers nothing of its own.
  return 'unknown';
}
