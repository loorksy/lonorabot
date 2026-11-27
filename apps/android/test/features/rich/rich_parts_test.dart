// `rich_content` validation (fail closed, whole content), the server-written voice / call /
// command parts, and the legacy v1 visual documents' values, state and actions.
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/features/rich/rich_parts.dart';
import 'package:lonora/features/rich/visual/visual_document.dart';

const _artifact = '0f8fad5b-d9cb-469f-a165-70867728950e';

Json _card() => {
  'type': 'ui',
  'document': {
    'v': 2,
    'kind': 'summary',
    'title': 'T',
    'icon': 'bell',
    'facts': <String, Object?>{},
    'state': <String, Object?>{},
    'calc': <String, Object?>{},
    'blocks': [
      {'type': 'Text', 'text': 'x'},
    ],
    'fallback': 'x',
  },
};

Json _visual([Map<String, Object?> root = const {}]) => {
  'version': 1,
  'mode': 'estimate',
  'state': {'qty': 2, 'pick': 'a', 'q': ''},
  'facts': {
    'price': {
      'value': 10,
      'source': 'quote',
      'observed_at': '2026-11-27T09:00:00Z',
    },
  },
  'root': {
    'id': 'root',
    'type': 'column',
    'children': [
      {
        'id': 'total',
        'type': 'metric',
        'label': 'Total',
        'value': {
          'op': 'mul',
          'args': [
            {'state': 'qty'},
            {'source': 'price'},
          ],
        },
      },
      {
        'id': 'pick',
        'type': 'select',
        'state_key': 'pick',
        'options': [
          {'value': 'a', 'label': 'A'},
          {'value': 'b', 'label': 'B'},
        ],
      },
      {'id': 'greet', 'type': 'text', 'text': 'Qty {{qty}}'},
      {
        'id': 'ask',
        'type': 'button',
        'label': 'Ask',
        'action': {'kind': 'follow_up', 'text': 'Buy {{qty}} of {{pick}}'},
      },
      ...?root['extra'] as List?,
    ],
  },
};

void main() {
  test('text, v2 card and v1 document parts keep their stored order', () {
    final parts = validateRichContent({
      'version': 1,
      'parts': [
        {'type': 'text', 'text': 'lead'},
        _card(),
        {'type': 'ui', 'document': _visual()},
      ],
    })!;
    expect(parts.map((p) => p.runtimeType), [TextPart, CardPart, VisualPart]);
  });

  test('one malformed part rejects the whole rich content', () {
    expect(
      validateRichContent({
        'version': 1,
        'parts': [
          {'type': 'text', 'text': 'ok'},
          {'type': 'text', 'text': 'x', 'html': '<b>'},
        ],
      }),
      isNull,
    );
    expect(validateRichContent({'version': 2, 'parts': []}), isNull);
    expect(validateRichContent({'version': 1, 'parts': []}), isNull);
    expect(
      validateRichContent({
        'version': 1,
        'parts': [
          {'type': 'video', 'url': 'x'},
        ],
      }),
      isNull,
    );
  });

  test('voice parts need 44 integer peaks and a known transcript status', () {
    Json voice({
      List<int>? peaks,
      Object duration = 12.5,
      String status = 'done',
    }) => {
      'version': 1,
      'parts': [
        {
          'type': 'voice',
          'artifact_id': _artifact,
          'duration': duration,
          'peaks': peaks ?? List.filled(44, 50),
          'transcript_status': status,
        },
      ],
    };
    final ok = validateRichContent(voice())!.single as VoicePart;
    expect(ok.duration, 12.5);
    expect(ok.peaks, hasLength(44));
    expect(validateRichContent(voice(peaks: List.filled(43, 1))), isNull);
    expect(validateRichContent(voice(duration: 121)), isNull);
    expect(validateRichContent(voice(status: 'maybe')), isNull);
  });

  test('call and command parts', () {
    final call =
        validateRichContent({
              'version': 1,
              'parts': [
                {
                  'type': 'call',
                  'direction': 'incoming',
                  'duration_seconds': 75,
                  'missed': false,
                },
              ],
            })!.single
            as CallPart;
    expect(call.durationSeconds, 75);
    final command =
        validateRichContent({
              'version': 1,
              'parts': [
                {
                  'type': 'command',
                  'name': 'skill',
                  'argument': 'this file',
                  'skill_id': 's1',
                  'skill_name': 'Summarise',
                },
              ],
            })!.single
            as CommandPart;
    expect(command.skillName, 'Summarise');
    expect(
      validateRichContent({
        'version': 1,
        'parts': [
          {'type': 'command', 'name': 'delete', 'argument': ''},
        ],
      }),
      isNull,
    );
  });

  group('v1 visual documents', () {
    test('validate, with legacy {{key}} text bound to declared state', () {
      final doc = validateVisualDocument(_visual())!;
      final greet = asJsonList(asJson(doc['root'])['children'])[2];
      expect(greet.containsKey('text'), isFalse);
      expect(
        evaluateVisualValue(greet['value'], doc, initialVisualState(doc)),
        'Qty 2',
      );
    });

    test(
      'unknown properties, undeclared state and bad actions fail closed',
      () {
        expect(
          validateVisualDocument(
            _visual({
              'extra': [
                {'id': 'x', 'type': 'text', 'text': 'a', 'style': 'red'},
              ],
            }),
          ),
          isNull,
        );
        expect(
          validateVisualDocument(
            _visual({
              'extra': [
                {'id': 'x', 'type': 'checkbox', 'state_key': 'missing'},
              ],
            }),
          ),
          isNull,
        );
        expect(
          validateVisualDocument(
            _visual({
              'extra': [
                {
                  'id': 'x',
                  'type': 'button',
                  'label': 'Go',
                  'action': {'kind': 'open_url', 'resource_id': 'https://x'},
                },
              ],
            }),
          ),
          isNull,
        );
      },
    );

    test('values, state updates and action expansion', () {
      final doc = validateVisualDocument(_visual())!;
      var state = initialVisualState(doc);
      final total = asJsonList(asJson(doc['root'])['children'])[0];
      expect(evaluateVisualValue(total['value'], doc, state), 20);
      // Only a declared option is accepted.
      state = updateVisualState(doc, state, 'pick', 'z');
      expect(state['pick'], 'a');
      state = updateVisualState(doc, state, 'pick', 'b');
      expect(state['pick'], 'b');
      final ask = asJsonList(asJson(doc['root'])['children'])[3];
      expect(expandVisualAction(ask['action'], doc, state), {
        'kind': 'follow_up',
        'text': 'Buy 2 of b',
      });
      expect(
        evaluateVisualValue(
          {
            'op': 'round',
            'args': [2.345, 2],
          },
          doc,
          state,
        ),
        2.35,
      );
      expect(
        evaluateVisualValue(
          {
            'op': 'div',
            'args': [1, 0],
          },
          doc,
          state,
        ),
        isNull,
      );
    });
  });
}
