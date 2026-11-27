// «ما أعرفه عنك»: profile lines with their origin, correct (bullet kept) and delete (confirmed),
// the learned habit and forgetting it (confirmed), the profile as text, the change log; goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/knowledge
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:lonora/design/design.dart' show LnIcons;
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/features/me/owner_knowledge_screen.dart';

import '../agent_profile/wpe_harness.dart';

void scriptKnowledge({bool empty = false}) {
  fakeApi
    ..on(
      'GET /owner/profile/lines',
      (_, _) => {
        'version': 12,
        'lines': empty
            ? []
            : [
                {
                  'text': '- يفضّل الردود القصيرة بالعربية.',
                  'origin': 'you_said',
                  'author': 'owner',
                },
                {
                  'text': '- Trades gold in the London session.',
                  'origin': 'observed',
                  'author': 'agent',
                  'author_agent_name': 'Gold desk',
                },
                {'text': 'Lives in Riyadh.', 'origin': 'earlier'},
              ],
      },
    )
    ..on(
      'GET /app-opens',
      (_, _) => {'first_open': empty ? null : '06:40', 'brief': '06:30'},
    )
    ..on(
      'GET /owner/profile',
      (_, _) => {
        'content': '- يفضّل الردود القصيرة بالعربية.\n- Trades gold in the London session.\nLives in Riyadh.',
        'version': 9,
        'chars': 90,
        'limit': 8000,
      },
    )
    ..on(
      'GET /owner/profile/revisions',
      (_, _) => empty
          ? []
          : [
              {
                'id': 'pr-1',
                'document': 'owner_profile',
                'author': 'agent',
                'author_agent_name': 'Gold desk',
                'change': 'edit',
                'created_at': '2026-11-25T07:00:00Z',
                'changes': [
                  {
                    'change': 'added',
                    'text': '- Trades gold in the London session.',
                  },
                ],
              },
              {
                'id': 'pr-2',
                'document': 'owner_preferences',
                'author': 'owner',
                'change': 'edit',
                'created_at': '2026-11-24T19:10:00Z',
                'changes': [
                  {'field': 'name', 'before': null, 'after': 'Ahmed'},
                ],
              },
            ],
    );
}

void main() {
  setUpAll(setUpWpeHarness);
  setUp(resetWpe);

  test('a correction keeps one bullet', () {
    expect(correctionWords('  - Lives in Jeddah. '), 'Lives in Jeddah.');
    expect(correctionWords('* x'), 'x');
    const line = ProfileLine(text: '- Old', origin: 'you_said');
    expect(line.bullet, '- ');
    expect(line.shown, 'Old');
  });

  testWidgets('lists each line with its origin', (tester) async {
    scriptKnowledge();
    await pumpScreen(tester, const OwnerKnowledgeScreen(), locale: 'en');
    expect(
      find.textContaining('Trades gold in the London session.'),
      findsNWidgets(2),
    );
    expect(find.text('You said'), findsOneWidget);
    expect(find.textContaining('Observed by'), findsOneWidget);
    expect(find.text('Earlier'), findsOneWidget);
    expect(find.textContaining('06:40'), findsOneWidget);
  });

  testWidgets('corrects a line, keeping its bullet', (tester) async {
    scriptKnowledge();
    fakeApi.on(
      'POST /owner/profile/lines',
      (_, _) => {'version': 13, 'lines': []},
    );
    await pumpScreen(tester, const OwnerKnowledgeScreen(), locale: 'en');
    await tapAndSettle(
      tester,
      find.textContaining('Trades gold in the London').first,
    );
    await tapAndSettle(tester, find.text('Correct the fact'));
    await tester.enterText(
      find.byType(EditableText),
      'Trades gold in New York.',
    );
    await tester.pump();
    await tapAndSettle(tester, find.text('Save'));
    expect(fakeApi.callsTo('POST', '/owner/profile/lines').single.body, {
      'version': 12,
      'text': '- Trades gold in the London session.',
      'replacement': '- Trades gold in New York.',
    });
    await settleToasts(tester);
  });

  testWidgets('deleting a line asks first', (tester) async {
    scriptKnowledge();
    fakeApi.on(
      'POST /owner/profile/lines',
      (_, _) => {'version': 13, 'lines': []},
    );
    await pumpScreen(tester, const OwnerKnowledgeScreen(), locale: 'en');
    await tapAndSettle(tester, find.textContaining('Lives in Riyadh.'));
    await tapAndSettle(tester, find.text('Delete the fact'));
    expect(find.text('Delete this fact?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Delete'));
    expect(fakeApi.callsTo('POST', '/owner/profile/lines').single.body, {
      'version': 12,
      'text': 'Lives in Riyadh.',
      'replacement': null,
    });
    await settleToasts(tester);
  });

  testWidgets('forgets the habit after confirming', (tester) async {
    scriptKnowledge();
    fakeApi.on(
      'DELETE /app-opens',
      (_, _) => {'first_open': null, 'brief': '07:00'},
    );
    await pumpScreen(tester, const OwnerKnowledgeScreen(), locale: 'en');
    await tapAndSettle(tester, find.textContaining('06:40'));
    expect(find.text('Forget this habit?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Forget'));
    expect(fakeApi.callsTo('DELETE', '/app-opens'), hasLength(1));
    expect(find.textContaining('06:40'), findsNothing);
    await settleToasts(tester);
  });

  testWidgets('undoes a settings change with no version', (tester) async {
    scriptKnowledge();
    fakeApi.on('POST /memory/revisions/pr-2/revert', (_, _) => {});
    await pumpScreen(tester, const OwnerKnowledgeScreen(), locale: 'en');
    final row = find.text('You').last;
    await tester.scrollUntilVisible(
      row,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tapAndSettle(tester, row);
    await tapAndSettle(tester, find.text('Undo this change to your settings'));
    expect(
      fakeApi.callsTo('POST', '/memory/revisions/pr-2/revert').single.body,
      {'version': null},
    );
    await settleToasts(tester);
  });

  testWidgets('saves the profile as text with its version', (tester) async {
    scriptKnowledge();
    fakeApi.on('PUT /owner/profile', (body, _) => {});
    await pumpScreen(tester, const OwnerKnowledgeScreen(), locale: 'en');
    await tapAndSettle(tester, find.text('Edit as text'));
    await tester.enterText(find.byType(EditableText), 'Lives in Riyadh.');
    await tester.pump();
    await tapAndSettle(tester, find.text('Save'));
    expect(fakeApi.callsTo('PUT', '/owner/profile').single.body, {
      'content': 'Lives in Riyadh.',
      'version': 9,
    });
    await settleToasts(tester);
  });

  testWidgets('a failed habit read keeps the profile lines', (tester) async {
    scriptKnowledge();
    fakeApi.on(
      'GET /app-opens',
      (_, _) => throw ApiError(status: 500, code: 'request_failed'),
    );
    await pumpScreen(tester, const OwnerKnowledgeScreen(), locale: 'en');
    expect(find.text('You said'), findsOneWidget);
    expect(find.text('The request failed. Try again.'), findsOneWidget);
    fakeApi.on(
      'GET /app-opens',
      (_, _) => {'first_open': '06:40', 'brief': '06:30'},
    );
    await tapAndSettle(tester, find.text('The request failed. Try again.'));
    expect(find.textContaining('06:40'), findsOneWidget);
  });

  testWidgets('nothing readable at all shows the page failure', (tester) async {
    for (final path in [
      '/owner/profile/lines',
      '/app-opens',
      '/owner/profile',
      '/owner/profile/revisions',
    ]) {
      fakeApi.on(
        'GET $path',
        (_, _) => throw ApiError(status: 500, code: 'request_failed'),
      );
    }
    await pumpScreen(tester, const OwnerKnowledgeScreen(), locale: 'en');
    expect(find.text('The request failed. Try again.'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('a change the server would refuse offers no undo', (
    tester,
  ) async {
    scriptKnowledge();
    fakeApi.on(
      'GET /owner/profile/revisions',
      (_, _) => [
        {
          'id': 'pr-3',
          'document': 'owner_preferences',
          'author': 'owner',
          'change': 'edit',
          'created_at': '2026-11-24T19:10:00Z',
          'changes': [
            {'field': 'reach_me', 'before': 'activity', 'after': 'calls'},
          ],
        },
      ],
    );
    await pumpScreen(tester, const OwnerKnowledgeScreen(), locale: 'en');
    final row = find.textContaining('You');
    await tester.scrollUntilVisible(
      row.last,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(row.last);
    await tester.pumpAndSettle();
    // The row carries no undo icon, and its sheet no undo button.
    expect(find.byIcon(LnIcons.undo2), findsNothing);
    await tapAndSettle(tester, row.last);
    expect(find.textContaining('How to reach you'), findsWidgets);
    expect(find.text('Undo this change to your settings'), findsNothing);
  });

  testWidgets('wf:C7 the undo arrow mirrors in Arabic', (tester) async {
    scriptKnowledge();
    await pumpScreen(tester, const OwnerKnowledgeScreen());
    final undo = find.byIcon(LnIcons.undo2);
    await tester.scrollUntilVisible(
      undo.first,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    // An icon with matchTextDirection is drawn flipped under a right-to-left Directionality.
    expect(LnIcons.undo2.matchTextDirection, isTrue);
    expect(Directionality.of(tester.element(undo.first)), TextDirection.rtl);
    expect(find.byIcon(FIcons.undo2), findsNothing);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptKnowledge();
        await pumpScreen(
          tester,
          const OwnerKnowledgeScreen(),
          brightness: v.brightness,
          locale: v.locale,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/owner_knowledge_${v.name}.png'),
        );
      });
    });
  }

  testWidgets('golden empty light_ar', (tester) async {
    await withRealShadows(() async {
      scriptKnowledge(empty: true);
      await pumpScreen(tester, const OwnerKnowledgeScreen());
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/owner_knowledge_empty_light_ar.png'),
      );
    });
  });
}
