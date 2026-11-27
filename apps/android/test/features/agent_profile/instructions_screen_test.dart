// The full-page instructions editor: the editor card's layout, the ✓ enabled only when the text
// changed, the save through `PATCH /agents/{id}`, the discard question, reading direction;
// goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/agent_profile
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart' show SemanticsAction;
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/agents/instructions_screen.dart';

import 'wpe_harness.dart';

bool _canTap(WidgetTester tester, String label) => tester
    .getSemantics(find.bySemanticsLabel(label))
    .getSemanticsData()
    .hasAction(SemanticsAction.tap);

void main() {
  setUpAll(setUpWpeHarness);
  setUp(resetWpe);

  testWidgets('the editor card fills the page under the header', (
    tester,
  ) async {
    await pumpScreen(
      tester,
      const AgentInstructionsScreen(agentId: 'a-gold'),
      locale: 'en',
      brightness: Brightness.dark,
    );
    expect(find.text('Instructions'), findsOneWidget);
    final scaffold = tester.widget<Scaffold>(find.byType(Scaffold));
    expect(scaffold.backgroundColor, LnPalette.dark.sheetPage);
    final card = find.ancestor(
      of: find.byType(TextField),
      matching: find.byWidgetPredicate(
        (w) =>
            w is DecoratedBox &&
            (w.decoration as BoxDecoration).color == LnPalette.dark.editorCard,
      ),
    );
    final box = tester.widget<DecoratedBox>(card);
    expect(
      (box.decoration as BoxDecoration).borderRadius,
      const BorderRadius.all(Radius.circular(26)),
    );
    final rect = tester.getRect(card);
    final screen = tester.getSize(find.byType(MaterialApp));
    expect(rect.left, 16);
    expect(rect.right, screen.width - 16);
    expect(screen.height - rect.bottom, 16);
    // Just under the header row.
    final back = tester.getRect(find.bySemanticsLabel('Back'));
    expect(rect.top - back.bottom, lessThan(16));
    // The text starts 16 dp inside the card.
    final text = tester.getRect(find.byType(EditableText));
    expect(text.left - rect.left, 16);
    expect(text.top - rect.top, 16);
  });

  testWidgets('✓ saves only a change, through the agent settings write', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    fakeApi.on(
      'PATCH /agents/a-gold',
      (body, _) => {...fixtureAgents[1], ...(body as Map<String, dynamic>)},
    );
    final store = await pumpScreen(
      tester,
      const AgentInstructionsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    expect(find.textContaining('Trade only XAUUSD.'), findsOneWidget);
    expect(_canTap(tester, 'Save'), isFalse);
    await tester.enterText(find.byType(TextField), 'Trade only gold.');
    await tester.pump();
    expect(_canTap(tester, 'Save'), isTrue);
    await tapAndSettle(tester, find.bySemanticsLabel('Save'));
    expect(fakeApi.callsTo('PATCH', '/agents/a-gold').single.body, {
      'instructions': 'Trade only gold.',
    });
    expect(
      store.state.shell.agents['a-gold']!.instructions,
      'Trade only gold.',
    );
    expect(shownRoute(tester), '/agent/a-gold');
    await settleToasts(tester);
    handle.dispose();
  });

  testWidgets('typing back the saved text turns ✓ off again', (tester) async {
    final handle = tester.ensureSemantics();
    await pumpScreen(
      tester,
      const AgentInstructionsScreen(agentId: 'a-research'),
      locale: 'en',
    );
    await tester.enterText(find.byType(TextField), 'x');
    await tester.pump();
    expect(_canTap(tester, 'Save'), isTrue);
    await tester.enterText(find.byType(TextField), '');
    await tester.pump();
    expect(_canTap(tester, 'Save'), isFalse);
    handle.dispose();
  });

  testWidgets('leaving with edits asks first', (tester) async {
    await pumpScreen(
      tester,
      const AgentInstructionsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await tester.enterText(find.byType(TextField), 'Something else');
    await tester.pump();
    await tapAndSettle(tester, find.bySemanticsLabel('Back'));
    expect(find.text('Discard the changes?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Keep editing'));
    expect(find.text('Something else'), findsOneWidget);
    expect(fakeApi.callsTo('PATCH', '/agents/a-gold'), isEmpty);
    await tapAndSettle(tester, find.bySemanticsLabel('Back'));
    await tapAndSettle(tester, find.text('Discard'));
    expect(shownRoute(tester), '/agent/a-gold');
  });

  testWidgets('empty, it shows the hint in the tertiary ink; an English '
      'instruction reads left to right in Arabic', (tester) async {
    await pumpScreen(
      tester,
      const AgentInstructionsScreen(agentId: 'a-research'),
    );
    final field = tester.widget<TextField>(find.byType(TextField));
    expect(
      field.decoration!.hintText,
      'ما يتبعه الوكيل في كل محادثة وكل مهمة.',
    );
    expect(field.decoration!.hintStyle!.color, LnPalette.light.fgSubtle);
    expect(field.textDirection, TextDirection.rtl);
    await tester.enterText(find.byType(TextField), 'Answer in English.');
    await tester.pump();
    expect(
      tester.widget<TextField>(find.byType(TextField)).textDirection,
      TextDirection.ltr,
    );
    // The › back circle is at the right (start) in Arabic, the ✓ at the left.
    final back = tester.getRect(find.bySemanticsLabel('رجوع'));
    final save = tester.getRect(find.bySemanticsLabel('حفظ'));
    expect(back.left, greaterThan(save.right));
  });

  testWidgets('header circles are 48 dp labelled targets', (tester) async {
    final handle = tester.ensureSemantics();
    await pumpScreen(
      tester,
      const AgentInstructionsScreen(agentId: 'a-gold'),
      locale: 'en',
    );
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
    handle.dispose();
  });

  for (final v in [goldenVariants[1], goldenVariants[2]]) {
    testWidgets('golden instructions ${v.name}', (tester) async {
      await withRealShadows(() async {
        await pumpScreen(
          tester,
          AgentInstructionsScreen(
            agentId: v.locale == 'ar' ? 'a-research' : 'a-gold',
          ),
          brightness: v.brightness,
          locale: v.locale,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/instructions_${v.name}.png'),
        );
      });
    });
  }
}
