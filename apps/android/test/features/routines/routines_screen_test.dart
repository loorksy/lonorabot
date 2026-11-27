// Routines: cards with When / Agent will / status, the detail actions (pause/resume, edit, delete
// with confirmation; never «run now» through /runs), the editor's repeat options and saves,
// execution history; goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/routines
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/routines/routine_editor.dart';
import 'package:lonora/features/routines/routines_screen.dart';

import '../agent_profile/wpe_harness.dart';

List<Map<String, Object?>> routinesFixture() => [
  {
    'id': 'r-1',
    'agent_id': 'a-gold',
    'title': 'Morning gold brief',
    'prompt': 'Summarize overnight gold moves and the key levels before London opens.',
    'cron': '30 7 * * 1-5',
    'timezone': 'Asia/Riyadh',
    'enabled': true,
    'next_run_at': '2026-11-30T04:30:00+00:00',
    'last_run_at': '2026-11-27T04:30:02+00:00',
  },
  {
    'id': 'r-2',
    'agent_id': 'a-gold',
    'title': 'مراجعة الأسبوع',
    'prompt': 'راجع صفقات الأسبوع واكتب ما تعلمته.',
    'cron': '0 18 * * 5',
    'timezone': 'Asia/Riyadh',
    'enabled': false,
    'next_run_at': '2026-11-27T15:00:00+00:00',
  },
  {
    'id': 'r-3',
    'agent_id': 'a-gold',
    'title': 'CPI check',
    'prompt': 'Check the CPI release and flatten if needed.',
    'run_at': '2026-11-12T13:25:00+00:00',
    'timezone': 'UTC',
    'enabled': false,
    'next_run_at': '2026-11-12T13:25:00+00:00',
    'last_run_at': '2026-11-12T13:25:01+00:00',
  },
];

void scriptRoutines() {
  fakeApi
    ..on('GET /routines', (_, _) => routinesFixture())
    ..on(
      'GET /routines/r-1/history',
      (_, _) => [
        {
          'id': 'run-1',
          'thread_id': 'work-1',
          'agent_id': 'a-gold',
          'status': 'completed',
          'trigger': 'routine',
          'model_metadata': {'origin_thread_id': 't-gold'},
          'created_at': '2026-11-27T04:30:02+00:00',
        },
      ],
    );
}

Future<void> pumpRoutines(WidgetTester tester, {String locale = 'en'}) =>
    pumpScreen(tester, const RoutinesScreen(agentId: 'a-gold'), locale: locale);

/// The device's time zone as the platform reports it.
void deviceZone(String zone) => TestDefaultBinaryMessengerBinding
    .instance
    .defaultBinaryMessenger
    .setMockMethodCallHandler(
      const MethodChannel('ai.lonora.android/platform'),
      (call) async => call.method == 'timeZone' ? zone : null,
    );

/// [editor] in a sheet over a placeholder page.
Future<void> openEditor(WidgetTester tester, Widget editor) async {
  await pumpScreen(
    tester,
    Builder(
      builder: (context) => Center(
        child: GestureDetector(
          onTap: () => showLnSheet<bool>(context, builder: (_) => editor),
          child: const Text('open'),
        ),
      ),
    ),
    locale: 'en',
  );
  await tapAndSettle(tester, find.text('open'));
}

/// The gold desk's watches: one conditional schedule, one without a prompt, one cancelled.
List<Map<String, Object?>> watchesFixture() => [
  {
    'id': 'w-1',
    'agent_id': 'a-gold',
    'version': 1,
    'payload': {
      'kind': 'price',
      'symbol': 'XAUUSD',
      'condition': 'above',
      'level': '2400',
      'prompt': 'Alert me when gold breaks out and say why.',
      'enabled': true,
    },
    'state': {'code': 'watch_active'},
  },
  {
    'id': 'w-2',
    'agent_id': 'a-gold',
    'version': 1,
    'payload': {
      'kind': 'price',
      'symbol': 'XAUUSD',
      'condition': 'below',
      'level': '2100',
      'enabled': true,
    },
    'state': {'code': 'watch_active'},
  },
  {
    'id': 'w-3',
    'agent_id': 'a-gold',
    'version': 2,
    'payload': {
      'kind': 'price',
      'symbol': 'XAUUSD',
      'condition': 'above',
      'level': '2500',
      'prompt': 'Old alert.',
      'enabled': false,
    },
    'state': {'code': 'watch_cancelled'},
  },
];

void main() {
  setUpAll(setUpWpeHarness);
  setUp(resetWpe);

  testWidgets('shows each routine as a schedule card', (tester) async {
    scriptRoutines();
    await pumpRoutines(tester);
    expect(find.textContaining('Morning gold brief'), findsOneWidget);
    expect(find.text('Weekdays at 07:30'), findsOneWidget);
    expect(find.text('When'), findsWidgets);
    expect(find.text('Agent will'), findsWidgets);
    expect(find.textContaining('Active · Next run'), findsOneWidget);
  });

  testWidgets('pauses from the card menu with only the switch', (tester) async {
    scriptRoutines();
    fakeApi.on(
      'PUT /routines/r-1',
      (body, _) => {...routinesFixture().first, 'enabled': false},
    );
    await pumpRoutines(tester);
    await tapAndSettle(tester, find.bySemanticsLabel('More').first);
    expect(find.text('Pause'), findsOneWidget);
    expect(find.text('Edit schedule'), findsOneWidget);
    expect(find.text('Delete schedule'), findsOneWidget);
    expect(find.textContaining('Run now'), findsNothing);
    await tapAndSettle(tester, find.text('Pause'));
    expect(fakeApi.callsTo('PUT', '/routines/r-1').single.body, {
      'enabled': false,
    });
    expect(fakeApi.calls.where((c) => c.path == '/runs'), isEmpty);
    await settleToasts(tester);
  });

  testWidgets('deleting asks first', (tester) async {
    scriptRoutines();
    fakeApi.on('DELETE /routines/r-1', (_, _) => {'deleted': true});
    await pumpRoutines(tester);
    await tapAndSettle(tester, find.bySemanticsLabel('More').first);
    await tapAndSettle(tester, find.text('Delete schedule'));
    expect(find.text('Delete this schedule?'), findsOneWidget);
    expect(fakeApi.callsTo('DELETE', '/routines/r-1'), isEmpty);
    await tapAndSettle(tester, find.text('Delete'));
    expect(fakeApi.callsTo('DELETE', '/routines/r-1'), hasLength(1));
    await settleToasts(tester);
  });

  testWidgets('history opens the conversation a run reports to', (
    tester,
  ) async {
    scriptRoutines();
    await pumpRoutines(tester);
    await tapAndSettle(tester, find.textContaining('Morning gold brief'));
    final history = find.text('Execution history');
    await tester.scrollUntilVisible(
      history,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, history);
    await tapAndSettle(tester, find.text('Completed').last);
    expect(shownRoute(tester), '/chats/thread/t-gold');
  });

  testWidgets('creates a weekly routine for this agent', (tester) async {
    scriptRoutines();
    fakeApi.on(
      'POST /routines/a-gold',
      (body, _) => {
        ...routinesFixture().first,
        ...(body! as Map<String, Object?>),
        'id': 'r-9',
      },
    );
    await pumpRoutines(tester);
    await tapAndSettle(tester, find.bySemanticsLabel('Create routine'));
    await tapAndSettle(tester, find.text('Repeat'));
    for (final option in [
      'Does not repeat',
      'Daily',
      'Weekly',
      'Monthly',
      'Weekdays',
      'Weekend',
      'Custom',
    ]) {
      expect(find.text(option), findsWidgets, reason: option);
    }
    await tapAndSettle(tester, find.text('Weekly'));
    await tester.enterText(
      find.byType(EditableText).first,
      'Plan the week ahead.',
    );
    await tester.pump();
    final save = find.text('Save');
    await tester.scrollUntilVisible(
      save,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, save);
    final body =
        fakeApi.callsTo('POST', '/routines/a-gold').single.body!
            as Map<String, Object?>;
    expect(body['prompt'], 'Plan the week ahead.');
    expect(body['title'], 'Plan the week ahead.');
    expect(body['cron'], matches(RegExp(r'^0 9 \* \* [0-6]$')));
    expect(body['timezone'], 'Asia/Riyadh');
    expect(body['enabled'], isTrue);
    expect(body.containsKey('run_at'), isFalse);
    await settleToasts(tester);
  });

  testWidgets('a routine kept in another time zone names it', (tester) async {
    scriptRoutines();
    deviceZone('Europe/London');
    await pumpRoutines(tester);
    expect(find.textContaining('Weekdays at 07:30 · '), findsOneWidget);
    expect(find.textContaining('Asia/Riyadh'), findsWidgets);
  });

  testWidgets('the same zone as the device is not repeated', (tester) async {
    scriptRoutines();
    await pumpRoutines(tester);
    expect(find.text('Weekdays at 07:30'), findsOneWidget);
  });

  testWidgets('a done one-shot is scheduled again in UTC and switched on', (
    tester,
  ) async {
    scriptRoutines();
    fakeApi.on(
      'PUT /routines/r-3',
      (body, _) => {
        ...routinesFixture().last,
        ...(body! as Map<String, Object?>),
      },
    );
    await pumpRoutines(tester);
    final cpi = find.textContaining('CPI check');
    await tester.scrollUntilVisible(
      cpi,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(cpi);
    await tester.pumpAndSettle();
    await tapAndSettle(
      tester,
      find.descendant(
        of: find.ancestor(of: cpi, matching: find.byType(ScheduleCard)),
        matching: find.bySemanticsLabel('More'),
      ),
    );
    await tapAndSettle(tester, find.text('Schedule again'));
    final save = find.text('Schedule again').last;
    await tester.scrollUntilVisible(
      save,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, save);
    final body =
        fakeApi.callsTo('PUT', '/routines/r-3').single.body!
            as Map<String, Object?>;
    expect(body['enabled'], isTrue);
    final at = DateTime.parse(body['run_at']! as String);
    expect(at.isUtc, isTrue);
    final local = at.toLocal();
    final stored = DateTime.parse('2026-11-12T13:25:00+00:00').toLocal();
    expect((local.hour, local.minute), (stored.hour, stored.minute));
    expect(local.isAfter(DateTime.now()), isTrue);
    await settleToasts(tester);
  });

  testWidgets('creates a one-shot with its instant in UTC', (tester) async {
    fakeApi.on(
      'POST /routines/a-gold',
      (body, _) => {
        ...routinesFixture().last,
        ...(body! as Map<String, Object?>),
        'id': 'r-8',
      },
    );
    await openEditor(
      tester,
      RoutineEditor(
        agentId: 'a-gold',
        agents: [Agent.fromJson(fixtureAgents[1])],
        now: fixtureNow,
      ),
    );
    await tapAndSettle(tester, find.text('Repeat'));
    await tapAndSettle(tester, find.text('Does not repeat'));
    await tapAndSettle(tester, find.text('Date'));
    await tapAndSettle(tester, find.text('28'));
    await tester.enterText(find.byType(EditableText).first, 'Check the CPI.');
    await tester.pump();
    final save = find.text('Save');
    await tester.scrollUntilVisible(
      save,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, save);
    final body =
        fakeApi.callsTo('POST', '/routines/a-gold').single.body!
            as Map<String, Object?>;
    expect(body['run_at'], DateTime(2026, 11, 28, 9).toUtc().toIso8601String());
    expect(body.containsKey('cron'), isFalse);
    await settleToasts(tester);
  });

  testWidgets('lists the agent watches; pause and a confirmed stop', (
    tester,
  ) async {
    scriptRoutines();
    fakeApi
      ..on('GET /watches', (_, _) => watchesFixture())
      ..on('POST /watches/w-1/control', (_, _) => {});
    await pumpRoutines(tester);
    expect(fakeApi.callsTo('GET', '/watches').single.query, {
      'agent_id': 'a-gold',
    });
    final card = find.textContaining('Alert me when gold breaks out');
    await tester.scrollUntilVisible(
      card,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('When a condition is met'), findsOneWidget);
    // A watch without a prompt or a cancelled one is not a schedule.
    expect(find.textContaining('2100'), findsNothing);
    expect(find.textContaining('2500'), findsNothing);
    await tester.ensureVisible(card);
    await tester.pumpAndSettle();
    await tapAndSettle(tester, card);
    await tapAndSettle(tester, find.text('Pause'));
    expect(fakeApi.callsTo('POST', '/watches/w-1/control').single.body, {
      'action': 'pause',
    });
    await settleToasts(tester);
    await tapAndSettle(tester, card);
    await tapAndSettle(tester, find.text('Stop the watch'));
    expect(find.text('Stop this watch?'), findsOneWidget);
    expect(fakeApi.callsTo('POST', '/watches/w-1/control'), hasLength(1));
    await tapAndSettle(tester, find.text('Stop the watch').last);
    expect(fakeApi.callsTo('POST', '/watches/w-1/control').last.body, {
      'action': 'cancel',
    });
    await settleToasts(tester);
  });

  testWidgets('creates a price condition for a trading agent', (tester) async {
    scriptRoutines();
    fakeApi.on('POST /watches', (_, _) => {'id': 'w-5'});
    await pumpRoutines(tester);
    await tapAndSettle(tester, find.bySemanticsLabel('Create routine'));
    await tapAndSettle(tester, find.text('On a condition'));
    final fields = find.byType(EditableText);
    await tester.enterText(fields.at(0), 'below 2330');
    await tester.enterText(fields.at(1), 'Tell me how gold trades below.');
    await tester.pump();
    final save = find.text('Save');
    await tester.scrollUntilVisible(
      save,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, save);
    expect(fakeApi.callsTo('POST', '/watches').single.body, {
      'agent_id': 'a-gold',
      'payload': {
        'kind': 'price',
        'account_id': 'acct-1',
        'symbol': 'XAUUSD',
        'condition': 'below',
        'level': '2330',
        'prompt': 'Tell me how gold trades below.',
      },
    });
    expect(fakeApi.callsTo('POST', '/routines/a-gold'), isEmpty);
    await settleToasts(tester);
  });

  testWidgets('an agent without an account and symbol has no condition', (
    tester,
  ) async {
    fakeApi.on('GET /routines', (_, _) => []);
    await pumpScreen(
      tester,
      const RoutinesScreen(agentId: 'a-research'),
      locale: 'en',
    );
    await tapAndSettle(tester, find.bySemanticsLabel('Create routine').first);
    expect(find.text('On a condition'), findsNothing);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptRoutines();
        // The test VM runs in UTC: the device says so too, so each time reads true.
        deviceZone('UTC');
        fakeApi.on('GET /watches', (_, _) => watchesFixture());
        await pumpScreen(
          tester,
          const RoutinesScreen(agentId: 'a-gold'),
          brightness: v.brightness,
          locale: v.locale,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/routines_${v.name}.png'),
        );
      });
    });
  }

  testWidgets('golden watches light_en', (tester) async {
    await withRealShadows(() async {
      scriptRoutines();
      deviceZone('UTC');
      fakeApi.on('GET /watches', (_, _) => watchesFixture());
      await pumpRoutines(tester);
      await tester.drag(find.byType(Scrollable).first, const Offset(0, -3000));
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/routines_watches_light_en.png'),
      );
    });
  });

  testWidgets('golden condition editor light_ar', (tester) async {
    await withRealShadows(() async {
      scriptRoutines();
      await pumpScreen(tester, const RoutinesScreen(agentId: 'a-gold'));
      await tester.tap(find.bySemanticsLabel('إنشاء مهمة مجدولة'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('عند تحقق شرط'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(EditableText).at(0), 'تحت 2330');
      await tester.pump();
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/condition_editor_light_ar.png'),
      );
    });
  });

  for (final v in [goldenVariants[0], goldenVariants[3]]) {
    testWidgets('golden editor ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptRoutines();
        await pumpScreen(
          tester,
          const RoutinesScreen(agentId: 'a-gold'),
          brightness: v.brightness,
          locale: v.locale,
        );
        await tester.tap(
          find.bySemanticsLabel(
            v.locale == 'ar' ? 'إنشاء مهمة مجدولة' : 'Create routine',
          ),
        );
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/routine_editor_${v.name}.png'),
        );
      });
    });
  }
}
