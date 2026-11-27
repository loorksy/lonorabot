// The owner's files (artifacts): the library (`GET /artifacts`, newest first, internal tool
// results excluded), one record (`GET /artifacts/{id}`), its bytes through the owner session
// (`GET /artifacts/{id}/file`, never a credential in a URL), upload (`POST /artifacts/upload`),
// text edits (`PUT /artifacts/{id}/text {expected_version, name, content}`) and deletion
// (`DELETE /artifacts/{id}`), as apps/mobile lib/artifacts.ts and apps/web FilesPages.tsx do.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:async_redux/async_redux.dart' show Store;
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart' show IconData;
import 'package:forui/forui.dart' show FIcons;
import 'package:path_provider/path_provider.dart';

import '../../app/services.dart';
import '../../core/json.dart';
import '../../state/actions/session_actions.dart' show signOutHooks;
import '../../state/app_state.dart';

/// Text previews read the first MiB (apps/mobile lib/artifacts.ts `TEXT_PREVIEW_BYTES`).
const textPreviewBytes = 1024 * 1024;

/// The largest text a file may hold for an edit (apps/web FilesPages.tsx `MAX_TEXT`).
const maxTextBytes = 600000;

/// Files larger than this are opened outside the app instead of previewed.
const previewLimitBytes = 25 * 1024 * 1024;

@immutable
class ArtifactRecord {
  const ArtifactRecord(this.raw);

  final Json raw;

  String get id => asStr(raw['id']);
  String? get agentId => asString(raw['agent_id']);
  String? get threadId => asString(raw['thread_id']);
  int get version => asInt(raw['version']) ?? 0;
  Json get payload => asJson(raw['payload']);
  String get name => asString(payload['name']) ?? id;
  int get size => asInt(payload['size']) ?? 0;
  String get mediaType =>
      (asString(payload['media_type']) ?? 'application/octet-stream')
          .split(';')
          .first
          .trim()
          .toLowerCase();
  DateTime? get createdAt => asDate(raw['created_at']);
  DateTime? get updatedAt => asDate(raw['updated_at']);

  FileKind get kind => fileKindOf(mediaType, name);
}

/// How a file is previewed.
enum FileKind { image, pdf, markdown, json, csv, code, html, text, other }

const _imageTypes = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'};

String _extension(String name) {
  final dot = name.lastIndexOf('.');
  return dot < 0 || dot == name.length - 1
      ? ''
      : name.substring(dot + 1).toLowerCase();
}

/// The language a code file is highlighted in, by its extension; null when it is not code.
String? codeLanguage(String name) => switch (_extension(name)) {
  'py' => 'python',
  'js' || 'mjs' || 'cjs' => 'javascript',
  'ts' || 'tsx' => 'typescript',
  'dart' => 'dart',
  'css' => 'css',
  'xml' => 'xml',
  'yaml' || 'yml' => 'yaml',
  'sh' || 'bash' => 'bash',
  'sql' => 'sql',
  'java' => 'java',
  'kt' => 'kotlin',
  'go' => 'go',
  'rs' => 'rust',
  'c' || 'h' => 'c',
  'cpp' || 'hpp' => 'cpp',
  'rb' => 'ruby',
  'php' => 'php',
  'swift' => 'swift',
  'toml' => 'ini',
  'ini' || 'cfg' => 'ini',
  'mq5' || 'mq4' || 'mqh' => 'cpp',
  _ => null,
};

/// The preview kind of a file by its media type, then its name (the server stores text files
/// with an octet-stream or empty type as text/plain; apps/web FilesPages.tsx `TEXT_NAME`).
FileKind fileKindOf(String mediaType, String name) {
  final mt = mediaType.split(';').first.trim().toLowerCase();
  final ext = _extension(name);
  if (_imageTypes.contains(mt)) return FileKind.image;
  if (mt == 'application/pdf' || ext == 'pdf') return FileKind.pdf;
  if (mt == 'text/markdown' || ext == 'md' || ext == 'markdown') {
    return FileKind.markdown;
  }
  if (mt == 'application/json' || ext == 'json' || ext == 'ndjson') {
    return FileKind.json;
  }
  if (mt == 'text/csv' || ext == 'csv') return FileKind.csv;
  if (mt == 'text/html' || ext == 'html' || ext == 'htm') return FileKind.html;
  if (codeLanguage(name) != null) return FileKind.code;
  if (mt.startsWith('text/') ||
      const {
        'application/xml',
        'application/yaml',
        'application/x-ndjson',
      }.contains(mt) ||
      const {'txt', 'log'}.contains(ext)) {
    return FileKind.text;
  }
  return FileKind.other;
}

/// Whether the file is text the owner can edit (`PUT /artifacts/{id}/text`).
bool isTextKind(FileKind k) => const {
  FileKind.markdown,
  FileKind.json,
  FileKind.csv,
  FileKind.code,
  FileKind.html,
  FileKind.text,
}.contains(k);

/// The badge of a media type: «PDF», «PNG», «PLAIN» (apps/mobile lib/artifacts.ts `mimeBadge`).
String mimeBadge(String mediaType) {
  final value = mediaType.split(';').first.split('/').last;
  final text = value
      .replaceFirst(RegExp('^x-'), '')
      .replaceFirst(RegExp(r'\+xml$'), '');
  return (text.isEmpty ? 'FILE' : text).toUpperCase();
}

IconData fileIcon(FileKind k) => switch (k) {
  FileKind.image => FIcons.image,
  FileKind.pdf => FIcons.fileText,
  FileKind.markdown => FIcons.fileText,
  FileKind.json => FIcons.fileJson,
  FileKind.csv => FIcons.sheet,
  FileKind.code => FIcons.fileCode,
  FileKind.html => FIcons.fileCode,
  FileKind.text => FIcons.fileText,
  FileKind.other => FIcons.file,
};

/// The library's type filters.
enum FileFilter { all, images, documents, text, data, other }

bool matchesFilter(FileKind k, FileFilter f) => switch (f) {
  FileFilter.all => true,
  FileFilter.images => k == FileKind.image,
  FileFilter.documents => k == FileKind.pdf || k == FileKind.markdown,
  FileFilter.text =>
    k == FileKind.text || k == FileKind.html || k == FileKind.code,
  FileFilter.data => k == FileKind.json || k == FileKind.csv,
  FileFilter.other => k == FileKind.other,
};

/// The rows of a CSV text (RFC 4180 quotes, CRLF or LF), at most [maxRows].
List<List<String>> parseCsv(String text, {int maxRows = 500}) {
  final rows = <List<String>>[];
  var row = <String>[];
  final field = StringBuffer();
  var quoted = false;
  var i = 0;
  void endField() {
    row.add(field.toString());
    field.clear();
  }

  void endRow() {
    endField();
    if (!(row.length == 1 && row.first.isEmpty)) rows.add(row);
    row = <String>[];
  }

  while (i < text.length && rows.length < maxRows) {
    final ch = text[i];
    if (quoted) {
      if (ch == '"') {
        if (i + 1 < text.length && text[i + 1] == '"') {
          field.write('"');
          i++;
        } else {
          quoted = false;
        }
      } else {
        field.write(ch);
      }
    } else if (ch == '"') {
      quoted = true;
    } else if (ch == ',') {
      endField();
    } else if (ch == '\n') {
      endRow();
    } else if (ch != '\r') {
      field.write(ch);
    }
    i++;
  }
  if (rows.length < maxRows && (field.isNotEmpty || row.isNotEmpty)) endRow();
  return rows;
}

/// JSON re-indented by two spaces; the text unchanged when it is not valid JSON.
String prettyJson(String text) {
  try {
    return const JsonEncoder.withIndent('  ').convert(jsonDecode(text));
  } catch (_) {
    return text;
  }
}

/// The first [textPreviewBytes] decoded as UTF-8 (malformed bytes replaced), and whether the
/// file is longer.
({String text, bool truncated}) previewText(Uint8List bytes) {
  final truncated = bytes.length > textPreviewBytes;
  final head = truncated ? bytes.sublist(0, textPreviewBytes) : bytes;
  return (text: utf8.decode(head, allowMalformed: true), truncated: truncated);
}

/// A local file name without path separators (apps/mobile lib/artifacts.ts `cacheName`).
String cacheName(String value) {
  final safe = value.replaceAll(
    RegExp(r'[^\p{L}\p{N}._-]', unicode: true),
    '_',
  );
  final cut = safe.substring(0, math.min(safe.length, 120));
  return cut.isEmpty ? 'artifact' : cut;
}

/// «27/11» this year, «27/11/25» before (Latin digits, day first).
String shortDate(DateTime t, {DateTime? now}) {
  final year = (now ?? DateTime.now()).year;
  return t.year == year
      ? '${t.day}/${t.month}'
      : '${t.day}/${t.month}/${(t.year % 100).toString().padLeft(2, '0')}';
}

/// Recently drawn file bytes (thumbnails, viewer, hand-offs), newest last, about 24 MB at
/// most, for one owner on one server, as the rich messages' ArtifactBytesCache is: another
/// owner or server (read from the app store when one is registered) empties it first, one
/// read per file at a time, and [clear] (sign-out) drops it with the hand-off copies. Keyed by
/// id and version, so an edited text file is read again.
final class FileBytes {
  FileBytes._();
  static final _bytes = <String, Uint8List>{};
  static final _pending = <String, Future<Uint8List>>{};
  static int _total = 0;
  static const _limit = 24 << 20;
  static String? _scope;
  static int _generation = 0;
  static bool _hooked = false;

  static void _sync() {
    if (!_hooked) {
      // Owner-scoped memory goes with the session (session_actions `signOutHooks`).
      _hooked = true;
      signOutHooks.add(() async => clear());
    }
    if (!sl.isRegistered<Store<AppState>>()) return;
    final session = appStore.state.session;
    final scope = '${session.server}\n${session.owner?.id}';
    if (_scope == scope) return;
    if (_scope != null) clear();
    _scope = scope;
  }

  static Uint8List? peek(String key) {
    _sync();
    return _bytes[key];
  }

  /// The cached bytes of [key], else [read] once (callers asking meanwhile share it).
  static Future<Uint8List> load(String key, Future<Uint8List> Function() read) {
    _sync();
    final cached = _bytes[key];
    if (cached != null) return Future.value(cached);
    final generation = _generation;
    return _pending[key] ??= read()
        .then((data) {
          // Read for an owner the cache was cleared for: handed back, never kept.
          if (generation == _generation) _put(key, data);
          return data;
        })
        .whenComplete(() {
          if (generation == _generation) _pending.remove(key);
        });
  }

  static void _put(String key, Uint8List data) {
    final old = _bytes.remove(key);
    if (old != null) _total -= old.length;
    _bytes[key] = data;
    _total += data.length;
    while (_total > _limit && _bytes.length > 1) {
      final first = _bytes.keys.first;
      _total -= _bytes.remove(first)!.length;
    }
  }

  /// Drops every cached file and the copies handed to other apps (sign-out, server change);
  /// reads still in flight are not kept.
  static void clear() {
    clearMemory();
    unawaited(deleteHandoffCopies());
  }

  /// Drops the bytes kept in memory only («Clear cache»); the copies handed to other apps stay
  /// on disk (one may still be reading its copy). Reads still in flight are not kept.
  static void clearMemory() {
    _generation++;
    _bytes.clear();
    _pending.clear();
    _total = 0;
  }
}

/// The library, newest first: the owner's latest files (the server returns at most 200), and,
/// opened from a conversation or for an agent, that conversation's own files
/// (`GET /artifacts?thread_id=`) and that agent's own files (`GET /artifacts?agent_id=`) too,
/// so older ones are never missing. One read alone may fail; all failing fails.
Future<List<ArtifactRecord>> fetchArtifacts({
  String? threadId,
  String? agentId,
}) async {
  List<ArtifactRecord> rows(Object? value) =>
      asJsonList(value).map(ArtifactRecord.new).toList();
  if (threadId == null && agentId == null) {
    return rows(await api.get('/artifacts'));
  }
  Future<Object?> read([Map<String, Object?>? query]) => api
      .get('/artifacts', query: query)
      .then<Object?>((v) => v, onError: (Object e) => e);
  final results = await Future.wait([
    read(),
    if (threadId != null) read({'thread_id': threadId}),
    if (agentId != null) read({'agent_id': agentId}),
  ]);
  if (results.every((r) => r is! List)) throw results.first!;
  final merged = <String, ArtifactRecord>{
    for (final r in results)
      if (r is List)
        for (final a in rows(r)) a.id: a,
  };
  final all = merged.values.toList()
    ..sort(
      (a, b) =>
          (b.createdAt ?? DateTime(0)).compareTo(a.createdAt ?? DateTime(0)),
    );
  return all;
}

Future<ArtifactRecord> fetchArtifact(String id) async => ArtifactRecord(
  asJson(await api.get('/artifacts/${Uri.encodeComponent(id)}')),
);

/// The file's bytes; [preview] asks for an inline image/PDF disposition. Cached per version.
Future<Uint8List> fetchArtifactBytes(
  ArtifactRecord record, {
  bool preview = false,
}) => FileBytes.load(
  '${record.id}@${record.version}',
  () => api.bytes(
    '/artifacts/${Uri.encodeComponent(record.id)}/file',
    query: preview ? {'preview': true} : null,
  ),
);

/// The directory files are written to before a hand-off (the app's cache; tests replace it).
Future<Directory> Function() cacheDirectory = getTemporaryDirectory;

const _handoffDir = 'lonora-artifacts';

/// How long a copy handed to another app is kept (it may read it after the hand-off
/// returns: a share target on send, a viewer while open).
const handoffKeep = Duration(hours: 1);

/// Writes the file into the app's cache (`lonora-artifacts/<id>/<name>`) for sharing or opening
/// in another app, after deleting copies older than [handoffKeep]; sign-out deletes them all.
Future<String> cacheArtifact(ArtifactRecord record, Uint8List bytes) async {
  final sep = Platform.pathSeparator;
  final root = Directory('${(await cacheDirectory()).path}$sep$_handoffDir');
  await _pruneHandoffs(root);
  final dir = Directory('${root.path}$sep${cacheName(record.id)}');
  await dir.create(recursive: true);
  final file = File('${dir.path}$sep${cacheName(record.name)}');
  await file.writeAsBytes(bytes, flush: true);
  return file.path;
}

Future<void> _pruneHandoffs(Directory root) async {
  try {
    if (!await root.exists()) return;
    final before = DateTime.now().subtract(handoffKeep);
    final dirs = <Directory>[];
    await for (final entry in root.list(recursive: true)) {
      if (entry is Directory) {
        dirs.add(entry);
      } else if ((await entry.stat()).modified.isBefore(before)) {
        await entry.delete();
      }
    }
    for (final d in dirs.reversed) {
      if (await d.list().isEmpty) await d.delete();
    }
  } catch (_) {
    // The system may clear its cache meanwhile.
  }
}

/// Deletes every copy handed to another app.
Future<void> deleteHandoffCopies() async {
  try {
    final dir = Directory(
      '${(await cacheDirectory()).path}${Platform.pathSeparator}$_handoffDir',
    );
    if (await dir.exists()) await dir.delete(recursive: true);
  } catch (_) {
    // No cache directory here (tests) or already gone.
  }
}

Future<void> deleteArtifact(String id) async {
  await api.delete('/artifacts/${Uri.encodeComponent(id)}');
}

/// A new version of a text file; `409 version_conflict` when it changed meanwhile.
Future<ArtifactRecord> saveArtifactText(
  ArtifactRecord record, {
  required String name,
  required String content,
}) async => ArtifactRecord(
  asJson(
    await api.put('/artifacts/${Uri.encodeComponent(record.id)}/text', {
      'expected_version': record.version,
      'name': name,
      'content': content,
    }),
  ),
);

/// Uploads a local file, filed under [threadId] and stored as [agentId]'s file when given
/// (apps/web domain api `uploadFile(file, agentId)`).
Future<ArtifactRecord> uploadArtifact({
  required String path,
  required String name,
  String? mimeType,
  String? threadId,
  String? agentId,
}) async => ArtifactRecord(
  asJson(
    await api.upload(
      '/artifacts/upload',
      filePath: path,
      fileName: name,
      mimeType: mimeType,
      fields: {'thread_id': ?threadId, 'agent_id': ?agentId},
    ),
  ),
);

/// A new text file: written to the cache, then uploaded (apps/web FilesPages.tsx new file).
Future<ArtifactRecord> createTextArtifact({
  required String name,
  required String content,
  String? threadId,
  String? agentId,
}) async {
  final base = await cacheDirectory();
  final file = File(
    '${base.path}${Platform.pathSeparator}lonora-new-${DateTime.now().microsecondsSinceEpoch}.txt',
  );
  await file.writeAsString(content, flush: true);
  try {
    return await uploadArtifact(
      path: file.path,
      name: name,
      mimeType: name.toLowerCase().endsWith('.md')
          ? 'text/markdown'
          : 'text/plain',
      threadId: threadId,
      agentId: agentId,
    );
  } finally {
    if (await file.exists()) await file.delete();
  }
}
