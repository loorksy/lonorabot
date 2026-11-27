import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/design/design.dart';

import 'harness.dart';

void main() {
  testWidgets('a scaled tappable can rebuild in place', (tester) async {
    final label = ValueNotifier('a');
    await tester.pumpWidget(
      lnTestApp(
        child: ValueListenableBuilder<String>(
          valueListenable: label,
          builder: (_, v, _) =>
              LnTappable(onTap: () {}, pressScale: 0.98, child: Text(v)),
        ),
      ),
    );
    label.value = 'b';
    await tester.pump();
    label.value = 'c';
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.text('c'), findsOneWidget);
  });

  testWidgets(
    'K10: excluding the child\'s semantics keeps the label, the button role and the tap',
    (tester) async {
      final handle = tester.ensureSemantics();
      var taps = 0;
      await tester.pumpWidget(
        lnTestApp(
          child: Center(
            child: LnTappable(
              onTap: () => taps++,
              semanticLabel: 'Search',
              excludeChildSemantics: true,
              child: const Text('child words'),
            ),
          ),
        ),
      );
      final node = find.semantics.byLabel('Search');
      expect(
        node.evaluate().single.getSemanticsData(),
        isSemantics(
          label: 'Search',
          isButton: true,
          isFocusable: true,
          hasTapAction: true,
          hasFocusAction: true,
        ),
      );
      expect(find.bySemanticsLabel('child words'), findsNothing);
      tester.semantics.tap(node);
      expect(taps, 1);
      handle.dispose();
    },
  );

  testWidgets('K10: the hint and the selected state sit on the same node as the label and the '
      'tap', (tester) async {
    final handle = tester.ensureSemantics();
    var taps = 0;
    await tester.pumpWidget(
      lnTestApp(
        child: Center(
          child: LnTappable(
            onTap: () => taps++,
            semanticLabel: 'Row',
            semanticHint: 'Opens the chat',
            selected: true,
            excludeChildSemantics: true,
            child: const Text('child words'),
          ),
        ),
      ),
    );
    final node = find.semantics.byLabel('Row');
    expect(
      node.evaluate().single.getSemanticsData(),
      isSemantics(
        label: 'Row',
        hint: 'Opens the chat',
        isButton: true,
        hasSelectedState: true,
        isSelected: true,
        hasTapAction: true,
        hasFocusAction: true,
      ),
    );
    // No second node carries the hint without the actions.
    expect(find.semantics.byHint('Opens the chat'), findsOne);
    tester.semantics.tap(node);
    expect(taps, 1);
    handle.dispose();
  });
}
