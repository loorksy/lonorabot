// The row menu's and the selection's commands against the fake API: archive with «تراجع»,
// clearing the messages after a confirmation, mute, mark unread, «حذف» keeping the clear
// cursors, a group without a conversation (nothing created), a failed undo, and the custom
// lists (create, the chats page, delete with confirmation and «تراجع»).
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/l10n/l10n.dart' show dotSeparator;
import 'package:lonora/state/app_state.dart';

import 'harness.dart';

Future<Store<AppState>> pumpChats(
  WidgetTester tester, {
  AppState? state,
}) async {
  setGoldenViewport(tester);
  final store = Store<AppState>(
    initialState: state ?? fixtureState(working: false),
  );
  await tester.pumpWidget(
    featureApp(store: store, router: testRouter(Routes.chats), locale: 'en'),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  return store;
}

/// `POST /threads/prefs` answering each thread with the change applied.
void servePrefs() {
  fakeApi.handlers['POST /threads/prefs'] = (body, _) {
    final change = {...asJson(body)}..remove('thread_ids');
    return [
      for (final id in asStringList(asJson(body)['thread_ids']))
        {'thread_id': id, ...change},
    ];
  };
}

Future<void> openMenu(WidgetTester tester, String row) async {
  await tester.longPress(find.text(row));
  await tester.pumpAndSettle();
}

/// Pulls the filters into view and scrolls them to their end (the lists and «+»).
Future<void> revealFilters(WidgetTester tester) async {
  await tester.drag(find.byType(CustomScrollView), const Offset(0, 80));
  await tester.pumpAndSettle();
  await tester.drag(find.text('All'), const Offset(-600, 0));
  await tester.pumpAndSettle();
}

List<Object?> prefsBodies() =>
    fakeApi.callsTo('POST', '/threads/prefs').map((c) => c.body).toList();

void main() {
  setUpAll(setUpFeatureHarness);
  setUp(resetFakeApi);

  testWidgets('archive from the menu, then «تراجع» brings it back', (
    tester,
  ) async {
    servePrefs();
    final store = await pumpChats(tester);
    await openMenu(tester, 'Gold desk');
    await tester.tap(find.text('Archive'));
    await tester.pumpAndSettle();
    expect(store.state.shell.entryFor('t-gold')!.archived, isTrue);
    expect(find.text('Undo'), findsOneWidget);
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(prefsBodies(), [
      {
        'thread_ids': ['t-gold'],
        'archived': true,
      },
      {
        'thread_ids': ['t-gold'],
        'archived': false,
      },
    ]);
    expect(store.state.shell.entryFor('t-gold')!.archived, isFalse);
    await settleToasts(tester);
  });

  testWidgets('a failed «تراجع» says so', (tester) async {
    var calls = 0;
    fakeApi.handlers['POST /threads/prefs'] = (body, _) => ++calls == 1
        ? [
            {'thread_id': 't-gold', 'archived': true},
          ]
        : ApiError(status: 409, code: 'version_conflict');
    final store = await pumpChats(tester);
    await openMenu(tester, 'Gold desk');
    await tester.tap(find.text('Archive'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(calls, 2);
    expect(store.state.shell.entryFor('t-gold')!.archived, isTrue);
    expect(
      find.text('This was changed on another device. Refresh and try again.'),
      findsOneWidget,
    );
    await settleToasts(tester);
  });

  testWidgets('mute and mark unread from the menu', (tester) async {
    servePrefs();
    final store = await pumpChats(tester);
    await openMenu(tester, 'Research');
    await tester.tap(find.text('Mute notifications'));
    await tester.pumpAndSettle();
    expect(find.text('Notifications muted'), findsOneWidget);
    await settleToasts(tester);
    await openMenu(tester, 'Research');
    await tester.tap(find.text('Mark as unread'));
    await tester.pumpAndSettle();
    expect(prefsBodies(), [
      {
        'thread_ids': ['t-research'],
        'muted': true,
      },
      {
        'thread_ids': ['t-research'],
        'marked_unread': true,
      },
    ]);
    final entry = store.state.shell.entryFor('t-research')!;
    expect(entry.muted, isTrue);
    expect(entry.markedUnread, isTrue);
  });

  testWidgets('«مسح الرسائل» asks first, then hides the history only', (
    tester,
  ) async {
    fakeApi.handlers['POST /threads/t-news/clear'] = (_, _) => {
      'thread_id': 't-news',
      'hidden_before_seq': 5,
      'last_read_seq': 5,
      'marked_unread': false,
    };
    final store = await pumpChats(tester);
    await openMenu(tester, 'Morning news');
    await tester.tap(find.text('Select'));
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('More'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Clear the messages'));
    await tester.pumpAndSettle();
    expect(find.text('Clear the messages?'), findsOneWidget);
    // Cancel first: nothing is sent.
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('POST', '/threads/t-news/clear'), isEmpty);
    await tester.tap(find.bySemanticsLabel('More'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Clear the messages'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Clear').last);
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('POST', '/threads/t-news/clear'), hasLength(1));
    expect(fakeApi.callsTo('POST', '/threads/prefs'), isEmpty);
    final entry = store.state.shell.entryFor('t-news')!;
    expect(entry.hiddenBeforeSeq, 5);
    expect(entry.markedUnread, isFalse);
    expect(find.text('Messages cleared'), findsOneWidget);
    await settleToasts(tester);
  });

  testWidgets('«حذف» keeps the clear cursors and drops the marks', (
    tester,
  ) async {
    fakeApi.handlers['POST /threads/t-gold/clear'] = (_, _) => {
      'thread_id': 't-gold',
      'hidden_before_seq': 5,
      'last_read_seq': 5,
    };
    // An answer without the cursors: the clear's must survive the second merge.
    fakeApi.handlers['POST /threads/prefs'] = (_, _) => [
      {'thread_id': 't-gold', 'pinned_order': null, 'favourite': false},
    ];
    final store = await pumpChats(tester);
    await openMenu(tester, 'Gold desk');
    await tester.tap(find.text('Select'));
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('Delete'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    final entry = store.state.shell.entryFor('t-gold')!;
    expect(entry.hiddenBeforeSeq, 5);
    expect(entry.lastReadSeq, 5);
    expect(entry.unreadCount, 0);
    await settleToasts(tester);
  });

  testWidgets('a group without a conversation is skipped, nothing created', (
    tester,
  ) async {
    servePrefs();
    final state = fixtureState(
      working: false,
      groups: [
        ...fixtureGroups,
        groupJson('g-bare', 'Bare group', ['a-gold', 'a-news']),
      ],
    );
    await pumpChats(tester, state: state);
    await tester.scrollUntilVisible(find.text('Bare group'), 200);
    await openMenu(tester, 'Bare group');
    await tester.tap(find.text('Mute notifications'));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('POST', '/threads'), isEmpty);
    expect(fakeApi.callsTo('GET', '/groups/g-bare'), isEmpty);
    expect(fakeApi.callsTo('POST', '/threads/prefs'), isEmpty);
    await settleToasts(tester);
  });

  testWidgets('lists: create, the chats page, delete with «تراجع»', (
    tester,
  ) async {
    final lists = <String, Json>{};
    var next = 0;
    fakeApi.handlers['POST /chat-lists'] = (body, _) {
      final id = 'l${++next}';
      return lists[id] = {
        'id': id,
        'name': asJson(body)['name'],
        'position': lists.length,
        'thread_ids': <String>[],
      };
    };
    for (final id in ['l1', 'l2']) {
      fakeApi.handlers['PUT /chat-lists/$id/members'] = (body, _) =>
          lists[id] = {...lists[id]!, 'thread_ids': asJson(body)['thread_ids']};
      fakeApi.handlers['PUT /chat-lists/$id'] = (body, _) =>
          lists[id] = {...lists[id]!, ...asJson(body)};
      fakeApi.handlers['DELETE /chat-lists/$id'] = (_, _) {
        lists.remove(id);
        return {'deleted': true};
      };
    }
    final store = await pumpChats(tester);
    // The filters rest above the list: pull them into view, then «+».
    await revealFilters(tester);
    await tester.tap(find.bySemanticsLabel('New list'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, 'Metals');
    await tester.pump();
    await tester.tap(find.text('Gold desk').last);
    await tester.pump();
    await tester.tap(find.text('Create the list · 1'));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('PUT', '/chat-lists/l1/members').single.body, {
      'thread_ids': ['t-gold'],
    });
    expect(store.state.shell.chatLists.single.name, 'Metals');
    await settleToasts(tester);

    // The list is the filter now; its menu's «The chats» shows the chats only.
    await tester.longPress(find.text('Metals'));
    await tester.pumpAndSettle();
    // The menu's title keeps its dot with the name (Q11).
    expect(find.text('Metals${dotSeparator}one chat'), findsOneWidget);
    await tester.tap(find.text('The chats'));
    await tester.pumpAndSettle();
    expect(find.text('Add to «Metals»'), findsOneWidget);
    expect(find.text('List name'), findsNothing);
    await tester.tap(find.text('Research').last);
    await tester.pump();
    await tester.tap(find.text('Save the list · 2'));
    await tester.pumpAndSettle();
    expect(
      asJson(
        fakeApi.callsTo('PUT', '/chat-lists/l1/members').last.body,
      )['thread_ids'],
      unorderedEquals(['t-gold', 't-research']),
    );
    await settleToasts(tester);

    // Delete asks first; «تراجع» recreates it with its chats at its place.
    await tester.longPress(find.text('Metals'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete the list'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    expect(store.state.shell.chatLists, isEmpty);
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('POST', '/chat-lists'), hasLength(2));
    expect(
      asJson(
        fakeApi.callsTo('PUT', '/chat-lists/l2/members').single.body,
      )['thread_ids'],
      unorderedEquals(['t-gold', 't-research']),
    );
    expect(fakeApi.callsTo('PUT', '/chat-lists/l2').single.body, {
      'position': 0,
    });
    expect(store.state.shell.chatLists.single.id, 'l2');
    // It was the filter: the restored list is shown again.
    final chips = tester.widgetList<LnTappable>(
      find.ancestor(of: find.text('Metals'), matching: find.byType(LnTappable)),
    );
    expect(chips.first.selected, isTrue);
    await settleToasts(tester);
  });

  testWidgets('a restored list whose chats fail is removed again', (
    tester,
  ) async {
    fakeApi.handlers['DELETE /chat-lists/l1'] = (_, _) => {'deleted': true};
    fakeApi.handlers['POST /chat-lists'] = (body, _) => {
      'id': 'l2',
      'name': asJson(body)['name'],
      'position': 1,
      'thread_ids': <String>[],
    };
    fakeApi.handlers['PUT /chat-lists/l2/members'] = (_, _) =>
        ApiError(status: 404, code: 'thread_not_found');
    fakeApi.handlers['DELETE /chat-lists/l2'] = (_, _) => {'deleted': true};
    final store = await pumpChats(
      tester,
      state: fixtureState(
        working: false,
        chatLists: [
          {
            'id': 'l1',
            'name': 'Metals',
            'position': 0,
            'thread_ids': ['t-gold'],
          },
        ],
      ),
    );
    await revealFilters(tester);
    await tester.longPress(find.text('Metals'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete the list'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(fakeApi.callsTo('DELETE', '/chat-lists/l2'), hasLength(1));
    expect(store.state.shell.chatLists, isEmpty);
    expect(find.byType(ErrorState), findsNothing);
    await settleToasts(tester);
  });
}
