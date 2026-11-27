import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:path_provider/path_provider.dart';

/// Small JSON documents on this phone (cached snapshots, outbox, drafts), namespaced by
/// server + owner so two accounts never see each other's data. Writes are serialised per
/// key and atomic (write to temp, rename). The server stays the system of record: a cache is
/// only shown until the first fresh snapshot arrives.
class LocalStore {
  LocalStore._(this._root);

  static Future<LocalStore> open() async {
    final dir = await getApplicationSupportDirectory();
    final root = Directory('${dir.path}/lonora');
    await root.create(recursive: true);
    return LocalStore._(root);
  }

  /// For tests.
  static LocalStore at(Directory root) => LocalStore._(root);

  final Directory _root;
  final Map<String, Future<void>> _writes = {};

  static String scope(String server, String ownerId) => sha256
      .convert(utf8.encode('$server\u0000$ownerId'))
      .toString()
      .substring(0, 24);

  File _file(String scope, String name) {
    final safe = name.replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');
    return File('${_root.path}/$scope/$safe.json');
  }

  Future<Object?> read(String scope, String name) async {
    final file = _file(scope, name);
    try {
      if (!await file.exists()) return null;
      return jsonDecode(await file.readAsString());
    } catch (_) {
      return null;
    }
  }

  Future<void> write(String scope, String name, Object? value) {
    final key = '$scope/$name';
    final previous = _writes[key] ?? Future<void>.value();
    final next = previous.catchError((_) {}).then((_) async {
      final file = _file(scope, name);
      await file.parent.create(recursive: true);
      if (value == null) {
        if (await file.exists()) await file.delete();
        return;
      }
      final tmp = File('${file.path}.tmp');
      await tmp.writeAsString(jsonEncode(value), flush: true);
      await tmp.rename(file.path);
    });
    _writes[key] = next;
    return next;
  }

  Future<void> clearScope(String scope) async {
    final dir = Directory('${_root.path}/$scope');
    if (await dir.exists()) await dir.delete(recursive: true);
  }
}
