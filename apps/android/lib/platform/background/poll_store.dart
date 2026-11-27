// Where the background check keeps its cursor: one small JSON file in the app's private
// support directory, shared by the app isolate (which writes the baseline while the owner is
// in the app) and the WorkManager isolate. It holds ids, sequence numbers, names and rules,
// never a token (the token stays in secure storage).
import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'poll_logic.dart';

abstract class PollStore {
  Future<PollState?> read();
  Future<void> write(PollState state);
  Future<void> clear();
}

class FilePollStore implements PollStore {
  FilePollStore([this._directory]);

  final Directory? _directory;
  static const fileName = 'lonora_background_check.json';

  Future<File> _file() async {
    final dir = _directory ?? await getApplicationSupportDirectory();
    return File('${dir.path}/$fileName');
  }

  @override
  Future<PollState?> read() async {
    try {
      final file = await _file();
      if (!await file.exists()) return null;
      return PollState.fromJson(jsonDecode(await file.readAsString()));
    } catch (_) {
      return null;
    }
  }

  /// Written beside and renamed over the old file, so a reader never sees half a file.
  @override
  Future<void> write(PollState state) async {
    try {
      final file = await _file();
      final temp = File('${file.path}.${pid}_${identityHashCode(state)}.tmp');
      await temp.writeAsString(jsonEncode(state.toJson()), flush: true);
      await temp.rename(file.path);
    } catch (_) {}
  }

  @override
  Future<void> clear() async {
    try {
      final file = await _file();
      if (await file.exists()) await file.delete();
    } catch (_) {}
  }
}

class MemoryPollStore implements PollStore {
  PollState? state;

  @override
  Future<PollState?> read() async => state;
  @override
  Future<void> write(PollState value) async => state = value;
  @override
  Future<void> clear() async => state = null;
}
