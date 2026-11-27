// Tasks: Active · Scheduled · Completed, status words, details with pause / resume / complete /
// cancel (confirmed) / delete (confirmed) and the conversation, create; goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/tasks
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FTile;
import 'package:lonora/avatar/avatar.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/design/design.dart' show LnIcons, LnSize;
import 'package:lonora/state/app_state.dart';
import 'package:lonora/features/tasks/tasks_data.dart';
import 'package:lonora/features/tasks/tasks_screen.dart';

import '../agent_profile/wpe_harness.dart';

Map<String, Object?> task(
  String id,
  String title,
  String status, {
  String agent = 'a-gold',
  bool canPause = false,
  bool canResume = false,
  bool canCancel = false,
  String? due,
  String criteria = '',
}) => {
  'id': id,
  'agent_id': agent,
  'title': title,
  'description': 'Watch the London open and report the range.',
  'version': 4,
  'status': status,
  'origin_thread_id': 't-$agent',
  'work_thread_id': 'w-$id',
  'due_at': due,
  'completion_criteria': criteria,
  'control_requested': null,
  'can_pause': canPause,
  'can_resume': canResume,
  'can_cancel': canCancel,
};

List<Map<String, Object?>> tasksFixture() => [
  task(
    'k-1',
    'London open range',
    'running',
    canPause: true,
    canCancel: true,
    due: '2030-01-02T15:00:00Z',
    criteria: 'A short report with the high and low.',
  ),
  task('k-2', 'تقرير الأسبوع', 'paused', agent: 'a-writer', canResume: true),
  task('k-3', 'CPI preparation', 'waiting', agent: 'a-research'),
  task('k-4', 'October review', 'completed'),
  task('k-5', 'Old idea', 'cancelled', agent: 'a-research'),
];

void scriptTasks() {
  fakeApi
    ..on('GET /tasks', (_, _) => tasksFixture())
    ..on('GET /routines', (_, _) => []);
}

void main() {
  setUpAll(setUpWpeHarness);
  setUp(resetWpe);

  test('status words and the due time', () {
    expect(taskStatusKey('running'), 'tk_inProgress');
    expect(taskStatusKey('queued'), 'tk_inProgress');
    expect(taskStatusKey('waiting'), 'tk_awaitingReview');
    expect(taskStatusKey('failed'), 'tk_awaitingReview');
    expect(taskStatusKey('paused'), 'tk_paused');
    expect(taskStatusKey('completed'), 'tk_completed');
    final now = DateTime(2026, 11, 27, 10);
    expect(dueFromTime(18, 0, now), DateTime(2026, 11, 27, 18));
    expect(dueFromTime(9, 0, now), DateTime(2026, 11, 28, 9));
    expect(dueFromTime(10, 0, now), DateTime(2026, 11, 28, 10));
  });

  testWidgets('filters active and completed tasks', (tester) async {
    scriptTasks();
    await pumpScreen(tester, const TasksScreen(), locale: 'en');
    expect(find.textContaining('London open range'), findsOneWidget);
    expect(find.textContaining('In progress'), findsOneWidget);
    expect(find.textContaining('Awaiting review'), findsOneWidget);
    expect(find.textContaining('October review'), findsNothing);
    await tapAndSettle(tester, find.text('Completed').first);
    expect(find.textContaining('October review'), findsOneWidget);
    expect(find.textContaining('Old idea'), findsOneWidget);
    expect(find.textContaining('London open range'), findsNothing);
  });

  testWidgets('pauses a task with its version', (tester) async {
    scriptTasks();
    fakeApi.on(
      'POST /tasks/control',
      (_, _) => task('k-1', 'London open range', 'paused', canResume: true),
    );
    await pumpScreen(tester, const TasksScreen(), locale: 'en');
    await tapAndSettle(tester, find.textContaining('London open range'));
    expect(
      find.textContaining('A short report with the high and low.'),
      findsWidgets,
    );
    await tapAndSettle(tester, find.text('Pause'));
    expect(fakeApi.callsTo('POST', '/tasks/control').single.body, {
      'task_id': 'k-1',
      'action': 'pause',
      'expected_version': 4,
    });
    expect(find.text('Resume'), findsOneWidget);
    await settleToasts(tester);
  });

  testWidgets('cancelling a task asks first', (tester) async {
    scriptTasks();
    await pumpScreen(tester, const TasksScreen(), locale: 'en');
    await tapAndSettle(tester, find.textContaining('London open range'));
    await tapAndSettle(tester, find.text('Cancel task'));
    expect(find.text('Cancel this task?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Keep'));
    expect(fakeApi.callsTo('POST', '/tasks/control'), isEmpty);
  });

  testWidgets('a finished task is deleted after confirming', (tester) async {
    scriptTasks();
    fakeApi.on('DELETE /tickets/k-4', (_, _) => {'deleted': true});
    await pumpScreen(tester, const TasksScreen(), locale: 'en');
    await tapAndSettle(tester, find.text('Completed').first);
    await tapAndSettle(tester, find.textContaining('October review'));
    await tapAndSettle(tester, find.text('Delete'));
    expect(find.text('Delete this task?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Delete').last);
    expect(fakeApi.callsTo('DELETE', '/tickets/k-4'), hasLength(1));
    await settleToasts(tester);
  });

  testWidgets('opens the conversation a task reports to', (tester) async {
    scriptTasks();
    await pumpScreen(tester, const TasksScreen(), locale: 'en');
    await tapAndSettle(tester, find.textContaining('London open range'));
    await tapAndSettle(tester, find.text('View conversation'));
    expect(shownRoute(tester), '/chats/thread/t-a-gold');
  });

  testWidgets('creates a task in the agent conversation', (tester) async {
    scriptTasks();
    fakeApi
      ..on('POST /agents/a-lonora/conversation', (_, _) => {'id': 't-l'})
      ..on(
        'POST /tasks?agent_id=a-lonora&thread_id=t-l',
        (_, _) => task('k-9', 'Prepare the brief', 'queued', agent: 'a-lonora'),
      );
    await pumpScreen(tester, const TasksScreen(), locale: 'en');
    await tapAndSettle(tester, find.bySemanticsLabel('Create task'));
    await tester.enterText(
      find.byType(EditableText).first,
      'Prepare the brief',
    );
    await tester.pump();
    final create = find.text('Create task').last;
    await tester.scrollUntilVisible(
      create,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, create);
    final body =
        fakeApi
                .callsTo('POST', '/tasks?agent_id=a-lonora&thread_id=t-l')
                .single
                .body!
            as Map<String, Object?>;
    expect(body['title'], 'Prepare the brief');
    expect(body['due_at'], isNotNull);
    expect(body.keys.toSet(), {
      'title',
      'description',
      'due_at',
      'completion_criteria',
    });
    await settleToasts(tester);
  });

  testWidgets('Scheduled lists every routine', (tester) async {
    scriptTasks();
    await pumpScreen(tester, const TasksScreen(), locale: 'en');
    await tapAndSettle(tester, find.text('Scheduled'));
    expect(find.text('No routines have been created yet.'), findsOneWidget);
  });

  testWidgets('Recent runs under the active tasks open their report', (
    tester,
  ) async {
    scriptTasks();
    final base = wpeStore(locale: 'en');
    final store = Store<AppState>(
      initialState: base.state.copyWith(
        shell: base.state.shell.copyWith(
          runs: [
            Run.fromJson({
              'id': 'run-1',
              'thread_id': 'work-1',
              'agent_id': 'a-gold',
              'status': 'running',
              'model_metadata': {'origin_thread_id': 't-gold'},
            }),
            Run.fromJson({
              'id': 'run-2',
              'thread_id': 'work-2',
              'agent_id': 'a-research',
              'status': 'failed',
            }),
            // A run of an agent that is gone is not listed.
            Run.fromJson({
              'id': 'run-3',
              'thread_id': 'work-3',
              'agent_id': 'a-removed',
              'status': 'completed',
            }),
          ],
        ),
      ),
    );
    await pumpScreen(tester, const TasksScreen(), locale: 'en', store: store);
    final runs = find.text('Recent runs');
    await tester.scrollUntilVisible(
      runs,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    // Gold desk also names the first active task's agent.
    expect(find.textContaining('Gold desk'), findsNWidgets(2));
    expect(find.textContaining('Research'), findsNWidgets(2));
    expect(find.byType(LonoraAvatar), findsNWidgets(2));
    // A run row (40 dp avatar, name and status) already clears the 48 dp touch target.
    expect(
      tester
          .getSize(
            find.ancestor(
              of: find.textContaining('Research').last,
              matching: find.byType(FTile),
            ),
          )
          .height,
      greaterThanOrEqualTo(LnSize.minTouch),
    );
    final goldRun = find.textContaining('Gold desk').last;
    await tester.ensureVisible(goldRun);
    await tester.pumpAndSettle();
    await tapAndSettle(tester, goldRun);
    expect(shownRoute(tester), '/chats/thread/t-gold');
  });

  testWidgets('golden runs light_ar', (tester) async {
    await withRealShadows(() async {
      scriptTasks();
      final base = wpeStore();
      final store = Store<AppState>(
        initialState: base.state.copyWith(
          shell: base.state.shell.copyWith(
            runs: [
              for (final (id, agent, status) in [
                ('run-1', 'a-gold', 'running'),
                ('run-2', 'a-research', 'completed'),
                ('run-3', 'a-writer', 'failed'),
              ])
                Run.fromJson({
                  'id': id,
                  'thread_id': 'w-$id',
                  'agent_id': agent,
                  'status': status,
                }),
            ],
          ),
        ),
      );
      await pumpScreen(tester, const TasksScreen(), store: store);
      await tester.drag(find.byType(Scrollable).first, const Offset(0, -300));
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/runs_light_ar.png'),
      );
    });
  });

  testWidgets('without any run there is no runs group', (tester) async {
    scriptTasks();
    await pumpScreen(tester, const TasksScreen(), locale: 'en');
    expect(find.text('Recent runs'), findsNothing);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptTasks();
        await pumpScreen(
          tester,
          const TasksScreen(),
          brightness: v.brightness,
          locale: v.locale,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/tasks_${v.name}.png'),
        );
      });
    });
  }

  testWidgets('wf:C6 the list icons mirror in Arabic', (tester) async {
    scriptTasks();
    await pumpScreen(tester, const TasksScreen());
    final icon = find.byIcon(LnIcons.listTodo);
    expect(icon, findsWidgets);
    expect(LnIcons.listTodo.matchTextDirection, isTrue);
    expect(Directionality.of(tester.element(icon.first)), TextDirection.rtl);
  });

  testWidgets(
    'wf:C1 the sheet\'s English content aligns by its own direction',
    (tester) async {
      scriptTasks();
      await pumpScreen(tester, const TasksScreen());
      await tapAndSettle(tester, find.textContaining('London open range'));
      // Title, description, agent and criterion: one rule, the text's own direction.
      for (final text in [
        'London open range',
        'Watch the London open and report the range.',
        'Gold desk',
        'A short report with the high and low.',
      ]) {
        final shown = find.text(text).last;
        expect(
          tester.widget<Text>(shown).textDirection,
          TextDirection.ltr,
          reason: text,
        );
      }
      final title = tester.getRect(find.text('London open range').last);
      final description = tester.getRect(
        find.text('Watch the London open and report the range.'),
      );
      expect(title.left, description.left);
    },
  );

  for (final v in [goldenVariants[0], goldenVariants[3]]) {
    testWidgets('golden details ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptTasks();
        await pumpScreen(
          tester,
          const TasksScreen(),
          brightness: v.brightness,
          locale: v.locale,
        );
        await tester.tap(find.textContaining('London open range'));
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/task_details_${v.name}.png'),
        );
      });
    });
  }
}
