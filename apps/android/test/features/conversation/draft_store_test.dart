// The phone's draft store (apps/mobile/lib/draft-store.ts, tests/mobile/draft-store.test.ts):
// one file per server, owner and conversation, validated on read, deleted when empty or too
// large, and wiped on sign-out.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/features/conversation/composer_assist.dart';
import 'package:lonora/features/conversation/conversation_composer.dart';
import 'package:lonora/features/conversation/draft_store.dart';

void main() {
  late Directory root;
  late DraftStore store;
  final scope = LocalStore.scope('https://lonora.example', 'owner-1');
  final other = LocalStore.scope('https://lonora.example', 'owner-2');

  File file(String scope, String thread) =>
      File('${root.path}/$scope/$thread.json');

  setUp(() async {
    root = await Directory.systemTemp.createTemp('lonora_drafts');
    store = DraftStore(
      LocalStore.at(root),
      wipe: () async {
        if (await root.exists()) await root.delete(recursive: true);
      },
    );
    DraftStore.debugOverride = store;
  });

  tearDown(() async {
    DraftStore.debugOverride = null;
    if (await root.exists()) await root.delete(recursive: true);
  });

  const draft = SavedDraft(
    text: 'راقب الذهب @Atlas',
    files: [
      {
        'id': 'art-1',
        'payload': {
          'name': 'chart.png',
          'media_type': 'image/png',
          'size': 2048,
        },
      },
    ],
    reply: {'id': 'm1', 'content': 'Gold is up', 'role': 'assistant'},
    replyAuthor: 'Atlas',
    mentions: [
      MentionRange(agentId: 'a1', token: '@Atlas', start: 11, end: 17),
    ],
  );

  test('a draft comes back only in its own conversation and scope', () async {
    await store.write(scope, 't1', draft, generation: DraftStore.generation);
    final back = await store.read(scope, 't1');
    expect(back?.text, draft.text);
    expect(back?.files.single['id'], 'art-1');
    expect(back?.reply?['id'], 'm1');
    expect(back?.replyAuthor, 'Atlas');
    expect(back?.mentions, draft.mentions);
    expect(await store.read(scope, 't2'), isNull);
    expect(await store.read(other, 't1'), isNull);
    // The saved shape (v1).
    final json = jsonDecode(await file(scope, 't1').readAsString()) as Map;
    expect(json['v'], 1);
    expect(json['thread_id'], 't1');
    expect(json.keys, containsAll(['text', 'files', 'reply', 'mentions']));
  });

  test('an empty draft deletes the saved copy', () async {
    await store.write(scope, 't1', draft, generation: DraftStore.generation);
    expect(file(scope, 't1').existsSync(), isTrue);
    await store.write(
      scope,
      't1',
      const SavedDraft(),
      generation: DraftStore.generation,
    );
    expect(file(scope, 't1').existsSync(), isFalse);
    await store.write(scope, 't1', draft, generation: DraftStore.generation);
    await store.write(scope, 't1', null, generation: DraftStore.generation);
    expect(await store.read(scope, 't1'), isNull);
  });

  test('a draft too large to keep deletes the older copy', () async {
    await store.write(scope, 't1', draft, generation: DraftStore.generation);
    final huge = SavedDraft(
      text: 'x' * 1000,
      files: [
        for (var i = 0; i < 10; i++)
          {
            'id': 'a$i',
            'payload': {'name': 'n' * 30000},
          },
      ],
    );
    await store.write(scope, 't1', huge, generation: DraftStore.generation);
    expect(file(scope, 't1').existsSync(), isFalse);
  });

  test('a broken or foreign saved draft is ignored and removed', () async {
    Future<void> raw(String content) async {
      final f = file(scope, 't1');
      await f.parent.create(recursive: true);
      await f.writeAsString(content);
    }

    await raw('{not json');
    expect(await store.read(scope, 't1'), isNull);

    final good = draft.toJson('t1');
    for (final bad in <Map<String, Object?>>[
      {...good, 'v': 2},
      {...good, 'thread_id': 't2'},
      {...good, 'text': 3},
      {...good, 'text': 'x' * (draftMaxText + 1)},
      {
        ...good,
        'files': [
          for (var i = 0; i < 11; i++) {'id': 'a$i'},
        ],
      },
      {
        ...good,
        'files': [
          {'name': 'no id'},
        ],
      },
      {
        ...good,
        'reply': {'id': 'm1'},
      },
      {...good, 'reply': 'm1'},
      {
        ...good,
        'mentions': [
          {'token': '@a', 'start': 0, 'end': 9},
        ],
      },
      {
        ...good,
        'mentions': [
          for (var i = 0; i < 101; i++)
            {'agent_id': 'a', 'token': '@a', 'start': 0, 'end': 2},
        ],
      },
    ]) {
      await raw(jsonEncode(bad));
      expect(await store.read(scope, 't1'), isNull, reason: '$bad');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(file(scope, 't1').existsSync(), isFalse, reason: '$bad');
    }
  });

  test('sign-out removes every saved draft, and an earlier write never '
      'lands after it', () async {
    final before = DraftStore.generation;
    await store.write(scope, 't1', draft, generation: before);
    await store.write(other, 't9', draft, generation: before);
    final cleared = DraftStore.clearAll();
    // A composer still open from the signed-out session writes its draft on close.
    final late = store.write(scope, 't2', draft, generation: before);
    await cleared;
    await late;
    expect(DraftStore.generation, before + 1);
    expect(await store.read(scope, 't1'), isNull);
    expect(await store.read(other, 't9'), isNull);
    expect(await store.read(scope, 't2'), isNull);
    // The next owner's drafts are kept again.
    await store.write(scope, 't3', draft, generation: DraftStore.generation);
    expect((await store.read(scope, 't3'))?.text, draft.text);
  });

  test(
    "the sign-out hook's future completes once the drafts are gone",
    () async {
      await store.write(scope, 't1', draft, generation: DraftStore.generation);
      // A write still pending when the owner signs out finishes first, then goes too.
      final pending = store.write(
        other,
        't9',
        draft,
        generation: DraftStore.generation,
      );
      await ConversationComposerState.clearDrafts();
      expect(root.existsSync(), isFalse);
      await pending;
      expect(root.existsSync(), isFalse);
    },
  );
}
