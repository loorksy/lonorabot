// Overlays (sheet, dialog, popover menu, toast) rendered over a simple screen, plus behaviour checks for
// interactive components.
//
// Regenerate with: flutter test --update-goldens test/design
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show SemanticsFlag;
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/design/design.dart';

import 'fonts.dart';
import 'harness.dart';

class _Host extends StatelessWidget {
  const _Host({required this.onOpen});

  final void Function(BuildContext context) onOpen;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      const SizedBox(height: 120),
      Center(
        child: LnPopoverMenu<String>(
          semanticLabel: 'Message',
          blurBackground: true,
          actions: const [
            LnMenuAction(label: 'Copy', icon: FIcons.copy, value: 'copy'),
            LnMenuAction(label: 'Reply', icon: FIcons.reply, value: 'reply'),
            LnMenuAction(
              label: 'Delete',
              icon: FIcons.trash2,
              value: 'delete',
              destructive: true,
            ),
          ],
          child: const MessageBubble.agent('Long-press me'),
        ),
      ),
      const SizedBox(height: 24),
      Builder(
        builder: (context) => BlockButton(
          label: 'Open',
          expand: false,
          onPressed: () => onOpen(context),
        ),
      ),
    ],
  );
}

Future<void> _pumpHost(
  WidgetTester tester,
  void Function(BuildContext) onOpen, {
  Brightness brightness = Brightness.light,
  TextDirection direction = TextDirection.ltr,
}) async {
  setGoldenViewport(tester);
  await tester.pumpWidget(
    lnTestApp(
      child: _Host(onOpen: onOpen),
      brightness: brightness,
      direction: direction,
      padding: const EdgeInsets.only(top: 24),
    ),
  );
  await tester.pump();
}

void main() {
  setUpAll(loadAppFonts);

  final variants = [
    (Brightness.light, TextDirection.ltr),
    (Brightness.dark, TextDirection.rtl),
  ];

  for (final (brightness, direction) in variants) {
    final variant = '${brightness.name}_${direction.name}';

    testWidgets('overlay action menu sheet $variant', (tester) async {
      await withRealShadows(() async {
        await _pumpHost(
          tester,
          (context) => showLnActionMenu<String>(
            context,
            title: 'Conversation',
            actions: const [
              LnMenuAction(label: 'Pin', icon: FIcons.pin, value: 'pin'),
              LnMenuAction(label: 'Mute', icon: FIcons.bellOff, value: 'mute'),
              LnMenuAction(
                label: 'Delete',
                icon: FIcons.trash2,
                value: 'delete',
                destructive: true,
              ),
            ],
          ),
          brightness: brightness,
          direction: direction,
        );
        await tester.tap(find.text('Open'));
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/overlay_sheet_$variant.png'),
        );
      });
    });

    testWidgets('overlay confirm dialog $variant', (tester) async {
      await withRealShadows(() async {
        await _pumpHost(
          tester,
          (context) => showLnConfirm(
            context,
            title: 'Delete conversation?',
            message: 'This removes it from all your devices.',
            confirmLabel: 'Delete',
            cancelLabel: 'Cancel',
            destructive: true,
          ),
          brightness: brightness,
          direction: direction,
        );
        await tester.tap(find.text('Open'));
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/overlay_dialog_$variant.png'),
        );
      });
    });

    testWidgets('overlay confirm dialog, stacked labels $variant', (
      tester,
    ) async {
      final rtl = direction == TextDirection.rtl;
      await withRealShadows(() async {
        await _pumpHost(
          tester,
          (context) => showLnConfirm(
            context,
            title: rtl ? 'إلغاء المراقبة؟' : 'Cancel this watch?',
            message: rtl
                ? 'لن تصلك تنبيهات هذا السهم بعد الآن.'
                : 'You will no longer be alerted about this symbol.',
            confirmLabel: rtl
                ? 'إلغاء المراقبة نهائيًا'
                : 'Cancel the watch for good',
            cancelLabel: rtl ? 'إبقاء المراقبة' : 'Keep watching it',
            destructive: true,
          ),
          brightness: brightness,
          direction: direction,
        );
        await tester.tap(find.text('Open'));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/overlay_dialog_stacked_$variant.png'),
        );
      });
    });

    testWidgets('overlay confirm dialog, wrapped label at 1.3 text scale '
        '$variant', (tester) async {
      tester.platformDispatcher.textScaleFactorTestValue = 1.3;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final rtl = direction == TextDirection.rtl;
      await withRealShadows(() async {
        await _pumpHost(
          tester,
          (context) => showLnConfirm(
            context,
            title: rtl ? 'حذف المحادثة؟' : 'Delete this conversation?',
            message: rtl
                ? 'لا يمكن التراجع عن هذا الإجراء.'
                : 'This cannot be undone.',
            confirmLabel: rtl
                ? 'حذف المحادثة نهائيًا من جميع الأجهزة المرتبطة بالحساب'
                : 'Delete this conversation for everyone',
            cancelLabel: rtl ? 'إلغاء' : 'Cancel',
            destructive: true,
          ),
          brightness: brightness,
          direction: direction,
        );
        await tester.tap(find.text('Open'));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/overlay_dialog_wrapped_$variant.png'),
        );
      });
    });

    testWidgets('overlay popover menu $variant', (tester) async {
      await withRealShadows(() async {
        await _pumpHost(
          tester,
          (_) {},
          brightness: brightness,
          direction: direction,
        );
        await tester.longPress(find.text('Long-press me'));
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/overlay_popover_$variant.png'),
        );
      });
    });

    testWidgets('overlay toast $variant', (tester) async {
      await withRealShadows(() async {
        await _pumpHost(
          tester,
          (context) => LnToast.show(
            context,
            'Alert saved',
            kind: LnToastKind.positive,
            action: ('Undo', () {}),
          ),
          brightness: brightness,
          direction: direction,
        );
        await tester.tap(find.text('Open'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 600));
        expect(find.text('Alert saved'), findsOneWidget);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/overlay_toast_$variant.png'),
        );
        // Let the toast time out so no timers are pending.
        await tester.pump(const Duration(seconds: 3));
        await tester.pumpAndSettle();
      });
    });
  }

  testWidgets('a toast left in a disposed tree does not break the next one', (
    tester,
  ) async {
    Future<void> showIn(String text) async {
      await _pumpHost(tester, (context) => LnToast.show(context, text));
      await tester.tap(find.text('Open'));
      await tester.pump(const Duration(milliseconds: 600));
      expect(find.text(text), findsOneWidget);
    }

    await showIn('First');
    // The tree (and its toaster) goes away while the toast still shows.
    await tester.pumpWidget(const SizedBox.shrink());
    await showIn('Second');
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  });

  testWidgets('an older toast finishing its exit keeps the newer one tracked', (
    tester,
  ) async {
    // Frame by frame, as a device draws them (one long pump is a single first tick).
    Future<void> frames(int ms) async {
      for (var t = 0; t < ms; t += 16) {
        await tester.pump(const Duration(milliseconds: 16));
      }
    }

    var n = 0;
    await _pumpHost(tester, (context) => LnToast.show(context, 'Toast ${++n}'));
    await tester.tap(find.text('Open'));
    await frames(500);
    await tester.tap(find.text('Open'));
    // Toast 1 finishes its exit; toast 2 stays current.
    await frames(900);
    await tester.tap(find.text('Open'));
    await frames(900);
    expect(find.text('Toast 3'), findsOneWidget);
    expect(find.text('Toast 2'), findsNothing);
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  });

  testWidgets('action menu returns the chosen value', (tester) async {
    String? chosen;
    await _pumpHost(tester, (context) async {
      chosen = await showLnActionMenu<String>(
        context,
        actions: const [
          LnMenuAction(label: 'Pin', value: 'pin'),
          LnMenuAction(label: 'Delete', value: 'delete', destructive: true),
        ],
      );
    });
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(chosen, 'delete');
  });

  testWidgets('confirm completes with true / false', (tester) async {
    bool? result;
    await _pumpHost(tester, (context) async {
      result = await showLnConfirm(
        context,
        title: 'Sure?',
        confirmLabel: 'Yes',
        cancelLabel: 'No',
      );
    });
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Yes'));
    await tester.pumpAndSettle();
    expect(result, isTrue);
  });

  testWidgets('composer trailing control follows text and running state', (
    tester,
  ) async {
    final controller = TextEditingController();
    String? sent;
    var running = false;
    late StateSetter setOuter;
    setGoldenViewport(tester);
    await tester.pumpWidget(
      lnTestApp(
        child: Center(
          child: StatefulBuilder(
            builder: (context, setState) {
              setOuter = setState;
              return Composer(
                controller: controller,
                placeholder: 'Message',
                running: running,
                onMic: () {},
                onStop: () {},
                onSend: (text) => sent = text,
              );
            },
          ),
        ),
      ),
    );
    expect(find.bySemanticsLabel('Voice input'), findsOneWidget);

    controller.text = '  hello  ';
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Send'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Send'));
    expect(sent, 'hello');

    controller.clear();
    setOuter(() => running = true);
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Stop'), findsOneWidget);
    controller.dispose();
  });

  testWidgets('tab bar reports taps and exposes selection semantics', (
    tester,
  ) async {
    var selected = 0;
    setGoldenViewport(tester);
    await tester.pumpWidget(
      lnTestApp(
        child: StatefulBuilder(
          builder: (context, setState) => Align(
            alignment: Alignment.bottomCenter,
            child: FloatingTabBar(
              items: const [
                LnTabItem(icon: LnGlyph(LnGlyphs.chats), label: 'Chats'),
                LnTabItem(icon: LnGlyph(LnGlyphs.market), label: 'Market'),
                LnTabItem(icon: LnGlyph(LnGlyphs.me), label: 'Me'),
              ],
              selectedIndex: selected,
              onSelect: (i) => setState(() => selected = i),
              actionIcon: const LnGlyph(LnGlyphs.attention),
              actionLabel: 'Attention',
              onAction: () {},
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('Market'));
    await tester.pumpAndSettle();
    expect(selected, 1);
    expect(
      tester.getSemantics(find.bySemanticsLabel('Market')),
      isSemantics(isSelected: true),
    );
    // K10: the labelled node is the button itself, with its tap and focus actions.
    final handle = tester.ensureSemantics();
    final me = find.semantics.byLabel('Me');
    expect(
      me.evaluate().single.getSemanticsData(),
      isSemantics(
        label: 'Me',
        hint: 'Tab 3 of 3',
        isButton: true,
        isFocusable: true,
        hasSelectedState: true,
        isInMutuallyExclusiveGroup: true,
        hasEnabledState: true,
        isEnabled: true,
        hasTapAction: true,
        hasFocusAction: true,
      ),
    );
    tester.semantics.tap(me);
    await tester.pumpAndSettle();
    expect(selected, 2);
    expect(
      find.semantics.byLabel('Me').evaluate().single.getSemanticsData(),
      isSemantics(
        label: 'Me',
        hint: 'Tab 3 of 3',
        isButton: true,
        isFocusable: true,
        hasSelectedState: true,
        isSelected: true,
        isInMutuallyExclusiveGroup: true,
        hasEnabledState: true,
        isEnabled: true,
        hasTapAction: true,
        hasFocusAction: true,
      ),
    );
    // No unlabelled button is left beside the tabs.
    for (final button
        in find.semantics.byFlag(SemanticsFlag.isButton).evaluate()) {
      expect(button.label, isNotEmpty);
    }
    handle.dispose();
  });

  testWidgets('the tab position hint is in the interface language', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    setGoldenViewport(tester);
    await tester.pumpWidget(
      lnTestApp(
        direction: TextDirection.rtl,
        child: Builder(
          builder: (context) => Localizations.override(
            context: context,
            locale: const Locale('ar'),
            delegates: GlobalMaterialLocalizations.delegates,
            child: Align(
              alignment: Alignment.bottomCenter,
              child: FloatingTabBar(
                items: const [
                  LnTabItem(icon: LnGlyph(LnGlyphs.chats), label: 'المحادثات'),
                  LnTabItem(icon: LnGlyph(LnGlyphs.me), label: 'أنا'),
                ],
                selectedIndex: 0,
                onSelect: (_) {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.semantics.byLabel('أنا').evaluate().single.hint,
      startsWith('علامة التبويب'),
    );
    expect(find.semantics.byHint(RegExp('Tab')), findsNothing);
    handle.dispose();
  });
}
