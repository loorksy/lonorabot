// The chats tab: order and marks of the rows, the hidden filters, the archived row, the row
// menu, the selection toolbar, the states, and goldens (light/dark × ar/en).
//
// Regenerate the goldens with: flutter test --update-goldens test/features/chats
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/agents/create_agent_sheet.dart';
import 'package:lonora/features/chats/chat_rows.dart';
import 'package:lonora/features/chats/chat_widgets.dart';
import 'package:lonora/features/groups/create_group_sheet.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart' show withRealShadows;
import 'harness.dart';

Future<Store<AppState>> pumpChats(
  WidgetTester tester, {
  AppState? state,
  Brightness brightness = Brightness.light,
  String locale = 'ar',
  String route = Routes.chats,
}) async {
  setGoldenViewport(tester);
  final store = Store<AppState>(initialState: state ?? fixtureState());
  await tester.pumpWidget(
    featureApp(
      store: store,
      router: testRouter(route),
      brightness: brightness,
      locale: locale,
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  return store;
}

List<String> visibleTitles(WidgetTester tester) => tester
    .widgetList<ChatListRow>(find.byType(ChatListRow))
    .map((r) => r.title)
    .toList();

void main() {
  setUpAll(setUpFeatureHarness);
  setUp(resetFakeApi);

  test('rows follow the shared order: pins, latest message, then agents before groups', () {
    final rows = chatRowsOf(fixtureState());
    expect(filterRows(rows, 'all').map((r) => r.name), [
      'Lonora',
      'Gold desk',
      'Morning news',
      'Trading desk',
      'Research',
      'FX watcher',
      'Reading club',
    ]);
    expect(archivedSummary(rows), (count: 1, unread: 1));
    expect(filterRows(rows, 'unread').map((r) => r.name), [
      'Gold desk',
      'Morning news',
      'Trading desk',
    ]);
    expect(filterRows(rows, 'groups').map((r) => r.name), [
      'Trading desk',
      'Reading club',
    ]);
    final desk = rows.firstWhere((r) => r.id == 'g-desk');
    expect(desk.threadId, 't-desk');
    expect(isMuted(desk), isTrue);
    expect(rowCount(desk), 1);
    final news = rows.firstWhere((r) => r.id == 'a-news');
    expect(rowMarkedOnly(news), isTrue);
    expect(rowUnread(news), 1);
    // An archived chat never keeps its pin position.
    final archived = chatRows(fixtureState().shell.orderedAgents, const [], [
      ...fixtureState().shell.inbox.where((e) => e.threadId != 't-old'),
      fixtureState().shell.inbox
          .firstWhere((e) => e.threadId == 't-old')
          .withPrefs({'pinned_order': 0}),
    ]);
    expect(isPinned(archived.firstWhere((r) => r.id == 'a-old')), isFalse);
    expect(pinsAfter(rows, [rows[1], rows[2], rows[3]]), 4);
    // cc:C1: the drafted name joins with the owner's language's list separator.
    expect(groupDraftName(['A', 'B', 'C', 'D'], 'ar'), 'A، B، C');
    expect(groupDraftName(['A', 'B', 'C', 'D'], 'en'), 'A, B, C');
  });

  testWidgets('shows the rows in order with the archived row, filters hidden', (
    tester,
  ) async {
    await pumpChats(tester);
    expect(visibleTitles(tester), [
      'Lonora',
      'Gold desk',
      'Morning news',
      'Trading desk',
      'Research',
      'FX watcher',
      'Reading club',
    ]);
    // The list starts at 111 dp (with a 48 dp status inset); the archived row comes first.
    final first = tester.getTopLeft(find.byType(ChatListRow).first);
    expect(first.dy, closeTo(111 + ArchivedRow.height, 0.5));
    expect(find.byType(ArchivedRow), findsOneWidget);
    // The filter bar rests above the first row, out of view.
    expect(find.text('الكل', skipOffstage: false), findsOneWidget);
    expect(find.text('الكل').hitTestable(), findsNothing);
    // Pulling the list down shows it.
    await tester.drag(find.byType(CustomScrollView), const Offset(0, 80));
    await tester.pumpAndSettle();
    expect(find.text('الكل').hitTestable(), findsOneWidget);
  });

  testWidgets('an unread filter shows only unread chats', (tester) async {
    await pumpChats(tester);
    await tester.drag(find.byType(CustomScrollView), const Offset(0, 80));
    await tester.pumpAndSettle();
    await tester.tap(find.text('غير مقروءة').first);
    await tester.pumpAndSettle();
    expect(visibleTitles(tester), [
      'Gold desk',
      'Morning news',
      'Trading desk',
    ]);
    expect(find.byType(ArchivedRow), findsNothing);
  });

  testWidgets('tapping a row opens its conversation', (tester) async {
    await pumpChats(tester);
    await tester.tap(find.text('Gold desk'));
    await tester.pumpAndSettle();
    expect(shownRoute(tester), '/chats/thread/t-gold');
  });

  testWidgets('an agent without a conversation gets one first', (tester) async {
    fakeApi.handlers['POST /agents/a-fx/conversation'] = (_, _) => {
      'id': 't-fx',
    };
    fakeApi.handlers['GET /agents'] = (_, _) => fixtureAgents;
    await pumpChats(tester);
    await tester.tap(find.text('FX watcher'));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('POST', '/agents/a-fx/conversation'), hasLength(1));
    expect(shownRoute(tester), '/chats/thread/t-fx');
  });

  testWidgets('the row menu pins a chat and says so', (tester) async {
    fakeApi.handlers['POST /threads/prefs'] = (body, _) => [
      {
        'thread_id': 't-gold',
        'last_read_seq': 2,
        'marked_unread': false,
        'muted': false,
        'archived': false,
        'favourite': false,
        'pinned_order': 1,
        'hidden_before_seq': 0,
      },
    ];
    final store = await pumpChats(tester, locale: 'en');
    await tester.longPress(find.text('Gold desk'));
    await tester.pumpAndSettle();
    expect(find.text('Agent profile'), findsOneWidget);
    expect(find.text('Mark as read'), findsOneWidget);
    expect(find.text('Mute notifications'), findsOneWidget);
    expect(find.text('Archive'), findsOneWidget);
    expect(find.text('Select'), findsOneWidget);
    await tester.tap(find.text('Pin'));
    await tester.pumpAndSettle();
    final call = fakeApi.callsTo('POST', '/threads/prefs').single;
    expect(call.body, {
      'thread_ids': ['t-gold'],
      'pinned': true,
    });
    expect(store.state.shell.entryFor('t-gold')!.pinnedOrder, 1);
    expect(find.text('Chat pinned to the top'), findsOneWidget);
    await settleToasts(tester);
  });

  testWidgets('a fourth pin is refused before any request', (tester) async {
    final inbox = fixtureInbox()
      ..[1]['pinned_order'] = 1
      ..[2]['pinned_order'] = 2;
    await pumpChats(
      tester,
      locale: 'en',
      state: fixtureState(inbox: inbox),
    );
    await tester.longPress(find.text('Research'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Pin'));
    await tester.pumpAndSettle();
    expect(fakeApi.calls, isEmpty);
    expect(find.text('You can pin 3 chats only'), findsOneWidget);
    await settleToasts(tester);
  });

  testWidgets('selection: toolbar, select all and delete with confirmation', (
    tester,
  ) async {
    fakeApi.handlers['POST /threads/t-gold/clear'] = (_, _) => {
      'thread_id': 't-gold',
      'hidden_before_seq': 5,
      'last_read_seq': 5,
    };
    fakeApi.handlers['POST /threads/prefs'] = (_, _) => <Object>[];
    fakeApi.handlers['GET /agents'] = (_, _) => fixtureAgents;
    await pumpChats(tester, locale: 'en');
    await tester.longPress(find.text('Gold desk'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Select'));
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Cancel the selection'), findsOneWidget);
    expect(find.bySemanticsLabel('1 selected'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Delete'));
    await tester.pumpAndSettle();
    expect(find.text('Delete the chats?'), findsOneWidget);
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('POST', '/threads/t-gold/clear'), hasLength(1));
    expect(fakeApi.callsTo('POST', '/threads/prefs').single.body, {
      'thread_ids': ['t-gold'],
      'pinned': false,
      'muted': false,
      'archived': false,
      'favourite': false,
    });
    expect(find.bySemanticsLabel('Cancel the selection'), findsNothing);
    await settleToasts(tester);
  });

  testWidgets('the + menu offers Lonora\'s create entries; new agent and new '
      'group open their stacked sheets', (tester) async {
    await pumpChats(tester, locale: 'en');
    await tester.tap(find.bySemanticsLabel('New chat'));
    await tester.pumpAndSettle();
    expect(find.text('New agent'), findsOneWidget);
    expect(find.text('New group'), findsOneWidget);
    expect(find.text('Manage agents'), findsOneWidget);
    await tester.tap(find.text('New agent'));
    await tester.pumpAndSettle();
    expect(find.byType(CreateAgentForm), findsOneWidget);
    // The sheet stacks over the list; no conversation opens.
    expect(shownRoute(tester), isNull);
    Navigator.of(tester.element(find.byType(CreateAgentForm))).pop();
    await tester.pumpAndSettle();
    expect(find.byType(CreateAgentForm), findsNothing);
    await tester.tap(find.bySemanticsLabel('New chat'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('New group'));
    await tester.pumpAndSettle();
    final form = tester.widget<NewGroupForm>(find.byType(NewGroupForm));
    expect(form.inSheet, isTrue);
    expect(shownRoute(tester), isNull);
    Navigator.of(tester.element(find.byType(NewGroupForm))).pop();
    await tester.pumpAndSettle();
  });

  testWidgets(
    'loading shows skeleton rows; a failed first load offers a retry',
    (tester) async {
      await pumpChats(
        tester,
        state: fixtureState(loaded: false, agents: [], groups: [], inbox: []),
      );
      expect(find.byType(SkeletonRows), findsOneWidget);
      // F4: the placeholder is announced in the owner's language.
      expect(find.bySemanticsLabel('جارٍ التحميل'), findsOneWidget);
      await pumpChats(
        tester,
        state: fixtureState(
          loaded: false,
          agents: [],
          groups: [],
          inbox: [],
          lastError: 'network',
        ),
      );
      expect(find.byType(ErrorState), findsOneWidget);
    },
  );

  for (final brightness in Brightness.values) {
    for (final locale in ['ar', 'en']) {
      testWidgets('golden ${brightness.name} $locale', (tester) async {
        await withRealShadows(() async {
          await pumpChats(tester, brightness: brightness, locale: locale);
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile(
              'goldens/chats_list_${brightness.name}_$locale.png',
            ),
          );
        });
      });
    }
  }

  testWidgets('golden: empty unread filter', (tester) async {
    await withRealShadows(() async {
      await pumpChats(
        tester,
        state: fixtureState(inbox: [fixtureInbox().first], working: false),
      );
      await tester.drag(find.byType(CustomScrollView), const Offset(0, 80));
      await tester.pumpAndSettle();
      await tester.tap(find.text('غير مقروءة').first);
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/chats_empty_unread_light_ar.png'),
      );
    });
  });

  testWidgets('golden: offline with the selection toolbar (light en)', (
    tester,
  ) async {
    await withRealShadows(() async {
      await pumpChats(tester, locale: 'en', state: fixtureState(offline: true));
      await tester.longPress(find.text('Gold desk'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Select'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Morning news'));
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/chats_offline_selection_light_en.png'),
      );
    });
  });

  testWidgets('golden: row menu (light ar)', (tester) async {
    await withRealShadows(() async {
      await pumpChats(tester);
      await tester.longPress(find.text('Gold desk'));
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/chats_row_menu_light_ar.png'),
      );
    });
  });

  testWidgets('golden: create menu (dark en)', (tester) async {
    await withRealShadows(() async {
      await pumpChats(tester, locale: 'en', brightness: Brightness.dark);
      await tester.tap(find.bySemanticsLabel('New chat'));
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/chats_create_menu_dark_en.png'),
      );
    });
  });
}
