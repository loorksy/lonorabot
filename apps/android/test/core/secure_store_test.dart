// The stored session: an unreadable entry is repaired (deleted) by the app's read, never by
// the background check's, which passes the failure on (it is not "no session").
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/platform/background/background_sync.dart';

const _channel = MethodChannel('plugins.it_nomads.com/flutter_secure_storage');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<String> deleted;
  late Object? Function() stored;

  setUp(() {
    deleted = [];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_channel, (call) async {
          final key = (call.arguments as Map)['key'];
          switch (call.method) {
            case 'read':
              return stored();
            case 'delete':
              deleted.add('$key');
          }
          return null;
        });
  });

  group('an unreadable entry (a Keystore failure)', () {
    setUp(() => stored = () => throw PlatformException(code: 'keystore'));

    test('the app reads none and deletes it', () async {
      expect(await SecureStore().readSession(), isNull);
      expect(deleted, ['lonora.session']);
    });

    test('readSessionNoRepair passes the failure on and keeps it', () async {
      await expectLater(
        SecureStore().readSessionNoRepair(),
        throwsA(isA<PlatformException>()),
      );
      expect(deleted, isEmpty);
    });

    test('the background check keeps it', () async {
      await expectLater(
        BackgroundCheckDeps.device().readSession(),
        throwsA(isA<PlatformException>()),
      );
      expect(deleted, isEmpty);
    });
  });

  test('both reads return a stored session', () async {
    stored = () => jsonEncode({
      'server': 'https://lonora.example.com',
      'token': 'opaque',
      'owner_id': 'owner-1',
      'email': 'owner@example.com',
    });
    expect((await SecureStore().readSession())?.ownerId, 'owner-1');
    expect((await SecureStore().readSessionNoRepair())?.ownerId, 'owner-1');
    expect(deleted, isEmpty);
  });
}
