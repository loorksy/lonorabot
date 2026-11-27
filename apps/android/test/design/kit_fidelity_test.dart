// Kit round 4: the look of the conversation, the header chrome, the grouped settings cards,
// the popover menus and the stacked full-height sheet. Layout values, RTL, semantics,
// interactions and text contrast, plus goldens (light/dark, Arabic/English).
//
// Regenerate with: flutter test --update-goldens test/design/kit_fidelity_test.dart
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/design/design.dart';

import 'fonts.dart';
import 'harness.dart';

Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  TextDirection direction = TextDirection.ltr,
  Brightness brightness = Brightness.light,
  Size size = goldenSize,
}) async {
  setGoldenViewport(tester, size: size);
  await tester.pumpWidget(
    lnTestApp(
      child: child,
      direction: direction,
      brightness: brightness,
      padding: const EdgeInsets.only(top: 24),
    ),
  );
  await tester.pump();
}

/// The box decoration painted by the nearest [Container]/[DecoratedBox] above [finder].
BoxDecoration _decorationOf(WidgetTester tester, Finder finder) {
  final box = tester.widget<DecoratedBox>(
    find.ancestor(of: finder, matching: find.byType(DecoratedBox)).first,
  );
  return box.decoration as BoxDecoration;
}

String _t(BuildContext context, String en, String ar) =>
    Directionality.of(context) == TextDirection.rtl ? ar : en;

void main() {
  setUpAll(loadAppFonts);

  group('tokens', () {
    test('agent bubble ink is white in dark; light keeps the warm ink', () {
      expect(LnPalette.dark.onAgentBubble, const Color(0xFFFFFFFF));
      expect(LnPalette.dark.onAgentBubble, LnPalette.dark.onUserBubble);
      expect(LnPalette.light.onAgentBubble, LnPalette.light.fgWarm);
    });

    test('chrome: #353535 circles in dark, a faint dark shadow', () {
      expect(LnPalette.dark.chromeCircle, const Color(0xFF353535));
      expect(LnPalette.light.chromeCircle, LnPalette.light.surface);
      for (final shadow in LnShadow.darkChrome) {
        expect(shadow.color.a, lessThanOrEqualTo(0.08));
      }
      expect(LnThemeData.dark.chromeRim, BorderSide.none);
      expect(LnThemeData.light.chromeRim.color, LnPalette.light.border);
    });

    test('rhythm, radii and sizes', () {
      expect(BubbleGroup.gap(sameSender: true, bubbleRun: true), 4);
      expect(BubbleGroup.gap(sameSender: true), 7);
      expect(BubbleGroup.gap(sameSender: false, bubbleRun: true), 16);
      expect(LnSpace.composerToBar, 8);
      expect(LnRadius.group, LnSize.tileRow / 2);
      expect(MessageBubble.maxWidthFor(384), moreOrLessEquals(299.52));
      expect(MessageBubble.maxWidthFor(430), LnSize.bubbleMaxWidth);
      expect(LnPalette.dark.sheetPage, const Color(0xFF171717));
      expect(LnPalette.dark.editorCard, const Color(0xFF252525));
    });
  });

  group('MessageBubble', () {
    Future<void> pumpBubbles(
      WidgetTester tester,
      List<Widget> bubbles, {
      TextDirection direction = TextDirection.ltr,
      Brightness brightness = Brightness.light,
    }) => _pump(
      tester,
      Align(
        alignment: AlignmentDirectional.topStart,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: bubbles,
        ),
      ),
      direction: direction,
      brightness: brightness,
    );

    Rect bubbleRect(WidgetTester tester, String text) => tester.getRect(
      find
          .ancestor(of: find.text(text), matching: find.byType(Container))
          .first,
    );

    testWidgets('n lines are n·24 + 18.75 dp; one line keeps the 44 dp floor', (
      tester,
    ) async {
      const two = 'Two lines of text in the bubble here';
      const four = 'Four lines of text that wrap again and again inside it';
      await pumpBubbles(tester, [
        const MessageBubble.agent('Hi'),
        const MessageBubble(
          sender: BubbleSender.agent,
          text: two,
          maxWidth: 200,
        ),
        const MessageBubble(
          sender: BubbleSender.user,
          text: four,
          maxWidth: 140,
        ),
      ]);
      expect(bubbleRect(tester, 'Hi').height, 44);
      // Lines of the text box: 24 each, ≈5.25 dp less for the first ascent and last descent
      // (the engine rounds those two line boxes: n·24 − 6 in Roboto).
      int lines(String text) =>
          ((tester.getSize(find.text(text)).height + 5.25) / 24).round();
      expect(lines(two), 2);
      expect(
        bubbleRect(tester, two).height,
        moreOrLessEquals(2 * 24 + 18.75, epsilon: 1),
      );
      expect(lines(four), greaterThanOrEqualTo(3));
      expect(
        bubbleRect(tester, four).height,
        moreOrLessEquals(lines(four) * 24 + 18.75, epsilon: 1),
      );
      // Each further line adds exactly 24.
      expect(
        bubbleRect(tester, four).height - bubbleRect(tester, two).height,
        (lines(four) - 2) * 24,
      );
      // The 16 × 12 padding stays.
      expect(
        tester.getRect(find.text(two)).top - bubbleRect(tester, two).top,
        12,
      );
    });

    testWidgets('the ink is white on both bubbles in dark', (tester) async {
      await pumpBubbles(tester, [
        const MessageBubble.agent('Agent'),
        const MessageBubble.user('Owner'),
      ], brightness: Brightness.dark);
      for (final text in ['Agent', 'Owner']) {
        final style = tester.renderObject<RenderParagraph>(find.text(text));
        expect(style.text.style!.color, const Color(0xFFFFFFFF));
      }
    });

    testWidgets('a wrapped bubble is 78 % of a 384 dp screen', (tester) async {
      setGoldenViewport(tester, size: const Size(384, 832));
      await tester.pumpWidget(
        lnTestApp(
          child: const Align(
            alignment: AlignmentDirectional.topStart,
            child: MessageBubble.agent(
              'A long message that certainly wraps onto a second line of text',
            ),
          ),
        ),
      );
      final rect = tester.getRect(find.byType(Container).first);
      expect(rect.width, moreOrLessEquals(384 * 0.78));
    });

    for (final direction in TextDirection.values) {
      testWidgets('a run joins its corners on the sender side '
          '(${direction.name})', (tester) async {
        await pumpBubbles(tester, [
          const MessageBubble.agent('First', joinBottom: true),
          const MessageBubble.agent('Middle', joinTop: true, joinBottom: true),
          const MessageBubble.user('Mine', joinTop: true),
        ], direction: direction);
        BorderRadius radius(String text) =>
            (_decorationOf(tester, find.text(text)).borderRadius!
                    as BorderRadiusDirectional)
                .resolve(direction);
        const full = Radius.circular(24);
        const joined = Radius.circular(5);
        final rtl = direction == TextDirection.rtl;
        // Agent: the start side (left in LTR, right in RTL).
        final first = radius('First');
        expect(rtl ? first.bottomRight : first.bottomLeft, joined);
        expect(rtl ? first.topRight : first.topLeft, full);
        expect(rtl ? first.bottomLeft : first.bottomRight, full);
        final middle = radius('Middle');
        expect(rtl ? middle.topRight : middle.topLeft, joined);
        expect(rtl ? middle.bottomRight : middle.bottomLeft, joined);
        // Owner: the end side.
        final mine = radius('Mine');
        expect(rtl ? mine.topLeft : mine.topRight, joined);
        expect(rtl ? mine.bottomLeft : mine.bottomRight, full);
        expect(rtl ? mine.topRight : mine.topLeft, full);
      });
    }

    for (final direction in TextDirection.values) {
      testWidgets('swipe toward the end side past 64 dp replies '
          '(${direction.name})', (tester) async {
        var replies = 0;
        await pumpBubbles(tester, [
          Padding(
            padding: const EdgeInsetsDirectional.only(start: 16),
            child: MessageBubble.agent(
              'Swipe me',
              onSwipeReply: () => replies++,
              replyLabel: 'Reply',
            ),
          ),
        ], direction: direction);
        final toEnd = direction == TextDirection.ltr ? 1.0 : -1.0;
        final start = tester.getRect(find.text('Swipe me'));

        // Short of the threshold: springs back without replying.
        final short = await tester.startGesture(start.center);
        for (var i = 0; i < 5; i++) {
          await short.moveBy(Offset(10 * toEnd, 0));
          await tester.pump();
        }
        expect(find.byIcon(LnIcons.reply), findsOneWidget);
        await short.up();
        await tester.pumpAndSettle();
        expect(replies, 0);
        expect(tester.getRect(find.text('Swipe me')), start);
        expect(find.byIcon(LnIcons.reply), findsNothing);

        // Past it: the bubble follows, the arrow shows at the start, release replies.
        final long = await tester.startGesture(start.center);
        for (var i = 0; i < 8; i++) {
          await long.moveBy(Offset(10 * toEnd, 0));
          await tester.pump();
        }
        final moved = tester.getRect(find.text('Swipe me'));
        expect((moved.left - start.left) * toEnd, greaterThan(64));
        final arrow = tester.getRect(find.byIcon(LnIcons.reply));
        expect(arrow.size, const Size.square(24));
        expect(
          direction == TextDirection.ltr
              ? arrow.left < moved.left
              : arrow.right > moved.right,
          isTrue,
        );
        await long.up();
        await tester.pumpAndSettle();
        expect(replies, 1);
        expect(tester.getRect(find.text('Swipe me')), start);
      });
    }

    testWidgets('a drag toward the start side does nothing', (tester) async {
      var replies = 0;
      await pumpBubbles(tester, [
        MessageBubble.agent('Back', onSwipeReply: () => replies++),
      ]);
      final start = tester.getRect(find.text('Back'));
      await tester.drag(find.text('Back'), const Offset(-120, 0));
      await tester.pumpAndSettle();
      expect(replies, 0);
      expect(tester.getRect(find.text('Back')), start);
    });

    testWidgets('screen readers reply through a custom action', (tester) async {
      final handle = tester.ensureSemantics();
      var replies = 0;
      await pumpBubbles(tester, [
        MessageBubble.agent(
          'Read me',
          onSwipeReply: () => replies++,
          replyLabel: 'رد',
        ),
      ]);
      final node = tester.getSemantics(find.text('Read me'));
      final data = node.getSemanticsData();
      final ids = data.customSemanticsActionIds!;
      expect(ids, hasLength(1));
      expect(CustomSemanticsAction.getAction(ids.single)!.label, 'رد');
      node.owner!.performAction(
        node.id,
        SemanticsAction.customAction,
        ids.single,
      );
      await tester.pump();
      expect(replies, 1);
      handle.dispose();
    });
  });

  group('DateSeparator', () {
    for (final palette in [LnPalette.light, LnPalette.dark]) {
      testWidgets('13/18 regular in the secondary ink '
          '(${palette.brightness.name})', (tester) async {
        await _pump(
          tester,
          const DateSeparator(label: '٨:٥٦ ص'),
          brightness: palette.brightness,
          direction: TextDirection.rtl,
        );
        final style = tester
            .renderObject<RenderParagraph>(find.text('٨:٥٦ ص'))
            .text
            .style!;
        expect(style.fontSize, 13);
        expect(style.height! * style.fontSize!, moreOrLessEquals(18));
        expect(style.fontWeight, FontWeight.w400);
        expect(style.color, palette.fgMuted);
        final semantics = tester.getSemantics(find.text('٨:٥٦ ص'));
        expect(semantics.flagsCollection.isHeader, isTrue);
      });
    }
  });

  // WCAG AA: 4.5:1 for text under 18 dp. The pairs are checked by value: the separator footnote
  // and the menu's time header in the secondary ink on the canvas and the menu surface, white on
  // the filled selection pill and count disc. textContrastGuideline reads the rendered page at
  // one pixel per dp, where 12–13 dp glyphs are mostly anti-aliased edges, so it is run on the
  // 16 dp labels on fills only.
  group('text contrast', () {
    double ratio(Color a, Color b) {
      final la = a.computeLuminance();
      final lb = b.computeLuminance();
      return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
    }

    for (final p in [LnPalette.light, LnPalette.dark]) {
      test('the pairs by value (${p.brightness.name})', () {
        final muted = Color.alphaBlend(p.fgMuted, p.bg);
        expect(ratio(muted, p.bg), greaterThanOrEqualTo(4.5));
        final onMenu = Color.alphaBlend(p.fgMuted, p.menuSurface);
        expect(ratio(onMenu, p.menuSurface), greaterThanOrEqualTo(4.5));
        expect(ratio(p.onAccent, p.selectionFill), greaterThanOrEqualTo(4.5));
      });

      testWidgets('white on the filled pill and the count disc '
          '(${p.brightness.name})', (tester) async {
        final handle = tester.ensureSemantics();
        await _pump(
          tester,
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              HeaderPillButton(label: 'Create', onPressed: () {}),
              const MenuPillButton(semanticLabel: 'Chats', unreadCount: 8),
            ],
          ),
          brightness: p.brightness,
        );
        await tester.pumpAndSettle();
        await expectLater(tester, meetsGuideline(textContrastGuideline));
        handle.dispose();
      });
    }

    testWidgets('the separator and the menu header use the secondary ink', (
      tester,
    ) async {
      await _pump(
        tester,
        const Column(
          children: [
            DateSeparator(label: '8:56 AM'),
            SizedBox(
              width: 250,
              child: LnMenuCard(
                header: 'Today, 08:56',
                children: [LnMenuRow(label: 'Reply')],
              ),
            ),
          ],
        ),
      );
      Color ink(String text) => tester
          .renderObject<RenderParagraph>(find.text(text))
          .text
          .style!
          .color!;
      expect(ink('8:56 AM'), LnPalette.light.fgMuted);
      expect(ink('Today, 08:56'), LnPalette.light.fgMuted);
    });
  });

  group('header chrome', () {
    for (final palette in [LnPalette.light, LnPalette.dark]) {
      testWidgets('CircleIconButton: Ø44 chrome circle in a 48 dp target '
          '(${palette.brightness.name})', (tester) async {
        final handle = tester.ensureSemantics();
        var taps = 0;
        await _pump(
          tester,
          Center(
            child: CircleIconButton(
              icon: const Icon(FIcons.phone),
              semanticLabel: 'Call',
              onTap: () => taps++,
            ),
          ),
          brightness: palette.brightness,
        );
        final circle = find.descendant(
          of: find.byType(CircleIconButton),
          matching: find.byType(Container),
        );
        expect(tester.getSize(circle), const Size.square(44));
        expect(
          tester.getSize(find.byType(CircleIconButton)),
          const Size.square(48),
        );
        final decoration =
            tester.widget<Container>(circle).decoration! as BoxDecoration;
        expect(decoration.color, palette.chromeCircle);
        final border = decoration.border! as Border;
        if (palette.isDark) {
          expect(border.top, BorderSide.none);
        } else {
          expect(border.top.color, palette.border);
          expect(decoration.boxShadow, LnShadow.chrome);
        }
        final node = find.semantics.byLabel('Call');
        expect(
          node.evaluate().single.getSemanticsData(),
          isSemantics(
            label: 'Call',
            isButton: true,
            hasTapAction: true,
            hasFocusAction: true,
            isFocusable: true,
          ),
        );
        tester.semantics.tap(node);
        await tester.tap(find.byType(CircleIconButton));
        await tester.pumpAndSettle();
        expect(taps, 2);
        handle.dispose();
      });
    }

    for (final direction in TextDirection.values) {
      testWidgets('TitleCapsule: 31 dp pill, 16 dp title, chevron 8 dp after '
          '(dark, ${direction.name})', (tester) async {
        await _pump(
          tester,
          Center(
            child: TitleCapsule(
              avatar: const FakeAvatar(FakeShape.circle, FakeAvatar.violet),
              title: 'Atlas',
              onTap: () {},
            ),
          ),
          brightness: Brightness.dark,
          direction: direction,
        );
        final pill = find.descendant(
          of: find.byType(TitleCapsule),
          matching: find.byType(Container),
        );
        expect(tester.getSize(pill).height, 31);
        expect(TitleCapsule.height, 39.5 + 31);
        final decoration =
            tester.widget<Container>(pill).decoration! as ShapeDecoration;
        expect(decoration.color, LnPalette.dark.chromeCircle);
        expect((decoration.shape as StadiumBorder).side, BorderSide.none);
        final style = tester
            .renderObject<RenderParagraph>(find.text('Atlas'))
            .text
            .style!;
        expect(style.color, LnPalette.dark.fg);
        expect(style.fontSize, 16);
        expect(style.fontWeight, FontWeight.w500);
        final name = tester.getRect(find.text('Atlas'));
        final chevron = tester.getRect(find.byType(NarrowChevron));
        expect(chevron.size, const Size(5, 10));
        final gap = direction == TextDirection.ltr
            ? chevron.left - name.right
            : name.left - chevron.right;
        expect(gap, moreOrLessEquals(8, epsilon: 0.01));
      });
    }

    testWidgets('JumpToLatestButton: Ø36 menu-fill circle in dark', (
      tester,
    ) async {
      await _pump(
        tester,
        Center(child: JumpToLatestButton(visible: true, onTap: () {})),
        brightness: Brightness.dark,
      );
      final circle = find.descendant(
        of: find.byType(JumpToLatestButton),
        matching: find.byType(Container),
      );
      expect(tester.getSize(circle), const Size.square(36));
      final decoration =
          tester.widget<Container>(circle).decoration! as BoxDecoration;
      expect(decoration.color, LnPalette.dark.menuSurface);
      expect(decoration.boxShadow, isNull);
      expect((decoration.border! as Border).top, BorderSide.none);
      final icon = tester.widget<Icon>(find.byIcon(FIcons.arrowDown));
      expect(icon.color, LnPalette.dark.fgWarm);
      expect(icon.size, 20);
    });
  });

  group('grouped settings cards', () {
    Widget card(BuildContext context) => ListView(
      padding: const EdgeInsets.only(top: 40),
      children: [
        LnSection(
          key: const ValueKey('group'),
          title: _t(context, 'Preferences', 'التفضيلات'),
          footer: _t(context, 'Applies everywhere.', 'ينطبق في كل مكان.'),
          children: [
            LnListTile(
              key: const ValueKey('language'),
              icon: FIcons.globe,
              title: _t(context, 'Language', 'اللغة'),
              value: _t(context, 'English', 'العربية'),
              onTap: () {},
            ),
            LnListTile(
              key: const ValueKey('appearance'),
              icon: FIcons.moon,
              title: _t(context, 'Appearance', 'المظهر'),
              value: _t(context, 'System', 'حسب النظام'),
              picker: true,
              onTap: () {},
            ),
            LnListTile(
              key: const ValueKey('web'),
              icon: FIcons.globe,
              title: _t(context, 'Open on the web', 'افتح على الويب'),
              external: true,
              onTap: () {},
            ),
          ],
        ),
        const SizedBox(height: LnSpace.xxl),
        LnSection(
          key: const ValueKey('single'),
          children: [
            LnListTile(
              key: const ValueKey('signOut'),
              icon: LnIcons.logOut,
              title: _t(context, 'Sign out', 'تسجيل الخروج'),
              destructive: true,
              onTap: () {},
            ),
          ],
        ),
      ],
    );

    Rect rowRect(WidgetTester tester, String key) => tester.getRect(
      find
          .descendant(
            of: find.byKey(ValueKey(key)),
            matching: find.byWidgetPredicate((w) => w is FTappable),
          )
          .first,
    );

    for (final direction in TextDirection.values) {
      testWidgets('card, rows, icons and trailing glyphs (${direction.name})', (
        tester,
      ) async {
        await _pump(
          tester,
          Builder(builder: card),
          direction: direction,
          brightness: Brightness.dark,
        );
        final ltr = direction == TextDirection.ltr;
        // The card: 6 % fill, radius 26, no border.
        final group = tester.widget<Container>(
          find
              .descendant(
                of: find.byKey(const ValueKey('group')),
                matching: find.byType(Container),
              )
              .first,
        );
        final decoration = group.decoration! as BoxDecoration;
        expect(decoration.color, LnPalette.dark.fill3);
        expect(
          decoration.borderRadius,
          const BorderRadius.all(Radius.circular(26)),
        );
        expect(decoration.border, isNull);

        // 52 dp rows in both scripts.
        for (final key in ['language', 'appearance', 'web', 'signOut']) {
          expect(rowRect(tester, key).height, LnSize.tileRow, reason: key);
        }
        final row = rowRect(tester, 'language');
        // 20 dp icon 16 dp from the card's start; title 12 dp after it (48 dp in).
        final icon = tester.getRect(
          find.descendant(
            of: find.byKey(const ValueKey('language')),
            matching: find.byIcon(FIcons.globe),
          ),
        );
        expect(icon.size, const Size.square(20));
        expect(ltr ? icon.left - row.left : row.right - icon.right, 16);
        final title = tester.getRect(find.text(ltr ? 'Language' : 'اللغة'));
        expect(ltr ? title.left - row.left : row.right - title.right, 48);
        expect(title.center.dy, moreOrLessEquals(row.center.dy, epsilon: 0.5));
        // Value, 12 dp, then a 20 dp chevron 16 dp from the card's end.
        final chevron = tester.getRect(
          find.descendant(
            of: find.byKey(const ValueKey('language')),
            matching: find.byIcon(FIcons.chevronRight),
          ),
        );
        expect(chevron.size, const Size.square(20));
        expect(ltr ? row.right - chevron.right : chevron.left - row.left, 16);
        final value = tester.getRect(find.text(ltr ? 'English' : 'العربية'));
        expect(
          ltr ? chevron.left - value.right : value.left - chevron.right,
          moreOrLessEquals(12, epsilon: 0.5),
        );
        final chevronIcon = tester.widget<Icon>(
          find.descendant(
            of: find.byKey(const ValueKey('language')),
            matching: find.byIcon(FIcons.chevronRight),
          ),
        );
        expect(
          IconTheme.of(tester.element(find.byWidget(chevronIcon))).color,
          LnPalette.dark.fgMuted,
        );

        // In-place choice: up-down chevrons; leaving the app: an up-right arrow that does not
        // mirror.
        expect(
          find.descendant(
            of: find.byKey(const ValueKey('appearance')),
            matching: find.byIcon(FIcons.chevronsUpDown),
          ),
          findsOneWidget,
        );
        expect(FIcons.arrowUpRight.matchTextDirection, isFalse);
        expect(
          find.descendant(
            of: find.byKey(const ValueKey('web')),
            matching: find.byIcon(FIcons.arrowUpRight),
          ),
          findsOneWidget,
        );
        expect(
          find.descendant(
            of: find.byKey(const ValueKey('web')),
            matching: find.byIcon(FIcons.chevronRight),
          ),
          findsNothing,
        );

        // Destructive rows are text only, in the error colour; a one-row card is a stadium.
        expect(find.byIcon(LnIcons.logOut), findsNothing);
        final signOut = tester
            .renderObject<RenderParagraph>(
              find.text(ltr ? 'Sign out' : 'تسجيل الخروج'),
            )
            .text
            .style!;
        expect(signOut.color, LnPalette.dark.error);
        expect(rowRect(tester, 'signOut').height, LnRadius.group * 2);

        // Section label: caption in the secondary ink, 16 dp in, 8 dp above the card.
        final label = find.text(ltr ? 'Preferences' : 'التفضيلات');
        final labelStyle = tester
            .renderObject<RenderParagraph>(label)
            .text
            .style!;
        expect(labelStyle.fontSize, 14);
        expect(labelStyle.fontWeight ?? FontWeight.w400, FontWeight.w400);
        expect(labelStyle.color, LnPalette.dark.fgMuted);
        final labelRect = tester.getRect(label);
        expect(
          ltr ? labelRect.left - row.left : row.right - labelRect.right,
          16,
        );
        final cardTop = tester
            .getRect(
              find
                  .descendant(
                    of: find.byKey(const ValueKey('group')),
                    matching: find.byType(Container),
                  )
                  .first,
            )
            .top;
        expect(cardTop - labelRect.bottom, moreOrLessEquals(8, epsilon: 1));
        // Note: a footnote in the secondary ink, 16 dp in.
        final note = find.text(
          ltr ? 'Applies everywhere.' : 'ينطبق في كل مكان.',
        );
        final noteStyle = tester
            .renderObject<RenderParagraph>(note)
            .text
            .style!;
        expect(noteStyle.fontSize, 13);
        expect(noteStyle.color, LnPalette.dark.fgMuted);
        final noteRect = tester.getRect(note);
        expect(ltr ? noteRect.left - row.left : row.right - noteRect.right, 16);
      });
    }

    testWidgets('rows read as buttons with their title and value', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await _pump(tester, Builder(builder: card));
      final row = find.semantics.byLabel(RegExp('^Language'));
      final data = row.evaluate().single.getSemanticsData();
      expect(data.label, contains('English'));
      expect(
        data,
        isSemantics(isButton: true, hasTapAction: true, hasFocusAction: true),
      );
      handle.dispose();
    });

    testWidgets('flat: rows on the page, 24 dp icons, a muted body label', (
      tester,
    ) async {
      await _pump(
        tester,
        ListView(
          children: [
            LnSection(
              key: const ValueKey('flat'),
              title: 'Settings',
              flat: true,
              children: [
                LnListTile(
                  key: const ValueKey('memory'),
                  icon: FIcons.brain,
                  title: 'Memory',
                  onTap: () {},
                ),
                LnListTile(
                  icon: FIcons.fileText,
                  title: 'Instructions',
                  onTap: () {},
                ),
              ],
            ),
          ],
        ),
        brightness: Brightness.dark,
      );
      final group = tester.widget<Container>(
        find
            .descendant(
              of: find.byKey(const ValueKey('flat')),
              matching: find.byType(Container),
            )
            .first,
      );
      expect((group.decoration! as BoxDecoration).color, isNull);
      final label = tester
          .renderObject<RenderParagraph>(find.text('Settings'))
          .text
          .style!;
      expect(label.fontSize, 16);
      expect(label.fontWeight ?? FontWeight.w400, FontWeight.w400);
      expect(label.color, LnPalette.dark.fgMuted);
      final icon = tester.getRect(find.byIcon(FIcons.brain));
      expect(icon.size, const Size.square(24));
      // At the page gutter.
      expect(icon.left, 16);
      expect(rowRect(tester, 'memory').height, LnSize.tileRow);
    });
  });

  group('popover menu', () {
    testWidgets(
      'the menu card: surface, radius 12, 48 dp rows with 24 dp icons '
      'in the warm ink, as LnMenuCard',
      (tester) async {
        await _pump(
          tester,
          Align(
            alignment: Alignment.topCenter,
            child: LnPopoverMenu<String>(
              openOnTap: true,
              semanticLabel: 'Create',
              actions: const [
                LnMenuAction(label: 'New agent', icon: FIcons.bot, value: 'a'),
                LnMenuAction(
                  label: 'New group',
                  icon: FIcons.users,
                  value: 'g',
                ),
              ],
              child: const SizedBox.square(dimension: 48),
            ),
          ),
          brightness: Brightness.dark,
        );
        await tester.tap(find.byType(LnPopoverMenu<String>));
        await tester.pumpAndSettle();
        final theme = FTheme.of(tester.element(find.text('New agent')));
        final decoration = theme.popoverMenuStyle.decoration;
        expect(decoration.color, LnPalette.dark.menuSurface);
        expect(
          decoration.borderRadius,
          const BorderRadius.all(Radius.circular(LnRadius.menu)),
        );
        expect(
          (decoration.border! as Border).top.color,
          LnPalette.dark.menuBorder,
        );
        expect(decoration.boxShadow, isNull, reason: 'no shadow in dark');
        final first = tester.getRect(find.text('New agent'));
        final second = tester.getRect(find.text('New group'));
        expect(second.top - first.top, LnSize.menuRow);
        final style = tester
            .renderObject<RenderParagraph>(find.text('New agent'))
            .text
            .style!;
        expect(style.color, LnPalette.dark.fgWarm);
        final icon = tester.getRect(find.byIcon(FIcons.bot));
        expect(icon.size, const Size.square(LnSize.menuIcon));
        expect(icon.center.dy, closeTo(first.center.dy, 0.5));
        // 6 dp above the first row and below the last, as in LnMenuCard.
        expect(
          theme.popoverMenuStyle.itemGroupStyle.spacing,
          LnMenuCard.verticalPadding,
        );
      },
    );

    testWidgets('light: the menu shadow, as LnMenuCard', (tester) async {
      await _pump(tester, const SizedBox());
      final theme = FTheme.of(tester.element(find.byType(SizedBox).first));
      expect(theme.popoverMenuStyle.decoration.boxShadow, LnShadow.menu);
      final card = await () async {
        await _pump(
          tester,
          const LnMenuCard(children: [LnMenuRow(label: 'Reply')]),
        );
        return tester.widget<DecoratedBox>(
          find
              .descendant(
                of: find.byType(LnMenuCard),
                matching: find.byType(DecoratedBox),
              )
              .first,
        );
      }();
      expect((card.decoration as ShapeDecoration).shadows, LnShadow.menu);
    });
  });

  group('stacked sheet', () {
    Widget host({bool showHandle = false, void Function(Object?)? onResult}) =>
        Builder(
          builder: (context) => Column(
            children: [
              const SizedBox(height: 80),
              Container(
                key: const ValueKey('page'),
                height: 200,
                color: context.ln.colors.fill3,
              ),
              Builder(
                builder: (context) => BlockButton(
                  label: 'Open',
                  expand: false,
                  onPressed: () async {
                    final result = await showLnStackedSheet<String>(
                      context,
                      showHandle: showHandle,
                      builder: (context) => Column(
                        children: [
                          LnSheetHeader(
                            title: _t(context, 'New group', 'مجموعة جديدة'),
                            closeLabel: _t(context, 'Close', 'إغلاق'),
                            action: HeaderPillButton(
                              label: _t(context, 'Create', 'إنشاء'),
                              onPressed: () =>
                                  Navigator.of(context).pop('created'),
                            ),
                          ),
                          Expanded(
                            child: ListView(
                              key: const ValueKey('body'),
                              controller: LnStackedSheet.scrollControllerOf(
                                context,
                              ),
                              children: const [SizedBox(height: 800)],
                            ),
                          ),
                        ],
                      ),
                    );
                    onResult?.call(result);
                  },
                ),
              ),
            ],
          ),
        );

    Future<void> open(WidgetTester tester) async {
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
    }

    for (final direction in TextDirection.values) {
      testWidgets('rises to 8 % from the top over the scaled page '
          '(${direction.name})', (tester) async {
        await _pump(
          tester,
          host(showHandle: true),
          brightness: Brightness.dark,
          direction: direction,
        );
        final before = tester.getRect(find.byKey(const ValueKey('page')));
        await open(tester);
        // The sheet: 8 % of the screen below the top, the opaque sheet page.
        final sheet = tester.getRect(
          find
              .ancestor(
                of: find.byType(LnSheetHeader),
                matching: find.byType(ColoredBox),
              )
              .first,
        );
        expect(sheet.top, moreOrLessEquals(852 * 0.08, epsilon: 0.01));
        expect(sheet.width, 393);
        final fill = tester.widget<ColoredBox>(
          find
              .ancestor(
                of: find.byType(LnSheetHeader),
                matching: find.byType(ColoredBox),
              )
              .first,
        );
        expect(fill.color, LnPalette.dark.sheetPage);
        // The page behind: scaled to 0.904 about its top centre and moved 7 % down, on black.
        final after = tester.getRect(find.byKey(const ValueKey('page')));
        expect(
          after.width,
          moreOrLessEquals(before.width * LnStackedSheetRoute.coverScale),
        );
        expect(
          after.top,
          moreOrLessEquals(852 * 0.07 + before.top * 0.904, epsilon: 0.01),
        );
        expect(
          find.byWidgetPredicate(
            (w) => w is ColoredBox && w.color == const Color(0xFF000000),
          ),
          findsOneWidget,
        );
        // The handle: 36 × 4, 5 dp below the sheet's top.
        final handle = tester.getRect(
          find
              .descendant(
                of: find.byType(LnSheetHandle),
                matching: find.byType(Container),
              )
              .first,
        );
        expect(handle.size, const Size(36, 4));
        expect(handle.top - sheet.top, 5);
        // Header: ✕ circle at the start gutter, the pill at the end, the title centred, the
        // circles 38 dp below the sheet's top.
        final ltr = direction == TextDirection.ltr;
        final close = tester.getRect(
          find
              .descendant(
                of: find.byType(CircleIconButton),
                matching: find.byType(Container),
              )
              .first,
        );
        expect(close.size, const Size.square(44));
        expect(ltr ? close.left : 393 - close.right, 16);
        expect(close.center.dy - sheet.top, 38);
        final pill = tester.getRect(
          find
              .descendant(
                of: find.byType(HeaderPillButton),
                matching: find.byType(Container),
              )
              .first,
        );
        expect(pill.height, LnSize.headerPill);
        expect(ltr ? 393 - pill.right : pill.left, 16);
        expect(pill.center.dy, close.center.dy);
        final title = tester.getRect(
          find.text(ltr ? 'New group' : 'مجموعة جديدة'),
        );
        expect(title.center.dx, moreOrLessEquals(393 / 2, epsilon: 0.5));
        expect(
          tester.getSize(find.byType(HeaderPillButton)).height,
          LnSize.minTouch,
        );
      });
    }

    testWidgets('the pill pops with a value; the ✕ and back close', (
      tester,
    ) async {
      final results = <Object?>[];
      await _pump(tester, host(onResult: results.add));
      await open(tester);
      await tester.tap(find.text('Create'));
      await tester.pumpAndSettle();
      expect(results, ['created']);
      expect(find.byType(LnSheetHeader), findsNothing);

      await open(tester);
      await tester.tap(find.byType(CircleIconButton));
      await tester.pumpAndSettle();
      expect(results, ['created', null]);

      await open(tester);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(results, ['created', null, null]);
      expect(find.byType(LnSheetHeader), findsNothing);
    });

    testWidgets('a downward drag closes it, also from the scroll top', (
      tester,
    ) async {
      final results = <Object?>[];
      await _pump(tester, host(onResult: results.add));
      await open(tester);
      await tester.drag(find.byType(LnSheetHeader), const Offset(0, 500));
      await tester.pumpAndSettle();
      expect(find.byType(LnSheetHeader), findsNothing);
      expect(results, [null]);

      await open(tester);
      expect(
        LnStackedSheet.scrollControllerOf(
          tester.element(find.byKey(const ValueKey('body'))),
        ),
        isNotNull,
      );
      await tester.drag(
        find.byKey(const ValueKey('body')),
        const Offset(0, 500),
      );
      await tester.pumpAndSettle();
      expect(find.byType(LnSheetHeader), findsNothing);
    });

    testWidgets('header semantics: the title, the close button, the pill', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await _pump(
        tester,
        Column(
          children: [
            const LnSheetHeader(
              title: 'إنشاء دردشة جماعية',
              closeLabel: 'إغلاق',
              action: HeaderPillButton(label: 'إنشاء'),
            ),
            LnSheetHeader(
              title: 'تحديد النص',
              closeLabel: 'إغلاق النافذة',
              plainClose: true,
              onClose: () {},
            ),
          ],
        ),
        direction: TextDirection.rtl,
      );
      expect(
        tester.getSemantics(find.text('إنشاء دردشة جماعية')),
        matchesSemantics(label: 'إنشاء دردشة جماعية', isHeader: true),
      );
      SemanticsData data(String label) =>
          find.semantics.byLabel(label).evaluate().single.getSemanticsData();
      expect(
        data('إغلاق'),
        isSemantics(label: 'إغلاق', isButton: true, hasTapAction: true),
      );
      // Disabled pill: a button without a tap action.
      expect(
        data('إنشاء'),
        isSemantics(label: 'إنشاء', isButton: true, hasTapAction: false),
      );
      // The plain ✕: a 48 dp button with its label.
      final plain = find.ancestor(
        of: find.byIcon(FIcons.x).last,
        matching: find.byType(LnTappable),
      );
      expect(tester.getSize(plain), const Size.square(48));
      expect(
        data('إغلاق النافذة'),
        isSemantics(label: 'إغلاق النافذة', isButton: true, hasTapAction: true),
      );
      handle.dispose();
    });

    for (final palette in [LnPalette.light, LnPalette.dark]) {
      testWidgets('the pill: the deeper selection fill when enabled, 4 % fill '
          'when not '
          '(${palette.brightness.name})', (tester) async {
        await _pump(
          tester,
          Column(
            children: [
              HeaderPillButton(label: 'Create', onPressed: () {}),
              const HeaderPillButton(label: 'Wait'),
            ],
          ),
          brightness: palette.brightness,
        );
        ShapeDecoration fill(String label) =>
            tester
                    .widget<Container>(
                      find.ancestor(
                        of: find.text(label),
                        matching: find.byType(Container),
                      ),
                    )
                    .decoration!
                as ShapeDecoration;
        Color ink(String label) => tester
            .renderObject<RenderParagraph>(find.text(label))
            .text
            .style!
            .color!;
        expect(fill('Create').color, palette.selectionFill);
        expect(ink('Create'), palette.onAccent);
        expect(fill('Wait').color, palette.fill1);
        expect(ink('Wait'), palette.fgSubtle);
        final pill = tester.getRect(
          find.ancestor(
            of: find.text('Create'),
            matching: find.byType(Container),
          ),
        );
        final label = tester.getRect(find.text('Create'));
        expect(pill.height, 36);
        expect(label.left - pill.left, 16);
      });
    }
  });

  group('goldens', () {
    final variants = [
      (Brightness.dark, TextDirection.rtl),
      (Brightness.light, TextDirection.ltr),
      (Brightness.dark, TextDirection.ltr),
      (Brightness.light, TextDirection.rtl),
    ];

    for (final (brightness, direction) in variants) {
      final variant = '${brightness.name}_${direction.name}';

      testWidgets('fidelity conversation $variant', (tester) async {
        setGoldenViewport(tester);
        await withRealShadows(() async {
          await tester.pumpWidget(
            lnTestApp(
              child: const _ConversationSample(),
              brightness: brightness,
              direction: direction,
              padding: const EdgeInsets.only(top: 24),
            ),
          );
          await tester.pump(const Duration(milliseconds: 400));
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile('goldens/fidelity_conversation_$variant.png'),
          );
        });
      });

      testWidgets('fidelity settings $variant', (tester) async {
        setGoldenViewport(tester);
        await withRealShadows(() async {
          await tester.pumpWidget(
            lnTestApp(
              child: const _SettingsSample(),
              brightness: brightness,
              direction: direction,
              padding: const EdgeInsets.only(top: 24),
            ),
          );
          await tester.pump();
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile('goldens/fidelity_settings_$variant.png'),
          );
        });
      });

      testWidgets('fidelity stacked sheet $variant', (tester) async {
        setGoldenViewport(tester);
        await withRealShadows(() async {
          await tester.pumpWidget(
            lnTestApp(
              child: const _SheetHost(),
              brightness: brightness,
              direction: direction,
              padding: const EdgeInsets.only(top: 24),
            ),
          );
          await tester.tap(find.byType(BlockButton));
          await tester.pumpAndSettle();
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile('goldens/fidelity_stacked_sheet_$variant.png'),
          );
        });
      });
    }
  });
}

/// A conversation slice: the header chrome, a run of agent bubbles, a separator, owner bubbles and
/// the jump button.
class _ConversationSample extends StatelessWidget {
  const _ConversationSample();

  @override
  Widget build(BuildContext context) {
    final ar = Directionality.of(context) == TextDirection.rtl;
    String t(String en, String a) => ar ? a : en;
    return Stack(
      children: [
        ListView(
          padding: EdgeInsets.only(
            top: ScreenHeader.heightOf(context, extra: 40),
            bottom: 24,
          ),
          children: [
            DateSeparator(label: t('Nov 24 7:54 PM', '٢٤ نوفمبر ٧:٥٤ م')),
            Padding(
              padding: BubbleGroup.gutter,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  MessageBubble.agent(
                    t(
                      'Gold held above the level all morning.',
                      'بقي الذهب فوق المستوى طوال الصباح.',
                    ),
                    joinBottom: true,
                  ),
                  BubbleGroup.spacer(sameSender: true, bubbleRun: true),
                  MessageBubble.agent(
                    t(
                      'I will watch it until the close and tell you if it breaks '
                          'below.',
                      'سأراقبه حتى الإغلاق وأخبرك إن كسر المستوى نزولًا.',
                    ),
                    joinTop: true,
                  ),
                ],
              ),
            ),
            DateSeparator(label: t('8:56 AM', '٨:٥٦ ص')),
            Padding(
              padding: BubbleGroup.gutter,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  MessageBubble.user(t('Thanks', 'شكرًا'), joinBottom: true),
                  BubbleGroup.spacer(sameSender: true, bubbleRun: true),
                  MessageBubble.user(
                    t('Call me if it moves.', 'اتصل بي إن تحرك.'),
                    joinTop: true,
                  ),
                ],
              ),
            ),
          ],
        ),
        ScreenHeader(
          leading: CircleIconButton(
            icon: const LnGlyph(LnGlyphs.menu),
            semanticLabel: 'Chats',
            onTap: () {},
          ),
          center: TitleCapsule(
            avatar: const FakeAvatar(FakeShape.hexagon, FakeAvatar.violet),
            title: t('Atlas', 'أطلس'),
            onTap: () {},
          ),
          trailing: CircleIconButton(
            icon: const Icon(FIcons.phone),
            semanticLabel: 'Call',
            onTap: () {},
          ),
        ),
        PositionedDirectional(
          end: 16 - 6,
          bottom: 20,
          child: JumpToLatestButton(visible: true, onTap: () {}),
        ),
      ],
    );
  }
}

/// A settings page: a one-row card, a grouped card with values and trailing glyphs, a labelled card
/// with a note, and a destructive one-row card.
class _SettingsSample extends StatelessWidget {
  const _SettingsSample();

  @override
  Widget build(BuildContext context) {
    final ar = Directionality.of(context) == TextDirection.rtl;
    String t(String en, String a) => ar ? a : en;
    return ListView(
      padding: const EdgeInsets.only(top: 40, bottom: 24),
      children: [
        LnSection(
          children: [
            LnListTile(
              icon: FIcons.messageSquare,
              title: t('Notifications', 'الإشعارات والتواصل'),
              value: 'Telegram',
              onTap: () {},
            ),
          ],
        ),
        const SizedBox(height: LnSpace.xxl),
        LnSection(
          children: [
            LnListTile(
              icon: FIcons.house,
              title: t('Home screen', 'الشاشة الرئيسية'),
              value: t('Last chat', 'آخر محادثة'),
              onTap: () {},
            ),
            LnListTile(
              icon: FIcons.globe,
              title: t('Language', 'اللغة'),
              value: t('English', 'العربية'),
              onTap: () {},
            ),
            LnListTile(
              icon: FIcons.moon,
              title: t('Appearance', 'المظهر'),
              value: t('System', 'حسب النظام'),
              picker: true,
              onTap: () {},
            ),
            LnListTile(
              icon: FIcons.eraser,
              title: t('Clear cache', 'مسح الذاكرة المؤقتة'),
              onTap: () {},
            ),
          ],
        ),
        const SizedBox(height: LnSpace.xxl),
        LnSection(
          title: t('About', 'حول'),
          footer: t(
            'Lonora checks for updates when it starts.',
            'يتحقق لونورا من التحديثات عند تشغيله.',
          ),
          children: [
            LnListTile(
              icon: FIcons.globe,
              title: t('Open Lonora on the web', 'افتح لونورا على الويب'),
              external: true,
              onTap: () {},
            ),
            LnListTile(
              icon: FIcons.info,
              title: t('Version', 'الإصدار'),
              value: '1.0.0',
            ),
          ],
        ),
        const SizedBox(height: LnSpace.xxl),
        LnSection(
          children: [
            LnListTile(
              icon: LnIcons.logOut,
              title: t('Sign out', 'تسجيل الخروج'),
              destructive: true,
              onTap: () {},
            ),
          ],
        ),
        const SizedBox(height: LnSpace.xxl),
        LnSection(
          title: t('Settings', 'الإعدادات'),
          flat: true,
          children: [
            LnListTile(
              icon: FIcons.fileText,
              title: t('Instructions', 'التعليمات'),
              onTap: () {},
            ),
            LnListTile(
              icon: FIcons.brain,
              title: t('Memory', 'الذاكرة'),
              onTap: () {},
            ),
          ],
        ),
      ],
    );
  }
}

/// A page that opens a stacked sheet with a header and a group of rows.
class _SheetHost extends StatelessWidget {
  const _SheetHost();

  @override
  Widget build(BuildContext context) {
    final ar = Directionality.of(context) == TextDirection.rtl;
    String t(String en, String a) => ar ? a : en;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ScreenHeader(
          leading: CircleIconButton(
            icon: const Icon(FIcons.search),
            semanticLabel: 'Search',
            onTap: () {},
          ),
          trailing: CircleIconButton(
            icon: const Icon(FIcons.plus),
            semanticLabel: 'New',
            onTap: () {},
          ),
        ),
        const SizedBox(height: 16),
        LnSection(
          children: [
            LnListTile(title: t('Agents', 'الوكلاء'), onTap: () {}),
            LnListTile(title: t('Routines', 'المهام الدورية'), onTap: () {}),
          ],
        ),
        const SizedBox(height: 16),
        Center(
          child: BlockButton(
            label: t('New group', 'مجموعة جديدة'),
            expand: false,
            onPressed: () => showLnStackedSheet<void>(
              context,
              showHandle: true,
              builder: (context) => Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  LnSheetHeader(
                    title: t('New group', 'إنشاء دردشة جماعية'),
                    closeLabel: t('Close', 'إغلاق'),
                    action: HeaderPillButton(label: t('Create', 'إنشاء')),
                  ),
                  const SizedBox(height: 16),
                  LnSection(
                    title: t('Members', 'الأعضاء'),
                    children: [
                      LnListTile(
                        icon: FIcons.bot,
                        title: 'Atlas',
                        subtitle: t('Markets', 'الأسواق'),
                        onTap: () {},
                      ),
                      LnListTile(
                        icon: FIcons.bot,
                        title: 'Nova',
                        subtitle: t('Research', 'البحث'),
                        onTap: () {},
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}
