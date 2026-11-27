// tool/release_manifest.py --update-manifest: what it prints is what the app's own parser
// (lib/platform/updates/update_manifest.dart) accepts. The fixture was printed by the script
// from a debug APK; with a built APK and ANDROID_HOME the script also runs here.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/platform/updates/update_manifest.dart';

const apk = 'build/app/outputs/flutter-apk/app-debug.apk';
const url = 'https://releases.example.com/lonora-android-1.0.0.apk';

void expectRead(Object? json) {
  final ar = ReleaseManifest.parse(
    json,
    appPackage: 'ai.lonora.android.debug',
    lang: 'ar',
  );
  expect(ar, isNotNull);
  expect(ar!.package, 'ai.lonora.android.debug');
  expect(ar.versionName, isNotEmpty);
  expect(ar.versionCode, greaterThan(0));
  expect(ar.url, Uri.parse(url));
  expect(ar.notes, 'مكالمات أوضح وإصلاحات.');
  final en = ReleaseManifest.parse(
    json,
    appPackage: 'ai.lonora.android.debug',
    lang: 'en',
  );
  expect(en!.notes, 'Clearer calls and fixes.');
  // Another build (the release package) refuses the debug build's manifest.
  expect(ReleaseManifest.parse(json, appPackage: 'ai.lonora.android'), isNull);
}

void main() {
  test('the script\'s manifest of a debug APK is read by the app', () {
    expectRead(
      jsonDecode(
        File('test/tool/update_manifest_fixture.json').readAsStringSync(),
      ),
    );
  });

  final sdk = Platform.environment['ANDROID_HOME'];
  test(
    'a fresh run against the built APK',
    () async {
      final out = await Process.run('python3', [
        'tool/release_manifest.py',
        apk,
        '--update-manifest',
        url,
        '--notes-ar',
        'مكالمات أوضح وإصلاحات.',
        '--notes-en',
        'Clearer calls and fixes.',
      ], stdoutEncoding: utf8);
      expect(out.exitCode, 0, reason: '${out.stderr}');
      expectRead(jsonDecode(out.stdout as String));
    },
    skip: sdk == null || !File(apk).existsSync()
        ? 'needs a built debug APK and ANDROID_HOME'
        : false,
  );
}
