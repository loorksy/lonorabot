import 'dart:async';
import 'dart:convert' show jsonEncode;
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/platform/updates/update_manifest.dart';
import 'package:lonora/platform/updates/update_service.dart';

class FakePlay implements PlayUpdates {
  UpdateInfo? next;
  int downloads = 0;
  int restarts = 0;
  Completer<bool> downloaded = Completer<bool>();
  @override
  Future<UpdateInfo?> check() async => next;
  @override
  Future<bool> download() {
    downloads++;
    return downloaded.future;
  }

  @override
  Future<void> restart() async => restarts++;
}

void main() {
  // The real fetch, kept before any test swaps it for a fake.
  final fetch = UpdateService.instance.fetchManifest;

  group('manifest fetch', () {
    const manifest = {
      'package': 'ai.lonora.android',
      'version_name': '1.1.0',
      'version_code': 12,
      'url': 'https://releases.example.com/lonora-1.1.0.apk',
    };
    late HttpServer server;
    late String contentType;

    setUp(() async {
      final overrides = HttpOverrides.current;
      HttpOverrides.global =
          null; // an in-process loopback server, nothing else
      addTearDown(() => HttpOverrides.global = overrides);
      server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(() => server.close(force: true));
      server.listen((request) {
        request.response.headers.set('content-type', contentType);
        request.response
          ..write(jsonEncode(manifest))
          ..close();
      });
    });

    for (final type in [
      'application/json',
      'text/plain; charset=utf-8',
      'application/octet-stream',
    ]) {
      test('a manifest served as $type is read', () async {
        contentType = type;
        final body = await fetch(
          Uri.parse('http://127.0.0.1:${server.port}/android.json'),
        );
        expect(body, manifest);
        expect(
          ReleaseManifest.parse(
            body,
            appPackage: 'ai.lonora.android',
          )?.versionCode,
          12,
        );
      });
    }
  });

  group('version compare', () {
    test('parts and order', () {
      expect(versionParts('1.10.2-beta+7'), [1, 10, 2]);
      expect(versionParts('2'), [2]);
      expect(compareVersionNames('1.10.0', '1.9.9'), greaterThan(0));
      expect(compareVersionNames('1.0', '1.0.0'), 0);
      expect(compareVersionNames('1.0.0', '1.0.1'), lessThan(0));
    });

    test('the version code decides when both builds have one', () {
      expect(
        isNewerVersion(
          candidateName: '1.0.0',
          candidateCode: 12,
          currentName: '1.0.0',
          currentCode: 11,
        ),
        isTrue,
      );
      expect(
        isNewerVersion(
          candidateName: '9.0.0',
          candidateCode: 10,
          currentName: '1.0.0',
          currentCode: 11,
        ),
        isFalse,
      );
      expect(
        isNewerVersion(
          candidateName: '1.2.0',
          candidateCode: 0,
          currentName: '1.1.9',
          currentCode: 11,
        ),
        isTrue,
      );
      expect(
        isNewerVersion(
          candidateName: '1.0.0',
          candidateCode: 11,
          currentName: '1.0.0',
          currentCode: 11,
        ),
        isFalse,
      );
    });
  });

  group('release manifest', () {
    const pkg = 'ai.lonora.android';
    test('reads Lonora for Android releases', () {
      final m = ReleaseManifest.parse(
        {
          'package': pkg,
          'version_name': '1.2.0',
          'version_code': 12,
          'url': 'https://releases.example.com/lonora-android-1.2.0.apk',
          'notes': {'ar': 'إصلاحات', 'en': 'Fixes'},
        },
        appPackage: pkg,
        lang: 'ar',
      )!;
      expect(m.versionName, '1.2.0');
      expect(m.versionCode, 12);
      expect(m.notes, 'إصلاحات');
      expect(m.url.host, 'releases.example.com');
    });

    test("never offers the Expo companion's APK or another package", () {
      for (final bad in [
        {
          'version_name': '2.0.0',
          'url': 'https://lonora.lork.cloud/download/lonora.apk',
        },
        {
          'package': expoCompanionPackage,
          'version_name': '2.0.0',
          'url': 'https://example.com/x.apk',
        },
        {
          'version_name': '2.0.0',
          'url': 'https://example.com/ai.lonora.mobile-2.0.apk',
        },
        {'version_name': '2.0.0', 'url': 'http://example.com/x.apk'},
        {'version_name': '2.0.0', 'url': 'https://user:pw@example.com/x.apk'},
        {'url': 'https://example.com/x.apk'},
        <String, Object?>{},
      ]) {
        expect(
          ReleaseManifest.parse(bad, appPackage: pkg),
          isNull,
          reason: '$bad',
        );
      }
    });

    test('the installer decides the channel', () {
      expect(distributionChannel('com.android.vending'), 'play');
      expect(distributionChannel(null), 'direct');
      expect(
        distributionChannel('com.google.android.packageinstaller'),
        'direct',
      );
      expect(distributionChannel('com.sec.android.app.samsungapps'), 'unknown');
    });
  });

  group('UpdateService', () {
    final service = UpdateService.instance;
    late FakePlay play;
    Uri? opened;
    Uri? fetched;

    setUp(() {
      service.resetForTest();
      play = FakePlay();
      opened = null;
      fetched = null;
      service
        ..play = play
        ..isAndroid = (() => true)
        ..current = (() =>
            (version: '1.0.0', build: 11, package: 'ai.lonora.android'))
        ..openDownload = (url) async {
          opened = url;
          return true;
        }
        ..fetchManifest = (url) async {
          fetched = url;
          return {
            'package': 'ai.lonora.android',
            'version_name': '1.1.0',
            'version_code': 12,
            'url': 'https://releases.example.com/lonora-1.1.0.apk',
          };
        };
    });

    test(
      'sideloaded without a configured manifest: no update, no request',
      () async {
        service
          ..installer = (() async => null)
          ..configuredManifest = '';
        expect(await service.check(userInitiated: true), isNull);
        expect(service.channel, 'direct');
        expect(fetched, isNull);
      },
    );

    test('sideloaded with a manifest: a newer build is offered, opened in the browser', () async {
      service
        ..installer = (() async => 'com.google.android.packageinstaller')
        ..configuredManifest = 'https://releases.example.com/android.json';
      final info = await service.check(userInitiated: true);
      expect(fetched.toString(), 'https://releases.example.com/android.json');
      expect(info?.versionName, '1.1.0');
      expect(info?.viaStore, isFalse);
      expect(service.available.value, same(info));
      expect(await service.install(info!), isTrue);
      expect(
        opened.toString(),
        'https://releases.example.com/lonora-1.1.0.apk',
      );
    });

    test('an http manifest address is ignored', () async {
      service
        ..installer = (() async => null)
        ..configuredManifest = 'http://releases.example.com/android.json';
      expect(await service.check(userInitiated: true), isNull);
      expect(fetched, isNull);
    });

    test('Google Play installs use the in-app update flow', () async {
      service.installer = () async => 'com.android.vending';
      play.next = const UpdateInfo(
        versionName: '',
        versionCode: 13,
        viaStore: true,
      );
      final info = await service.check(userInitiated: true);
      expect(service.channel, 'play');
      expect(info?.viaStore, isTrue);
      // «Update» hands over to Play's dialog; the download runs in the background.
      expect(await service.install(info!), isTrue);
      expect(play.downloads, 1);
      expect(service.readyToRestart.value, isFalse);
      // A second tap while Play downloads starts nothing new.
      expect(await service.install(info), isTrue);
      expect(play.downloads, 1);
      expect(play.restarts, 0, reason: 'nothing installs by itself');
      play.downloaded.complete(true);
      await Future<void>.delayed(Duration.zero);
      expect(service.readyToRestart.value, isTrue);
      expect(play.restarts, 0);
      // Only the owner's «Restart» installs it.
      expect(await service.install(info), isTrue);
      expect(play.restarts, 1);
      expect(opened, isNull);
    });

    test('a download refused in Play leaves nothing ready', () async {
      service.installer = () async => 'com.android.vending';
      play.next = const UpdateInfo(
        versionName: '',
        versionCode: 13,
        viaStore: true,
      );
      final info = await service.check(userInitiated: true);
      await service.install(info!);
      play.downloaded.complete(false);
      await Future<void>.delayed(Duration.zero);
      expect(service.readyToRestart.value, isFalse);
      expect(play.restarts, 0);
    });

    test(
      'an update Play downloaded in an earlier session asks for the restart',
      () async {
        service.installer = () async => 'com.android.vending';
        play.next = const UpdateInfo(
          versionName: '',
          versionCode: 13,
          viaStore: true,
          downloaded: true,
        );
        final info = await service.check(userInitiated: true);
        expect(service.readyToRestart.value, isTrue);
        await service.install(info!);
        expect(play.downloads, 0);
        expect(play.restarts, 1);
      },
    );

    test('a failed check is told apart from «up to date»', () async {
      service
        ..installer = (() async => 'com.google.android.packageinstaller')
        ..configuredManifest = 'https://releases.example.com/android.json'
        ..fetchManifest = (_) async => throw Exception('offline');
      expect(await service.check(userInitiated: true), isNull);
      expect(service.lastCheckFailed, isTrue);
      expect(service.checksEnabled, isTrue);
      service.configuredManifest = '';
      expect(await service.check(userInitiated: true), isNull);
      expect(service.lastCheckFailed, isFalse);
      expect(service.checksEnabled, isFalse);
    });

    test(
      'a manifest address that answers a web page is a failed check',
      () async {
        final overrides = HttpOverrides.current;
        HttpOverrides.global =
            null; // an in-process loopback server, nothing else
        addTearDown(() => HttpOverrides.global = overrides);
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        addTearDown(() => server.close(force: true));
        server.listen((request) {
          request.response.headers.set('content-type', 'text/html');
          request.response
            ..write('<html>oops</html>')
            ..close();
        });
        final page = Uri.parse('http://127.0.0.1:${server.port}/android.json');
        await expectLater(fetch(page), throwsFormatException);
        service
          ..installer = (() async => 'com.google.android.packageinstaller')
          ..configuredManifest = 'https://releases.example.com/android.json'
          ..fetchManifest = (_) => fetch(page);
        expect(await service.check(userInitiated: true), isNull);
        expect(service.lastCheckFailed, isTrue);
        expect(service.available.value, isNull);
      },
    );

    test('automatic checks are throttled; asked ones are not', () async {
      var calls = 0;
      service
        ..installer = (() async {
          calls++;
          return null;
        })
        ..configuredManifest = '';
      await service.check();
      await service.check();
      expect(calls, 1);
      await service.check(userInitiated: true);
      expect(calls, 2);
    });
  });
}
