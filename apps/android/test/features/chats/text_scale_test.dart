// Every screen of the feature lays out without overflow at a 1.3 text scale, in both
// languages (an overflow fails the test).
import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart' show Size;
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/state/app_state.dart';

import 'harness.dart';

void main() {
  setUpAll(setUpFeatureHarness);
  setUp(() {
    resetFakeApi();
    fakeApi.handlers['GET /search'] = (_, _) => {
      'q': '',
      'counts': {'chats': 1},
      'results': {
        'chats': [
          {
            'category': 'chats',
            'id': 'a-gold',
            'title': 'Gold desk',
            'kind': 'agent',
            'agent_id': 'a-gold',
          },
        ],
      },
    };
    fakeApi.handlers['GET /groups/g-desk'] = (_, _) => fixtureGroups.first;
  });

  for (final route in [
    Routes.chats,
    Routes.archived,
    Routes.search,
    Routes.agents,
    Routes.newGroup(members: ['a-gold']),
    Routes.groupSettings('g-desk'),
  ]) {
    for (final locale in ['ar', 'en']) {
      testWidgets('$route at 1.3 ($locale)', (tester) async {
        setGoldenViewport(tester, size: const Size(360, 740));
        final store = Store<AppState>(initialState: fixtureState());
        await tester.pumpWidget(
          featureApp(
            store: store,
            router: testRouter(route),
            locale: locale,
            textScale: 1.3,
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(tester.takeException(), isNull);
      });
    }
  }

  for (final locale in ['ar', 'en']) {
    testWidgets('the row menu, the selection toolbar and its sheet at 1.3 '
        '($locale)', (tester) async {
      setGoldenViewport(tester, size: const Size(360, 740));
      final store = Store<AppState>(initialState: fixtureState(working: false));
      await tester.pumpWidget(
        featureApp(
          store: store,
          router: testRouter(Routes.chats),
          locale: locale,
          textScale: 1.3,
        ),
      );
      await tester.pumpAndSettle();
      await tester.longPress(find.text('Gold desk'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.tap(find.text(locale == 'ar' ? 'تحديد' : 'Select'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Morning news'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.bySemanticsLabel(locale == 'ar' ? 'المزيد' : 'More'),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }
}
