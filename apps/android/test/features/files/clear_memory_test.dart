// «Clear cache» drops the files' bytes kept in memory (FileBytes.clearMemory) but leaves the
// copies handed to other apps on disk (one may still be reading its copy); sign-out's
// FileBytes.clear deletes those too.
import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/features/files/files_data.dart';
import 'package:lonora/features/me/me_actions.dart';

import '../market/wpf_harness.dart';
import 'files_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;
  final record = ArtifactRecord(artifact('f-1', 'a.txt', 'text/plain', 3));
  const key = 'f-1@1';

  setUp(() async {
    await resetWpf();
    FileBytes.clearMemory();
    dir = Directory.systemTemp.createTempSync('lonora_clear_memory');
    cacheDirectory = () async => dir;
    fakeApi.files['/artifacts/f-1/file'] = Uint8List.fromList([1, 2, 3]);
  });
  tearDown(() {
    if (dir.existsSync()) dir.deleteSync(recursive: true);
  });

  int reads() => fakeApi.calls.where((c) => c.method == 'BYTES').length;

  test(
    'clearMemory drops the bytes in memory and keeps the hand-off copies',
    () async {
      final path = await cacheArtifact(
        record,
        await fetchArtifactBytes(record),
      );
      expect(FileBytes.peek(key), [1, 2, 3]);
      FileBytes.clearMemory();
      expect(FileBytes.peek(key), isNull);
      await pumpEventQueue();
      expect(File(path).existsSync(), isTrue);
      // The next draw reads the file again.
      await fetchArtifactBytes(record);
      expect(reads(), 2);
    },
  );

  test(
    'a read in flight when memory is cleared is handed back, not kept',
    () async {
      final gate = Completer<Uint8List>();
      final read = FileBytes.load('k@1', () => gate.future);
      FileBytes.clearMemory();
      gate.complete(Uint8List.fromList([9]));
      expect(await read, [9]);
      expect(FileBytes.peek('k@1'), isNull);
    },
  );

  test('sign-out\'s clear deletes the hand-off copies too', () async {
    final path = await cacheArtifact(record, await fetchArtifactBytes(record));
    FileBytes.clear();
    await pumpEventQueue();
    for (var i = 0; i < 50 && File(path).existsSync(); i++) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
    }
    expect(FileBytes.peek(key), isNull);
    expect(File(path).existsSync(), isFalse);
  });

  test(
    '«Clear cache» drops the files\' bytes in memory, not the copies',
    () async {
      final path = await cacheArtifact(
        record,
        await fetchArtifactBytes(record),
      );
      await wpfStore(locale: 'en').dispatchAndWait(ClearLocalCacheAction());
      expect(FileBytes.peek(key), isNull);
      expect(File(path).existsSync(), isTrue);
      await fetchArtifactBytes(record);
      expect(reads(), 2);
    },
  );
}
