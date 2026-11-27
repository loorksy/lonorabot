// The count phrases against the TS functions' own outputs (fixtures written by
// tool/i18n/port_i18n.mjs, which runs the TS for 0, 1, 2, 3, 10, 11, 100 and more).
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/l10n/l10n.dart';

void main() {
  final cases = (jsonDecode(
    File('test/l10n/fixtures/plurals.json').readAsStringSync(),
  ) as List).cast<Map<String, dynamic>>();
  final now = DateTime.parse('2026-11-27T16:30:00');
  // Q12: English writes 2 in digits like every other count (the TS spells it out); Arabic keeps
  // its dual.
  const android = {
    'chatsWord["en",2]': '2 chats',
    'agentsWord["en",2]': '2 agents',
  };

  final functions = <String, Object? Function(List<dynamic> a)>{
    'chatsWord': (a) => chatsWord(a[0] as String, a[1] as int),
    'waitingSentText': (a) => waitingSentText(a[0] as String, a[1] as int),
    'agentsWord': (a) => agentsWord(a[0] as String, a[1] as int),
    'networkWaitingText': (a) =>
        networkWaitingText(a[0] as String, a[1] as int),
    'uncertainLine': (a) => uncertainLine(a[0] as num, a[1] as String),
    'tradingSubLine': (a) =>
        tradingSubLine(a[0] as int?, a[1] as String?, a[2] as String),
    'modeChangeLine': (a) => modeChangeLine(
      a[0] as String,
      a[1] as String,
      a[2] as num,
      a[3] as String,
    ),
    'tradingReadinessLine': (a) => tradingReadinessLine(
      (a[0] as Map).cast<String, Object?>(),
      a[1] as String,
      now,
    ),
    'arCount': (a) => arCount(a[0] as num),
    'plural': (a) => plural(
      a[0] as num,
      one: a[1] as String,
      two: a[2] as String,
      few: a[3] as String,
      many: a[4] as String,
      zero: a[5] as String,
    ),
  };

  for (final MapEntry(key: name, value: call) in functions.entries) {
    test(name, () {
      final rows = cases.where((row) => row['fn'] == name).toList();
      expect(rows, isNotEmpty);
      for (final row in rows) {
        final key = '$name${jsonEncode(row['args'])}';
        final out = call(row['args'] as List);
        expect(
          // Q11: Android's no-break space before the « · » is the TS's plain space.
          out is String ? out.replaceAll(dotSeparator, ' · ') : out,
          android[key] ?? row['out'],
          reason: key,
        );
      }
    });
  }

  test('every fixture has a Dart port', () {
    expect(cases.map((row) => row['fn']).toSet(), functions.keys.toSet());
  });

  test('the counts the brief names are covered for both languages', () {
    for (final fn in ['chatsWord', 'agentsWord', 'waitingSentText']) {
      for (final locale in ['ar', 'en']) {
        final counts = cases
            .where(
              (row) => row['fn'] == fn && (row['args'] as List)[0] == locale,
            )
            .map((row) => (row['args'] as List)[1]);
        expect(counts, containsAll([0, 1, 2, 3, 10, 11, 100]));
      }
    }
    // A spot check that the fixtures hold the TS functions' words.
    expect(agentsWord('ar', 11), '11 وكيلًا');
    expect(agentsWord('ar', 100), '100 وكيل');
    expect(chatsWord('ar', 3), '3 محادثات');
    expect(chatsWord('ar', 11), '11 محادثة');
    expect(agentsWord('ar', 2), 'وكيلان');
    expect(chatsWord('ar', 2), 'محادثتان');
    expect(
      [agentsWord('en', 1), agentsWord('en', 2), agentsWord('en', 3)],
      ['one agent', '2 agents', '3 agents'],
    );
  });
}
