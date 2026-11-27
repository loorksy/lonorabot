// The conversation's inline event rows keep their gaps now that a tappable row is at least 48 dp
// tall: the gaps are measured on the rendered tree, from the bubble above to the row's icon slot
// and from the slot to the bubble below.
import 'dart:async';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/conversation/conversation_composer.dart';
import 'package:lonora/features/conversation/conversation_screen.dart';
import 'package:lonora/features/conversation/message_widgets.dart';
import 'package:lonora/features/conversation/run_rows.dart';
import 'package:lonora/features/rich/rich_content_view.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';

import '../../design/fonts.dart';
import '../../design/harness.dart';
import 'conversation_harness.dart';

late L10n l10n;

/// The owner event feed: [emit] hands a run event to the open conversation.
class _Feed extends RealtimeController {
  _Feed(super.store);

  final _feed = StreamController<LonoraEvent>.broadcast();
  int _cursor = 0;

  @override
  Stream<LonoraEvent> get events => _feed.stream;

  void emit(String kind, Map<String, Object?> payload) => _feed.add(
    LonoraEvent(
      cursor: ++_cursor,
      kind: kind,
      threadId: threadId,
      runId: 'r1',
      payload: payload,
      createdAt: at(6),
    ),
  );
}

Message system(String id, int seq, String content, DateTime t, [Map? rich]) =>
    Message.fromJson({
      ...messageJson(
        id: id,
        seq: seq,
        role: 'system',
        content: content,
        createdAt: t,
      ),
      'agent_id': agentId,
      'rich_content': ?rich,
    });

const missedCall = {
  'version': 1,
  'parts': [
    {
      'type': 'call',
      'direction': 'outgoing',
      'duration_seconds': 0,
      'missed': true,
    },
  ],
};

/// Bubble above, event row, bubble below: each event row between two agent bubbles.
AppState spacingState() => conversationState(
  messages: [
    message('m1', 1, 'assistant', 'First reply.', at(1)),
    system('m2', 2, 'Missed voice call', at(2), missedCall),
    message('m3', 3, 'assistant', 'Second reply.', at(3)),
    system('m4', 4, 'Atlas joined the group.', at(4)),
    message('m5', 5, 'assistant', 'Third reply.', at(5)),
    Message.fromJson(
      messageJson(
        id: 'm6',
        seq: 6,
        role: 'tool',
        content: '{"ok":true}',
        createdAt: at(6),
      ),
    ),
    message('m7', 7, 'assistant', 'Fourth reply.', at(7)),
  ],
);

/// The bubble showing [text].
Rect bubble(WidgetTester tester, String text) => tester.getRect(
  find.ancestor(of: find.text(text), matching: find.byType(MessageBubble)),
);

/// The event row's icon slot: its icon's box grown to the 22 dp (start) or 20 dp (centred)
/// slot it is centred in.
Rect slot(WidgetTester tester, Finder row, double size) {
  final icon = tester.getRect(
    find.descendant(of: row, matching: find.byType(Icon)).first,
  );
  return Rect.fromCenter(center: icon.center, width: size, height: size);
}

({double above, double below}) gaps(
  WidgetTester tester,
  Finder row,
  double size,
  String before,
  String after,
) {
  final s = slot(tester, row, size);
  return (
    above: s.top - bubble(tester, before).bottom,
    below: bubble(tester, after).top - s.bottom,
  );
}

void main() {
  setUpAll(() async {
    await loadAppFonts();
    l10n = await L10n.load();
    if (!sl.isRegistered<LocalStore>()) {
      final dir = await Directory.systemTemp.createTemp('lonora_spacing_test');
      sl.registerSingleton<LocalStore>(LocalStore.at(dir));
    }
  });
  setUp(registerFakeApi);
  tearDown(() async {
    if (sl.isRegistered<ApiClient>()) await sl.unregister<ApiClient>();
    ConversationComposerState.clearDrafts();
  });

  testWidgets('event rows keep their gaps', (tester) async {
    setGoldenViewport(tester);
    await tester.pumpWidget(
      conversationApp(
        store: Store<AppState>(initialState: spacingState()),
        l10n: l10n,
        child: const ConversationScreen(threadId: threadId),
      ),
    );
    await tester.pump(const Duration(milliseconds: 500));

    final call = gaps(
      tester,
      find.byType(CallLogRow),
      22,
      'First reply.',
      'Second reply.',
    );
    final system = gaps(
      tester,
      find.byType(SystemRow),
      20,
      'Second reply.',
      'Third reply.',
    );
    final tool = gaps(
      tester,
      find.byType(ToolResultRow),
      22,
      'Third reply.',
      'Fourth reply.',
    );
    // Start rows that call back or open (a call-log row with ›): 15.3 above and 13 below. The row
    // is 48 dp tall (the touch-target floor), so the gap below is 4.5 more than the 8.5 a 22 dp row
    // would leave.
    for (final g in [call, tool]) {
      expect(g.above, closeTo(15.3, 0.5));
      expect(g.below, 13);
    }
    expect(tester.getSize(find.byType(CallLogRow)).height, LnSize.minTouch);
    expect(tester.getSize(find.byType(ToolResultRow)).height, LnSize.minTouch);
    // A centred system line is not tappable: it keeps its 36 dp and its gaps.
    expect(tester.getSize(find.byType(SystemRow)).height, 36);
    expect(system.above, 15);
    expect(system.below, 8);
  });

  testWidgets(
    'a tappable row under a time separator keeps the separator\'s gap',
    (tester) async {
      setGoldenViewport(tester);
      await tester.pumpWidget(
        conversationApp(
          store: Store<AppState>(
            initialState: conversationState(
              messages: [
                system('m1', 1, 'Missed voice call', at(1), missedCall),
                message('m2', 2, 'assistant', 'A reply.', at(2)),
              ],
            ),
          ),
          l10n: l10n,
          child: const ConversationScreen(threadId: threadId),
        ),
      );
      await tester.pump(const Duration(milliseconds: 500));

      final label = tester.getRect(
        find.descendant(
          of: find.byType(DateSeparator),
          matching: find.byType(Text),
        ),
      );
      final row = tester.getRect(find.byType(CallLogRow));
      expect(row.height, LnSize.minTouch);
      // K14: the 48 dp row's 38 dp content (5 dp below its top) sits the separator's 16 dp
      // under the label, as a plain row does.
      expect(row.top + 5 - label.bottom, LnSpace.md);
    },
  );

  testWidgets('a tappable activity line keeps the gap of a plain one', (
    tester,
  ) async {
    setGoldenViewport(tester);
    final store = Store<AppState>(
      initialState: conversationState(
        messages: [message('m1', 1, 'user', 'Find the levels.', at(5))],
        runs: {'r1': run('r1', 'running', inputSeq: 1, createdAt: at(6))},
      ),
    );
    final feed = _Feed(store);
    realtime = feed;
    await tester.pumpWidget(
      conversationApp(
        store: store,
        l10n: l10n,
        child: const ConversationScreen(threadId: threadId),
      ),
    );
    await tester.pump(const Duration(milliseconds: 500));

    final line = find.byType(ActivityLine);
    double above() {
      final spinner = tester.getRect(
        find.descendant(of: line, matching: find.byType(LnSpinner)),
      );
      final s = Rect.fromCenter(center: spinner.center, width: 22, height: 22);
      return s.top - bubble(tester, 'Find the levels.').bottom;
    }

    // A tool step without a call id: the line shows, with nothing to open.
    feed.emit('tool.started', {'name': 'market.quote'});
    await tester.pump(const Duration(milliseconds: 500));
    expect(tester.getSize(line).height, 38);
    final plain = above();
    // A call to open: the line is a 48 dp button, its content where it was.
    feed.emit('tool.started', {'call_id': 'c1', 'name': 'market.quote'});
    await tester.pump(const Duration(milliseconds: 500));
    expect(tester.getSize(line).height, LnSize.minTouch);
    expect(above(), plain);
    // The change of sender's 16 dp and the row's own 8 dp.
    expect(plain, 24);
    // Opened, the call's status follows a dot that keeps to the call's name (Q11).
    await tester.tap(
      find.descendant(of: line, matching: find.byType(InlineEventRow)),
    );
    await tester.pump(const Duration(milliseconds: 300));
    expect(
      find.textContaining('$dotSeparator${l10n.t('activity_call_running')}'),
      findsOneWidget,
    );
  });
}
