import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/state/reply_stream.dart';

LonoraEvent ev(
  int cursor,
  String kind,
  Map<String, dynamic> payload, {
  String run = 'r1',
}) => LonoraEvent(
  cursor: cursor,
  kind: kind,
  runId: run,
  threadId: 't1',
  agentId: 'a1',
  payload: payload,
);

Map<String, dynamic> id({
  int fence = 1,
  int generation = 0,
  int sequence = 0,
  String turn = 'turn',
}) => {
  'turn_id': turn,
  'fence': fence,
  'generation': generation,
  'sequence': sequence,
  'phase': 'streaming',
};

void main() {
  group('accumulateStream (port of packages/core/src/reply-stream.ts)', () {
    test('appends contiguous chunks', () {
      LiveReplyStream? s;
      s = accumulateStream(s, ev(1, 'run.reply_started', id()));
      s = accumulateStream(
        s,
        ev(2, 'run.delta', {...id(sequence: 1), 'text': 'Hel'}),
      );
      s = accumulateStream(
        s,
        ev(3, 'run.delta', {...id(sequence: 2), 'text': 'lo'}),
      );
      expect(s!.text, 'Hello');
      expect(s.gap, isFalse);
      expect(s.sequence, 2);
      expect(s.streaming, isTrue);
    });

    test('ignores duplicate and older sequences', () {
      LiveReplyStream? s;
      s = accumulateStream(s, ev(1, 'run.reply_started', id()));
      s = accumulateStream(
        s,
        ev(2, 'run.delta', {...id(sequence: 1), 'text': 'a'}),
      );
      s = accumulateStream(
        s,
        ev(3, 'run.delta', {...id(sequence: 1), 'text': 'a'}),
      );
      expect(s!.text, 'a');
    });

    test('a sequence jump marks a gap and stops appending', () {
      LiveReplyStream? s;
      s = accumulateStream(s, ev(1, 'run.reply_started', id()));
      s = accumulateStream(
        s,
        ev(2, 'run.delta', {...id(sequence: 1), 'text': 'a'}),
      );
      s = accumulateStream(
        s,
        ev(3, 'run.delta', {...id(sequence: 3), 'text': 'c'}),
      );
      expect(s!.gap, isTrue);
      expect(s.text, 'a');
    });

    test(
      'a newer generation replaces the preview; an older one is ignored',
      () {
        LiveReplyStream? s;
        s = accumulateStream(s, ev(1, 'run.reply_started', id(generation: 1)));
        s = accumulateStream(
          s,
          ev(2, 'run.delta', {
            ...id(generation: 1, sequence: 1),
            'text': 'old',
          }),
        );
        s = accumulateStream(s, ev(3, 'run.reply_started', id(generation: 2)));
        s = accumulateStream(
          s,
          ev(4, 'run.delta', {
            ...id(generation: 2, sequence: 1),
            'text': 'new',
          }),
        );
        expect(s!.text, 'new');
        s = accumulateStream(
          s,
          ev(5, 'run.delta', {
            ...id(generation: 1, sequence: 2),
            'text': 'stale',
          }),
        );
        expect(s!.text, 'new');
      },
    );

    test(
      'commit settles; delayed chunks never resurrect a terminal preview',
      () {
        LiveReplyStream? s;
        s = accumulateStream(s, ev(1, 'run.reply_started', id()));
        s = accumulateStream(
          s,
          ev(2, 'run.delta', {...id(sequence: 1), 'text': 'done'}),
        );
        s = accumulateStream(
          s,
          ev(3, 'run.reply_committed', {
            ...id(sequence: 1),
            'phase': 'committed',
            'message_id': 'm1',
          }),
        );
        expect(s!.phase, 'committed');
        expect(s.messageId, 'm1');
        s = accumulateStream(
          s,
          ev(4, 'run.delta', {...id(sequence: 2), 'text': ' more'}),
        );
        expect(s!.text, 'done');
      },
    );

    test('discarded commit means no message will come', () {
      LiveReplyStream? s;
      s = accumulateStream(s, ev(1, 'run.reply_started', id()));
      s = accumulateStream(
        s,
        ev(2, 'run.reply_committed', {...id(), 'phase': 'discarded'}),
      );
      expect(s!.phase, 'discarded');
      expect(s.richContent, isNull);
    });

    test('cancel and failure keep the accepted preview with their phase', () {
      LiveReplyStream? s;
      s = accumulateStream(s, ev(1, 'run.reply_started', id()));
      s = accumulateStream(
        s,
        ev(2, 'run.delta', {...id(sequence: 1), 'text': 'partial'}),
      );
      final cancelled = accumulateStream(s, ev(3, 'run.cancelled', {}));
      expect(cancelled!.phase, 'cancelled');
      expect(cancelled.text, 'partial');
      final failed = accumulateStream(s, ev(3, 'run.failed', {'code': 'x'}));
      expect(failed!.phase, 'failed');
    });

    test('events of another run are ignored', () {
      LiveReplyStream? s;
      s = accumulateStream(s, ev(1, 'run.reply_started', id()));
      final other = accumulateStream(
        s,
        ev(2, 'run.delta', {...id(sequence: 1), 'text': 'x'}, run: 'r2'),
      );
      expect(identical(other, s), isTrue);
    });

    test('rich content is cumulative and replaces the previous tree', () {
      LiveReplyStream? s;
      s = accumulateStream(s, ev(1, 'run.reply_started', id()));
      s = accumulateStream(
        s,
        ev(2, 'run.rich_partial', {
          ...id(sequence: 1),
          'rich_content': {
            'version': 1,
            'parts': [
              {'type': 'text', 'text': 'a'},
            ],
          },
        }),
      );
      expect((s!.richContent!['parts'] as List).length, 1);
    });

    test('text is bounded to 60000 code points', () {
      LiveReplyStream? s;
      s = accumulateStream(s, ev(1, 'run.reply_started', id()));
      s = accumulateStream(
        s,
        ev(2, 'run.delta', {...id(sequence: 1), 'text': 'x' * 59999}),
      );
      s = accumulateStream(
        s,
        ev(3, 'run.delta', {...id(sequence: 2), 'text': '😀😀'}),
      );
      expect(s!.text.runes.length, maxStreamChars);
    });
  });

  group('seedStream', () {
    Run run(Map<String, dynamic> stream) => Run.fromJson({
      'id': 'r1',
      'thread_id': 't1',
      'agent_id': 'a1',
      'status': 'running',
      'stream': stream,
    });

    test('rebases a gapped preview on the durable snapshot', () {
      LiveReplyStream? s;
      s = accumulateStream(s, ev(1, 'run.reply_started', id()));
      s = accumulateStream(
        s,
        ev(2, 'run.delta', {...id(sequence: 1), 'text': 'a'}),
      );
      s = accumulateStream(
        s,
        ev(3, 'run.delta', {...id(sequence: 3), 'text': 'c'}),
      );
      expect(s!.gap, isTrue);
      final seeded = seedStream(
        s,
        run({...id(sequence: 3), 'text': 'abc', 'truncated': false}),
      );
      expect(seeded!.text, 'abc');
      expect(seeded.gap, isFalse);
    });

    test('keeps a contiguous live preview that is ahead of the snapshot', () {
      LiveReplyStream? s;
      s = accumulateStream(s, ev(1, 'run.reply_started', id()));
      s = accumulateStream(
        s,
        ev(2, 'run.delta', {...id(sequence: 1), 'text': 'a'}),
      );
      s = accumulateStream(
        s,
        ev(3, 'run.delta', {...id(sequence: 2), 'text': 'b'}),
      );
      final seeded = seedStream(s, run({...id(sequence: 1), 'text': 'a'}));
      expect(identical(seeded, s), isTrue);
    });

    test('a terminal local phase survives a streaming snapshot', () {
      LiveReplyStream? s;
      s = accumulateStream(s, ev(1, 'run.reply_started', id()));
      s = accumulateStream(
        s,
        ev(2, 'run.delta', {...id(sequence: 1), 'text': 'a'}),
      );
      s = accumulateStream(
        s,
        ev(3, 'run.reply_committed', {
          ...id(sequence: 1),
          'phase': 'committed',
          'message_id': 'm',
        }),
      );
      final seeded = seedStream(s, run({...id(sequence: 1), 'text': 'a'}));
      expect(seeded!.phase, 'committed');
      expect(seeded.messageId, 'm');
    });
  });
}
