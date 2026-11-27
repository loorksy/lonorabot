// The transcript model: ordering of messages, unsent messages, live previews, run rows and
// cards; the preview/commit hand-over; rhythm and separators; questions; retry rules.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/features/cards/thread_cards.dart';
import 'package:lonora/features/conversation/conversation_timeline.dart';
import 'package:lonora/state/app_state.dart';

import 'conversation_harness.dart';

ThreadState thread({
  List<Message> messages = const [],
  Map<String, Run> runs = const {},
  Map<String, dynamic> streams = const {},
}) => ThreadState(
  threadId: threadId,
  messages: messages,
  runs: runs,
  streams: streams.cast(),
  loaded: true,
);

List<String> keys(List<TimelineItem> items) => [for (final i in items) i.key];

void main() {
  final m1 = message('m1', 1, 'user', 'Hello', at(1));
  final m2 = message('m2', 2, 'assistant', 'Hi', at(2));
  final m3 = message('m3', 3, 'user', 'Status?', at(3));

  group('buildTimeline', () {
    test('messages by seq, unsent messages after them', () {
      final items = buildTimeline(
        thread: thread(messages: [m1, m2]),
        outbox: [
          OutgoingMessage(
            nonce: 'n1',
            threadId: threadId,
            body: const {'content': 'later'},
            delivery: Delivery.sending,
            createdAt: at(4),
          ),
        ],
      );
      expect(keys(items), ['m:m1', 'm:m2', 'o:n1']);
    });

    test('an acknowledged nonce is not drawn twice', () {
      final acked = Message.fromJson({
        ...messageJson(
          id: 'm3',
          seq: 3,
          role: 'user',
          content: 'Status?',
          createdAt: at(3),
        ),
        'client_nonce': 'n1',
      });
      final items = buildTimeline(
        thread: thread(messages: [m1, acked]),
        outbox: [
          OutgoingMessage(
            nonce: 'n1',
            threadId: threadId,
            body: const {'content': 'Status?'},
            delivery: Delivery.sending,
            createdAt: at(3),
          ),
        ],
      );
      expect(keys(items), ['m:m1', 'm:m3']);
    });

    test('a working run shows its preview right after the owner input', () {
      final items = buildTimeline(
        thread: thread(
          messages: [m1, m2, m3],
          runs: {'r1': run('r1', 'running', inputSeq: 1, createdAt: at(1))},
        ),
      );
      expect(keys(items), ['m:m1', 'p:r1', 'm:m2', 'm:m3']);
      final preview = items[1] as PreviewItem;
      expect(preview.visible, isFalse);
    });

    test('the live stream is drawn until its message is committed', () {
      final live = liveStream('r1', 'Partial answer', inputSeq: 3);
      var items = buildTimeline(
        thread: thread(
          messages: [m1, m2, m3],
          runs: {'r1': run('r1', 'running', inputSeq: 3)},
          streams: {'r1': live},
        ),
      );
      expect(keys(items).last, 'p:r1');
      expect((items.last as PreviewItem).visible, isTrue);

      final committed = live.copyWith(phase: 'committed', messageId: 'm4');
      final m4 = message('m4', 4, 'assistant', 'Full answer', at(5));
      items = buildTimeline(
        thread: thread(
          messages: [m1, m2, m3, m4],
          runs: {'r1': run('r1', 'completed', inputSeq: 3)},
          streams: {'r1': committed},
        ),
      );
      expect(keys(items), ['m:m1', 'm:m2', 'm:m3', 'm:m4']);
    });

    test('a failed reply gets a run row; a background one only for quota', () {
      var items = buildTimeline(
        thread: thread(
          messages: [m1, m2, m3],
          runs: {
            'r1': run('r1', 'failed', inputSeq: 3, errorCode: 'model_timeout'),
          },
        ),
      );
      expect(keys(items).last, 'r:r1');

      final background = Run.fromJson({
        ...run('r2', 'failed', inputSeq: 3).raw,
        'background': true,
        'failure': {'family': 'rate'},
      });
      items = buildTimeline(
        thread: thread(messages: [m1, m2, m3], runs: {'r2': background}),
      );
      expect(keys(items), isNot(contains('r:r2')));
    });

    test('cards follow their anchor message, or their time', () {
      Widget empty(BuildContext _) => const SizedBox();
      final items = buildTimeline(
        thread: thread(messages: [m1, m2, m3]),
        cards: [
          TimelineCard(key: 'a', at: at(0), seq: 1, builder: empty),
          TimelineCard(key: 'b', at: at(2), builder: empty),
          TimelineCard(key: 'c', at: at(30), builder: empty),
        ],
      );
      expect(keys(items), ['m:m1', 'c:a', 'c:b', 'm:m2', 'm:m3', 'c:c']);
    });

    test('cards on one seq keep the order of the cards list', () {
      Widget empty(BuildContext _) => const SizedBox();
      // A replaced owner action before its replacement, although its id sorts after it.
      final items = buildTimeline(
        thread: thread(messages: [m1, m2]),
        cards: [
          TimelineCard(
            key: 'owner_action:z-old',
            at: at(1),
            seq: 1,
            builder: empty,
          ),
          TimelineCard(
            key: 'owner_action:a-new',
            at: at(2),
            seq: 1,
            builder: empty,
          ),
          TimelineCard(key: 'receipt:b', at: at(3), seq: 1, builder: empty),
        ],
      );
      expect(keys(items), [
        'm:m1',
        'c:owner_action:z-old',
        'c:owner_action:a-new',
        'c:receipt:b',
        'm:m2',
      ]);
    });
  });

  group('presentTimeline', () {
    test('same-sender rhythm, a first separator, group sender rows', () {
      final m2b = message('m2b', 3, 'assistant', 'More', at(2));
      final rows = presentTimeline(
        buildTimeline(thread: thread(messages: [m1, m2, m2b])),
        group: true,
        sameSenderGap: 7,
        senderChangeGap: 16,
      );
      expect(rows[0].separator, isNotNull);
      expect(rows[0].gap, 0);
      expect(rows[1].gap, 16);
      expect(rows[1].showSender, isTrue);
      expect(rows[2].gap, 7);
      expect(rows[2].showSender, isFalse);
    });

    test('a 15 minute pause starts a new separator', () {
      final late = message('m9', 9, 'assistant', 'Later', at(40));
      final rows = presentTimeline(
        buildTimeline(thread: thread(messages: [m1, late])),
        group: false,
        sameSenderGap: 7,
        senderChangeGap: 16,
      );
      expect(rows[1].separator, isNotNull);
    });

    test('one sender groups only within 3 minutes', () {
      final soon = message('m2b', 3, 'assistant', 'And another thing', at(4));
      final later = message('m2c', 4, 'assistant', 'One more', at(10));
      final rows = presentTimeline(
        buildTimeline(thread: thread(messages: [m1, m2, soon, later])),
        group: true,
        sameSenderGap: 7,
        senderChangeGap: 16,
      );
      // 2 minutes after the previous bubble: grouped.
      expect(rows[2].gap, 7);
      expect(rows[2].showSender, isFalse);
      // 6 minutes later (no separator yet): a new group, named again.
      expect(rows[3].separator, isNull);
      expect(rows[3].gap, 16);
      expect(rows[3].showSender, isTrue);
    });
  });

  group('bubble runs', () {
    bool bubble(TimelineItem item) => item is MessageItem;
    test('one sender\'s bubbles join, 4 dp apart', () {
      final a = message('a1', 2, 'assistant', 'One', at(1));
      final b = message('a2', 3, 'assistant', 'Two', at(1));
      final c = message('a3', 4, 'assistant', 'Three', at(2));
      final rows = presentTimeline(
        buildTimeline(thread: thread(messages: [m1, a, b, c])),
        group: false,
        sameSenderGap: 7,
        senderChangeGap: 16,
        bubbleRunGap: 4,
        startsWithBubble: bubble,
        endsWithBubble: bubble,
      );
      expect(
        [for (final r in rows) (r.joinTop, r.joinBottom)],
        [(false, false), (false, true), (true, true), (true, false)],
      );
      expect([for (final r in rows) r.gap].skip(1), [16, 4, 4]);
    });

    test('a row that does not end with its bubble breaks the run', () {
      final a = message('a1', 2, 'assistant', 'One', at(1));
      final b = message('a2', 3, 'assistant', 'Two', at(1));
      final rows = presentTimeline(
        buildTimeline(thread: thread(messages: [a, b])),
        group: false,
        sameSenderGap: 7,
        senderChangeGap: 16,
        bubbleRunGap: 4,
        startsWithBubble: bubble,
        // Files under the first bubble.
        endsWithBubble: (item) => (item as MessageItem).message.id != 'a1',
      );
      expect(rows[1].joinTop, isFalse);
      expect(rows[0].joinBottom, isFalse);
      expect(rows[1].gap, 7);
    });

    test('without the predicates nothing joins', () {
      final a = message('a1', 2, 'assistant', 'One', at(1));
      final b = message('a2', 3, 'assistant', 'Two', at(1));
      final rows = presentTimeline(
        buildTimeline(thread: thread(messages: [a, b])),
        group: false,
        sameSenderGap: 7,
        senderChangeGap: 16,
      );
      expect(rows.any((r) => r.joinTop || r.joinBottom), isFalse);
      expect(rows[1].gap, 7);
    });
  });

  group('run controls', () {
    test('Stop targets the working and waiting runs of this thread', () {
      final runs = [
        run('a', 'running'),
        run('b', 'queued'),
        run('c', 'waiting_input'),
        run('d', 'waiting_takeover'),
        run('e', 'completed'),
        run('f', 'failed'),
        Run.fromJson({...run('g', 'running').raw, 'thread_id': 'other'}),
      ];
      expect(
        [for (final r in stopTargets(runs, threadId)) r.id],
        ['a', 'b', 'c', 'd'],
      );
    });

    test('the run banner names the newest waiting or reportable run', () {
      final routine = run(
        'rt',
        'waiting_takeover',
        trigger: 'routine',
        background: true,
        createdAt: at(20),
      );
      final older = run('old', 'waiting_input', createdAt: at(5));
      expect(bannerRun([older, routine], const {})?.id, 'rt');
      // The transcript draws it with its controls: no banner.
      expect(bannerRun([older, routine], {'rt'}), isNull);
      // A background failure is news only for model access or quota.
      final quiet = run(
        'bg',
        'failed',
        trigger: 'routine',
        background: true,
        failure: {'family': 'timeout'},
        createdAt: at(30),
      );
      expect(bannerRun([quiet], const {}), isNull);
      final quota = run(
        'bq',
        'failed',
        trigger: 'routine',
        background: true,
        failure: {'family': 'quota'},
        createdAt: at(30),
      );
      expect(bannerRun([quiet, quota, routine], const {})?.id, 'bq');
      expect(bannerRun([run('w', 'running')], const {}), isNull);
    });
  });

  test('threadQuestions keys questions by their message', () {
    final r = run(
      'r1',
      'waiting_input',
      inputRequests: [
        {
          'id': 'q1',
          'run_id': 'r1',
          'message_id': 'm2',
          'thread_id': threadId,
          'question': 'Which?',
          'choices': [
            {'id': 'a', 'label': 'A'},
          ],
          'status': 'pending',
        },
        {
          'id': 'q2',
          'run_id': 'r1',
          'message_id': 'mx',
          'thread_id': 'other-thread',
          'question': 'Elsewhere',
          'choices': const [],
          'status': 'pending',
        },
      ],
    );
    final questions = threadQuestions([r], threadId);
    expect(questions.keys, ['m2']);
    expect(questions['m2']!.choices.single.label, 'A');
  });

  group('retryableFailure', () {
    test('the newest provider failure, after its Retry-After', () {
      final failed = Run.fromJson({
        ...run('r1', 'failed', createdAt: at(10)).raw,
        'failure': {'family': 'rate', 'retry_after_seconds': 30},
      });
      final early = retryableFailure([failed], at(10));
      expect(early!.run.id, 'r1');
      expect(early.ready, isFalse);
      expect(retryableFailure([failed], at(11))!.ready, isTrue);
    });

    test('never an "other" failure, nor one already retried', () {
      final other = run('r1', 'failed', errorCode: 'tool_crashed');
      expect(retryableFailure([other], at(20)), isNull);
      final rate = run('r2', 'failed', errorCode: 'rate_limited');
      final retry = Run.fromJson({
        ...run('r3', 'queued', createdAt: at(9)).raw,
        'model_metadata': {'retry_of': 'r2'},
      });
      expect(retryableFailure([rate, retry], at(20)), isNull);
    });
  });

  test('menu rules: edit and resend, task, submit marks', () {
    expect(canEditAndResend(m1), isTrue);
    expect(canEditAndResend(m2), isFalse);
    final withFile = message('m5', 5, 'user', 'see', at(1), attachments: ['f']);
    expect(canEditAndResend(withFile), isFalse);
    expect(canTurnIntoTask(m2), isTrue);
    expect(canTurnIntoTask(withFile), isFalse);
    final notRun = Message.fromJson({
      ...messageJson(
        id: 'm6',
        seq: 6,
        role: 'user',
        content: 'Buy',
        createdAt: at(1),
      ),
      'origin': 'ui_submit',
      'ui_submit': {'mark': 'not_run'},
    });
    expect(submitMark(notRun), 'not_run');
    expect(canEditAndResend(notRun), isFalse);
  });

  test('file helpers', () {
    expect(isImageType('image/png'), isTrue);
    expect(isImageType('application/pdf'), isFalse);
    expect(mimeBadge('application/pdf'), 'PDF');
    expect(mimeBadge('image/svg+xml'), 'SVG');
    expect(mimeFor('report.PDF'), 'application/pdf');
    expect(mimeFor('noext'), isNull);
    expect(
      plainLine('**Bold** and [link](https://x.y)\n`code`'),
      'Bold and link code',
    );
  });
}
