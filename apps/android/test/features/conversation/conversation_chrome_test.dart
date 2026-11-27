// The conversation's chrome and gestures: the header (back or the drawer's ☰, the call circle,
// the name capsule that opens the conversation's actions), the anchored message menu (lifted
// message, reactions, time header, Lonora's entries in order), the «+» menu over the composer
// (sources and web search), swipe to reply, bubble runs, the jump button's place, the composer's
// distance to the keyboard and the time separators (time only today), in English and Arabic.
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/chats/chat_drawer.dart';
import 'package:lonora/features/conversation/conversation_header.dart';
import 'package:lonora/features/conversation/conversation_composer.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/features/conversation/conversation_screen.dart';
import 'package:lonora/features/conversation/message_widgets.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/fonts.dart';
import '../../design/harness.dart';
import 'conversation_harness.dart';

late L10n l10n;
late FakeApi fake;

/// Messages of today (the fixed clock of the time separators is the real one: today's date).
DateTime today(int hour, int minute) {
  final now = DateTime.now();
  return DateTime(now.year, now.month, now.day, hour, minute);
}

AppState _state({
  bool paused = false,
  bool webSearch = false,
  List<Message>? messages,
}) => conversationState(
  agent: fixtureAgent(paused: paused),
  webSearch: webSearch,
  messages:
      messages ??
      [
        message('m1', 1, 'user', 'Morning', today(9, 0)),
        message('m2', 2, 'assistant', 'Good morning.', today(9, 1)),
        message('m3', 3, 'assistant', 'Gold opened flat.', today(9, 1)),
        message('m4', 4, 'assistant', 'I will watch it.', today(9, 2)),
      ],
);

Future<Store<AppState>> _pump(
  WidgetTester tester, {
  AppState? state,
  String locale = 'en',
  LnDrawerController? drawer,
  bool home = false,
  EdgeInsets keyboard = EdgeInsets.zero,
  Brightness brightness = Brightness.light,
}) async {
  setGoldenViewport(tester);
  final store = Store<AppState>(initialState: state ?? _state());
  Widget screen = ConversationScreen(threadId: threadId, home: home);
  if (drawer != null) {
    screen = ChatDrawerScope(controller: drawer, child: screen);
  }
  await tester.pumpWidget(
    conversationApp(
      store: store,
      l10n: l10n,
      locale: locale,
      brightness: brightness,
      child: Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(context).copyWith(viewInsets: keyboard),
          child: screen,
        ),
      ),
    ),
  );
  await tester.pump(const Duration(milliseconds: 100));
  await tester.pump(const Duration(milliseconds: 400));
  return store;
}

/// A group conversation ("Desk": Atlas and Nova).
AppState _groupState() {
  final base = _state();
  final nova = Agent.fromJson({
    'id': 'agent-2',
    'name': 'Nova',
    'avatar': 'orb',
    'color': 'red',
  });
  final group = Group.fromJson({
    'id': 'group-1',
    'version': 1,
    'payload': {
      'name': 'Desk',
      'member_ids': [agentId, 'agent-2'],
    },
  });
  final t = base.thread(threadId);
  return base
      .copyWith(
        shell: base.shell.copyWith(
          agents: {...base.shell.agents, 'agent-2': nova},
          groups: {'group-1': group},
        ),
      )
      .withThread(
        t.copyWith(
          thread: Thread.fromJson({
            'id': threadId,
            'group_id': 'group-1',
            'options': {'web_search': false},
          }),
        ),
      );
}

/// The transcript scrollbar's thumb (the only 3 dp wide rounded rect it paints); [onThumb] gets
/// its rect.
PaintPattern _thumb(void Function(Rect rect) onThumb) =>
    paints..something((method, args) {
      if (method != #drawRRect) return false;
      final rrect = args[0] as RRect;
      if ((rrect.width - 3).abs() > 0.01) return false;
      onThumb(rrect.outerRect);
      return true;
    });

Finder _circle(String label) => find.byWidgetPredicate(
  (w) => w is CircleIconButton && w.semanticLabel == label,
);

double _width(WidgetTester tester) =>
    tester.view.physicalSize.width / tester.view.devicePixelRatio;

void main() {
  setUpAll(() async {
    await loadAppFonts();
    l10n = await L10n.load();
    if (!sl.isRegistered<LocalStore>()) {
      final dir = await Directory.systemTemp.createTemp('lonora_chrome_test');
      sl.registerSingleton<LocalStore>(LocalStore.at(dir));
    }
  });
  setUp(() => fake = registerFakeApi());
  tearDown(() async {
    if (sl.isRegistered<ApiClient>()) await sl.unregister<ApiClient>();
    ConversationComposerState.clearDrafts();
  });

  group('header', () {
    for (final locale in ['en', 'ar']) {
      testWidgets('back at the start, call at the end ($locale)', (
        tester,
      ) async {
        await _pump(tester, locale: locale);
        final back = tester.getRect(_circle(l10n.t('back')));
        final call = tester.getRect(_circle(l10n.t('callAgent')));
        final width = _width(tester);
        // 48 dp targets, the circles 16 dp from the edges.
        expect(back.size, const Size(48, 48));
        expect(call.size, const Size(48, 48));
        if (locale == 'ar') {
          expect(width - back.right, LnSpace.pageGutter - 2);
          expect(call.left, LnSpace.pageGutter - 2);
        } else {
          expect(back.left, LnSpace.pageGutter - 2);
          expect(width - call.right, LnSpace.pageGutter - 2);
        }
      });
    }

    testWidgets('no call circle while the agent is paused', (tester) async {
      await _pump(tester, state: _state(paused: true));
      expect(_circle('Call agent'), findsNothing);
      expect(_circle('Back'), findsOneWidget);
    });

    testWidgets('as the drawer home, ☰ opens the drawer', (tester) async {
      final drawer = LnDrawerController();
      addTearDown(drawer.dispose);
      await _pump(tester, drawer: drawer, home: true);
      expect(_circle('Back'), findsNothing);
      await tester.tap(find.byType(MenuPillButton));
      await tester.pump();
      expect(drawer.isOpen, isTrue);
      // Pushed (not the home), the same conversation keeps back.
      await _pump(tester, drawer: drawer);
      expect(find.byType(MenuPillButton), findsNothing);
      expect(_circle('Back'), findsOneWidget);
    });

    testWidgets(
      'the capsule opens the conversation\'s actions, profile first',
      (tester) async {
        final handle = tester.ensureSemantics();
        await _pump(tester);
        final capsule = find.byType(TitleCapsule);
        expect(
          tester.getSemantics(find.bySemanticsLabel('Atlas').last),
          isSemantics(label: 'Atlas', hint: 'Agent actions', isButton: true),
        );
        await tester.tap(capsule);
        await tester.pump(const Duration(milliseconds: 300));
        final rows = tester
            .widgetList<LnMenuRow>(find.byType(LnMenuRow))
            .map((r) => r.label)
            .toList();
        expect(rows, [
          'Agent profile',
          'Charts',
          'Routines',
          'Artifacts',
          'Chat experience',
          'Agent settings',
        ]);
        // The menu hangs from the name pill, not over it.
        final pill = tester.getRect(capsule);
        expect(
          tester.getRect(find.byType(LnMenuCard)).top,
          greaterThanOrEqualTo(pill.bottom),
        );
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
        await tester.tapAt(const Offset(5, 800));
        await tester.pump(const Duration(milliseconds: 300));
        handle.dispose();
      },
    );
  });

  group('header (group)', () {
    testWidgets('a group\'s capsule names the group\'s actions', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await _pump(tester, state: _groupState());
      expect(
        tester.getSemantics(find.bySemanticsLabel('Desk').last),
        isSemantics(label: 'Desk', hint: 'Group actions', isButton: true),
      );
      await tester.tap(find.byType(TitleCapsule));
      await tester.pump(const Duration(milliseconds: 300));
      expect(
        tester.widgetList<LnMenuRow>(find.byType(LnMenuRow)).first.label,
        'Group settings',
      );
      expect(find.bySemanticsLabel('Group actions'), findsWidgets);
      await tester.tapAt(const Offset(5, 800));
      await tester.pump(const Duration(milliseconds: 300));
      handle.dispose();
    });
  });

  group('message menu', () {
    testWidgets('anchored to the message: reactions, time, entries in order', (
      tester,
    ) async {
      await _pump(tester);
      await tester.longPress(find.text('Gold opened flat.'));
      await tester.pump(const Duration(milliseconds: 500));
      // The message is lifted: drawn again over the blurred transcript.
      expect(find.text('Gold opened flat.'), findsNWidgets(2));
      expect(find.byType(BackdropFilter), findsOneWidget);
      // Today's message: the time only.
      expect(find.text(l10n.timeSeparator(today(9, 1))), findsWidgets);
      final rows = tester
          .widgetList<LnMenuRow>(find.byType(LnMenuRow))
          .map((r) => r.label)
          .toList();
      expect(rows, ['Reply', 'Copy text', 'Select text', 'Turn into a task']);
      for (final emoji in ['👍', '❤️', '😂', '😮', '😢', '🙏']) {
        expect(
          find.byWidgetPredicate(
            (w) => w is LnTappable && w.semanticLabel == 'React $emoji',
          ),
          findsOneWidget,
        );
      }
      // The pill above the message, the card below it.
      final lifted = tester.getRect(find.text('Gold opened flat.').last);
      expect(
        tester.getRect(find.byType(LnMenuCard)).top,
        greaterThan(lifted.bottom),
      );
      await tester.tap(find.text('Reply'));
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(ComposerReplyBar), findsOneWidget);
    });
  });

  group('composer', () {
    testWidgets('«+» opens the sources and web search over the composer', (
      tester,
    ) async {
      fake.answers['PUT /threads/$threadId/options'] = (_) => {
        'id': threadId,
        'options': {'web_search': true},
      };
      await _pump(tester, state: signedIn(_state()));
      await tester.tap(
        find.byWidgetPredicate(
          (w) => w is LnTappable && w.semanticLabel == 'Attach file',
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));
      final rows = tester.widgetList<LnMenuRow>(find.byType(LnMenuRow));
      expect(rows.map((r) => r.label), [
        'Camera',
        'Photos',
        'Files',
        'Web search',
      ]);
      expect(rows.map((r) => r.icon), [
        FIcons.camera,
        FIcons.image,
        FIcons.file,
        FIcons.globe,
      ]);
      // No scrim; the menu overlaps the composer's top edge, 7 dp inside its start edge.
      final composer = tester.getRect(find.byType(Composer));
      final menu = tester.getRect(find.byType(LnMenuCard));
      expect(menu.bottom, closeTo(composer.top + 4, 0.01));
      expect(
        menu.left,
        closeTo(
          composer.left + ConversationComposerState.attachMenuInset,
          0.01,
        ),
      );
      await tester.tap(find.text('Web search'));
      await tester.pump(const Duration(milliseconds: 300));
      expect(
        fake.calls.where(
          (c) => c.method == 'PUT' && c.path == '/threads/$threadId/options',
        ),
        hasLength(1),
      );
    });

    testWidgets('in Arabic the «+» menu keeps 7 dp inside the composer\'s '
        'right (start) edge', (tester) async {
      await _pump(tester, locale: 'ar');
      await tester.tap(
        find.byWidgetPredicate(
          (w) => w is LnTappable && w.semanticLabel == l10n.t('attach'),
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));
      final composer = tester.getRect(find.byType(Composer));
      final menu = tester.getRect(find.byType(LnMenuCard));
      expect(
        menu.right,
        closeTo(
          composer.right - ConversationComposerState.attachMenuInset,
          0.01,
        ),
      );
      await tester.tapAt(const Offset(5, 100));
      await tester.pump(const Duration(milliseconds: 300));
    });

    testWidgets('turning web search on says what it does', (tester) async {
      fake.answers['PUT /threads/$threadId/options'] = (_) => {
        'id': threadId,
        'options': {'web_search': true},
      };
      await _pump(tester, state: signedIn(_state()));
      await tester.tap(
        find.byWidgetPredicate(
          (w) => w is LnTappable && w.semanticLabel == 'Attach file',
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(find.text('Web search'));
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text(l10n.t('webSearchOn')), findsOneWidget);
      await tester.pump(const Duration(seconds: 5));
    });

    String? hint(WidgetTester tester) => tester
        .widget<TextField>(
          find.descendant(
            of: find.byType(Composer),
            matching: find.byType(TextField),
          ),
        )
        .decoration
        ?.hintText;

    testWidgets('the empty composer: hold to talk; while the agent works it '
        'names the agent (and the hold still records)', (tester) async {
      await _pump(tester);
      expect(hint(tester), 'Hold to talk, tap to type');
      final base = _state();
      final t = base.thread(threadId);
      await _pump(
        tester,
        state: base.withThread(
          t.copyWith(runs: {'r1': run('r1', 'running', inputSeq: 4)}),
        ),
      );
      expect(hint(tester), 'Message Atlas');
      expect(tester.widget<Composer>(find.byType(Composer)).running, isTrue);
      expect(
        tester.widget<Composer>(find.byType(Composer)).holdToTalk,
        isNotNull,
      );
    });

    testWidgets('with web search on, its row is checked', (tester) async {
      await _pump(tester, state: _state(webSearch: true));
      await tester.tap(
        find.byWidgetPredicate(
          (w) => w is LnTappable && w.semanticLabel == 'Attach file',
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));
      final web = tester.widget<LnMenuRow>(
        find.widgetWithText(LnMenuRow, 'Web search'),
      );
      expect(web.checked, isTrue);
      await tester.tapAt(const Offset(5, 100));
      await tester.pump(const Duration(milliseconds: 300));
    });

    testWidgets('the composer sits 12 dp above the keyboard', (tester) async {
      await _pump(tester, keyboard: const EdgeInsets.only(bottom: 300));
      final height =
          tester.view.physicalSize.height / tester.view.devicePixelRatio;
      final composer = tester.getRect(find.byType(Composer));
      expect(height - 300 - composer.bottom, LnSpace.sm);
    });
  });

  group('transcript', () {
    testWidgets('one sender\'s bubbles run 4 dp apart with joined corners', (
      tester,
    ) async {
      await _pump(tester);
      MessageBubble bubble(String id) => tester.widget<MessageBubble>(
        find.descendant(
          of: find.byWidgetPredicate(
            (w) => w is MessageTile && w.message.id == id,
          ),
          matching: find.byType(MessageBubble),
        ),
      );
      expect((bubble('m2').joinTop, bubble('m2').joinBottom), (false, true));
      expect((bubble('m3').joinTop, bubble('m3').joinBottom), (true, true));
      expect((bubble('m4').joinTop, bubble('m4').joinBottom), (true, false));
      expect((bubble('m1').joinTop, bubble('m1').joinBottom), (false, false));
      Rect box(String text) => tester.getRect(
        find
            .descendant(
              of: find.ancestor(
                of: find.text(text),
                matching: find.byType(MessageBubble),
              ),
              matching: find.byType(Container),
            )
            .first,
      );
      expect(
        box('Gold opened flat.').top - box('Good morning.').bottom,
        LnSpace.bubbleRunGap,
      );
    });

    testWidgets('swiping a bubble toward the end replies to it', (
      tester,
    ) async {
      await _pump(tester);
      final gesture = await tester.startGesture(
        tester.getCenter(find.text('Gold opened flat.')),
      );
      for (var i = 0; i < 12; i++) {
        await gesture.moveBy(const Offset(10, 0));
        await tester.pump();
      }
      await gesture.up();
      await tester.pump(const Duration(milliseconds: 500));
      final bar = find.byType(ComposerReplyBar);
      expect(bar, findsOneWidget);
      expect(
        find.descendant(of: bar, matching: find.text('Gold opened flat.')),
        findsOneWidget,
      );
    });

    testWidgets('today\'s separator is the time alone; screen readers get a '
        'reply action', (tester) async {
      final handle = tester.ensureSemantics();
      await _pump(tester, locale: 'ar');
      final label = l10n.timeSeparator(today(9, 0));
      expect(find.text(label), findsOneWidget);
      // Arabic-Indic digits, no «اليوم».
      expect(label, isNot(contains('اليوم')));
      expect(RegExp('[0-9]').hasMatch(label), isFalse);
      expect(RegExp('[٠-٩]').hasMatch(label), isTrue);
      final node = tester.getSemantics(
        find
            .ancestor(
              of: find.text('Gold opened flat.'),
              matching: find.byType(MessageBubble),
            )
            .first,
      );
      expect(
        node.getSemanticsData().customSemanticsActionIds,
        isNotEmpty,
        reason: 'swipe to reply as a custom action',
      );
      handle.dispose();
    });

    for (final locale in ['en', 'ar']) {
      testWidgets('a 3 dp scrollbar at the end edge while scrolling, gone '
          'when idle ($locale)', (tester) async {
        await _pump(
          tester,
          locale: locale,
          state: _state(
            messages: [
              for (var i = 1; i <= 30; i++)
                message(
                  'm$i',
                  i,
                  i.isEven ? 'assistant' : 'user',
                  'Message number $i with some words in it',
                  today(9, i),
                ),
            ],
          ),
        );
        final bar = tester.widget<RawScrollbar>(find.byType(RawScrollbar));
        expect(bar.thickness, 3);
        expect(bar.radius, const Radius.circular(1.5));
        final scrollbar = tester.renderObject(find.byType(RawScrollbar));
        // Nothing shows before the transcript moves.
        expect(scrollbar, isNot(_thumb((_) {})));
        final gesture = await tester.startGesture(
          tester.getCenter(find.byType(ListView)),
        );
        for (var i = 0; i < 6; i++) {
          await gesture.moveBy(const Offset(0, 40));
          await tester.pump(const Duration(milliseconds: 50));
        }
        await tester.pump(const Duration(milliseconds: 400));
        Rect? thumb;
        expect(scrollbar, _thumb((r) => thumb = r));
        final width = _width(tester);
        expect(thumb!.width, 3);
        expect(thumb!.height, greaterThanOrEqualTo(36));
        if (locale == 'ar') {
          expect(thumb!.left, 0);
        } else {
          expect(thumb!.right, width);
        }
        // Below the header, above the composer.
        expect(
          thumb!.top,
          greaterThanOrEqualTo(tester.getRect(find.byType(TitleCapsule)).top),
        );
        expect(
          thumb!.bottom,
          lessThanOrEqualTo(tester.getRect(find.byType(Composer)).top),
        );
        await gesture.up();
        await tester.pump(const Duration(milliseconds: 600));
        // Idle: it fades away.
        await tester.pump(const Duration(seconds: 2));
        await tester.pump(const Duration(milliseconds: 500));
        expect(scrollbar, isNot(_thumb((_) {})));
      });
    }

    testWidgets('the transcript fades over 18 dp into the canvas above the '
        'composer', (tester) async {
      await _pump(tester);
      final fade = find.byWidgetPredicate((w) {
        final gradient = w is DecoratedBox && w.decoration is BoxDecoration
            ? (w.decoration as BoxDecoration).gradient
            : null;
        return gradient is LinearGradient &&
            gradient.colors.length == 2 &&
            (gradient.colors.last.a - 0.7).abs() < 0.01;
      });
      expect(fade, findsOneWidget);
      final rect = tester.getRect(fade);
      expect(rect.height, 18);
      expect(rect.width, _width(tester));
      final composer = tester.getRect(find.byType(ConversationComposer));
      expect(rect.bottom, closeTo(composer.top - LnSpace.xs, 0.01));
      final gradient =
          (tester.widget<DecoratedBox>(fade).decoration as BoxDecoration)
                  .gradient!
              as LinearGradient;
      expect(gradient.colors.first.a, 0);
      expect(
        tester
            .widget<IgnorePointer>(
              find
                  .ancestor(of: fade, matching: find.byType(IgnorePointer))
                  .first,
            )
            .ignoring,
        isTrue,
      );
    });

    testWidgets('the header hides the transcript down to the circles\' '
        'bottom, then fades it in until 64 dp under the capsule', (
      tester,
    ) async {
      await _pump(tester);
      final fade = find.descendant(
        of: find.byType(ConversationHeader),
        matching: find.byWidgetPredicate(
          (w) =>
              w is DecoratedBox &&
              w.decoration is BoxDecoration &&
              (w.decoration as BoxDecoration).gradient is LinearGradient,
        ),
      );
      expect(fade, findsOneWidget);
      final rect = tester.getRect(fade);
      final gradient =
          (tester.widget<DecoratedBox>(fade).decoration as BoxDecoration)
                  .gradient!
              as LinearGradient;
      expect(gradient.colors.map((c) => c.a).toList(), [1, 1, 0]);
      // Opaque down to the back circle's bottom (its Ø44 disc in a 48 dp target).
      final back = tester.getRect(_circle(l10n.t('back')));
      expect(rect.top, 0);
      expect(
        rect.top + gradient.stops![1] * rect.height,
        closeTo(back.bottom - 2, 0.01),
      );
      // Clear 64 dp under the capsule (its name pill's bottom).
      final capsule = tester.getRect(find.byType(TitleCapsule));
      expect(rect.bottom, closeTo(capsule.bottom + 64, 0.01));
    });

    testWidgets(
      'the jump button: end side, 16 dp in, 20 dp above the composer',
      (tester) async {
        await _pump(
          tester,
          state: _state(
            messages: [
              for (var i = 1; i <= 30; i++)
                message(
                  'm$i',
                  i,
                  i.isEven ? 'assistant' : 'user',
                  'Message number $i with some words in it',
                  today(9, i),
                ),
            ],
          ),
        );
        await tester.drag(find.byType(ListView), const Offset(0, 600));
        await tester.pump(const Duration(milliseconds: 500));
        // The button grows in.
        await tester.pump(const Duration(milliseconds: 500));
        final jump = find.byType(JumpToLatestButton);
        final disc = tester.getRect(
          find.descendant(
            of: jump,
            matching: find.byWidgetPredicate(
              (w) =>
                  w is Container &&
                  w.constraints?.maxWidth == LnSize.jumpButton,
            ),
          ),
        );
        final composer = tester.getRect(find.byType(Composer));
        expect(disc.size, const Size(LnSize.jumpButton, LnSize.jumpButton));
        expect(_width(tester) - disc.right, LnSpace.pageGutter);
        expect(composer.top - disc.bottom, 20);
      },
    );
  });

  group('goldens', () {
    for (final (brightness, locale) in [
      (Brightness.dark, 'ar'),
      (Brightness.light, 'en'),
    ]) {
      final name = '${brightness.name}_$locale';
      testWidgets('message menu $name', (tester) async {
        await withRealShadows(() async {
          await _pump(tester, locale: locale, brightness: brightness);
          await tester.longPress(find.text('Gold opened flat.'));
          await tester.pump(const Duration(milliseconds: 500));
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile('goldens/message_menu_$name.png'),
          );
        });
      });

      testWidgets('attach menu $name', (tester) async {
        await withRealShadows(() async {
          await _pump(tester, locale: locale, brightness: brightness);
          await tester.tap(
            find.byWidgetPredicate(
              (w) => w is LnTappable && w.semanticLabel == l10n.t('attach'),
            ),
          );
          await tester.pump(const Duration(milliseconds: 300));
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile('goldens/attach_menu_$name.png'),
          );
        });
      });
    }
  });
}
