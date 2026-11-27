import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/design/design.dart';

import 'harness.dart';

void main() {
  testWidgets('K15: the caller\'s whole label is announced as given', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      lnTestApp(
        direction: TextDirection.rtl,
        child: Center(
          child: JumpToLatestButton(
            visible: true,
            onTap: () {},
            unreadCount: 3,
            semanticLabel: 'الانتقال إلى الأحدث، 3 غير مقروءة',
          ),
        ),
      ),
    );
    // The Arabic comma stays; nothing English is appended for the count.
    expect(
      find.bySemanticsLabel('الانتقال إلى الأحدث، 3 غير مقروءة'),
      findsOneWidget,
    );
    expect(find.bySemanticsLabel(RegExp('unread|, ')), findsNothing);
    handle.dispose();
  });

  testWidgets('without unread messages only the label is announced', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      lnTestApp(
        child: Center(
          child: JumpToLatestButton(
            visible: true,
            onTap: () {},
            semanticLabel: 'Jump to latest',
          ),
        ),
      ),
    );
    expect(find.bySemanticsLabel('Jump to latest'), findsOneWidget);
    handle.dispose();
  });
}
