// New group (the /groups/new page, the same form as the create-group sheet): the member field and
// picker (search, limit), the drafted name from the selection, the coordinator,
// `POST /groups/create` and the group's conversation; group settings save; goldens.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/state/app_state.dart';

import 'package:lonora/features/groups/create_group_sheet.dart';
import 'package:lonora/features/groups/form_sheet.dart';
import 'package:lonora/features/groups/member_picker.dart';

import '../../design/harness.dart' show withRealShadows;
import '../chats/harness.dart';

/// The header's «إنشاء» pill.
HeaderPillButton createPill(WidgetTester tester) =>
    tester.widget<HeaderPillButton>(find.byType(HeaderPillButton));

/// The text field of the [index]th stadium field (0 the name, 1 the purpose), scrolled into
/// view.
Future<Finder> detailField(WidgetTester tester, int index) async {
  final field = find.byType(StadiumField);
  await tester.scrollUntilVisible(
    field.at(index),
    200,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
  return find.descendant(of: field.at(index), matching: find.byType(TextField));
}

/// The member field's search.
Finder memberQuery() => find.descendant(
  of: find.byType(MemberField),
  matching: find.byType(TextField),
);

Future<Store<AppState>> pumpRoute(
  WidgetTester tester,
  String route, {
  Brightness brightness = Brightness.light,
  String locale = 'ar',
  AppState? state,
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
  await tester.pumpAndSettle();
  return store;
}

void main() {
  setUpAll(setUpFeatureHarness);
  setUp(resetFakeApi);

  testWidgets('creates a group from picked agents and opens its conversation', (
    tester,
  ) async {
    fakeApi.handlers['POST /groups/create'] = (body, _) => {
      'id': 'g-new',
      'version': 1,
      'payload': asJson(body),
      'state': {'thread_id': 't-new'},
      'thread_id': 't-new',
    };
    final store = await pumpRoute(tester, Routes.newGroup(), locale: 'en');
    expect(createPill(tester).onPressed, isNull);
    await tester.enterText(await detailField(tester, 0), '  Metals  ');
    await tester.pump();
    expect(
      createPill(tester).onPressed,
      isNull,
      reason: 'a group needs a member',
    );
    await tester.scrollUntilVisible(
      find.text('Research'),
      -200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Research'));
    await tester.pump();
    await tester.tap(find.text('Gold desk'));
    await tester.pump();
    expect(find.text('2/12'), findsOneWidget);
    // The picked agents are chips in the member field.
    expect(
      find.descendant(
        of: find.byType(MemberField),
        matching: find.text('Research'),
      ),
      findsOneWidget,
    );
    await tester.scrollUntilVisible(
      find.text('Coordinator'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Coordinator'), findsWidgets);
    // A typed name is the owner's: picking more does not redraft it.
    expect(find.text('  Metals  '), findsOneWidget);
    await tester.tap(find.byType(HeaderPillButton));
    await tester.pumpAndSettle();
    final call = fakeApi.callsTo('POST', '/groups/create').single;
    expect(call.body, {
      'name': 'Metals',
      'member_ids': ['a-research', 'a-gold'],
      'participation': 'mentions_or_lead',
      'purpose': '',
      'lead_agent_id': 'a-research',
    });
    expect(store.state.shell.groups['g-new']?.name, 'Metals');
    expect(shownRoute(tester), '/chats/thread/t-new');
  });

  testWidgets('«group from selected» drafts the name and the members', (
    tester,
  ) async {
    await pumpRoute(
      tester,
      Routes.newGroup(members: ['a-gold', 'a-news']),
      locale: 'en',
    );
    expect(find.text('2/12'), findsOneWidget);
    expect(createPill(tester).onPressed, isNotNull);
    // cc:C1: the English comma in English, the Arabic one in Arabic.
    await detailField(tester, 0);
    expect(find.text('Gold desk, Morning news'), findsOneWidget);
  });

  testWidgets('an Arabic draft name joins with the Arabic comma', (
    tester,
  ) async {
    await pumpRoute(tester, Routes.newGroup(members: ['a-gold', 'a-news']));
    await detailField(tester, 0);
    expect(find.text('Gold desk، Morning news'), findsOneWidget);
  });

  testWidgets('a picked member wears the check circle and becomes a chip', (
    tester,
  ) async {
    await pumpRoute(tester, Routes.newGroup(), locale: 'en');
    await tester.tap(find.text('Research'));
    await tester.pump();
    final marks = tester.widgetList<MemberCheck>(find.byType(MemberCheck));
    expect(marks.length, greaterThan(1));
    expect(marks.where((m) => m.checked), hasLength(1));
    await tester.pumpAndSettle();
    // A tap on the chip removes it again.
    await tester.tap(find.bySemanticsLabel('Remove Research'));
    await tester.pumpAndSettle();
    expect(
      tester
          .widgetList<MemberCheck>(find.byType(MemberCheck))
          .where((m) => m.checked),
      isEmpty,
    );
    expect(find.byType(MemberChip), findsNothing);
  });

  testWidgets('the member search filters the agents', (tester) async {
    await pumpRoute(tester, Routes.newGroup(), locale: 'en');
    await tester.enterText(memberQuery(), 'news');
    await tester.pump();
    expect(find.text('Morning news'), findsOneWidget);
    expect(find.text('Research'), findsNothing);
  });

  testWidgets('a refused creation shows the server reason and stays', (
    tester,
  ) async {
    fakeApi.handlers['POST /groups/create'] = (_, _) =>
        ApiError(status: 409, code: 'version_conflict');
    await pumpRoute(tester, Routes.newGroup(members: ['a-gold']), locale: 'en');
    await tester.tap(find.byType(HeaderPillButton));
    await tester.pumpAndSettle();
    expect(shownRoute(tester), isNull);
    expect(
      find.text('This was changed on another device. Refresh and try again.'),
      findsOneWidget,
    );
  });

  testWidgets(
    'group settings: rename, remove a member, save with the version',
    (tester) async {
      final group = fixtureGroups.first;
      fakeApi.handlers['GET /groups/g-desk'] = (_, _) => group;
      fakeApi.handlers['PUT /groups/g-desk'] = (body, _) => {
        ...group,
        'version': 3,
        'payload': asJson(asJson(body)['payload']),
      };
      final store = await pumpRoute(
        tester,
        Routes.groupSettings('g-desk'),
        locale: 'en',
      );
      expect(find.text('Trading desk'), findsOneWidget);
      expect(find.text('FX watcher'), findsOneWidget);
      await tester.enterText(find.byType(TextField).first, 'Desk');
      await tester.tap(
        find.bySemanticsLabel('Remove from the group: FX watcher'),
      );
      await tester.pump();
      await tester.tap(find.bySemanticsLabel('Save'));
      await tester.pumpAndSettle();
      final call = fakeApi.callsTo('PUT', '/groups/g-desk').single;
      expect(asJson(call.body)['version'], 2);
      expect(asJson(asJson(call.body)['payload'])['name'], 'Desk');
      expect(asJson(asJson(call.body)['payload'])['member_ids'], [
        'a-gold',
        'a-news',
      ]);
      expect(store.state.shell.groups['g-desk']?.version, 3);
      await settleToasts(tester);
    },
  );

  testWidgets(
    'group settings: a version conflict adopts the newer group, keeping the edits',
    (tester) async {
      final group = fixtureGroups.first;
      final newer = {
        ...group,
        'version': 5,
        'payload': {...asJson(group['payload']), 'purpose': 'Macro desk'},
      };
      var reads = 0;
      fakeApi.handlers['GET /groups/g-desk'] = (_, _) =>
          ++reads == 1 ? group : newer;
      var puts = 0;
      fakeApi.handlers['PUT /groups/g-desk'] = (body, _) => ++puts == 1
          ? ApiError(status: 409, code: 'version_conflict')
          : {
              ...newer,
              'version': 6,
              'payload': asJson(asJson(body)['payload']),
            };
      await pumpRoute(tester, Routes.groupSettings('g-desk'), locale: 'en');
      await tester.enterText(find.byType(TextField).first, 'Desk');
      await tester.pump();
      await tester.tap(find.bySemanticsLabel('Save'));
      await tester.pumpAndSettle();
      expect(
        find.text('This was changed on another device. Refresh and try again.'),
        findsOneWidget,
      );
      expect(reads, 2);
      // The edited name stays; the untouched purpose takes the newer value.
      expect(find.text('Desk'), findsOneWidget);
      expect(find.text('Macro desk'), findsOneWidget);
      await settleToasts(tester);
      await tester.tap(find.bySemanticsLabel('Save'));
      await tester.pumpAndSettle();
      final second = asJson(fakeApi.callsTo('PUT', '/groups/g-desk').last.body);
      expect(second['version'], 5);
      expect(asJson(second['payload'])['name'], 'Desk');
      expect(asJson(second['payload'])['purpose'], 'Macro desk');
      await settleToasts(tester);
    },
  );

  testWidgets('leaving a new group with edits asks first', (tester) async {
    setGoldenViewport(tester);
    final router = testRouter(Routes.chats);
    await tester.pumpWidget(
      featureApp(
        store: Store<AppState>(initialState: fixtureState(working: false)),
        router: router,
        locale: 'en',
      ),
    );
    await tester.pumpAndSettle();
    router.push(Routes.newGroup());
    await tester.pumpAndSettle();
    // Nothing typed yet: the ✕ leaves at once.
    await tester.tap(find.bySemanticsLabel('Close'));
    await tester.pumpAndSettle();
    expect(find.text('New group'), findsNothing);
    router.push(Routes.newGroup());
    await tester.pumpAndSettle();
    await tester.enterText(await detailField(tester, 0), 'Metals');
    await tester.pump();
    await tester.tap(find.bySemanticsLabel('Close'));
    await tester.pumpAndSettle();
    expect(find.text('Leave the edits?'), findsOneWidget);
    await tester.tap(find.text('Keep editing'));
    await tester.pumpAndSettle();
    expect(find.text('Metals'), findsOneWidget);
    // The system back asks too.
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.text('Leave the edits?'), findsOneWidget);
    await tester.tap(find.text('Discard'));
    await tester.pumpAndSettle();
    expect(find.text('New group'), findsNothing);
    expect(find.text('Gold desk'), findsWidgets);
  });

  testWidgets('a failed first load offers a retry instead of the members', (
    tester,
  ) async {
    await pumpRoute(
      tester,
      Routes.newGroup(),
      locale: 'en',
      state: fixtureState(
        loaded: false,
        agents: [],
        groups: [],
        inbox: [],
        lastError: 'network',
      ),
    );
    expect(tester.takeException(), isNull);
    expect(find.byType(ErrorState), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('opening the group chat with unsaved edits asks first', (
    tester,
  ) async {
    fakeApi.handlers['GET /groups/g-desk'] = (_, _) => fixtureGroups.first;
    await pumpRoute(tester, Routes.groupSettings('g-desk'), locale: 'en');
    await tester.enterText(find.byType(TextField).first, 'Desk');
    await tester.pump();
    final open = find.text('Open the group chat');
    await tester.scrollUntilVisible(
      open,
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(open);
    await tester.pumpAndSettle();
    expect(find.text('Leave the edits?'), findsOneWidget);
    await tester.tap(find.text('Keep editing'));
    await tester.pumpAndSettle();
    expect(shownRoute(tester), isNull);
    await tester.tap(open);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Discard'));
    await tester.pumpAndSettle();
    expect(shownRoute(tester), '/chats/thread/t-desk');
  });

  testWidgets('an existing group has no member cap', (tester) async {
    final extra = [for (var i = 0; i < 12; i++) agentJson('a-x$i', 'Extra $i')];
    final members = [for (var i = 0; i < 12; i++) 'a-x$i'];
    fakeApi.handlers['GET /groups/g-big'] = (_, _) =>
        groupJson('g-big', 'Big desk', members, thread: 't-big');
    await pumpRoute(
      tester,
      Routes.groupSettings('g-big'),
      locale: 'en',
      state: fixtureState(
        working: false,
        agents: [...fixtureAgents, ...extra],
        groups: [
          ...fixtureGroups,
          groupJson('g-big', 'Big desk', members, thread: 't-big'),
        ],
      ),
    );
    await tester.scrollUntilVisible(
      find.text('Add an agent'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Add an agent'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Gold desk').last);
    await tester.pump();
    expect(find.textContaining('You can add up to'), findsNothing);
    await tester.tap(find.text('Add'));
    await tester.pumpAndSettle();
    expect(find.text('Gold desk'), findsOneWidget);
  });

  group('create-group sheet', () {
    Future<GoRouter> openSheet(
      WidgetTester tester, {
      String locale = 'en',
    }) async {
      setGoldenViewport(tester);
      final router = testRouter(Routes.agents);
      await tester.pumpWidget(
        featureApp(
          store: Store<AppState>(initialState: fixtureState(working: false)),
          router: router,
          locale: locale,
        ),
      );
      await tester.pumpAndSettle();
      final create = find.text(
        locale == 'ar' ? 'إنشاء مجموعة' : 'Create a group',
      );
      await tester.scrollUntilVisible(
        create,
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(create);
      await tester.pumpAndSettle();
      return router;
    }

    FormSheetRoute<dynamic> sheetRoute(WidgetTester tester) =>
        ModalRoute.of(tester.element(find.byType(NewGroupForm)))!
            as FormSheetRoute<dynamic>;

    /// Drags the sheet down from its header by most of the screen, as a closing swipe does.
    /// While a spinner turns nothing settles, so [settle] false pumps a second instead.
    Future<void> dragDown(WidgetTester tester, {bool settle = true}) async {
      await tester.timedDrag(
        find.byType(LnSheetHeader),
        const Offset(0, 600),
        const Duration(milliseconds: 300),
      );
      if (settle) {
        await tester.pumpAndSettle();
      } else {
        await tester.pump(const Duration(seconds: 1));
      }
    }

    testWidgets('«Create a group» opens the form in a stacked sheet with a '
        'handle and the «Create» pill in its header', (tester) async {
      await openSheet(tester);
      expect(find.byType(NewGroupForm), findsOneWidget);
      expect(find.byType(LnSheetHandle), findsOneWidget);
      expect(find.text('New group'), findsOneWidget);
      expect(createPill(tester).onPressed, isNull);
      // The pill sits in the header row, at the end side (right in English).
      final pill = tester.getRect(find.byType(HeaderPillButton));
      final close = tester.getRect(find.bySemanticsLabel('Close'));
      expect(pill.center.dy, moreOrLessEquals(close.center.dy, epsilon: 0.5));
      expect(pill.left, greaterThan(close.right));
      expect(sheetRoute(tester), isA<FormSheetRoute<dynamic>>());
    });

    testWidgets('a downward drag closes the clean sheet', (tester) async {
      await openSheet(tester);
      await dragDown(tester);
      expect(find.byType(NewGroupForm), findsNothing);
    });

    testWidgets('with a pick the drag no longer closes it; ✕ asks first', (
      tester,
    ) async {
      await openSheet(tester);
      await tester.tap(find.text('Research').last);
      await tester.pumpAndSettle();
      expect(createPill(tester).onPressed, isNotNull);
      await dragDown(tester);
      expect(find.byType(NewGroupForm), findsOneWidget);
      expect(find.text('Leave the edits?'), findsNothing);
      expect(find.byType(MemberChip), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('Close'));
      await tester.pumpAndSettle();
      expect(find.text('Leave the edits?'), findsOneWidget);
      await tester.tap(find.text('Discard'));
      await tester.pumpAndSettle();
      expect(find.byType(NewGroupForm), findsNothing);
      expect(find.text('Agents'), findsWidgets);
    });

    testWidgets('while a preselected group is being created the drag does '
        'not close the sheet', (tester) async {
      final answer = Completer<Object?>();
      fakeApi.handlers['POST /groups/create'] = (_, _) => answer.future;
      await openSheet(tester);
      await tester.tap(find.bySemanticsLabel('Close'));
      await tester.pumpAndSettle();
      // «مجموعة من المحددين»: the picks are what the sheet opened with, so it is clean.
      unawaited(
        showCreateGroupSheet(
          tester.element(find.text('Create a group')),
          memberIds: const ['a-news'],
        ),
      );
      await tester.pumpAndSettle();
      await dragDown(tester);
      expect(find.byType(NewGroupForm), findsNothing, reason: 'clean');
      unawaited(
        showCreateGroupSheet(
          tester.element(find.text('Create a group')),
          memberIds: const ['a-news'],
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byType(HeaderPillButton));
      await tester.pump();
      await dragDown(tester, settle: false);
      expect(find.byType(NewGroupForm), findsOneWidget);
      answer.complete({
        'id': 'g-new',
        'version': 1,
        'state': {'thread_id': 't-new'},
        'thread_id': 't-new',
      });
      await tester.pumpAndSettle();
      expect(find.byType(NewGroupForm), findsNothing);
      expect(shownRoute(tester), '/chats/thread/t-new');
    });

    testWidgets('«Create» closes the sheet and opens the group', (
      tester,
    ) async {
      fakeApi.handlers['POST /groups/create'] = (body, _) => {
        'id': 'g-new',
        'version': 1,
        'payload': asJson(body),
        'state': {'thread_id': 't-new'},
        'thread_id': 't-new',
      };
      await openSheet(tester);
      await tester.tap(find.text('Morning news').last);
      await tester.pump();
      await tester.tap(find.byType(HeaderPillButton));
      await tester.pumpAndSettle();
      expect(
        asJson(fakeApi.callsTo('POST', '/groups/create').single.body)['name'],
        'Morning news',
      );
      expect(find.byType(NewGroupForm), findsNothing);
      expect(shownRoute(tester), '/chats/thread/t-new');
    });

    testWidgets('RTL: 70 dp rows with the avatar at the start and the 24 dp '
        'check at the end; 48 dp targets everywhere', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpRoute(tester, Routes.newGroup(members: ['a-gold']));
      final row = find.byKey(const ValueKey('member-a-news'));
      final rect = tester.getRect(row);
      expect(rect.height, MemberPicker.rowHeight);
      final check = tester.getRect(
        find.descendant(of: row, matching: find.byType(MemberCheck)),
      );
      expect(check.size, const Size.square(MemberCheck.size));
      // Arabic reads right to left: the check circle is at the left (end) edge, 16 dp in.
      expect(check.left - rect.left, 16);
      final name = tester.getRect(
        find.descendant(of: row, matching: find.text('Morning news')),
      );
      expect(rect.right - name.right, 16 + 40 + MemberPicker.textGap);
      // The chip of the picked agent is a 48 dp target named after what it does.
      expect(
        tester.getSize(find.bySemanticsLabel('إزالة Gold desk')).height,
        LnSize.minTouch,
      );
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      handle.dispose();
    });
  });

  for (final (brightness, locale) in [
    (Brightness.light, 'ar'),
    (Brightness.dark, 'en'),
  ]) {
    testWidgets('golden new group ${brightness.name} $locale', (tester) async {
      await withRealShadows(() async {
        await pumpRoute(
          tester,
          Routes.newGroup(members: ['a-gold', 'a-news']),
          brightness: brightness,
          locale: locale,
        );
        FocusManager.instance.primaryFocus?.unfocus();
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/new_group_${brightness.name}_$locale.png'),
        );
      });
    });
  }

  testWidgets('golden group settings light ar', (tester) async {
    fakeApi.handlers['GET /groups/g-desk'] = (_, _) => fixtureGroups.first;
    await withRealShadows(() async {
      await pumpRoute(tester, Routes.groupSettings('g-desk'));
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/group_settings_light_ar.png'),
      );
    });
  });
}
