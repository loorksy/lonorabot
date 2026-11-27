import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/platform/background/poll_logic.dart';
import 'package:lonora/platform/heads_up/heads_up_rules.dart';
import 'package:lonora/platform/notifications/notification_payload.dart';

import 'platform_fixtures.dart';

PollState state({
  Map<String, int> seqs = const {},
  List<String> seen = const [],
  Map<String, List<NoteLine>> notified = const {},
  Set<String> notifiedAttention = const {},
  QuietHours? quiet,
  Set<String> off = const {},
  DateTime? since,
}) => PollState(
  ownerId: 'owner-1',
  server: 'https://lonora.example.com',
  since: since ?? t0.subtract(const Duration(minutes: 30)),
  seqs: seqs,
  seenAttention: seen,
  notified: notified,
  notifiedAttention: notifiedAttention,
  titles: const {'t-sara': 'Sara', 't-desk': 'Desk'},
  agentNames: const {'a-sara': 'Sara', 'a-omar': 'Omar'},
  quiet: quiet,
  off: off,
);

PollResult poll(
  PollState s, {
  List<Json> inbox = const [],
  List<Json> attention = const [],
  DateTime? now,
}) => computePoll(
  s,
  inbox: inbox,
  attention: attention,
  now: now ?? t0,
  newMessage: 'New message',
  attentionText: (code, _) => 'title:$code',
);

void main() {
  group('messages', () {
    test("a new agent answer becomes the conversation's notification", () {
      final r = poll(
        state(seqs: {'t-sara': 4}),
        inbox: [
          inboxJson(
            't-sara',
            agentId: 'a-sara',
            unread: 2,
            last: lastMessage(
              id: 'm5',
              seq: 5,
              agentId: 'a-sara',
              content: '**EURUSD** closed at 1.08',
            ),
          ),
        ],
      );
      expect(r.notes, hasLength(1));
      final n = r.notes.single;
      expect(n.kind, PlannedKind.message);
      expect(n.channel, LnChannels.messages);
      expect(n.title, 'Sara');
      expect(n.body, 'EURUSD closed at 1.08');
      expect(n.count, 2);
      expect(n.id, threadNotificationId('t-sara'));
      expect(n.payload, const NotificationPayload.thread('t-sara'));
      expect(r.next.seqs['t-sara'], 5);
      expect(r.next.notified['t-sara'], [
        const NoteLine('EURUSD closed at 1.08'),
      ]);
    });

    test(
      'nothing for an unchanged seq, the owner, read, muted or archived',
      () {
        Json row({
          int seq = 5,
          String role = 'assistant',
          int unread = 1,
          bool muted = false,
          bool archived = false,
        }) => inboxJson(
          't-sara',
          agentId: 'a-sara',
          unread: unread,
          muted: muted,
          archived: archived,
          last: lastMessage(id: 'm', seq: seq, role: role, agentId: 'a-sara'),
        );
        final base = state(seqs: {'t-sara': 4});
        expect(poll(state(seqs: {'t-sara': 5}), inbox: [row()]).notes, isEmpty);
        expect(poll(base, inbox: [row(role: 'user')]).notes, isEmpty);
        expect(poll(base, inbox: [row(unread: 0)]).notes, isEmpty);
        expect(poll(base, inbox: [row(muted: true)]).notes, isEmpty);
        expect(poll(base, inbox: [row(archived: true)]).notes, isEmpty);
        // Still advanced: a later check does not announce it either.
        expect(poll(base, inbox: [row(muted: true)]).next.seqs['t-sara'], 5);
      },
    );

    test('older than the baseline, an agent switched off, or quiet hours', () {
      final row = inboxJson(
        't-sara',
        agentId: 'a-sara',
        unread: 1,
        last: lastMessage(
          id: 'm',
          seq: 5,
          agentId: 'a-sara',
          at: t0.subtract(const Duration(hours: 2)),
        ),
      );
      expect(poll(state(seqs: {'t-sara': 4}), inbox: [row]).notes, isEmpty);
      final fresh = inboxJson(
        't-sara',
        agentId: 'a-sara',
        unread: 1,
        last: lastMessage(id: 'm', seq: 5, agentId: 'a-sara'),
      );
      expect(
        poll(
          state(seqs: {'t-sara': 4}, off: {'a-sara'}),
          inbox: [fresh],
        ).notes,
        isEmpty,
      );
      expect(
        poll(
          state(
            seqs: {'t-sara': 4},
            quiet: const QuietHours(
              start: 9 * 60,
              end: 11 * 60,
              timezone: 'Asia/Riyadh',
            ),
          ),
          inbox: [fresh],
          now: DateTime(2026, 11, 27, 10),
        ).notes,
        isEmpty,
      );
    });

    test('a group line names its speaker; lines accumulate up to five', () {
      var s = state(
        seqs: {'t-desk': 1},
        notified: {
          't-desk': [
            for (var i = 0; i < 5; i++) NoteLine('old $i', who: 'Sara'),
          ],
        },
      );
      final r = poll(
        s,
        inbox: [
          inboxJson(
            't-desk',
            groupId: 'g-desk',
            unread: 6,
            last: lastMessage(id: 'm', seq: 2, agentId: 'a-omar', content: ''),
          ),
        ],
      );
      final n = r.notes.single;
      expect(n.groupConversation, isTrue);
      expect(n.title, 'Desk');
      expect(n.lines, hasLength(maxNotificationLines));
      expect(n.lines.first.text, 'old 1');
      expect(n.lines.last, const NoteLine('New message', who: 'Omar'));
      s = r.next;
      expect(s.notified['t-desk'], n.lines);
    });

    test('a conversation read elsewhere loses its notification', () {
      final r = poll(
        state(
          seqs: {'t-sara': 5},
          notified: {
            't-sara': [const NoteLine('hi')],
          },
        ),
        inbox: [
          inboxJson(
            't-sara',
            agentId: 'a-sara',
            last: lastMessage(id: 'm', seq: 5, agentId: 'a-sara'),
          ),
        ],
      );
      expect(r.clearThreads, ['t-sara']);
      expect(r.next.notified, isEmpty);
    });

    test('a new conversation (no stored seq) announces a fresh answer', () {
      final r = poll(
        state(),
        inbox: [
          inboxJson(
            't-new',
            agentId: 'a-new',
            unread: 1,
            last: lastMessage(id: 'm', seq: 1, agentId: 'a-new'),
          ),
        ],
      );
      expect(r.notes.single.title, 'Lonora');
    });
  });

  group('attention', () {
    test('urgent items post once on the attention channel', () {
      final item = attentionJson('at1', agentId: 'a-sara', threadId: 't-sara');
      final r = poll(state(), attention: [item]);
      final n = r.notes.single;
      expect(n.kind, PlannedKind.attention);
      expect(n.channel, LnChannels.attention);
      expect(n.body, 'title:approval_required');
      expect(n.title, 'Sara');
      expect(
        n.payload,
        const NotificationPayload.attention(threadId: 't-sara'),
      );
      expect(r.next.seenAttention, ['at1']);
      expect(r.next.notifiedAttention, {'at1'});
      expect(poll(r.next, attention: [item]).notes, isEmpty);
    });

    test(
      'push codes are urgent; other items are quiet and respect quiet hours',
      () {
        final pushCode = attentionJson(
          'a1',
          code: 'broker_connection_lost',
          importance: 'informational',
        );
        expect(
          poll(state(), attention: [pushCode]).notes.single.channel,
          LnChannels.attention,
        );
        final info = attentionJson(
          'a2',
          code: 'agent_notification',
          importance: 'informational',
          parameters: {'summary': 'Weekly recap ready'},
        );
        final r = poll(state(), attention: [info]);
        expect(r.notes.single.channel, LnChannels.status);
        expect(r.notes.single.body, 'Weekly recap ready');
        expect(
          poll(
            state(
              quiet: const QuietHours(
                start: 9 * 60,
                end: 11 * 60,
                timezone: 'Asia/Riyadh',
              ),
            ),
            attention: [info],
            now: DateTime(2026, 11, 27, 10),
          ).notes,
          isEmpty,
        );
        // Urgent ones ignore quiet hours.
        expect(
          poll(
            state(
              quiet: const QuietHours(
                start: 9 * 60,
                end: 11 * 60,
                timezone: 'Asia/Riyadh',
              ),
            ),
            attention: [attentionJson('a3', importance: 'critical')],
            now: DateTime(2026, 11, 27, 10),
          ).notes,
          hasLength(1),
        );
      },
    );

    test('resolved items lose their notification; old ones are only seen', () {
      final r = poll(state(notifiedAttention: {'gone'}), attention: []);
      expect(r.clearAttention, ['gone']);
      expect(r.next.notifiedAttention, isEmpty);
      final old = poll(
        state(),
        attention: [
          attentionJson('old', at: t0.subtract(const Duration(hours: 3))),
        ],
      );
      expect(old.notes, isEmpty);
      expect(old.next.seenAttention, ['old']);
    });
  });

  test('baseline: everything now is seen and nothing is announced', () {
    final b = baselineState(
      ownerId: 'o',
      server: 's',
      inbox: [
        inboxJson('t1', last: lastMessage(id: 'm', seq: 9)),
        inboxJson('t2'),
      ],
      attention: [attentionJson('x')],
      now: t0,
    );
    expect(b.seqs, {'t1': 9, 't2': 0});
    expect(b.seenAttention, ['x']);
    expect(b.since, t0);
  });

  test('PollState survives its JSON file', () {
    final s = state(
      seqs: {'t': 3},
      seen: ['a'],
      notified: {
        't': [const NoteLine('x', who: 'Sara')],
      },
      notifiedAttention: {'a'},
      quiet: const QuietHours(start: 1, end: 2, timezone: 'Asia/Riyadh'),
      off: {'a-x'},
    ).copyWith(foregroundAt: t0);
    final back = PollState.fromJson(s.toJson())!;
    expect(back.toJson(), s.toJson());
    expect(back.foregroundActive(t0.add(const Duration(minutes: 1))), isTrue);
    expect(back.foregroundActive(t0.add(const Duration(minutes: 5))), isFalse);
    expect(PollState.fromJson({'owner': 'o'}), isNull);
  });
}
