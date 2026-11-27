// The Dart ports of @lonora/core against the TS functions' own outputs: every case in
// fixtures/core_cases.json was computed by running the TS source (tool/i18n/port_i18n.mjs).
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/l10n/l10n.dart';

Map<String, Object?> m(Object? value) => (value as Map).cast<String, Object?>();
Map<String, Object?>? mOrNull(Object? value) => value == null ? null : m(value);
DateTime at(Object? iso) => DateTime.parse(iso as String);

/// The Dart output as the TS prints it: Android puts a no-break space before the « · » of the
/// metadata lines (Q11, [dotSeparator]) where the TS has a plain space.
Object? tsSpacing(Object? value) => switch (value) {
  String s => s.replaceAll(dotSeparator, ' · '),
  List l => [for (final item in l) tsSpacing(item)],
  Map map => {for (final e in map.entries) e.key: tsSpacing(e.value)},
  _ => value,
};

/// Android's own rules where it deliberately differs from the TS output (owner decisions; the
/// Android side is pinned in date_digits_test.dart):
/// * a date or time of day prints Arabic-Indic digits in Arabic, so the rows of these functions
///   are compared with every digit read by value;
const datedFunctions = {
  'ownerActionCard',
  'watchUntil',
  'agentStatusLine',
  'sourceLine',
  'serverLine',
  'readinessTime',
  'tradingReadinessLine',
};

/// * the conversation's time separator shows the time alone today and the date otherwise,
///   without naming the day, so its TS rows are not compared.
const androidOwnRules = {'formatTimeSeparator'};

/// [value] with Arabic-Indic digits read as Latin ones.
Object? latinDigits(Object? value) => switch (value) {
  String s => s.replaceAllMapped(
    RegExp('[\u0660-\u0669]'),
    (m) => String.fromCharCode(m[0]!.codeUnitAt(0) - 0x0660 + 0x30),
  ),
  List l => [for (final item in l) latinDigits(item)],
  Map map => {for (final e in map.entries) e.key: latinDigits(e.value)},
  _ => value,
};

void main() {
  final cases = (jsonDecode(
    File('test/l10n/fixtures/core_cases.json').readAsStringSync(),
  ) as List).cast<Map<String, dynamic>>();

  setUpAll(ensureDateFormatting);

  final functions = <String, Object? Function(List<dynamic> a)>{
    // agent-permission-errors / financial-boundary
    'agentPermissionError': (a) => agentPermissionError(a[0], a[1]),
    'financialBoundaryError': (a) => financialBoundaryError(a[0], a[1]),
    'financialResultReason': (a) => financialResultReason(a[0], a[1], a[2]),
    'operationStatusKey': (a) => operationStatusKey(a[0], a[1]),
    'operationStatusText': (a) => operationStatusText(a[0], a[1], a[2]),
    'approvalStatusText': (a) => approvalStatusText(a[0], a[1]),
    'approvalEndTone': (a) => approvalEndTone(m(a[0])),
    'brokerTicketLabel': (a) => brokerTicketLabel(a[0]),
    'brokerPriceLabel': (a) => brokerPriceLabel(a[0], a[1]),
    'failedResultFallback': (a) => failedResultFallback(a[0]),
    'brokerWordsLabel': (a) => brokerWordsLabel(a[0]),
    'runStatusText': (a) => runStatusText(a[0], a[1]),
    // owner-actions
    'ownerActionError': (a) => ownerActionError(a[0], a[1]),
    'mandateLine': (a) => mandateLine(a[0], a[1]),
    'modeChangeLine': (a) => modeChangeLine(a[0], a[1], a[2], a[3]),
    'ownerActionStatus': (a) => ownerActionStatus(m(a[0]), a[1]),
    'ownerActionCard': (a) => ownerActionCard(m(a[0]), a[1], at(a[2])).toJson(),
    // owner-profile
    'ownerProfileError': (a) => ownerProfileError(a[0], a[1]),
    'ownerProfileLabel': (a) => ownerProfileLabel(a[0], a[1]),
    'reachMeLabel': (a) => reachMeLabel(a[0], a[1]),
    'reachMeHint': (a) => reachMeHint(a[0], a[1]),
    'replyLanguageLabel': (a) => replyLanguageLabel(a[0], a[1]),
    'preferenceFieldLabel': (a) => preferenceFieldLabel(a[0], a[1]),
    'preferenceValueText': (a) => preferenceValueText(a[0], a[1], a[2]),
    // chatgpt-plan
    'chatgptError': (a) => chatgptError(a[0], a[1]),
    'continuingAsLine': (a) => continuingAsLine(a[0], a[1]),
    'chatgptRow': (a) {
      final row = chatgptRow(mOrNull(a[0]), a[1]);
      return row == null ? null : {'line': row.line, 'signOut': row.signOut};
    },
    'signOutLine': (a) => signOutLine(m(a[0]), a[1]),
    'planLimitReached': (a) => planLimitReached(mOrNull(a[0])),
    // agent-status
    'watchCondition': (a) => watchCondition(m(a[0]), a[1]),
    'watchUntil': (a) => watchUntil(m(a[0]), a[1], at(a[2])),
    'agentStatusLine': (a) => agentStatusLine(m(a[0]), a[1], at(a[2])),
    'liveAvatarState': (a) => liveAvatarState(mOrNull(a[0])),
    // agent-model
    'tokenCount': (a) => tokenCount(a[0], a[1]),
    'usageLine': (a) => usageLine(m(a[0]), a[1], a[2]),
    'agentModelLines': (a) => agentModelLines(m(a[0]), a[1]),
    'modelName': (a) => modelName(mOrNull(a[0])),
    'offersDefaultModel': (a) => offersDefaultModel(m(a[0])),
    'usesChatGptPlan': (a) => usesChatGptPlan(m(a[0])),
    // capabilities
    'sourceLine': (a) => sourceLine(m(a[0]), a[1]),
    'skillLine': (a) => skillLine(m(a[0]), a[1]),
    'serverLine': (a) => serverLine(m(a[0]), a[1]),
    'integrationLine': (a) => integrationLine(m(a[0]), a[1]),
    'builtInLine': (a) => builtInLine(m(a[0]), a[1]),
    'toolTitle': (a) => toolTitle(m(a[0]), a[1]),
    // trading-readiness
    'readinessTime': (a) => readinessTime(a[0], a[1], at(a[2])),
    'tradingReadinessLine': (a) {
      final names = m(a[3]);
      return tradingReadinessLine(
        m(a[0]),
        a[1],
        at(a[2]),
        (id) => names[id] as String?,
      );
    },
    'tradingReadinessTone': (a) => tradingReadinessTone(m(a[0])),
    'listSeparator': (a) => listSeparator(a[0]),
    'isolate': (a) => isolate(a[0]),
    'textDirection': (a) => switch (readingDirection(a[0])) {
      null => null,
      final direction => direction.name,
    },
    // turn-activity
    'activityCallLabel': (a) => activityCallLabel(
      toolset: m(a[0])['toolset'] as String?,
      effect: m(a[0])['effect'] as String?,
      name: m(a[0])['name'] as String?,
      locale: a[1],
    ),
    'turnActivity': (a) {
      final result = turnActivity(m(a[0]), (a[1] as List).map(m).toList());
      return {
        'phase': result.phase,
        'avatar': result.avatar,
        'calls': [for (final call in result.calls) call.toJson()],
        'observedAt': result.observedAt,
      };
    },
    // order-line
    'orderLineText': (a) => orderLineText(a[0], a[1]),
    'orderLineAction': (a) {
      final action = orderLineAction(m(a[0]), a[1]);
      return {
        'label': action.label,
        'volume': action.volume,
        'direction': action.direction,
      };
    },
    // time-separators, attachments, list rows, files
    'needsTimeSeparator': (a) => needsTimeSeparator(a[0], a[1]),
    'attachmentTooLarge': (a) => attachmentTooLarge(a[0]),
    'clockTime': (a) => clockTime(a[0]),
    'formatFileSize': (a) => formatFileSize(a[0], a[1]),
  };

  for (final MapEntry(key: name, value: call) in functions.entries) {
    test(name, () {
      final rows = cases.where((row) => row['fn'] == name).toList();
      expect(rows, isNotEmpty, reason: 'no fixture for $name');
      final Object? Function(Object?) digits = datedFunctions.contains(name)
          ? latinDigits
          : (value) => value;
      for (final row in rows) {
        expect(
          digits(tsSpacing(call(row['args'] as List))),
          digits(row['out']),
          reason: '$name${jsonEncode(row['args'])}',
        );
      }
    });
  }

  test('Q11: a metadata line never wraps before its « · »', () {
    final line = sourceLine({
      'kind': 'news_feed',
      'label': 'old.example.com',
      'added_via': 'owner',
      'active': false,
    }, 'ar');
    expect(line, contains('\u00a0· '));
    expect(line, isNot(contains(' · ')));
    expect(
      serverLine({
        'name': 'Docs',
        'trusted_tier': 'read',
        'enabled': true,
      }, 'en'),
      isNot(contains(' · ')),
    );
    // The other metadata lines the l10n layer builds use the same join.
    for (final locale in ['ar', 'en']) {
      final readiness = tradingReadinessLine(
        {
          'state': 'on_its_own',
          'params': {
            'account_id': 'a1',
            'symbols': ['XAUUSD'],
          },
        },
        locale,
        DateTime(2026, 11, 27),
        (_) => 'Demo',
      );
      expect(dotSeparator.allMatches(readiness), hasLength(3));
      expect(readiness, isNot(contains(' · ')));
      expect(
        modeChangeLine('Atlas', 'full', 2, locale),
        allOf(contains(dotSeparator), isNot(contains(' · '))),
      );
      expect(
        watchCondition({'kind': 'calendar'}, locale),
        allOf(contains(dotSeparator), isNot(contains(' · '))),
      );
    }
  });

  test('every fixture has a Dart port', () {
    expect(
      cases.map((row) => row['fn']).toSet().difference({
        ...functions.keys,
        ...androidOwnRules,
      }),
      isEmpty,
    );
    expect(functions.keys.toSet().containsAll(datedFunctions), isTrue);
  });
}
