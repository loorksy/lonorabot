import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/models/models.dart';

void main() {
  group('Group.fromJson', () {
    test('reads the conversation from state.thread_id (server record)', () {
      final g = Group.fromJson({
        'id': 'g1',
        'version': 3,
        'payload': {
          'name': 'Desk',
          'member_ids': ['a', 'b'],
        },
        'state': {'thread_id': 't-group'},
      });
      expect(g.threadId, 't-group');
      expect(g.name, 'Desk');
      expect(g.version, 3);
    });

    test('falls back to a top-level or payload thread_id', () {
      expect(Group.fromJson({'id': 'g', 'thread_id': 't1'}).threadId, 't1');
      expect(
        Group.fromJson({
          'id': 'g',
          'state': {'thread_id': ''},
          'payload': {'thread_id': 't2'},
        }).threadId,
        't2',
      );
      expect(Group.fromJson({'id': 'g'}).threadId, isNull);
    });
  });
}
