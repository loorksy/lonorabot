// Goldens of rich message content (light/dark × ar/en, 393 × 852 dp at DPR 2): an agent reply
// in Lonora Markdown, a code block and a table, the owner's plain text, a streaming preview,
// and a lonora-ui v2 form card drawn as the conversation draws it (no bubble).
//
// Regenerate with: flutter test --update-goldens test/features/rich
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/rich/markdown_view.dart';
import 'package:lonora/features/rich/rich_content_view.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/fonts.dart';
import '../../design/harness.dart';
import 'rich_harness.dart';

const _thread = 't-rich';
const _agent = 'a-rich';

const _replyAr = '''## خطة اليوم

راقبتُ **الذهب** منذ الصباح: السعر الآن `2346.80` والتغيّر (+1.2%) خلال اليوم. التفاصيل في [صفحة السوق](https://lonora.ai/market).

- مراجعة الدعم اليومي
- [x] إرسال الملخص
- [ ] انتظار تأكيد الإغلاق

> لا أنفّذ أي صفقة دون موافقتك.''';

const _replyEn = '''## Today's plan

I watched **gold** since the morning: price is `2346.80`, change (+1.2%) today. Details on the [market page](https://lonora.ai/market).

- Review the daily support
- [x] Send the summary
- [ ] Wait for the close to confirm

> I never place a trade without your approval.''';

const _codeAr = '''هذه الدالة تحسب حجم الصفقة:

```python
def lots(balance, risk, stop):
    cash = balance * risk / 100
    return round(cash / (stop * 10), 2)
```

| الرمز | السعر | التغيّر |
| :-- | --: | --: |
| XAUUSD | 2346.80 | +1.2% |
| XAGUSD | 28.92 | -0.4% |
| EURUSD | 1.0842 | +0.1% |''';

const _codeEn = '''This function sizes a position:

```python
def lots(balance, risk, stop):
    cash = balance * risk / 100
    return round(cash / (stop * 10), 2)
```

| Symbol | Price | Change |
| :-- | --: | --: |
| XAUUSD | 2346.80 | +1.2% |
| XAGUSD | 28.92 | -0.4% |
| EURUSD | 1.0842 | +0.1% |''';

Json _form(bool ar) => {
  'version': 1,
  'parts': [
    {
      'type': 'text',
      'text': ar ? 'جهّزت لك نموذج التنبيه:' : 'Here is the alert form:',
    },
    {
      'type': 'ui',
      'document': {
        'v': 2,
        'kind': 'form',
        'title': ar ? 'تنبيه سعر' : 'Price alert',
        'sub': ar ? 'أُبلغك حين يصل السعر' : 'I tell you when price gets there',
        'icon': 'bell',
        'agent_id': _agent,
        'facts': <String, Object?>{},
        'state': {'side': 'above', 'price': 2400, 'when': 'once', 'risk': 2},
        'calc': <String, Object?>{},
        'blocks': [
          {
            'type': 'Segmented',
            'bind': 'side',
            'label': ar ? 'الاتجاه' : 'Direction',
            'options': [
              {'value': 'above', 'label': ar ? 'فوق' : 'Above'},
              {'value': 'below', 'label': ar ? 'تحت' : 'Below'},
            ],
          },
          {
            'type': 'Number',
            'bind': 'price',
            'label': ar ? 'السعر' : 'Price',
            'hint': ar ? 'بالدولار' : 'in USD',
            'prefix': r'$',
            'required': true,
          },
          {
            'type': 'Select',
            'bind': 'when',
            'label': ar ? 'التكرار' : 'Repeat',
            'options': [
              {'value': 'once', 'label': ar ? 'مرة واحدة' : 'Once'},
              {'value': 'daily', 'label': ar ? 'يوميًا' : 'Daily'},
            ],
          },
          {
            'type': 'Slider',
            'bind': 'risk',
            'label': ar ? 'المخاطرة' : 'Risk',
            'min': 1,
            'max': 5,
            'show': r'{$risk}%',
          },
          {
            'type': 'Note',
            'tone': 'warn',
            'text': ar
                ? 'التنبيه **لا ينفّذ** أي صفقة.'
                : 'An alert **never** places a trade.',
          },
          {
            'type': 'Button',
            'label': ar ? 'أنشئ التنبيه' : 'Create alert',
            'style': 'primary',
            'action': {'do': 'send', 'intent': 'create_watch'},
          },
        ],
        'why': ar ? 'الأرقام أوضح في نموذج.' : 'Numbers read better in a form.',
        'fallback': ar ? 'تنبيه عند 2400' : 'Alert at 2400',
      },
    },
  ],
};

Message _message(int seq, String role, String content, {Json? rich}) =>
    Message.fromJson({
      'id': 'm$seq',
      'thread_id': _thread,
      'role': role,
      'agent_id': role == 'assistant' ? _agent : null,
      'seq': seq,
      'content': content,
      'rich_content': ?rich,
      'created_at': '2026-11-27T09:0$seq:00Z',
    });

void main() {
  late L10n l10n;
  setUpAll(() async {
    await loadAppFonts();
    await loadMonospaceFont();
    // Real asset I/O does not complete inside testWidgets' fake async zone.
    l10n = await loadTestL10n();
  });

  final agent = Agent.fromJson({
    'id': _agent,
    'name': 'Lonora',
    'avatar': 'face-smile',
  });

  Store<AppState> storeWith(List<Message> messages) => Store<AppState>(
    initialState: signedInState(
      agents: {_agent: agent},
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

  Widget agentBubble(String text, {bool streaming = false}) => Align(
    alignment: AlignmentDirectional.centerStart,
    child: MessageBubble(
      sender: BubbleSender.agent,
      child: RichContentView(
        threadId: _thread,
        text: text,
        streaming: streaming,
      ),
    ),
  );

  for (final (brightness, locale) in goldenVariants) {
    final ar = locale == 'ar';
    final name = variantName(brightness, locale);

    testWidgets('rich message $name', (tester) async {
      setGoldenViewport(tester);
      await withRealShadows(() async {
        await tester.pumpWidget(
          richTestApp(
            l10n: l10n,
            store: storeWith(const []),
            brightness: brightness,
            locale: locale,
            child: Directionality(
              textDirection: ar ? TextDirection.rtl : TextDirection.ltr,
              child: ListView(
                padding: BubbleGroup.gutter.copyWith(top: 12, bottom: 12),
                children: [
                  Align(
                    alignment: AlignmentDirectional.centerEnd,
                    child: MessageBubble(
                      sender: BubbleSender.user,
                      child: RichContentView(
                        threadId: _thread,
                        text: ar
                            ? 'كيف يبدو الذهب اليوم؟ **راجع** https://lonora.ai'
                            : 'How does gold look today? **check** https://lonora.ai',
                        onUserBubble: true,
                      ),
                    ),
                  ),
                  BubbleGroup.spacer(sameSender: false),
                  agentBubble(ar ? _replyAr : _replyEn),
                  BubbleGroup.spacer(sameSender: true),
                  agentBubble(
                    ar ? 'أكتب الملخص الآن' : 'Writing the summary now',
                    streaming: true,
                  ),
                ],
              ),
            ),
          ),
        );
        await settle(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/rich_message_$name.png'),
        );
      });
    });

    testWidgets('code block and table $name', (tester) async {
      setGoldenViewport(tester);
      await tester.pumpWidget(
        richTestApp(
          l10n: l10n,
          store: storeWith(const []),
          brightness: brightness,
          locale: locale,
          child: ListView(
            padding: BubbleGroup.gutter.copyWith(top: 12),
            children: [agentBubble(ar ? _codeAr : _codeEn)],
          ),
        ),
      );
      await settle(tester);
      expect(find.byType(MarkdownView), findsOneWidget);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/code_table_$name.png'),
      );
    });

    testWidgets('GenUI form $name', (tester) async {
      setGoldenViewport(tester);
      final rich = _form(ar);
      final message = _message(2, 'assistant', 'Alert at 2400', rich: rich);
      await withRealShadows(() async {
        await tester.pumpWidget(
          richTestApp(
            l10n: l10n,
            store: storeWith([message]),
            brightness: brightness,
            locale: locale,
            child: ListView(
              padding: BubbleGroup.gutter.copyWith(top: 12, bottom: 24),
              children: [
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: RichContentView(
                    threadId: _thread,
                    text: message.content,
                    richContent: rich,
                    message: message,
                  ),
                ),
              ],
            ),
          ),
        );
        await settle(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/genui_form_$name.png'),
        );
      });
    });
  }

  // Large text: the form at 1.3× (Arabic, light) lays out without overflow.
  testWidgets('GenUI form at text scale 1.3', (tester) async {
    setGoldenViewport(tester);
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    final rich = _form(true);
    final message = _message(2, 'assistant', 'Alert at 2400', rich: rich);
    await withRealShadows(() async {
      await tester.pumpWidget(
        richTestApp(
          l10n: l10n,
          store: storeWith([message]),
          child: ListView(
            padding: BubbleGroup.gutter.copyWith(top: 12, bottom: 24),
            children: [
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: RichContentView(
                  threadId: _thread,
                  text: message.content,
                  richContent: rich,
                  message: message,
                ),
              ),
            ],
          ),
        ),
      );
      await settle(tester);
      expect(tester.takeException(), isNull);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/genui_form_scale13_light_ar.png'),
      );
    });
  });
}
