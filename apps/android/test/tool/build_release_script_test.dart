// tool/build_release.sh without a real build: the script runs in a scratch copy of the app folder
// with a stand-in `flutter` (it records its arguments and writes a fake APK) and a stand-in
// release_manifest.py. Checked: the arguments (output folder, --build-number), the signing
// identity it requires (environment or properties file, and its keystore, outside the repository
// by their real paths), the Flutter version, the exact build command, the two files it writes
// (nothing when the APK's version is not pubspec's), and that no password is printed.
// The real build (run by hand with a throwaway key outside the repository) is in README.md.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

const secret = 'not-a-real-password-71';
const alias = 'lonora-upload';

late Directory root; // the scratch "repository"
late Directory app; // root/apps/android
late Directory work; // where the script is started from, outside the repository
late Directory keys; // work/keys
late File log;

/// Runs the copied script with [args] and only the variables in [env] (plus PATH and HOME).
Future<ProcessResult> run(
  List<String> args, {
  Map<String, String> env = const {},
}) => Process.run(
  'bash',
  ['${app.path}/tool/build_release.sh', ...args],
  workingDirectory: work.path,
  includeParentEnvironment: false,
  environment: {
    'PATH': '${root.path}/bin:${Platform.environment['PATH']}',
    'HOME': '${root.path}/home',
    'ANDROID_HOME': '${root.path}/sdk',
    'STUB_LOG': log.path,
    ...env,
  },
);

/// The identity from the environment, with a keystore outside the repository.
Map<String, String> signingEnv() => {
  'LONORA_ANDROID_KEYSTORE': '${keys.path}/upload.p12',
  'LONORA_ANDROID_KEYSTORE_PASSWORD': secret,
  'LONORA_ANDROID_KEY_ALIAS': alias,
  'LONORA_ANDROID_KEY_PASSWORD': secret,
};

List<String> flutterCalls() => log.existsSync()
    ? log
          .readAsLinesSync()
          .where((l) => l.startsWith('flutter '))
          .map((l) => l.substring('flutter '.length))
          .toList()
    : const [];

void expectRefused(ProcessResult r, String reason) {
  expect(r.exitCode, isNot(0), reason: '${r.stdout}');
  expect('${r.stderr}', contains(reason));
  expect('${r.stdout}${r.stderr}', isNot(contains(secret)));
  // Nothing was built.
  expect(flutterCalls().where((c) => !c.startsWith('--version')), isEmpty);
}

void main() {
  setUp(() {
    root = Directory.systemTemp.createTempSync('lonora_build_release');
    app = Directory('${root.path}/apps/android')..createSync(recursive: true);
    work = Directory.systemTemp.createTempSync('lonora_build_work');
    keys = Directory('${work.path}/keys')..createSync();
    log = File('${root.path}/calls.log');
    Directory('${app.path}/tool').createSync();
    File('tool/build_release.sh').copySync('${app.path}/tool/build_release.sh');
    File('${app.path}/pubspec.yaml')
        .writeAsStringSync('name: lonora\nversion: 2.3.4+5\n');
    // Stands in for the real script: the manifest for the URL it is given.
    File('${app.path}/tool/release_manifest.py').writeAsStringSync('''
import json, os, sys
args = sys.argv[1:]
if "--update-manifest" in args:
    url = args[args.index("--update-manifest") + 1]
    print(json.dumps({"package": "ai.lonora.android",
                      "version_name": os.environ.get("STUB_APK_VERSION", "2.3.4"),
                      "version_code": 42, "url": url}))
else:
    print(json.dumps({"file": os.path.basename(args[0])}))
''');
    final bin = Directory('${root.path}/bin')..createSync();
    final flutter = File('${bin.path}/flutter')
      ..writeAsStringSync(r'''#!/usr/bin/env bash
printf 'flutter %s\n' "$*" >> "$STUB_LOG"
case "$1" in
  --version) printf '{"frameworkVersion": "%s"}\n' "${STUB_FLUTTER_VERSION:-3.47.9}" ;;
  build)
    printf 'keystore %s\n' "${LONORA_ANDROID_KEYSTORE:-}" >> "$STUB_LOG"
    printf 'props %s\n' "${LONORA_ANDROID_SIGNING_PROPERTIES:-}" >> "$STUB_LOG"
    printf 'cwd %s\n' "$PWD" >> "$STUB_LOG"
    mkdir -p build/app/outputs/flutter-apk
    printf 'fake apk' > build/app/outputs/flutter-apk/app-release.apk ;;
esac
''');
    Process.runSync('chmod', ['+x', flutter.path]);
    File('${keys.path}/upload.p12').writeAsStringSync('not a keystore');
  });

  tearDown(() {
    root.deleteSync(recursive: true);
    work.deleteSync(recursive: true);
  });

  test('--help prints the usage', () async {
    final r = await run(['--help']);
    expect(r.exitCode, 0);
    expect('${r.stdout}', contains('Usage: tool/build_release.sh'));
  });

  group('arguments', () {
    test('an output folder is required, and only one', () async {
      expectRefused(
        await run([], env: signingEnv()),
        'missing the output folder',
      );
      expectRefused(
        await run(['a', 'b'], env: signingEnv()),
        'one output folder only',
      );
      expectRefused(
        await run(['--release', 'out'], env: signingEnv()),
        'unknown option: --release',
      );
    });

    test('--build-number is a versionCode: 1 to 2100000000', () async {
      for (final bad in ['0', 'abc', '-3', '1.5', '2100000001', '']) {
        expectRefused(
          await run(['--build-number', bad, 'out'], env: signingEnv()),
          '--build-number must be a whole number',
        );
      }
      expectRefused(
        await run(['out', '--build-number'], env: signingEnv()),
        '--build-number needs a value',
      );
      expect(Directory('${work.path}/out').existsSync(), isFalse);
    });
  });

  group('signing identity', () {
    test('none at all: says how to give one, builds nothing', () async {
      final r = await run(['out']);
      expectRefused(r, 'no signing identity');
      expect('${r.stderr}', contains('LONORA_ANDROID_KEYSTORE'));
      expect(Directory('${work.path}/out').existsSync(), isFalse);
    });

    test('a keystore without its password or alias', () async {
      expectRefused(
        await run([
          'out',
        ], env: {...signingEnv()}..remove('LONORA_ANDROID_KEYSTORE_PASSWORD')),
        'LONORA_ANDROID_KEYSTORE_PASSWORD is not set',
      );
      expectRefused(
        await run([
          'out',
        ], env: {...signingEnv()}..remove('LONORA_ANDROID_KEY_ALIAS')),
        'LONORA_ANDROID_KEY_ALIAS is not set',
      );
      expectRefused(
        await run(
          ['out'],
          env: {
            ...signingEnv(),
            'LONORA_ANDROID_KEYSTORE': '${keys.path}/missing.p12',
          },
        ),
        'does not name a readable file',
      );
    });

    test(
      'a keystore inside the repository is refused, however it is named',
      () async {
        final inRepo = File('${app.path}/upload.p12')
          ..writeAsStringSync('not a keystore');
        // Through "..", from where the script is started.
        final rootName = root.uri.pathSegments.where((s) => s.isNotEmpty).last;
        // Through a symlink outside the repository.
        Link('${keys.path}/link.p12').createSync(inRepo.path);
        for (final path in [
          inRepo.path,
          '../$rootName/apps/android/upload.p12',
          '${work.path}/../$rootName/apps/android/../android/upload.p12',
          'keys/link.p12',
        ]) {
          expectRefused(
            await run(
              ['out'],
              env: {...signingEnv(), 'LONORA_ANDROID_KEYSTORE': path},
            ),
            'must stay outside the repository',
          );
        }
        expect(Directory('${work.path}/out').existsSync(), isFalse);
      },
    );

    test('a properties file outside the repository whose storeFile is inside '
        'it is refused', () async {
      final inRepo = File('${app.path}/upload.p12')
        ..writeAsStringSync('not a keystore');
      Link('${keys.path}/link.p12').createSync(inRepo.path);
      final props = File('${keys.path}/signing.properties');
      for (final storeFile in [inRepo.path, 'link.p12']) {
        props.writeAsStringSync(
          'storeFile=$storeFile\nstorePassword=$secret\nkeyAlias=$alias\n',
        );
        expectRefused(
          await run(
            ['out'],
            env: {'LONORA_ANDROID_SIGNING_PROPERTIES': props.path},
          ),
          'must stay outside the repository',
        );
      }
      // The properties file itself, inside the repository.
      final repoProps = File('${app.path}/signing.properties')
        ..writeAsStringSync(
          'storeFile=${keys.path}/upload.p12\nstorePassword=$secret\n'
          'keyAlias=$alias\n',
        );
      expectRefused(
        await run(
          ['out'],
          env: {'LONORA_ANDROID_SIGNING_PROPERTIES': repoProps.path},
        ),
        'must stay outside the repository',
      );
      // A storeFile that names nothing.
      props.writeAsStringSync(
        'storeFile=missing.p12\nstorePassword=$secret\nkeyAlias=$alias\n',
      );
      expectRefused(
        await run(
          ['out'],
          env: {'LONORA_ANDROID_SIGNING_PROPERTIES': props.path},
        ),
        'does not name a readable file: ${keys.path}/missing.p12',
      );
    });

    test(
      'a properties file needs storeFile, storePassword and keyAlias',
      () async {
        final props = File('${keys.path}/signing.properties')
          ..writeAsStringSync('storeFile=upload.p12\nstorePassword=$secret\n');
        expectRefused(
          await run(
            ['out'],
            env: {'LONORA_ANDROID_SIGNING_PROPERTIES': props.path},
          ),
          'has no keyAlias',
        );
      },
    );
  });

  test('another Flutter version is refused', () async {
    expectRefused(
      await run(
        ['out'],
        env: {...signingEnv(), 'STUB_FLUTTER_VERSION': '3.44.0'},
      ),
      'Flutter 3.47.9 is needed',
    );
  });

  test('builds with the update address and writes the APK and its manifest', () async {
    // A relative keystore path, from where the script is started.
    final env = {...signingEnv(), 'LONORA_ANDROID_KEYSTORE': 'keys/upload.p12'};
    final r = await run(['--build-number', '42', 'release/out'], env: env);
    expect(r.exitCode, 0, reason: '${r.stdout}\n${r.stderr}');
    expect('${r.stdout}${r.stderr}', isNot(contains(secret)));
    expect(flutterCalls(), [
      '--version --machine',
      'pub get --enforce-lockfile',
      'build apk --release '
          '--dart-define=LONORA_UPDATE_MANIFEST=https://lonora.io/download/lonora-android.json '
          '--build-number=42',
    ]);
    final lines = log.readAsLinesSync();
    // Gradle gets an absolute keystore path; the build runs in the app folder.
    expect(
      lines,
      contains('keystore ${keys.resolveSymbolicLinksSync()}/upload.p12'),
    );
    expect(lines, contains('cwd ${app.resolveSymbolicLinksSync()}'));
    final out = Directory('${work.path}/release/out');
    expect(
      File('${out.path}/lonora-android-2.3.4.apk').readAsStringSync(),
      'fake apk',
    );
    expect(
      jsonDecode(File('${out.path}/lonora-android.json').readAsStringSync()),
      {
        'package': 'ai.lonora.android',
        'version_name': '2.3.4',
        'version_code': 42,
        'url': 'https://lonora.io/download/lonora-android-2.3.4.apk',
      },
    );
    expect(out.listSync().map((e) => e.uri.pathSegments.last).toSet(), {
      'lonora-android-2.3.4.apk',
      'lonora-android.json',
    });
  });

  test(
    'a properties file and --build-number=N; no build number is optional',
    () async {
      File('${keys.path}/signing.properties').writeAsStringSync(
        'storeFile = upload.p12\nstorePassword = $secret\nkeyAlias = $alias\n',
      );
      // A relative path, from where the script is started; Gradle gets the absolute one.
      final env = {
        'LONORA_ANDROID_SIGNING_PROPERTIES': 'keys/signing.properties',
      };
      var r = await run(['--build-number=7', 'out'], env: env);
      expect(r.exitCode, 0, reason: '${r.stderr}');
      expect(
        flutterCalls().last,
        endsWith('lonora-android.json --build-number=7'),
      );
      expect(
        log.readAsLinesSync(),
        contains(
          'props ${work.resolveSymbolicLinksSync()}/keys/signing.properties',
        ),
      );
      expect('${r.stdout}${r.stderr}', isNot(contains(secret)));
      log.deleteSync();
      r = await run(['out'], env: env);
      expect(r.exitCode, 0, reason: '${r.stderr}');
      expect(flutterCalls().last, endsWith('lonora-android.json'));
    },
  );

  test('an APK whose version is not pubspec\'s writes nothing and leaves the '
      'published APK alone', () async {
    final out = Directory('${work.path}/out')..createSync();
    final published = File('${out.path}/lonora-android-2.3.4.apk')
      ..writeAsStringSync('published apk');
    final r = await run(
      ['out'],
      env: {...signingEnv(), 'STUB_APK_VERSION': '9.9.9'},
    );
    expect(r.exitCode, isNot(0));
    expect('${r.stderr}', contains("the APK says version '9.9.9'"));
    expect(published.readAsStringSync(), 'published apk');
    // No manifest, and no partial file left behind.
    expect(out.listSync().map((e) => e.uri.pathSegments.last), [
      'lonora-android-2.3.4.apk',
    ]);
  });
}
