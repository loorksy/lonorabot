// Behaviour of the rich renderer: a GenUI card's send posts exactly `ui_submit` (never via the
// outbox) and locks; required fields hold the send; v1 follow-ups use the thread's send path;
// malformed rich content falls back to the message text; voice, call and command parts.
import 'dart:math' as math;

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/design/design.dart' show LnPalette;
import 'package:lonora/features/rich/rich_content_view.dart';
import 'package:lonora/features/rich/visual/visual_view.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/fonts.dart';
import '../cards/card_fixtures.dart' show FakeApi;
import 'rich_harness.dart';

const _thread = 't-w';
const _agent = 'a-w';
const _artifact = '0f8fad5b-d9cb-469f-a165-70867728950e';

Json _cardDoc({bool required = false}) => {
  'version': 1,
  'parts': [
    {
      'type': 'ui',
      'document': {
        'v': 2,
        'kind': 'form',
        'title': 'Alert',
        'icon': 'bell',
        'facts': <String, Object?>{},
        'state': {'side': 'above', 'price': required ? null : 2400},
        'calc': <String, Object?>{},
        'blocks': [
          {
            'type': 'Segmented',
            'bind': 'side',
            'label': 'Direction',
            'options': [
              {'value': 'above', 'label': 'Above'},
              {'value': 'below', 'label': 'Below'},
            ],
          },
          {
            'type': 'Number',
            'bind': 'price',
            'label': 'Price',
            'required': true,
          },
          {
            'type': 'Button',
            'label': 'Create',
            'style': 'primary',
            'action': {'do': 'send', 'intent': 'create_watch', 'lock': true},
          },
        ],
        'fallback': 'Alert',
      },
    },
  ],
};

Message _msg(
  Json rich, {
  String role = 'assistant',
  String content = 'Alert',
}) => Message.fromJson({
  'id': 'card-msg',
  'thread_id': _thread,
  'role': role,
  'agent_id': role == 'assistant' ? _agent : null,
  'seq': 3,
  'content': content,
  'rich_content': rich,
  'created_at': '2026-11-27T10:00:00Z',
});

void main() {
  late L10n l10n;
  setUpAll(() async {
    await loadAppFonts();
    l10n = await loadTestL10n();
  });

  Store<AppState> storeWith(List<Message> messages) => Store<AppState>(
    initialState: signedInState(
      agents: {
        _agent: Agent.fromJson({'id': _agent, 'name': 'Lonora'}),
      },
      threads: {
        _thread: ThreadState(
          threadId: _thread,
          thread: const Thread(id: _thread, agentId: _agent),
          messages: messages,
          loaded: true,
        ),
      },
    ),
  );

  Future<FakeApi> withApi(Map<String, Object? Function(Object?)> routes) async {
    await sl.reset();
    final fake = FakeApi(routes);
    sl.registerSingleton<ApiClient>(fake);
    return fake;
  }

  Future<void> pump(
    WidgetTester tester,
    Store<AppState> store,
    Widget child,
  ) async {
    tester.view.physicalSize = const Size(393, 1200) * 2;
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      richTestApp(
        l10n: l10n,
        store: store,
        locale: 'en',
        child: SingleChildScrollView(child: child),
      ),
    );
    await settle(tester);
  }

  testWidgets('a card send posts only ui_submit with its values, then locks', (
    tester,
  ) async {
    final fake = await withApi({
      'POST /threads/$_thread/messages': (body) => {
        'message': {
          'id': 'sub-1',
          'thread_id': _thread,
          'role': 'user',
          'seq': 4,
          'origin': 'ui_submit',
          'reply_to': 'card-msg',
          'client_nonce': asJson(body)['client_nonce'],
          'content': 'Create',
          'ui_submit': {
            'source_message_id': 'card-msg',
            'part': 0,
            'intent': 'create_watch',
            'lock': true,
            'run_id': 'run-9',
          },
        },
        'runs': [
          {
            'id': 'run-9',
            'thread_id': _thread,
            'agent_id': _agent,
            'status': 'queued',
          },
        ],
      },
    });
    final message = _msg(_cardDoc());
    final store = storeWith([message]);
    await pump(
      tester,
      store,
      RichContentView(
        threadId: _thread,
        text: message.content,
        richContent: message.richContent,
        message: message,
      ),
    );
    await tester.tap(find.text('Below'));
    await settle(tester);
    await tester.tap(find.text('Create'));
    await settle(tester);

    expect(fake.calls, ['POST /threads/$_thread/messages']);
    final body = asJson(fake.bodies.single);
    expect(body['content'], '');
    expect(body['client_nonce'], isA<String>());
    expect(body.keys.toSet(), {'content', 'client_nonce', 'ui_submit'});
    expect(body['ui_submit'], {
      'source_message_id': 'card-msg',
      'part': 0,
      'path': '2',
      'values': {'side': 'below', 'price': 2400},
    });
    // Never through the offline outbox; the accepted submission and its Run merge in.
    expect(store.state.outbox, isEmpty);
    expect(store.state.thread(_thread).messages.map((m) => m.id), [
      'card-msg',
      'sub-1',
    ]);
    expect(store.state.thread(_thread).runs.keys, ['run-9']);
    // Locked: «Sent to Lonora» and «Edit».
    expect(find.text(l10n.t('uiSentTo', ['Lonora'])), findsOneWidget);
    expect(find.text(l10n.t('uiEdit')), findsOneWidget);
  });

  testWidgets('a required field holds the send and says which', (tester) async {
    final fake = await withApi({});
    final message = _msg(_cardDoc(required: true));
    await pump(
      tester,
      storeWith([message]),
      RichContentView(
        threadId: _thread,
        text: message.content,
        richContent: message.richContent,
        message: message,
      ),
    );
    await tester.tap(find.text('Create'));
    await settle(tester);
    expect(fake.calls, isEmpty);
    expect(find.text(l10n.t('uiCompleteFirst', ['Price'])), findsOneWidget);
  });

  testWidgets('a live preview card keeps every control disabled', (
    tester,
  ) async {
    final fake = await withApi({});
    final rich = _cardDoc();
    await pump(
      tester,
      storeWith(const []),
      RichContentView(
        threadId: _thread,
        text: '',
        richContent: rich,
        streaming: true,
      ),
    );
    await tester.tap(find.text('Create'));
    await settle(tester);
    expect(fake.calls, isEmpty);
  });

  testWidgets('malformed rich content falls back to the message text', (
    tester,
  ) async {
    await withApi({});
    final message = _msg({
      'version': 1,
      'parts': [
        {'type': 'text', 'text': 'x', 'unknown': true},
      ],
    }, content: 'The plain fallback');
    await pump(
      tester,
      storeWith([message]),
      RichContentView(
        threadId: _thread,
        text: message.content,
        richContent: message.richContent,
        message: message,
      ),
    );
    expect(find.textContaining('The plain fallback'), findsOneWidget);
  });

  testWidgets('voice, call and command parts', (tester) async {
    await withApi({});
    await pump(
      tester,
      storeWith(const []),
      Column(
        children: [
          RichContentView(
            threadId: _thread,
            text: 'Remind me at five',
            onUserBubble: true,
            richContent: {
              'version': 1,
              'parts': [
                {
                  'type': 'voice',
                  'artifact_id': _artifact,
                  'duration': 7.4,
                  'peaks': List.filled(44, 40),
                  'transcript_status': 'done',
                },
              ],
            },
          ),
          const RichContentView(
            threadId: _thread,
            text: '',
            richContent: {
              'version': 1,
              'parts': [
                {
                  'type': 'call',
                  'direction': 'outgoing',
                  'duration_seconds': 95,
                  'missed': false,
                },
              ],
            },
          ),
          const RichContentView(
            threadId: _thread,
            text: '/task Review the report',
            onUserBubble: true,
            richContent: {
              'version': 1,
              'parts': [
                {
                  'type': 'command',
                  'name': 'task',
                  'argument': 'Review the report',
                },
              ],
            },
          ),
        ],
      ),
    );
    expect(find.textContaining('0:07'), findsOneWidget);
    expect(find.text('Remind me at five'), findsOneWidget);
    expect(find.textContaining(l10n.t('voiceCall')), findsOneWidget);
    expect(find.text('/${l10n.t('cmdTask')}'), findsOneWidget);
    expect(find.text('Review the report'), findsOneWidget);
  });

  testWidgets('a success tone draws its text in the text-safe green', (
    tester,
  ) async {
    Json node(String id, String type, Json extra) => {
      'id': id,
      'type': type,
      'tone': 'success',
      ...extra,
    };
    await pump(
      tester,
      storeWith(const []),
      VisualDocumentView(
        threadId: _thread,
        document: {
          'version': 1,
          'root': {
            'id': 'root',
            'type': 'column',
            'children': [
              node('t', 'text', {'text': 'Filled'}),
              node('h', 'heading', {'text': 'Done'}),
              node('m', 'metric', {'label': 'P&L', 'value': 12}),
              node('i', 'icon', {'text': 'clock'}),
            ],
          },
        },
      ),
    );
    final c = LnPalette.light;
    Color ink(String text) =>
        tester.widget<Text>(find.text(text)).style!.color!;
    double contrast(Color a, Color b) {
      final x = a.computeLuminance(), y = b.computeLuminance();
      return (math.max(x, y) + 0.05) / (math.min(x, y) + 0.05);
    }

    // Q7: text, heading and metric value read at AA on the page and on a grey tile.
    for (final text in ['Filled', 'Done', '12']) {
      expect(ink(text), c.successText);
    }
    expect(contrast(c.successText, c.bg), greaterThanOrEqualTo(4.5));
    expect(
      contrast(c.successText, const Color(0xFFF2F2F2)),
      greaterThanOrEqualTo(4.5),
    );
    // The icon keeps the function green.
    expect(tester.widget<Icon>(find.byType(Icon)).color, c.success);
  });
}
