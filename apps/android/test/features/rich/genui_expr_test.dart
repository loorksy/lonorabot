// The lonora-ui v2 expression evaluator against the shared vectors
// (tests/fixtures/genui/expr-vectors.json, copied into fixtures/), which keep the TS, Python
// and Dart evaluators equal, plus the template and formatting rules.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/features/rich/genui/expr.dart';
import 'package:lonora/features/rich/genui/functions.dart';

bool _same(Object? a, Object? b) {
  if (a is num && b is num) return a == b;
  if (a is List && b is List) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (!_same(a[i], b[i])) return false;
    }
    return true;
  }
  if (a is Map && b is Map) {
    if (a.length != b.length) return false;
    return a.keys.every((k) => b.containsKey(k) && _same(a[k], b[k]));
  }
  return a == b;
}

void main() {
  final vectors = jsonDecode(
    File('test/features/rich/fixtures/expr-vectors.json').readAsStringSync(),
  ) as Map<String, dynamic>;
  final env = Env(
    values: Map<String, Object?>.from(vectors['values'] as Map),
    facts: Map<String, Object?>.from(vectors['facts'] as Map),
  );

  group('shared vectors', () {
    for (final raw in vectors['cases'] as List) {
      final c = raw as Map<String, dynamic>;
      test(c['src'], () {
        final got = evaluate(c['src'], env);
        expect(
          _same(got, c['expected']),
          isTrue,
          reason: '${c['src']} → $got, expected ${c['expected']}',
        );
      });
    }
  });

  test('arity table matches the shared fixture', () {
    final arity = jsonDecode(
      File('test/features/rich/fixtures/arity.json').readAsStringSync(),
    ) as Map<String, dynamic>;
    for (final MapEntry(:key, :value) in arity.entries) {
      final pair = value as List;
      expect(genuiArity[key], (pair[0], pair[1]), reason: key);
    }
  });

  group('templates and display', () {
    test('numbers group with en-US commas, integers without decimals', () {
      expect(display(2400.0), '2,400');
      expect(display(1234.5678), '1,234.57');
      expect(display(-0.004), '0');
      expect(display([1.0, 2.5]), '1، 2.5');
      expect(display(null), '');
      expect(display(true), 'true');
    });

    test('renderTemplate fills expressions, failures read empty', () {
      final e = environment(
        {'risk': 1, 'balance': 10000},
        {'cash': r'$balance*$risk/100'},
        const {},
      );
      expect(renderTemplate(r'{@Fmt($cash,0)} $', e), r'100 $');
      expect(renderTemplate('a{1+}b', e), 'ab');
      expect(renderTemplate('{@Money(12.5,2)}', e), '12.50');
    });

    test('formatters', () {
      final usd = Env(
        values: const {},
        facts: const {},
        context: const FormatContext(currency: 'USD'),
      );
      expect(evaluate('@Money(-1234.5,2)', usd), r'-$1,234.50');
      expect(evaluate('@Signed(-3,1)', usd), '−3.0');
      expect(evaluate('@Pct(12.345,1)', usd), '12.3%');
      expect(evaluate("@Plural(3,'one','two','few','many')", usd), 'few');
      expect(evaluate("@Plural(0,'one','two','few','many')", usd), 'many');
    });

    test('Random only inside a set action', () {
      expect(evaluate('@Random()', env), isNull);
      final allowed = env.withContext(const FormatContext(allowRandom: true));
      final value = evaluate('@Random(1,3,true)', allowed);
      expect(value, isA<num>());
      expect((value as num) >= 1 && value <= 3, isTrue);
    });

    test('DayLabel names today and tomorrow in both languages', () {
      final now = DateTime.utc(2026, 11, 27, 9);
      final ar = Env(
        values: const {},
        facts: const {},
        context: FormatContext(now: now),
      );
      final en = Env(
        values: const {},
        facts: const {},
        context: FormatContext(now: now, language: 'en'),
      );
      expect(evaluate("@DayLabel('2026-11-27')", ar), 'اليوم 27 نوفمبر');
      expect(evaluate("@DayLabel('2026-11-28')", en), 'Tomorrow November 28');
      expect(evaluate("@DayLabel('2026-11-30')", en), 'Monday November 30');
      expect(evaluate("@DayLabel('2026-13-01')", en), isNull);
    });
  });
}
