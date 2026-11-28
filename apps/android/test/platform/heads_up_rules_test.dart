import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/platform/heads_up/heads_up_rules.dart';

import 'platform_fixtures.dart';

void main() {
  group('inQuietHours', () {
    test('no window, or start == end, is never quiet', () {
      expect(inQuietHours(null, t0), isFalse);
      expect(inQuietHours(const QuietHours(start: 60), t0), isFalse);
      expect(inQuietHours(const QuietHours(start: 60, end: 60), t0), isFalse);
    });

    test('a same-day window on the UTC clock', () {
      const q = QuietHours(start: 9 * 60, end: 11 * 60, timezone: 'UTC');
      expect(inQuietHours(q, DateTime.utc(2026, 1, 1, 10, 30)), isTrue);
      expect(inQuietHours(q, DateTime.utc(2026, 1, 1, 11)), isFalse);
      expect(inQuietHours(q, DateTime.utc(2026, 1, 1, 8, 59)), isFalse);
    });

    test('a window crossing midnight', () {
      const q = QuietHours(start: 22 * 60, end: 7 * 60, timezone: 'UTC');
      expect(inQuietHours(q, DateTime.utc(2026, 1, 1, 23)), isTrue);
      expect(inQuietHours(q, DateTime.utc(2026, 1, 1, 3)), isTrue);
      expect(inQuietHours(q, DateTime.utc(2026, 1, 1, 7)), isFalse);
      expect(inQuietHours(q, DateTime.utc(2026, 1, 1, 12)), isFalse);
    });

    test("another zone reads on the offset the phone resolved for it, the phone's zone on "
        'its own clock', () {
      // 22:00–07:00 in a zone at UTC+3: 20:30 UTC is 23:30 there.
      const q = QuietHours(
        start: 22 * 60,
        end: 7 * 60,
        timezone: 'Asia/Riyadh',
        offsetMinutes: 180,
      );
      expect(inQuietHours(q, DateTime.utc(2026, 1, 1, 20, 30)), isTrue);
      expect(inQuietHours(q, DateTime.utc(2026, 1, 1, 18, 30)), isFalse);
      expect(inQuietHours(q, DateTime.utc(2026, 1, 1, 3, 59)), isTrue);
      expect(inQuietHours(q, DateTime.utc(2026, 1, 1, 4)), isFalse);
      // The offset rides along in the background check's file, never to the server.
      final stored = QuietHours.fromJson(q.toJson())!;
      expect(stored.offsetMinutes, 180);
      expect(const QuietHours(start: 1, end: 2).toJson(), {
        'quiet_start_minute': 1,
        'quiet_end_minute': 2,
        'timezone': 'UTC',
      });
      // Without an offset the phone's clock decides.
      final local = DateTime(2026, 1, 1, 23);
      expect(
        inQuietHours(
          const QuietHours(
            start: 22 * 60,
            end: 7 * 60,
            timezone: 'Asia/Riyadh',
          ),
          local,
        ),
        isTrue,
      );
    });

    test('reads minutes when the server sent them, else hours', () {
      final minutes = QuietHours.fromJson({
        'quiet_start_hour': 22,
        'quiet_end_hour': 7,
        'quiet_start_minute': 22 * 60 + 30,
        'quiet_end_minute': 6 * 60 + 45,
        'timezone': 'Asia/Riyadh',
      })!;
      expect(minutes.start, 1350);
      expect(minutes.end, 405);
      expect(minutes.timezone, 'Asia/Riyadh');
      final hours = QuietHours.fromJson({
        'quiet_start_hour': 22,
        'quiet_end_hour': 7,
        'timezone': 'UTC',
      })!;
      expect(hours.start, 1320);
      expect(hours.end, 420);
      expect(QuietHours.fromJson(null), isNull);
    });
  });

  test('attentionAlwaysShows: critical and action_required only', () {
    expect(attentionAlwaysShows('critical'), isTrue);
    expect(attentionAlwaysShows('action_required'), isTrue);
    expect(attentionAlwaysShows('opportunity'), isFalse);
    expect(attentionAlwaysShows(null), isFalse);
  });

  test('DeliveryRules.offFrom reads in_app == false', () {
    expect(
      DeliveryRules.offFrom({
        'a1': {'in_app': true, 'calls': true},
        'a2': {'in_app': false, 'calls': true},
        'a3': {'calls': false},
      }),
      {'a2'},
    );
  });

  group('messageBanner', () {
    final opened = t0.subtract(const Duration(minutes: 1));
    HeadsUpBanner? banner(
      dynamic event, {
      String? current,
      DeliveryRules rules = const DeliveryRules(),
      bool saraMuted = false,
      bool deskArchived = false,
    }) => messageBanner(
      event,
      shell: demoShell(saraMuted: saraMuted, deskArchived: deskArchived),
      current: current,
      rules: rules,
      openedAt: opened,
      now: t0,
      newMessage: 'New message',
    );

    test("an agent's answer in another chat shows, cut to one plain line", () {
      final b = banner(
        messageCreated(
          thread: 't-sara',
          id: 'm1',
          agentId: 'a-sara',
          content: '**Done**: EURUSD +0.4% today. ${'word ' * 40}',
        ),
        current: 't-omar',
      )!;
      expect(b.threadId, 't-sara');
      expect(b.agentId, 'a-sara');
      expect(b.kind, HeadsUpKind.message);
      expect(b.who, isNull);
      expect(b.text, startsWith('Done: EURUSD \u2066+0.4%\u2069 today.'));
      expect(b.text, endsWith('…'));
      expect(b.key, 'm1');
    });

    test('none for the open chat, the owner, or before the app opened', () {
      expect(
        banner(
          messageCreated(thread: 't-sara', id: 'm', agentId: 'a-sara'),
          current: 't-sara',
        ),
        isNull,
      );
      expect(
        banner(messageCreated(thread: 't-sara', id: 'm', role: 'user')),
        isNull,
      );
      expect(
        banner(
          messageCreated(
            thread: 't-sara',
            id: 'm',
            agentId: 'a-sara',
            at: opened.subtract(const Duration(seconds: 6)),
          ),
        ),
        isNull,
      );
      // 5 s of slack.
      expect(
        banner(
          messageCreated(
            thread: 't-sara',
            id: 'm',
            agentId: 'a-sara',
            at: opened.subtract(const Duration(seconds: 4)),
          ),
        ),
        isNotNull,
      );
    });

    test('mute, archive, an unknown chat, quiet hours and the in-app rule', () {
      final event = messageCreated(
        thread: 't-sara',
        id: 'm',
        agentId: 'a-sara',
      );
      expect(banner(event, saraMuted: true), isNull);
      expect(
        banner(
          messageCreated(thread: 't-desk', id: 'm', agentId: 'a-sara'),
          deskArchived: true,
        ),
        isNull,
      );
      expect(
        banner(messageCreated(thread: 't-unknown', id: 'm', agentId: 'a-x')),
        isNull,
      );
      expect(
        banner(
          event,
          rules: const DeliveryRules(
            quiet: QuietHours(start: 9 * 60, end: 11 * 60, timezone: 'UTC'),
          ),
        ),
        isNull,
      );
      expect(
        banner(event, rules: const DeliveryRules(off: {'a-sara'})),
        isNull,
      );
    });

    test('a group shows the speaker apart; no words read «New message»', () {
      final group = banner(
        messageCreated(thread: 't-desk', id: 'm', agentId: 'a-omar'),
      )!;
      expect(group.groupId, 'g-desk');
      expect(group.who, 'Omar:');
      final empty = banner(
        messageCreated(
          thread: 't-sara',
          id: 'm',
          agentId: 'a-sara',
          content: '',
        ),
      )!;
      expect(empty.text, 'New message');
      expect(empty.who, isNull);
    });
  });

  group('attentionBanner', () {
    final opened = t0.subtract(const Duration(minutes: 1));
    HeadsUpBanner? banner(Map<String, dynamic> item) => attentionBanner(
      item,
      shell: demoShell(),
      openedAt: opened,
      title: 'Approval needed',
    );

    test(
      'urgent items show on their agent chat, with the summary or title',
      () {
        final b = banner(attentionJson('at1', agentId: 'a-sara'))!;
        expect(b.threadId, 't-sara');
        expect(b.kind, HeadsUpKind.attention);
        expect(b.text, 'Approval needed');
        expect(
          banner(
            attentionJson(
              'at2',
              agentId: 'a-sara',
              parameters: {'summary': 'Buy 0.1 lot?'},
            ),
          )!.text,
          'Buy 0.1 lot?',
        );
      },
    );

    test('not urgent, or older than the app, shows nothing', () {
      expect(
        banner(
          attentionJson('a', agentId: 'a-sara', importance: 'opportunity'),
        ),
        isNull,
      );
      expect(
        banner(
          attentionJson(
            'a',
            agentId: 'a-sara',
            at: opened.subtract(const Duration(minutes: 1)),
          ),
        ),
        isNull,
      );
    });

    test(
      'a group item goes to the group; broker health to the personal agent',
      () {
        expect(
          banner(
            attentionJson(
              'a',
              agentId: 'a-sara',
              parameters: {'group_id': 'g-desk'},
            ),
          )!.threadId,
          't-desk',
        );
        expect(
          banner(
            attentionJson(
              'a',
              code: 'broker_connection_lost',
              importance: 'critical',
            ),
          )!.threadId,
          't-omar',
        );
      },
    );

    test('broker health opens «التعطل والاستعادة» on its account; others their chat', () {
      final health = banner(
        attentionJson(
          'h1',
          code: 'broker_connection_lost',
          importance: 'critical',
          parameters: {'account_id': 'acct-1'},
        ),
      )!;
      expect(health.location, '/settings/recovery?account=acct-1');
      expect(health.withText('x').location, health.location);
      expect(
        banner(
          attentionJson(
            'h2',
            code: 'broker_token_rejected',
            importance: 'critical',
          ),
        )!.location,
        '/settings/recovery',
      );
      expect(banner(attentionJson('h3', agentId: 'a-sara'))!.location, isNull);
    });
  });
}
