// Search: the browse feed, a debounced query with highlighted hits, tabs, message hits opening
// their conversation at their place, the "no results" state, and goldens.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/features/chats/search_screen.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart' show withRealShadows;
import 'harness.dart';

Json _hit(String category, String id, Json extra) => {
  'category': category,
  'id': id,
  'title': '',
  'snippet': '',
  'created_at': DateTime(2026, 11, 27, 11, 40).toUtc().toIso8601String(),
  ...extra,
};

Json searchResponse(String q, String? category) {
  final chats = [
    _hit('chats', 'a-gold', {
      'title': 'Gold desk',
      'kind': 'agent',
      'agent_id': 'a-gold',
    }),
    _hit('chats', 'g-desk', {
      'title': 'Trading desk',
      'kind': 'group',
      'group_id': 'g-desk',
    }),
  ];
  final messages = [
    _hit('messages', 'm1', {
      'snippet': 'Gold is +1.2% since the open; the plan holds.',
      'thread_id': 't-gold',
      'seq': 4,
      'role': 'assistant',
      'agent_id': 'a-gold',
      'thread_agent_id': 'a-gold',
    }),
    _hit('messages', 'm2', {
      'snippet': 'Watch gold into the close please',
      'thread_id': 't-gold',
      'seq': 3,
      'role': 'user',
      'agent_id': 'a-gold',
      'thread_agent_id': 'a-gold',
    }),
  ];
  final files = [
    _hit('files', 'f1', {
      'title': 'gold-plan.md',
      'snippet': 'gold-plan.md',
      'agent_id': 'a-gold',
    }),
  ];
  if (q == 'nothing') {
    return {'q': q, 'counts': <String, int>{}, 'results': <String, Object>{}};
  }
  final all = {'chats': chats, 'messages': messages, 'files': files};
  final results = category == null ? all : {category: ?all[category]};
  return {
    'q': q,
    'category': category,
    'counts': {for (final e in results.entries) e.key: e.value.length},
    'results': results,
  };
}

Future<void> pumpSearch(
  WidgetTester tester, {
  Brightness brightness = Brightness.light,
  String locale = 'ar',
}) async {
  setGoldenViewport(tester);
  fakeApi.handlers['GET /search'] = (_, query) =>
      searchResponse(asStr(query?['q']), asString(query?['category']));
  final store = Store<AppState>(initialState: fixtureState());
  await tester.pumpWidget(
    featureApp(
      store: store,
      router: testRouter(Routes.search),
      brightness: brightness,
      locale: locale,
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> typeQuery(WidgetTester tester, String q) async {
  await tester.enterText(find.byType(TextField), q);
  await tester.pump(const Duration(milliseconds: 200));
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(setUpFeatureHarness);
  setUp(() {
    resetFakeApi();
    forgetSearchResume();
  });

  testWidgets('an empty query browses what is recent', (tester) async {
    await pumpSearch(tester, locale: 'en');
    final call = fakeApi.callsTo('GET', '/search').single;
    expect(call.query, {'q': '', 'limit': 4, 'offset': 0});
    expect(find.text('Recent chats'), findsOneWidget);
    expect(find.text('Recent messages'), findsOneWidget);
    expect(
      find.text('Type a word to search chats, messages, tasks and files.'),
      findsOneWidget,
    );
  });

  testWidgets(
    'a query is debounced, only the latest lands, and hits are marked',
    (tester) async {
      await pumpSearch(tester, locale: 'en');
      fakeApi.calls.clear();
      await tester.enterText(find.byType(TextField), 'g');
      await tester.pump(const Duration(milliseconds: 50));
      await tester.enterText(find.byType(TextField), 'gold');
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pumpAndSettle();
      final calls = fakeApi.callsTo('GET', '/search');
      expect(calls, hasLength(1));
      expect(calls.single.query, {'q': 'gold', 'limit': 3, 'offset': 0});
      expect(find.text('Agents and groups'), findsOneWidget);
      expect(find.text('Matching messages'), findsOneWidget);
      // The match is a marked span inside the hit's text.
      final marked = tester
          .widgetList<RichText>(find.byType(RichText))
          .map((r) => r.text.toPlainText())
          .where((t) => t.contains('Gold is'))
          .toList();
      expect(marked, isNotEmpty);
    },
  );

  testWidgets('a message hit opens its conversation at its place', (
    tester,
  ) async {
    await pumpSearch(tester, locale: 'en');
    await typeQuery(tester, 'gold');
    await tester.tap(find.textContaining('since the open'));
    await tester.pumpAndSettle();
    expect(shownRoute(tester), '/chats/thread/t-gold?around=4');
  });

  testWidgets('a chat hit opens the chat; a file hit opens the file', (
    tester,
  ) async {
    await pumpSearch(tester, locale: 'en');
    await typeQuery(tester, 'gold');
    await tester.tap(find.text('gold-plan.md'));
    await tester.pumpAndSettle();
    expect(shownRoute(tester), '/files/f1');
    await pumpSearch(tester, locale: 'en');
    await typeQuery(tester, 'gold');
    // The chats section comes first (the file hit's meta names the agent too).
    await tester.tap(find.text('Gold desk').first);
    await tester.pumpAndSettle();
    expect(shownRoute(tester), '/chats/thread/t-gold');
  });

  testWidgets('a stale answer arriving last never replaces the latest', (
    tester,
  ) async {
    await pumpSearch(tester, locale: 'en');
    fakeApi.handlers['GET /search'] = (_, query) {
      final q = asStr(query?['q']);
      final answer = searchResponse(q, asString(query?['category']));
      if (q != 'g') return answer;
      // The first query's answer comes back after the second one's.
      return Future.delayed(const Duration(seconds: 1), () {
        return {
          ...answer,
          'counts': {'chats': 1},
          'results': {
            'chats': [
              _hit('chats', 'a-news', {
                'title': 'Stale answer',
                'kind': 'agent',
                'agent_id': 'a-news',
              }),
            ],
          },
        };
      });
    };
    await tester.enterText(find.byType(TextField), 'g');
    await tester.pump(const Duration(milliseconds: 200));
    await tester.enterText(find.byType(TextField), 'gold');
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('GET', '/search').map((c) => c.query?['q']), [
      '',
      'g',
      'gold',
    ]);
    expect(find.text('Stale answer'), findsNothing);
    expect(find.text('Gold desk'), findsWidgets);
  });

  testWidgets('the next search resumes the query a hit left', (tester) async {
    await pumpSearch(tester, locale: 'en');
    await typeQuery(tester, 'gold');
    await tester.tap(find.text('Messages'));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('since the open'));
    await tester.pumpAndSettle();
    expect(shownRoute(tester), '/chats/thread/t-gold?around=4');
    fakeApi.calls.clear();
    await pumpSearch(tester, locale: 'en');
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      'gold',
    );
    expect(
      fakeApi.callsTo('GET', '/search').first.query?['category'],
      'messages',
    );
    // Only once: a search opened afterwards starts empty.
    await pumpSearch(tester, locale: 'en');
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      isEmpty,
    );
  });

  testWidgets('a tab pages its category', (tester) async {
    await pumpSearch(tester, locale: 'en');
    await typeQuery(tester, 'gold');
    fakeApi.calls.clear();
    await tester.tap(find.text('Messages'));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('GET', '/search').single.query, {
      'q': 'gold',
      'limit': 32,
      'offset': 0,
      'category': 'messages',
    });
    expect(find.textContaining('since the open'), findsOneWidget);
    expect(find.text('Gold desk'), findsNothing);
  });

  testWidgets('no results says so', (tester) async {
    await pumpSearch(tester, locale: 'en');
    await typeQuery(tester, 'nothing');
    expect(find.text('No results'), findsOneWidget);
    expect(
      find.text(
        'We found no results for «nothing». Try a shorter word or a different term.',
      ),
      findsOneWidget,
    );
  });

  for (final (brightness, locale) in [
    (Brightness.light, 'ar'),
    (Brightness.light, 'en'),
    (Brightness.dark, 'ar'),
  ]) {
    testWidgets('golden results ${brightness.name} $locale', (tester) async {
      await withRealShadows(() async {
        await pumpSearch(tester, brightness: brightness, locale: locale);
        await typeQuery(tester, locale == 'ar' ? 'gold' : 'gold');
        FocusManager.instance.primaryFocus?.unfocus();
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(
            'goldens/search_results_${brightness.name}_$locale.png',
          ),
        );
      });
    });
  }

  testWidgets('golden no results light ar', (tester) async {
    await withRealShadows(() async {
      await pumpSearch(tester);
      await typeQuery(tester, 'nothing');
      FocusManager.instance.primaryFocus?.unfocus();
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/search_empty_light_ar.png'),
      );
    });
  });
}
