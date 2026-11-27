// lonora-ui v2 documents: fail-closed validation (the server's compiled parity cards pass,
// malformed ones never render), typed numbers, card Markdown, and the shared lock / mark /
// send rules (packages/core/src/genui/submit.ts).
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/features/rich/genui/spec.dart';

Json _doc([Map<String, Object?> extra = const {}]) => {
  'v': 2,
  'kind': 'form',
  'title': 'T',
  'icon': 'bell',
  'facts': <String, Object?>{},
  'state': <String, Object?>{'x': 1},
  'calc': <String, Object?>{},
  'blocks': [
    {'type': 'Text', 'text': 'hi'},
  ],
  'fallback': 'hi',
  ...extra,
};

void main() {
  final parity =
      (jsonDecode(
            File('test/features/rich/fixtures/parity-compiled.json')
                .readAsStringSync(),
          ) as Map<String, dynamic>)['documents']
          as List;

  test('every compiled parity card validates', () {
    expect(parity, isNotEmpty);
    for (final doc in parity) {
      expect(
        validateUiDocument(doc),
        isNotNull,
        reason: jsonEncode(doc).substring(0, 80),
      );
    }
  });

  group('fails closed', () {
    test(
      'a minimal card passes',
      () => expect(validateUiDocument(_doc()), isNotNull),
    );

    for (final (name, doc) in [
      ('v1', _doc({'v': 1})),
      ('unknown kind', _doc({'kind': 'video'})),
      ('missing fallback', {..._doc()}..remove('fallback')),
      (
        'unknown node',
        _doc({
          'blocks': [
            {'type': 'Iframe'},
          ],
        }),
      ),
      (
        'bad when',
        _doc({
          'blocks': [
            {'type': 'Text', 'text': 'x', 'when': r'$x >'},
          ],
        }),
      ),
      (
        'nested slot',
        _doc({
          'blocks': [
            {
              'type': 'Card',
              'children': [
                {'type': 'Slot', 'card': 'settle', 'record': 'r1'},
              ],
            },
          ],
        }),
      ),
      (
        'slot with text',
        _doc({
          'blocks': [
            {'type': 'Slot', 'card': 'settle', 'record': 'r1', 'text': 'x'},
          ],
        }),
      ),
      (
        'open http',
        _doc({
          'blocks': [
            {
              'type': 'Button',
              'label': 'Go',
              'action': {'do': 'open', 'url': 'http://example.com'},
            },
          ],
        }),
      ),
      (
        'unknown action',
        _doc({
          'blocks': [
            {
              'type': 'Button',
              'label': 'Go',
              'action': {'do': 'execute'},
            },
          ],
        }),
      ),
      (
        'proto key',
        _doc({
          'state': <String, Object?>{'__proto__': 1},
        }),
      ),
      (
        'too many blocks',
        _doc({
          'blocks': [
            for (var i = 0; i < 15; i++) {'type': 'Divider'},
          ],
        }),
      ),
      (
        'too many children',
        _doc({
          'blocks': [
            {
              'type': 'Row',
              'children': [
                for (var i = 0; i < 9; i++) {'type': 'Divider'},
              ],
            },
          ],
        }),
      ),
      (
        'bad calc',
        _doc({
          'calc': <String, Object?>{'a': '1 +'},
        }),
      ),
      (
        'non-finite',
        _doc({
          'state': <String, Object?>{'x': double.infinity},
        }),
      ),
    ]) {
      test(name, () => expect(validateUiDocument(doc), isNull));
    }

    test('a part with an unknown key or a negative cut is refused', () {
      expect(validateUiPart({'type': 'ui', 'document': _doc()}), isNotNull);
      expect(
        validateUiPart({'type': 'ui', 'document': _doc(), 'extra': 1}),
        isNull,
      );
      expect(
        validateUiPart({'type': 'ui', 'document': _doc(), 'cut': -1}),
        isNull,
      );
      final part = validateUiPart({
        'type': 'ui',
        'document': _doc(),
        'building': true,
        'cut': 0,
      })!;
      expect(part.building, isTrue);
      expect(part.cut, 0);
    });
  });

  group('typed numbers', () {
    test('plain, grouped and Arabic digits read; malformed drafts do not', () {
      expect(parseCardNumber(''), isNull);
      expect(parseCardNumber('2400'), 2400);
      expect(parseCardNumber('2,400.5'), 2400.5);
      expect(parseCardNumber('٢٬٤٠٠٫٥'), 2400.5);
      expect(parseCardNumber('۱۲'), 12);
      expect(parseCardNumber('-3'), -3);
      expect(identical(parseCardNumber('2,4'), unreadable), isTrue);
      expect(identical(parseCardNumber('1e5'), unreadable), isTrue);
      expect(identical(parseCardNumber('abc'), unreadable), isTrue);
    });
  });

  test('card Markdown: paragraphs, lists, bold; links show their label', () {
    final blocks = cardMarkdown(
      '## Plan\n- **one** item\n- [two](https://x.y)\n\n1. first\n2) second',
    );
    expect(blocks.map((b) => b.kind), ['p', 'ul', 'ol']);
    expect(blocks[1].lines[0].first.bold, isTrue);
    expect(blocks[1].lines[1].single.text, 'two');
    expect(blocks[2].lines, hasLength(2));
  });

  group('submit rules', () {
    Message msg(Json j) => Message.fromJson({
      'thread_id': 't1',
      'role': 'assistant',
      'created_at': '2026-11-27T10:00:00Z',
      ...j,
    });
    final card = msg({'id': 'card', 'seq': 5, 'agent_id': 'a1'});
    Message submission(int seq, {Json extra = const {}}) => msg({
      'id': 's$seq',
      'seq': seq,
      'role': 'user',
      'origin': 'ui_submit',
      'reply_to': 'card',
      'ui_submit': {
        'source_message_id': 'card',
        'part': 0,
        'intent': 'ask',
        'lock': true,
        'run_id': 'r$seq',
        ...extra,
      },
    });

    test(
      'a locking submission locks its part; an unlock after it frees it',
      () {
        final sent = submission(
          6,
          extra: {'started_at': '2026-11-27T10:01:00Z'},
        );
        expect(cardLock(card, 0, [card, sent]), (id: 's6', seq: 6));
        expect(cardLock(card, 1, [card, sent]), isNull);
        final unlocked = msg({
          'id': 'card',
          'seq': 5,
          'ui_state': {
            'parts': {
              '0': {'unlocked_seq': 6},
            },
          },
        });
        expect(cardLock(unlocked, 0, [unlocked, sent]), isNull);
      },
    );

    test('a never-run send is marked and never locks', () {
      final notRun = submission(7, extra: {'mark': 'not_run'});
      expect(submitMark(notRun), 'not_run');
      expect(cardLock(card, 0, [card, notRun]), isNull);
    });

    test(
      "the server's derived lock holds when the submission is not loaded",
      () {
        final derived = msg({
          'id': 'card',
          'seq': 5,
          'ui_lock': {
            '0': {'message_id': 'older', 'seq': 3, 'agent_id': 'a1'},
          },
        });
        expect(cardLock(derived, 0, [derived]), (id: 'older', seq: 3));
      },
    );

    test('sends wait for a paused agent, a waiting run or a queued send', () {
      Run run(String id, String status) => Run.fromJson({
        'id': id,
        'thread_id': 't1',
        'agent_id': 'a1',
        'status': status,
      });
      expect(sendBlocked('a1', 't1', [card], const [], paused: true), 'paused');
      expect(
        sendBlocked(
          'a1',
          't1',
          [card],
          [run('r1', 'waiting_input')],
          paused: false,
        ),
        'waiting',
      );
      final queued = submission(8);
      expect(
        sendBlocked(
          'a1',
          't1',
          [card, queued],
          [run('r8', 'queued')],
          paused: false,
        ),
        'queued',
      );
      expect(
        sendBlocked(
          'a1',
          't1',
          [card, queued],
          [run('r8', 'completed')],
          paused: false,
        ),
        isNull,
      );
    });
  });
}
