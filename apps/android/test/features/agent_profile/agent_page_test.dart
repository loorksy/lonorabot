// Kit adoption in the shared agent page pieces (ADOPT-A): ContentField hands its reading
// direction and length cap to LnTextField, a one-line FullTile is a 52 dp row like
// LnListTile, and the editor's ✓ circle.
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart' show SemanticsAction;
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/agents/profile/agent_page.dart';

import '../../design/fonts.dart';
import '../../design/harness.dart';

Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  TextDirection direction = TextDirection.rtl,
}) async {
  setGoldenViewport(tester);
  await tester.pumpWidget(
    lnTestApp(
      direction: direction,
      child: ListView(children: [child]),
    ),
  );
  await tester.pump();
}

TextDirection? _editDirection(WidgetTester tester) =>
    tester.widget<EditableText>(find.byType(EditableText)).textDirection;

void main() {
  setUpAll(loadAppFonts);

  group('ContentField', () {
    testWidgets('the text reads in its own direction; the field and label '
        'follow the interface', (tester) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await _pump(tester, ContentField(controller: controller, label: 'الاسم'));
      expect(
        tester.widget<LnTextField>(find.byType(LnTextField)).textDirection,
        TextDirection.rtl,
      );

      await tester.enterText(find.byType(TextField), 'Buy the dip');
      await tester.pump();
      expect(_editDirection(tester), TextDirection.ltr);
      expect(
        tester.widget<LnTextField>(find.byType(LnTextField)).textDirection,
        TextDirection.ltr,
      );
      // The direction goes to LnTextField, not to a Directionality around it: the field's
      // chrome (padding, touch band, label) stays Arabic.
      expect(
        Directionality.of(tester.element(find.byType(LnTextField))),
        TextDirection.rtl,
      );

      await tester.enterText(find.byType(TextField), 'اشترِ عند الهبوط');
      await tester.pump();
      expect(_editDirection(tester), TextDirection.rtl);
    });

    testWidgets('ltrOnly reads left to right, hint included', (tester) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await _pump(
        tester,
        ContentField(controller: controller, hint: '0 9 * * 1', ltrOnly: true),
      );
      expect(_editDirection(tester), TextDirection.ltr);
      expect(
        tester.widget<Text>(find.text('0 9 * * 1')).textDirection,
        TextDirection.ltr,
      );
    });

    testWidgets('F1 ltrOnly turns autocorrect and suggestions off', (
      tester,
    ) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      for (final ltrOnly in [true, false]) {
        await _pump(
          tester,
          ContentField(
            key: ValueKey(ltrOnly),
            controller: controller,
            ltrOnly: ltrOnly,
          ),
        );
        final field = tester.widget<TextField>(find.byType(TextField));
        expect(field.autocorrect, !ltrOnly, reason: 'ltrOnly: $ltrOnly');
        expect(field.enableSuggestions, !ltrOnly, reason: 'ltrOnly: $ltrOnly');
      }
    });

    testWidgets('maxLength caps the input through LnTextField, no counter', (
      tester,
    ) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await _pump(tester, ContentField(controller: controller, maxLength: 5));
      expect(tester.widget<LnTextField>(find.byType(LnTextField)).maxLength, 5);
      expect(tester.widget<TextField>(find.byType(TextField)).maxLength, 5);

      await tester.enterText(find.byType(TextField), 'abcdefgh');
      await tester.pump();
      expect(controller.text, 'abcde');
      expect(find.text('5/5'), findsNothing);
    });
  });

  group('FullTile', () {
    for (final direction in TextDirection.values) {
      testWidgets('a one-line row is 52 dp (${direction.name})', (
        tester,
      ) async {
        await _pump(
          tester,
          LnSection(
            children: [
              FullTile(
                icon: FIcons.eye,
                title: 'Prefers short replies',
                onTap: () {},
              ),
              FullTile(
                title: 'Opens the app at 8',
                subtitle: 'Observed',
                onTap: () {},
              ),
            ],
          ),
          direction: direction,
        );
        // Each row's pressable box (inside forui's divider margin).
        final rows = find.byWidgetPredicate((w) => w is FTappable);
        expect(rows, findsNWidgets(2));
        final one = tester.getRect(rows.first);
        expect(one.height, LnSize.tileRow);
        // Two-line rows keep forui's own height (already above the minimum).
        expect(tester.getRect(rows.last).height, greaterThan(LnSize.minTouch));
        // The title sits in the middle of the taller row, at its reading edge.
        final title = tester.getRect(find.text('Prefers short replies'));
        expect(title.center.dy, one.center.dy);
        if (direction == TextDirection.ltr) {
          expect(title.left - one.left, lessThan(one.width / 3));
        } else {
          expect(one.right - title.right, lessThan(one.width / 3));
        }
      });
    }
  });

  group('ConfirmCircle', () {
    testWidgets('a 44 dp circle in a 48 dp button; enabled it is the action '
        'blue with a white check', (tester) async {
      var taps = 0;
      await _pump(
        tester,
        Center(
          child: ConfirmCircle(semanticLabel: 'Save', onTap: () => taps++),
        ),
      );
      final button = find.bySemanticsLabel('Save');
      expect(tester.getSize(button), const Size.square(LnSize.minTouch));
      final circle = tester.widget<AnimatedContainer>(
        find.byType(AnimatedContainer),
      );
      final fill = (circle.decoration! as BoxDecoration).color;
      expect(fill, LnPalette.light.selectionFill);
      expect(
        tester.widget<Icon>(find.byIcon(FIcons.check)).color,
        LnPalette.light.onAccent,
      );
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(taps, 1);
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
    });

    testWidgets('disabled it is the chrome circle with a tertiary check and '
        'no tap', (tester) async {
      final handle = tester.ensureSemantics();
      await _pump(
        tester,
        const Center(child: ConfirmCircle(semanticLabel: 'Save')),
      );
      final circle = tester.widget<AnimatedContainer>(
        find.byType(AnimatedContainer),
      );
      expect(
        (circle.decoration! as BoxDecoration).color,
        LnPalette.light.chromeCircle,
      );
      expect(
        tester.widget<Icon>(find.byIcon(FIcons.check)).color,
        LnPalette.light.fgSubtle,
      );
      expect(
        tester
            .getSemantics(find.bySemanticsLabel('Save'))
            .getSemanticsData()
            .hasAction(SemanticsAction.tap),
        isFalse,
      );
      handle.dispose();
    });
  });
}
