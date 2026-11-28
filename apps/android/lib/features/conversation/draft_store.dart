// Composer drafts on this phone, as Lonora's Expo app keeps them (apps/mobile/lib/draft-store.ts)
// with Web's mention ranges (apps/web/src/lib/composer-drafts.ts): per server, owner and
// conversation, the unsent text, the finished attachments, the reply and the committed
// @mentions survive an app restart. Running uploads, errors, local paths and an edit's text are
// never saved. The drafts live in their own directory (`lonora-drafts`), so «مسح ذاكرة التخزين
// المؤقت» keeps them and a sign-out removes them all at once.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import '../../core/json.dart';
import '../../core/storage/local_store.dart';
import 'composer_assist.dart' show MentionRange;

/// A saved draft is dropped (and its file deleted) above this many UTF-16 units of JSON
/// (draft-store.ts `MAX_BYTES`, compared with `raw.length`).
const draftMaxLength = 256 * 1024;

/// The server's `content` limit (contracts domain.py).
const draftMaxText = 30000;

/// One conversation's saved draft.
class SavedDraft {
  const SavedDraft({
    this.text = '',
    this.files = const [],
    this.reply,
    this.replyAuthor,
    this.mentions = const [],
  });

  final String text;

  /// Each finished upload's artifact as `/artifacts/upload` answered it.
  final List<Json> files;

  /// The quoted message's raw JSON.
  final Json? reply;
  final String? replyAuthor;
  final List<MentionRange> mentions;

  /// Nothing worth keeping: the saved copy is deleted at once.
  bool get isEmpty => text.isEmpty && files.isEmpty && reply == null;

  Json toJson(String threadId) => {
    'v': 1,
    'thread_id': threadId,
    'text': text,
    'files': files,
    'reply': reply,
    'reply_author': replyAuthor,
    'mentions': [for (final m in mentions) m.toJson()],
  };

  /// The saved draft of [threadId] in [value], or null when anything in it is off (another
  /// conversation, too long, too many files, a malformed reply or mention).
  static SavedDraft? parse(Object? value, String threadId) {
    if (value is! Map) return null;
    final j = asJson(value);
    if (jsonEncode(j).length > draftMaxLength) return null;
    if (j['v'] != 1 || j['thread_id'] != threadId) return null;
    final text = j['text'];
    if (text is! String || text.length > draftMaxText) return null;
    final files = j['files'];
    if (files is! List || files.length > 10) return null;
    if (!files.every((f) => f is Map && f['id'] is String)) return null;
    final reply = j['reply'];
    if (reply != null &&
        (reply is! Map ||
            reply['id'] is! String ||
            reply['content'] is! String)) {
      return null;
    }
    final author = j['reply_author'];
    if (author != null && author is! String) return null;
    final mentions = j['mentions'] ?? const [];
    if (mentions is! List || mentions.length > 100) return null;
    final ranges = [for (final m in mentions) MentionRange.fromJson(m)];
    if (ranges.contains(null)) return null;
    return SavedDraft(
      text: text,
      files: [for (final f in files) asJson(f)],
      reply: reply == null ? null : asJson(reply),
      replyAuthor: author as String?,
      mentions: [for (final r in ranges) r!],
    );
  }
}

/// The drafts' own [LocalStore]: scope = `LocalStore.scope(server, ownerId)`, name = the
/// conversation id. Reads and writes never throw: a failure means no draft, and composing or
/// sending is never blocked.
class DraftStore {
  DraftStore(this._store, {this.wipe});

  final LocalStore _store;

  /// Removes every saved draft at once (the phone's store deletes its directory).
  final Future<void> Function()? wipe;

  /// Replaces the phone's store (tests).
  static DraftStore? debugOverride;
  static Future<DraftStore?>? _opening;

  /// Bumped by [clearAll] (sign-out): a write or a restore started before it is dropped.
  static int generation = 0;
  static final Set<Future<void>> _pending = {};
  static Future<void>? _clearing;

  /// The phone's draft store (`<application support>/lonora-drafts`), or null where there is
  /// no file system to keep drafts in.
  static Future<DraftStore?> instance() {
    final override = debugOverride;
    if (override != null) return Future.value(override);
    return _opening ??= _open();
  }

  static Future<DraftStore?> _open() async {
    try {
      final support = await getApplicationSupportDirectory();
      final root = Directory('${support.path}/lonora-drafts');
      return DraftStore(
        LocalStore.at(root),
        wipe: () async {
          if (await root.exists()) await root.delete(recursive: true);
        },
      );
    } catch (_) {
      return null;
    }
  }

  /// The saved draft of [threadId], or null. A copy that fails validation is deleted.
  Future<SavedDraft?> read(String scope, String threadId) async {
    try {
      await _clearing;
      final raw = await _store.read(scope, threadId);
      if (raw == null) return null;
      final draft = SavedDraft.parse(raw, threadId);
      if (draft == null) {
        unawaited(write(scope, threadId, null, generation: generation));
      }
      return draft;
    } catch (_) {
      return null;
    }
  }

  /// Saves [draft]; an empty or null draft, or one too large to keep, deletes the saved copy
  /// (an older version must not come back in its place). Dropped when [generation] is stale.
  Future<void> write(
    String scope,
    String threadId,
    SavedDraft? draft, {
    required int generation,
  }) {
    late final Future<void> future;
    future = () async {
      try {
        await _clearing;
        if (generation != DraftStore.generation) return;
        Json? json = draft == null || draft.isEmpty
            ? null
            : draft.toJson(threadId);
        if (json != null && jsonEncode(json).length > draftMaxLength) {
          json = null;
        }
        await _store.write(scope, threadId, json);
      } catch (_) {
        // A draft that cannot be saved is only lost on a restart.
      } finally {
        _pending.remove(future);
      }
    }();
    _pending.add(future);
    return future;
  }

  /// Sign-out and expiry: no write or restore started before survives, pending writes finish,
  /// and every saved draft of every owner goes.
  static Future<void> clearAll() {
    generation++;
    final previous = _clearing;
    // Writes started from now on wait for this clear (they are dropped by the generation).
    final pending = List.of(_pending);
    final opened = instance();
    late final Future<void> done;
    done = () async {
      try {
        await previous;
        await Future.wait(pending);
        final store = await opened;
        await store?.wipe?.call();
      } catch (_) {
        // Nothing to remove.
      } finally {
        if (identical(_clearing, done)) _clearing = null;
      }
    }();
    _clearing = done;
    return done;
  }
}
