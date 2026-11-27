// Update discovery and installation. Installed from Google Play → Play's in-app update
// (flexible flow: the owner confirms in Play's dialog, Play downloads in the background, and
// once it is downloaded the app asks for the restart that installs it — never by itself).
// Sideloaded → Lonora for Android's own release manifest (`--dart-define=
// LONORA_UPDATE_MANIFEST`, absent = off), compared with this build; «Download» opens the APK
// link in the browser and the owner installs it. Nothing is ever installed silently. The Expo
// companion's `/download/lonora.apk` (ai.lonora.mobile) is never offered (update_manifest.dart).
import 'dart:async';
import 'dart:convert' show jsonDecode;
import 'dart:io' show Platform;

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:in_app_update/in_app_update.dart';

import '../../app/services.dart';
import '../platform_bridge.dart';
import 'update_manifest.dart';

class UpdateInfo {
  const UpdateInfo({
    required this.versionName,
    required this.versionCode,
    this.notes,
    this.downloadUrl,
    this.viaStore = false,
    this.downloaded = false,
  });
  final String versionName;
  final int versionCode;
  final String? notes;
  final Uri? downloadUrl;
  final bool viaStore;

  /// Play already downloaded it (an earlier session): installing is the restart.
  final bool downloaded;
}

/// Google Play's side, behind an interface for tests.
abstract class PlayUpdates {
  Future<UpdateInfo?> check();

  /// Play's flexible flow: the owner confirms in Play's dialog, then Play downloads in the
  /// background. Resolves true once downloaded; false when refused or failed.
  Future<bool> download();

  /// Installs the downloaded update; Play restarts the app. Only on the owner's tap.
  Future<void> restart();
}

class _InAppUpdatePlay implements PlayUpdates {
  @override
  Future<UpdateInfo?> check() async {
    final info = await InAppUpdate.checkForUpdate();
    final downloaded = info.installStatus == InstallStatus.downloaded;
    if (!downloaded &&
        (info.updateAvailability != UpdateAvailability.updateAvailable ||
            !info.flexibleUpdateAllowed)) {
      return null;
    }
    final code = info.availableVersionCode ?? 0;
    // Play gives the version code only; the sheet then names no version.
    return UpdateInfo(
      versionName: '',
      versionCode: code,
      viaStore: true,
      downloaded: downloaded,
    );
  }

  @override
  Future<bool> download() async =>
      await InAppUpdate.startFlexibleUpdate() == AppUpdateResult.success;

  @override
  Future<void> restart() => InAppUpdate.completeFlexibleUpdate();
}

class UpdateService {
  UpdateService._();
  static final UpdateService instance = UpdateService._();

  /// The release manifest of sideloaded builds (empty = no updates for them).
  static const manifestUrl = String.fromEnvironment('LONORA_UPDATE_MANIFEST');

  /// Automatic checks run at most this often; a check the owner asks for always runs.
  static const automaticInterval = Duration(hours: 6);

  final ValueNotifier<UpdateInfo?> available = ValueNotifier(null);

  /// Play finished downloading [available]: the next step is the owner's «Restart».
  final ValueNotifier<bool> readyToRestart = ValueNotifier(false);

  String _channel = 'unknown';
  DateTime? _checkedAt;
  Future<UpdateInfo?>? _running;
  bool _failed = false;
  bool _downloading = false;

  /// How this build is distributed ("play", "direct" or "unknown").
  String get channel => _channel;

  /// The last check could not reach Play or the manifest (null then means «unknown»).
  bool get lastCheckFailed => _failed;

  /// Whether this build looks for updates at all (Google Play, or a configured manifest).
  bool get checksEnabled =>
      _channel == 'play' ||
      (_channel == 'direct' && configuredManifest.trim().isNotEmpty);

  @visibleForTesting
  Future<String?> Function() installer = PlatformBridge.installerPackage;
  @visibleForTesting
  PlayUpdates play = _InAppUpdatePlay();
  @visibleForTesting
  Future<Object?> Function(Uri url) fetchManifest = _fetch;
  @visibleForTesting
  Future<bool> Function(Uri url) openDownload = PlatformBridge.openExternal;
  @visibleForTesting
  String configuredManifest = manifestUrl;
  @visibleForTesting
  bool Function() isAndroid = () => !kIsWeb && Platform.isAndroid;
  @visibleForTesting
  ({String version, int build, String package}) Function() current = () {
    final info = appInfo;
    return (
      version: info.version,
      build: int.tryParse(info.buildNumber) ?? 0,
      package: info.packageName,
    );
  };

  /// Looks for an update; the result is also published in [available]. Null when there is
  /// none, updates are off for this build, or the check failed (nothing is shown for that).
  Future<UpdateInfo?> check({bool userInitiated = false, String lang = 'ar'}) {
    final now = DateTime.now();
    final last = _checkedAt;
    if (!userInitiated &&
        last != null &&
        now.difference(last) < automaticInterval) {
      return Future.value(available.value);
    }
    return _running ??= _check(lang).whenComplete(() => _running = null);
  }

  Future<UpdateInfo?> _check(String lang) async {
    if (!isAndroid()) return null;
    _checkedAt = DateTime.now();
    _failed = false;
    try {
      _channel = distributionChannel(await installer());
      final found = switch (_channel) {
        'play' => await play.check(),
        'direct' => await _checkManifest(lang),
        _ => null,
      };
      available.value = found;
      if (found?.downloaded ?? false) readyToRestart.value = true;
      return found;
    } catch (_) {
      _failed = true;
      return null;
    }
  }

  Future<UpdateInfo?> _checkManifest(String lang) async {
    final address = configuredManifest.trim();
    if (address.isEmpty) return null;
    final url = Uri.tryParse(address);
    if (url == null || !url.isScheme('https')) return null;
    final build = current();
    final manifest = ReleaseManifest.parse(
      await fetchManifest(url),
      appPackage: build.package,
      lang: lang,
    );
    if (manifest == null) return null;
    final newer = isNewerVersion(
      candidateName: manifest.versionName,
      candidateCode: manifest.versionCode,
      currentName: build.version,
      currentCode: build.build,
    );
    if (!newer) return null;
    return UpdateInfo(
      versionName: manifest.versionName,
      versionCode: manifest.versionCode,
      notes: manifest.notes,
      downloadUrl: manifest.url,
    );
  }

  /// Play: starts the flexible update (the owner confirms in Play's dialog; the download then
  /// runs in the background and [readyToRestart] turns true) or, once downloaded, restarts to
  /// install it. Sideloaded: opens the download link in the browser. Returns whether it
  /// started.
  Future<bool> install(UpdateInfo info) async {
    try {
      if (info.viaStore) {
        if (info.downloaded || readyToRestart.value) {
          await play.restart();
          return true;
        }
        if (!_downloading) unawaited(_download());
        return true;
      }
      final url = info.downloadUrl;
      if (url == null || !url.isScheme('https')) return false;
      return await openDownload(url);
    } catch (_) {
      return false;
    }
  }

  Future<void> _download() async {
    _downloading = true;
    try {
      if (await play.download()) readyToRestart.value = true;
    } catch (_) {
      // Refused in Play's dialog or failed there: Play shows its own reason.
    } finally {
      _downloading = false;
    }
  }

  @visibleForTesting
  void resetForTest() {
    _channel = 'unknown';
    _checkedAt = null;
    _running = null;
    _failed = false;
    _downloading = false;
    available.value = null;
    readyToRestart.value = false;
  }

  /// The manifest over a plain client: no Lonora token ever goes to the release host. dio decodes
  /// only a JSON content type; a manifest served as text/plain or octet-stream (a GitHub release
  /// asset) arrives as text and is decoded here.
  static Future<Object?> _fetch(Uri url) async {
    final dio = Dio(
      BaseOptions(
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 15),
        responseType: ResponseType.json,
      ),
    );
    try {
      final response = await dio.getUri<Object?>(url);
      final data = response.data;
      return data is String ? jsonDecode(data) : data;
    } finally {
      dio.close();
    }
  }
}
