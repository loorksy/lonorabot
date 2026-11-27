// Agent memory: the memory text, its edit and save, the change log with a one-change undo, and
// knowledge notes and links (add, edit, delete); goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/agent_settings
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart' show SemanticsAction;
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/agents/agent_memory_screen.dart';
import 'package:lonora/features/agents/memory/semantic_section.dart';

import '../agent_profile/wpe_harness.dart';

const memoryText =
    '## Gold desk\n'
    '- يتابع الذهب في جلسة لندن ويكتب ملخصًا قبل الافتتاح.\n'
    '- The owner prefers short reports with the levels first.\n'
    '- Never trade during the US CPI release.';

void scriptMemory({String content = memoryText}) {
  fakeApi
    ..on(
      'GET /agents/a-gold/memory',
      (_, _) => {
        'agent_id': 'a-gold',
        'content': content,
        'version': 7,
        'updated_at': '2026-11-26T08:15:00+00:00',
      },
    )
    ..on(
      'GET /agents/a-gold/memory/revisions',
      (_, _) => [
        {
          'id': 'rev-2',
          'document': 'agent_memory',
          'author': 'agent',
          'author_agent_name': 'Gold desk',
          'from_owner_message': true,
          'change': 'edit',
          'created_at': '2026-11-26T08:15:00+00:00',
          'changes': [
            {
              'change': 'added',
              'text': '- Never trade during the US CPI release.',
            },
          ],
          'changes_truncated': false,
        },
        {
          'id': 'rev-1',
          'document': 'agent_memory',
          'author': 'owner',
          'change': 'edit',
          'created_at': '2026-11-20T18:40:00+00:00',
          'changes': [
            {'change': 'removed', 'text': '- Weekly reports on Sunday.'},
          ],
        },
      ],
    )
    ..on(
      'GET /agents/a-gold/knowledge',
      (_, _) => [
        {
          'id': 'n-1',
          'type': 'note',
          'title': 'London open playbook',
          'content': 'Wait for the first 15-minute candle to close.',
          'version': null,
        },
        {
          'id': 'l-1',
          'type': 'link',
          'title': 'World Gold Council',
          'content': 'Demand trends',
          'url': 'https://www.gold.org/goldhub',
          'version': 2,
        },
      ],
    );
}

void main() {
  setUpAll(setUpWpeHarness);
  setUp(resetWpe);

  testWidgets('edits the memory and saves it with its version', (tester) async {
    scriptMemory();
    fakeApi.on(
      'PUT /agents/a-gold/memory',
      (body, _) => {...(body as Map<String, dynamic>), 'version': 8},
    );
    await pumpScreen(
      tester,
      const AgentMemoryScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    expect(find.textContaining('Never trade during'), findsWidgets);
    await tapAndSettle(tester, find.text('Edit memory'));
    await tester.enterText(find.byType(EditableText), 'Only gold.');
    await tester.pump();
    await tapAndSettle(tester, find.text('Save'));
    expect(fakeApi.callsTo('PUT', '/agents/a-gold/memory').single.body, {
      'content': 'Only gold.',
      'version': 7,
    });
    await settleToasts(tester);
  });

  testWidgets('a refused save shows the server words', (tester) async {
    scriptMemory();
    fakeApi.on(
      'PUT /agents/a-gold/memory',
      (_, _) => throw ApiError(status: 409, code: 'version_conflict'),
    );
    await pumpScreen(
      tester,
      const AgentMemoryScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tapAndSettle(tester, find.text('Edit memory'));
    await tester.enterText(find.byType(EditableText), 'x');
    await tester.pump();
    await tapAndSettle(tester, find.text('Save'));
    expect(
      find.text('This was changed on another device. Refresh and try again.'),
      findsOneWidget,
    );
    await settleToasts(tester);
  });

  testWidgets('undoes one change from the change log', (tester) async {
    scriptMemory();
    fakeApi.on('POST /memory/revisions/rev-2/revert', (_, _) => {});
    await pumpScreen(
      tester,
      const AgentMemoryScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final row = find.textContaining('from your message');
    await tester.scrollUntilVisible(
      row,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tapAndSettle(tester, row);
    await tapAndSettle(tester, find.text('Undo this change'));
    expect(
      fakeApi.callsTo('POST', '/memory/revisions/rev-2/revert').single.body,
      {'version': 7},
    );
    await settleToasts(tester);
  });

  testWidgets('adds a knowledge note and deletes a link after confirming', (
    tester,
  ) async {
    scriptMemory();
    fakeApi
      ..on('POST /agents/a-gold/knowledge/notes', (_, _) => {'id': 'n-2'})
      ..on('DELETE /knowledge-links/l-1', (_, _) => {'deleted': true});
    await pumpScreen(
      tester,
      const AgentMemoryScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tapAndSettle(tester, find.text('Knowledge'));
    expect(find.textContaining('London open playbook'), findsOneWidget);
    await tapAndSettle(tester, find.text('Add knowledge'));
    final fields = find.byType(EditableText);
    await tester.enterText(fields.at(0), 'CPI days');
    await tester.enterText(fields.at(1), 'Flat before the release.');
    await tester.pump();
    await tapAndSettle(tester, find.text('Save'));
    expect(
      fakeApi.callsTo('POST', '/agents/a-gold/knowledge/notes').single.body,
      {'title': 'CPI days', 'content': 'Flat before the release.'},
    );
    await settleToasts(tester);
    await tapAndSettle(tester, find.textContaining('World Gold Council'));
    await tapAndSettle(tester, find.text('Delete'));
    expect(find.text('Delete this knowledge?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Delete').last);
    expect(fakeApi.callsTo('DELETE', '/knowledge-links/l-1'), hasLength(1));
    await settleToasts(tester);
  });

  testWidgets('a failed knowledge read leaves the memory shown', (
    tester,
  ) async {
    scriptMemory();
    fakeApi.on(
      'GET /agents/a-gold/knowledge',
      (_, _) => throw ApiError(status: 500, code: 'request_failed'),
    );
    await pumpScreen(
      tester,
      const AgentMemoryScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    expect(find.textContaining('Never trade during'), findsWidgets);
    await tapAndSettle(tester, find.text('Knowledge'));
    expect(find.text('The request failed. Try again.'), findsOneWidget);
    fakeApi.on('GET /agents/a-gold/knowledge', (_, _) => []);
    await tapAndSettle(tester, find.text('Retry'));
    expect(find.text('No sources for this agent.'), findsOneWidget);
  });

  testWidgets('edits a link with its version', (tester) async {
    scriptMemory();
    fakeApi.on('PUT /knowledge-links/l-1', (_, _) => {});
    await pumpScreen(
      tester,
      const AgentMemoryScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tapAndSettle(tester, find.text('Knowledge'));
    await tapAndSettle(tester, find.textContaining('World Gold Council'));
    final title = find.byWidgetPredicate(
      (w) => w is EditableText && w.controller.text == 'World Gold Council',
    );
    await tester.enterText(title, 'WGC');
    await tester.pump();
    await tapAndSettle(tester, find.text('Save'));
    expect(fakeApi.callsTo('PUT', '/knowledge-links/l-1').single.body, {
      'version': 2,
      'payload': {
        'title': 'WGC',
        'url': 'https://www.gold.org/goldhub',
        'note': 'Demand trends',
      },
    });
    await settleToasts(tester);
  });

  testWidgets('adds a goal and marks one completed with its version', (
    tester,
  ) async {
    scriptMemory();
    fakeApi
      ..on(
        'GET /agent-goals',
        (_, _) => [
          {
            'id': 'g-1',
            'agent_id': 'a-gold',
            'version': 3,
            'payload': {
              'title': 'Keep drawdown under 2%',
              'description': '',
              'done': false,
            },
          },
        ],
      )
      ..on('POST /agent-goals', (_, _) => {'id': 'g-2'})
      ..on('PUT /agent-goals/g-1', (_, _) => {});
    await pumpScreen(
      tester,
      const AgentMemoryScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tapAndSettle(tester, find.text('Goals'));
    expect(fakeApi.callsTo('GET', '/agent-goals').single.query, {
      'agent_id': 'a-gold',
    });
    expect(find.textContaining('Keep drawdown'), findsOneWidget);
    await tapAndSettle(tester, find.text('Add a goal'));
    await tester.enterText(find.byType(EditableText).first, 'Weekly report');
    await tester.pump();
    await tapAndSettle(tester, find.text('Save'));
    expect(fakeApi.callsTo('POST', '/agent-goals').single.body, {
      'agent_id': 'a-gold',
      'payload': {'title': 'Weekly report', 'description': '', 'done': false},
    });
    await settleToasts(tester);
    await tapAndSettle(tester, find.textContaining('Keep drawdown'));
    await tapAndSettle(tester, find.text('Completed').last);
    await tapAndSettle(tester, find.text('Save'));
    expect(fakeApi.callsTo('PUT', '/agent-goals/g-1').single.body, {
      'version': 3,
      'payload': {
        'title': 'Keep drawdown under 2%',
        'description': '',
        'done': true,
      },
    });
    await settleToasts(tester);
  });

  testWidgets('scratchpad: add, edit with its version, delete confirmed', (
    tester,
  ) async {
    scriptMemory();
    fakeApi
      ..on(
        'GET /scratchpad',
        (_, _) => [
          {
            'id': 's-1',
            'agent_id': 'a-gold',
            'version': 5,
            'payload': {'title': 'Levels', 'content': '2330 / 2350'},
          },
        ],
      )
      ..on('POST /scratchpad', (_, _) => {'id': 's-2'})
      ..on('PUT /scratchpad/s-1', (_, _) => {})
      ..on('DELETE /scratchpad/s-1', (_, _) => {'deleted': true});
    await pumpScreen(
      tester,
      const AgentMemoryScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    // The scratchpad is a group under Knowledge.
    await tapAndSettle(tester, find.text('Knowledge'));
    expect(find.text('Scratchpad'), findsOneWidget);
    final add = find.text('Add');
    await tester.scrollUntilVisible(
      add,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(add);
    await tester.pumpAndSettle();
    await tapAndSettle(tester, add);
    final fields = find.byType(EditableText);
    await tester.enterText(fields.at(0), 'Plan');
    await tester.enterText(fields.at(1), 'Wait for London.');
    await tester.pump();
    await tapAndSettle(tester, find.text('Save'));
    expect(fakeApi.callsTo('POST', '/scratchpad').single.body, {
      'agent_id': 'a-gold',
      'payload': {'title': 'Plan', 'content': 'Wait for London.'},
    });
    await settleToasts(tester);
    await tester.ensureVisible(find.textContaining('Levels'));
    await tester.pumpAndSettle();
    await tapAndSettle(tester, find.textContaining('Levels'));
    await tester.enterText(
      find.byWidgetPredicate(
        (w) => w is EditableText && w.controller.text == '2330 / 2350',
      ),
      '2330 / 2360',
    );
    await tester.pump();
    await tapAndSettle(tester, find.text('Save'));
    expect(fakeApi.callsTo('PUT', '/scratchpad/s-1').single.body, {
      'version': 5,
      'payload': {'title': 'Levels', 'content': '2330 / 2360'},
    });
    await settleToasts(tester);
    await tapAndSettle(tester, find.textContaining('Levels'));
    await tapAndSettle(tester, find.text('Delete'));
    expect(find.text('Delete this note?'), findsOneWidget);
    expect(fakeApi.callsTo('DELETE', '/scratchpad/s-1'), isEmpty);
    await tapAndSettle(tester, find.text('Delete').last);
    expect(fakeApi.callsTo('DELETE', '/scratchpad/s-1'), hasLength(1));
    await settleToasts(tester);
  });

  testWidgets('semantic memory: turns on with a model, then indexes a note', (
    tester,
  ) async {
    scriptMemory();
    fakeApi
      ..on(
        'GET /memory/semantic/config',
        (_, _) => {'enabled': false, 'model': null},
      )
      ..on('PUT /memory/semantic/config', (body, _) => body)
      ..on('POST /agents/a-gold/memory/semantic', (_, _) => {'id': 'n-9'});
    await pumpScreen(
      tester,
      const AgentMemoryScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    Future<void> reveal(Finder f) async {
      await tester.scrollUntilVisible(
        f,
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.ensureVisible(f);
      await tester.pumpAndSettle();
    }

    await reveal(find.text('Index note'));
    // Off: nothing can be indexed yet.
    final index = find.ancestor(
      of: find.text('Index note'),
      matching: find.byType(BlockButton),
    );
    expect(tester.widget<BlockButton>(index).onPressed, isNull);
    await reveal(find.text('Enable semantic retrieval'));
    await tapAndSettle(tester, find.text('Enable semantic retrieval'));
    await tapAndSettle(tester, find.text('Global embedding model'));
    await tapAndSettle(tester, find.textContaining('text-embedding-3-small'));
    await reveal(find.text('Index note'));
    await tapAndSettle(tester, find.text('Save').last);
    expect(fakeApi.callsTo('PUT', '/memory/semantic/config').single.body, {
      'enabled': true,
      'model': 'text-embedding-3-small',
    });
    await settleToasts(tester);
    // The note field of the semantic section (the «remember» field is empty too).
    final note = find.descendant(
      of: find.byType(SemanticSection),
      matching: find.byWidgetPredicate(
        (w) => w is EditableText && w.controller.text.isEmpty,
      ),
    );
    await tester.enterText(note.last, 'Gold reacts to real yields.');
    await tester.pump();
    await reveal(find.text('Index note'));
    await tapAndSettle(tester, find.text('Index note'));
    expect(
      fakeApi.callsTo('POST', '/agents/a-gold/memory/semantic').single.body,
      {'text': 'Gold reacts to real yields.'},
    );
    await settleToasts(tester);
  });

  group('page and «remember» field', () {
    Finder remember() => find.descendant(
      of: find.byType(RememberField),
      matching: find.byType(TextField),
    );

    testWidgets('the memory reads in one editor-card on the sub-page fill', (
      tester,
    ) async {
      scriptMemory();
      await pumpScreen(
        tester,
        const AgentMemoryScreen(agentId: 'a-gold'),
        locale: 'en',
        brightness: Brightness.dark,
      );
      expect(
        tester.widget<Scaffold>(find.byType(Scaffold)).backgroundColor,
        LnPalette.dark.sheetPage,
      );
      final card = find.byType(MemoryCard);
      final box = tester.widget<DecoratedBox>(
        find.descendant(of: card, matching: find.byType(DecoratedBox)).first,
      );
      final decoration = box.decoration as BoxDecoration;
      expect(decoration.color, LnPalette.dark.editorCard);
      expect(
        decoration.borderRadius,
        const BorderRadius.all(Radius.circular(26)),
      );
      final rect = tester.getRect(card);
      expect(rect.left, 16);
      expect(rect.right, tester.getSize(find.byType(MaterialApp)).width - 16);
    });

    testWidgets('a 56 dp stadium at the bottom names the agent; its send '
        'disc waits for text', (tester) async {
      final handle = tester.ensureSemantics();
      scriptMemory();
      await pumpScreen(
        tester,
        const AgentMemoryScreen(agentId: 'a-gold'),
        locale: 'en',
      );
      expect(find.byType(RememberField), findsOneWidget);
      final field = tester.getRect(find.byType(RememberField));
      final screen = tester.getSize(find.byType(MaterialApp));
      expect(screen.height - field.bottom, lessThan(16));
      expect(
        tester
            .getSize(
              find
                  .descendant(
                    of: find.byType(RememberField),
                    matching: find.byType(Container),
                  )
                  .first,
            )
            .height,
        RememberField.height,
      );
      expect(
        tester.widget<TextField>(remember()).decoration!.hintText,
        'Ask \u2068Gold desk\u2069 to remember…',
      );
      bool canSend() => tester
          .getSemantics(find.bySemanticsLabel('Send'))
          .getSemanticsData()
          .hasAction(SemanticsAction.tap);
      expect(canSend(), isFalse);
      await tester.enterText(remember(), 'I prefer levels first');
      await tester.pump();
      expect(canSend(), isTrue);
      // Both parts are 48 dp targets or more (the page's segmented tabs are the kit's own).
      expect(
        tester.getSize(find.bySemanticsLabel('Send')),
        const Size.square(LnSize.minTouch),
      );
      expect(tester.getSize(remember()).height, RememberField.height);
      handle.dispose();
    });

    testWidgets('sending puts «Remember: …» in the agent conversation', (
      tester,
    ) async {
      scriptMemory();
      fakeApi
        ..on(
          'POST /agents/a-gold/conversation',
          (_, _) => {'id': 't-gold', 'agent_id': 'a-gold'},
        )
        ..on(
          'POST /threads/t-gold/messages',
          (body, _) => {
            'message': {
              'id': 'm-1',
              'thread_id': 't-gold',
              'role': 'user',
              'seq': 4,
              'content': (body as Map)['content'],
            },
            'runs': [],
          },
        );
      await pumpScreen(
        tester,
        const AgentMemoryScreen(agentId: 'a-gold'),
        locale: 'en',
      );
      await tester.enterText(remember(), '  I prefer levels first ');
      await tester.pump();
      await tapAndSettle(tester, find.bySemanticsLabel('Send'));
      final call = fakeApi.callsTo('POST', '/threads/t-gold/messages').single;
      expect((call.body! as Map)['content'], 'Remember: I prefer levels first');
      expect((call.body! as Map)['attachment_ids'], isEmpty);
      expect(find.text('I prefer levels first'), findsNothing);
      expect(
        find.text('Sent to your conversation with \u2068Gold desk\u2069'),
        findsOneWidget,
      );
      await settleToasts(tester);
    });

    testWidgets('only under the Memory tab, and not while editing', (
      tester,
    ) async {
      scriptMemory();
      await pumpScreen(
        tester,
        const AgentMemoryScreen(agentId: 'a-gold'),
        locale: 'en',
      );
      await tapAndSettle(tester, find.text('Knowledge'));
      expect(find.byType(RememberField), findsNothing);
      await tapAndSettle(tester, find.text('Memory'));
      expect(find.byType(RememberField), findsOneWidget);
      await tapAndSettle(tester, find.text('Edit memory'));
      expect(find.byType(RememberField), findsNothing);
    });

    testWidgets('an Arabic date line uses Arabic-Indic digits only', (
      tester,
    ) async {
      scriptMemory();
      await pumpScreen(tester, const AgentMemoryScreen(agentId: 'a-gold'));
      final line = find.textContaining('آخر تحديث');
      expect(line, findsOneWidget);
      final text = tester.widget<Text>(line).data!;
      expect(text, contains('٠٨:١٥'));
      expect(text, isNot(matches(RegExp('[0-9]'))));
    });
  });

  testWidgets('an undone change shows «Restored» and offers no undo', (
    tester,
  ) async {
    scriptMemory();
    fakeApi.on(
      'GET /agents/a-gold/memory/revisions',
      (_, _) => [
        {
          'id': 'rev-3',
          'document': 'agent_memory',
          'author': 'owner',
          'change': 'revert',
          'reverted_revision_id': 'rev-2',
          'created_at': '2026-11-26T09:00:00+00:00',
          'changes': [
            {
              'change': 'removed',
              'text': '- Never trade during the US CPI release.',
            },
          ],
        },
        {
          'id': 'rev-2',
          'document': 'agent_memory',
          'author': 'agent',
          'author_agent_name': 'Gold desk',
          'change': 'edit',
          'created_at': '2026-11-26T08:15:00+00:00',
          'changes': [
            {
              'change': 'added',
              'text': '- Never trade during the US CPI release.',
            },
          ],
        },
      ],
    );
    await pumpScreen(
      tester,
      const AgentMemoryScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    final restored = find.text('Restored');
    await tester.scrollUntilVisible(
      restored,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(restored, findsOneWidget);
    await tester.ensureVisible(restored);
    await tester.pumpAndSettle();
    await tapAndSettle(tester, restored);
    expect(find.text('Undo this change'), findsNothing);
  });

  for (final v in goldenVariants) {
    testWidgets('golden memory ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptMemory();
        await pumpScreen(
          tester,
          const AgentMemoryScreen(agentId: 'a-gold'),
          brightness: v.brightness,
          locale: v.locale,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/memory_${v.name}.png'),
        );
      });
    });
  }

  for (final v in [goldenVariants[0], goldenVariants[3]]) {
    testWidgets('golden knowledge ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptMemory();
        await pumpScreen(
          tester,
          const AgentMemoryScreen(agentId: 'a-gold'),
          brightness: v.brightness,
          locale: v.locale,
        );
        await tester.tap(find.text(v.locale == 'ar' ? 'المعرفة' : 'Knowledge'));
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/knowledge_${v.name}.png'),
        );
      });
    });
  }

  for (final (v, tab) in [
    (goldenVariants[0], 'goals'),
    (goldenVariants[3], 'scratchpad'),
  ]) {
    testWidgets('golden $tab ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptMemory();
        fakeApi
          ..on(
            'GET /agent-goals',
            (_, _) => [
              {
                'id': 'g-1',
                'version': 3,
                'payload': {
                  'title': 'إبقاء التراجع تحت 2%',
                  'description':
                      'Close the day flat when the drawdown nears the limit.',
                  'done': false,
                },
              },
              {
                'id': 'g-2',
                'version': 1,
                'payload': {
                  'title': 'Weekly report every Friday',
                  'description': '',
                  'done': true,
                },
              },
            ],
          )
          ..on(
            'GET /scratchpad',
            (_, _) => [
              {
                'id': 's-1',
                'version': 5,
                'payload': {
                  'title': 'Levels',
                  'content': '2330 support · 2350 resistance 📈',
                },
              },
            ],
          );
        await pumpScreen(
          tester,
          const AgentMemoryScreen(agentId: 'a-gold'),
          brightness: v.brightness,
          locale: v.locale,
        );
        final label = switch ((tab, v.locale)) {
          ('goals', 'ar') => 'الأهداف',
          ('goals', _) => 'Goals',
          (_, 'ar') => 'المعرفة',
          _ => 'Knowledge',
        };
        await tester.tap(find.text(label));
        await tester.pumpAndSettle();
        if (tab == 'scratchpad') {
          // The scratchpad group under the notes and links.
          await tester.drag(
            find.byType(Scrollable).first,
            const Offset(0, -400),
          );
          await tester.pumpAndSettle();
        }
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/${tab}_${v.name}.png'),
        );
      });
    });
  }

  testWidgets('golden memory bottom light_ar', (tester) async {
    await withRealShadows(() async {
      scriptMemory();
      await pumpScreen(tester, const AgentMemoryScreen(agentId: 'a-gold'));
      await tester.drag(find.byType(Scrollable).first, const Offset(0, -1200));
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/memory_bottom_light_ar.png'),
      );
    });
  });

  testWidgets('golden empty memory light_ar', (tester) async {
    await withRealShadows(() async {
      scriptMemory(content: '');
      fakeApi.on('GET /agents/a-gold/memory/revisions', (_, _) => []);
      await pumpScreen(tester, const AgentMemoryScreen(agentId: 'a-gold'));
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/memory_empty_light_ar.png'),
      );
    });
  });
}
