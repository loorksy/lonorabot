import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/platform/notifications/notification_payload.dart';

void main() {
  group('NotificationPayload', () {
    test('a thread payload round-trips and opens the conversation', () {
      const p = NotificationPayload.thread('a31a5846-d84e', around: 17);
      final back = NotificationPayload.decode(p.encode());
      expect(back, p);
      expect(back!.location, '/chats/thread/a31a5846-d84e?around=17');
    });

    test('an attention payload opens its conversation, else the list', () {
      expect(
        const NotificationPayload.attention(threadId: 't1').location,
        '/chats/thread/t1',
      );
      expect(const NotificationPayload.attention().location, '/attention');
      expect(
        NotificationPayload.decode(
          const NotificationPayload.attention().encode(),
        ),
        const NotificationPayload.attention(),
      );
    });

    test('agent and call payloads', () {
      expect(const NotificationPayload.agent('ag-1').location, '/agent/ag-1');
      final call = NotificationPayload.decode(
        const NotificationPayload.call().encode(),
      );
      expect(call?.target, NotificationTarget.call);
      expect(call?.location, isNull);
    });

    test('rejects foreign or unsafe payloads', () {
      for (final raw in [
        null,
        '',
        'not json',
        '[]',
        '{"t":"unknown","id":"x"}',
        '{"t":"thread"}',
        '{"t":"thread","id":"../settings"}',
        '{"t":"thread","id":"a b"}',
        '{"t":"agent","id":"${'x' * 81}"}',
      ]) {
        expect(NotificationPayload.decode(raw), isNull, reason: raw);
      }
    });

    test('a non-positive around is dropped', () {
      final p = NotificationPayload.decode(
        '{"t":"thread","id":"t1","around":0}',
      );
      expect(p, const NotificationPayload.thread('t1'));
      expect(p!.location, '/chats/thread/t1');
    });
  });

  group('notification ids', () {
    test('are stable, positive 31-bit and clear of the reserved range', () {
      final a = notificationIdFor('thread:abc');
      expect(a, notificationIdFor('thread:abc'));
      expect(a, greaterThanOrEqualTo(10000));
      expect(a, lessThanOrEqualTo(0x7fffffff));
      expect(threadNotificationId('abc'), a);
      expect(attentionNotificationId('abc'), isNot(a));
      // Known value (FNV-1a), so every isolate and every run agrees.
      expect(notificationIdFor(''), 0x811c9dc5 & 0x7fffffff);
    });
  });
}
