// The agents list: every agent with its status (tap → profile), the groups with their size,
// «إنشاء مجموعة», and goldens.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart' show withRealShadows;
import '../chats/harness.dart';

Future<void> pumpAgents(
  WidgetTester tester, {
  Brightness brightness = Brightness.light,
  String locale = 'ar',
}) async {
  setGoldenViewport(tester);
  final store = Store<AppState>(initialState: fixtureState(working: false));
  await tester.pumpWidget(
    featureApp(
      store: store,
      router: testRouter(Routes.agents),
      brightness: brightness,
      locale: locale,
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(setUpFeatureHarness);
  setUp(resetFakeApi);

  testWidgets('lists every agent with its status and opens its profile', (
    tester,
  ) async {
    await pumpAgents(tester, locale: 'en');
    expect(find.text('Lonora'), findsOneWidget);
    expect(find.text('Your personal assistant'), findsOneWidget);
    expect(find.text('Active'), findsNWidgets(5));
    expect(find.text('Paused'), findsOneWidget);
    await tester.tap(find.text('Gold desk'));
    await tester.pumpAndSettle();
    expect(shownRoute(tester), '/agent/a-gold');
  });

  testWidgets('lists the groups with their size and creates one', (
    tester,
  ) async {
    await pumpAgents(tester, locale: 'en');
    await tester.scrollUntilVisible(find.text('Create a group'), 200);
    expect(find.text(L10n.instance.agentsWord(3)), findsOneWidget);
    await tester.tap(find.text('Create a group'));
    await tester.pumpAndSettle();
    expect(find.text('New group'), findsOneWidget);
  });

  testWidgets('a failed first load offers a retry', (tester) async {
    setGoldenViewport(tester);
    fakeApi.handlers['GET /agents'] = (_, _) => fixtureAgents;
    await tester.pumpWidget(
      featureApp(
        store: Store<AppState>(
          initialState: fixtureState(
            loaded: false,
            agents: [],
            groups: [],
            inbox: [],
            lastError: 'network',
          ),
        ),
        router: testRouter(Routes.agents),
        locale: 'en',
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(ErrorState), findsOneWidget);
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('GET', '/agents'), hasLength(1));
    expect(find.text('Gold desk'), findsOneWidget);
    await settleToasts(tester);
  });

  testWidgets(
    'Q7 «Active» reads in the text-safe green; the dot keeps its own',
    (tester) async {
      await pumpAgents(tester, locale: 'en');
      final c = LnPalette.light;
      final label = tester.widget<Text>(find.text('Active').first);
      expect(label.style!.color, c.successText);
      final row = find.ancestor(
        of: find.text('Active').first,
        matching: find.byType(Row),
      );
      final dot = tester.widget<Container>(
        find.descendant(of: row.first, matching: find.byType(Container)).first,
      );
      expect((dot.decoration! as BoxDecoration).color, c.success);
      expect(tester.widget<Text>(find.text('Paused')).style!.color, c.fgMuted);
    },
  );

  testWidgets('F4 the loading rows are announced in the interface language', (
    tester,
  ) async {
    setGoldenViewport(tester);
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      featureApp(
        store: Store<AppState>(
          initialState: fixtureState(
            loaded: false,
            agents: [],
            groups: [],
            inbox: [],
          ),
        ),
        router: testRouter(Routes.agents),
        locale: 'ar',
      ),
    );
    await tester.pump();
    expect(find.byType(SkeletonRows), findsOneWidget);
    expect(find.bySemanticsLabel('جارٍ التحميل'), findsOneWidget);
    expect(find.bySemanticsLabel('Loading'), findsNothing);
    handle.dispose();
  });

  for (final (brightness, locale) in [
    (Brightness.light, 'ar'),
    (Brightness.dark, 'en'),
  ]) {
    testWidgets('golden ${brightness.name} $locale', (tester) async {
      await withRealShadows(() async {
        await pumpAgents(tester, brightness: brightness, locale: locale);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/agents_${brightness.name}_$locale.png'),
        );
      });
    });
  }
}
