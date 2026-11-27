// The kit pieces of the drawer home, the anchored menus and the press-to-talk composer: the
// push-reveal drawer scaffold, the message long-press menu, the popover menu, the ☰ pill, the compact
// drawer row, hold-to-talk and the recording bar, the reply pill and the dark tab bar. Layout values,
// RTL, semantics and interactions, plus goldens (light/dark × English LTR / Arabic RTL).
//
// Regenerate the goldens with: flutter test --update-goldens test/design/round4_components_test.dart
import 'dart:io';
import 'dart:ui' show ImageFilter, Tristate;

import 'package:flutter/material.dart';
import 'package:flutter/gestures.dart' show kLongPressTimeout;
import 'package:flutter/semantics.dart' show SemanticsAction;
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/design/design.dart';

import 'fonts.dart';
import 'harness.dart';

const _insets = EdgeInsets.only(top: 32, bottom: 16);

/// Colour emoji for the reaction pill's goldens (the test engine has no system emoji font).
const _emojiFamily = 'NotoColorEmoji';

Future<void> _loadEmoji() async {
  final file = File(
    '${Platform.environment['FLUTTER_ROOT'] ?? '/opt/flutter'}'
    '/engine/src/flutter/txt/third_party/fonts/NotoColorEmoji.ttf',
  );
  if (!file.existsSync()) return;
  await (FontLoader(_emojiFamily)
        ..addFont(Future.value(ByteData.sublistView(file.readAsBytesSync()))))
      .load();
}

String _variant(Brightness b, TextDirection d) => '${b.name}_${d.name}';

bool _ar(BuildContext context) =>
    Directionality.of(context) == TextDirection.rtl;

String _t(BuildContext context, String en, String ar) => _ar(context) ? ar : en;

Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  TextDirection direction = TextDirection.ltr,
  Brightness brightness = Brightness.light,
  EdgeInsets padding = _insets,
}) async {
  setGoldenViewport(tester);
  await tester.pumpWidget(
    lnTestApp(
      child: child,
      direction: direction,
      brightness: brightness,
      padding: padding,
    ),
  );
  await tester.pump();
}

const _tabs = [
  LnTabItem(
    icon: LnGlyph(LnGlyphs.chats),
    selectedIcon: LnGlyph(LnGlyphs.chatsFilled),
    label: 'Chats',
  ),
  LnTabItem(
    icon: LnGlyph(LnGlyphs.market),
    selectedIcon: LnGlyph(LnGlyphs.marketFilled),
    label: 'Market',
  ),
  LnTabItem(
    icon: LnGlyph(LnGlyphs.me),
    selectedIcon: LnGlyph(LnGlyphs.meFilled),
    label: 'Me',
  ),
];

/// A conversation page: the ☰ pill in the header, two bubbles, the composer above the tab bar.
class _ConversationPage extends StatelessWidget {
  const _ConversationPage({this.onMenu});

  final VoidCallback? onMenu;

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.paddingOf(context).top;
    return Stack(
      children: [
        Positioned.fill(
          child: ListView(
            padding: EdgeInsets.fromLTRB(16, top + 76, 16, 200),
            children: [
              Align(
                alignment: AlignmentDirectional.centerEnd,
                child: MessageBubble.user(
                  _t(context, 'Any news on NVDA?', 'هل من جديد عن إنفيديا؟'),
                ),
              ),
              const SizedBox(height: LnSpace.senderChangeGap),
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: MessageBubble.agent(
                  _t(
                    context,
                    'It crossed 140 this morning, up 3.2 %. I will alert you '
                        'if it falls back under 135.',
                    'تجاوز 140 صباح اليوم بارتفاع 3.2 %. سأنبهك إن عاد دون 135.',
                  ),
                ),
              ),
            ],
          ),
        ),
        PositionedDirectional(
          start: 14,
          top: top + 8,
          child: MenuPillButton(
            semanticLabel: _t(context, 'Chats', 'المحادثات'),
            unreadCount: 3,
            onTap: onMenu,
          ),
        ),
        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: LnSpace.chromeGutter,
                ),
                child: Composer(
                  controller: TextEditingController(),
                  placeholder: _t(context, 'Message Lonora', 'راسل لونورا'),
                  onMic: () {},
                  holdToTalk: ComposerHoldToTalk(
                    placeholder: _t(
                      context,
                      'Hold to talk, tap to type',
                      'اضغط مطولاً للتحدث، انقر للكتابة',
                    ),
                  ),
                ),
              ),
              const SizedBox(height: LnSpace.composerToBar),
              FloatingTabBar(
                items: _tabs,
                selectedIndex: 0,
                onSelect: (_) {},
                actionIcon: const LnGlyph(LnGlyphs.attention),
                actionLabel: 'Needs your attention',
                onAction: () {},
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// The drawer's content: the search and «+» circles and compact rows.
class _DrawerList extends StatelessWidget {
  const _DrawerList();

  @override
  Widget build(BuildContext context) {
    final rows = [
      (FakeShape.circle, FakeAvatar.violet, 'Lonora', 'لونورا', 0),
      (FakeShape.square, FakeAvatar.green, 'Market Watch', 'مراقب السوق', 2),
      (FakeShape.diamond, FakeAvatar.orange, 'Travel desk', 'مكتب السفر', 0),
      (FakeShape.hexagon, FakeAvatar.cyan, 'Crypto Desk', 'Crypto Desk', 0),
      (FakeShape.circle, FakeAvatar.slate, 'Family', 'العائلة', 0),
    ];
    return SafeArea(
      bottom: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                CircleIconButton(
                  icon: const Icon(FIcons.search),
                  semanticLabel: 'Search',
                  onTap: () {},
                ),
                CircleIconButton(
                  icon: const Icon(FIcons.plus),
                  semanticLabel: 'New',
                  onTap: () {},
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          for (final (i, (shape, color, en, ar, unread)) in rows.indexed)
            ChatListRow.compact(
              avatar: FakeAvatar(shape, color),
              title: _t(context, en, ar),
              current: i == 1,
              unreadCount: unread,
              unreadDot: i == 3,
              muted: i == 4,
              onTap: () {},
            ),
        ],
      ),
    );
  }
}

void main() {
  setUpAll(() async {
    await loadAppFonts();
    await _loadEmoji();
  });

  group('MenuPillButton', () {
    for (final direction in TextDirection.values) {
      testWidgets('a Ø44 circle that grows into a stadium with the count '
          'at its end (${direction.name})', (tester) async {
        final handle = tester.ensureSemantics();
        var taps = 0;
        await _pump(
          tester,
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                MenuPillButton(
                  key: const ValueKey('plain'),
                  semanticLabel: 'Chats',
                  onTap: () => taps++,
                ),
                const MenuPillButton(
                  key: ValueKey('count'),
                  semanticLabel: 'Chats',
                  unreadCount: 3,
                  unreadLabel: '3 unread',
                ),
                const MenuPillButton(
                  key: ValueKey('many'),
                  semanticLabel: 'Chats',
                  unreadCount: 150,
                ),
              ],
            ),
          ),
          direction: direction,
        );
        await tester.pumpAndSettle();
        expect(
          tester.getSize(find.byKey(const ValueKey('plain'))),
          const Size(48, 48),
        );
        expect(
          tester.getSize(find.byKey(const ValueKey('count'))),
          const Size(10 + 24 + 4 + 20 + 12 + 4, 48),
        );
        // The glyph keeps the start, the disc (Latin digits) sits at the end.
        final glyph = tester.getRect(
          find.descendant(
            of: find.byKey(const ValueKey('count')),
            matching: find.byType(LnGlyph),
          ),
        );
        final disc = tester.getRect(
          find.descendant(
            of: find.byKey(const ValueKey('count')),
            matching: find.byType(UnreadPill),
          ),
        );
        final pill = tester.getRect(find.byKey(const ValueKey('count')));
        final rtl = direction == TextDirection.rtl;
        if (rtl) {
          expect(glyph.right, pill.right - 2 - 10);
          expect(disc.left, pill.left + 2 + 12);
          expect(disc.right, glyph.left - 4);
        } else {
          expect(glyph.left, pill.left + 2 + 10);
          expect(disc.right, pill.right - 2 - 12);
          expect(disc.left, glyph.right + 4);
        }
        expect(disc.height, 20);
        expect(find.text('3'), findsOneWidget);
        expect(find.text('99+'), findsOneWidget);
        expect(find.bySemanticsLabel('Chats'), findsOneWidget);
        expect(find.bySemanticsLabel('Chats, 3 unread'), findsOneWidget);
        expect(find.bySemanticsLabel('Chats, 150 unread'), findsOneWidget);
        await tester.tap(find.byKey(const ValueKey('plain')));
        await tester.pumpAndSettle();
        expect(taps, 1);
        handle.dispose();
      });
    }

    for (final b in Brightness.values) {
      testWidgets('the count disc: white digits on the deeper selection fill '
          'at AA (${b.name})', (tester) async {
        final handle = tester.ensureSemantics();
        await _pump(
          tester,
          const Center(
            child: MenuPillButton(semanticLabel: 'Chats', unreadCount: 8),
          ),
          brightness: b,
        );
        await tester.pumpAndSettle();
        final palette = b == Brightness.dark ? LnPalette.dark : LnPalette.light;
        expect(
          tester.widget<UnreadPill>(find.byType(UnreadPill)).color,
          palette.selectionFill,
        );
        await expectLater(tester, meetsGuideline(textContrastGuideline));
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
        handle.dispose();
      });
    }

    testWidgets('chrome circle fill; the rim only in light', (tester) async {
      for (final b in Brightness.values) {
        await _pump(
          tester,
          const Center(child: MenuPillButton(semanticLabel: 'Chats')),
          brightness: b,
        );
        final deco =
            tester
                    .widget<DecoratedBox>(
                      find
                          .descendant(
                            of: find.byType(MenuPillButton),
                            matching: find.byType(DecoratedBox),
                          )
                          .first,
                    )
                    .decoration
                as ShapeDecoration;
        final palette = b == Brightness.dark ? LnPalette.dark : LnPalette.light;
        expect(deco.color, palette.chromeCircle);
        final side = (deco.shape as StadiumBorder).side;
        expect(
          side.style,
          b == Brightness.dark ? BorderStyle.none : BorderStyle.solid,
        );
      }
    });
  });

  group('ChatListRow.compact', () {
    for (final direction in TextDirection.values) {
      testWidgets('62 dp pitch, 32 dp avatar 22 dp in, title 20 dp after it, '
          'unread at the end (${direction.name})', (tester) async {
        await _pump(
          tester,
          Column(
            children: [
              ChatListRow.compact(
                key: const ValueKey('row'),
                avatar: const FakeAvatar(FakeShape.circle, FakeAvatar.violet),
                title: 'Market Watch',
                unreadCount: 2,
                onTap: () {},
              ),
              ChatListRow.compact(
                key: const ValueKey('current'),
                avatar: const FakeAvatar(FakeShape.circle, FakeAvatar.green),
                title: 'Lonora',
                current: true,
                onTap: () {},
              ),
              ChatListRow(
                key: const ValueKey('full'),
                avatar: const FakeAvatar(FakeShape.circle, FakeAvatar.green),
                title: 'Lonora',
                preview: 'Hello',
                onTap: () {},
              ),
            ],
          ),
          direction: direction,
          padding: EdgeInsets.zero,
        );
        final rtl = direction == TextDirection.rtl;
        const w = 393.0;
        final row = tester.getRect(find.byKey(const ValueKey('row')));
        expect(row.height, ChatListRow.compactPitch);
        expect(
          tester.getSize(find.byKey(const ValueKey('full'))).height,
          LnSize.listRow,
        );
        final avatar = tester.getRect(
          find.descendant(
            of: find.byKey(const ValueKey('row')),
            matching: find.byType(FakeAvatar),
          ),
        );
        expect(row.height, 62);
        expect(avatar.size, const Size.square(32));
        expect(rtl ? w - avatar.right : avatar.left, 22);
        expect(avatar.center.dy, row.center.dy);
        final title = tester.getRect(find.text('Market Watch'));
        expect(rtl ? avatar.left - title.right : title.left - avatar.right, 20);
        final pill = tester.getRect(find.byType(UnreadPill));
        expect(rtl ? pill.left : w - pill.right, 28);
        // Name-only: no second line.
        expect(title.center.dy, closeTo(row.center.dy, 0.5));

        // The current row: fill1, radius 16, 60 dp tall, 8 dp from both edges.
        final highlight = find.descendant(
          of: find.byKey(const ValueKey('current')),
          matching: find.byType(AnimatedContainer),
        );
        final rect = tester.getRect(
          find.descendant(of: highlight, matching: find.byType(DecoratedBox)),
        );
        expect(rect.height, 60);
        expect(rect.height, ChatListRow.compactHighlightHeight);
        expect(rect.left, 8);
        expect(w - rect.right, 8);
        final deco =
            tester.widget<AnimatedContainer>(highlight).decoration!
                as BoxDecoration;
        expect(deco.color, LnPalette.light.fill1);
        expect(deco.borderRadius, const BorderRadius.all(Radius.circular(16)));
      });
    }

    testWidgets('the current row is selected for screen readers; a preview '
        'adds a second line', (tester) async {
      final handle = tester.ensureSemantics();
      await _pump(
        tester,
        Column(
          children: [
            ChatListRow.compact(
              avatar: const FakeAvatar(FakeShape.circle, FakeAvatar.violet),
              title: 'Lonora',
              current: true,
              onTap: () {},
            ),
            ChatListRow.compact(
              key: const ValueKey('preview'),
              avatar: const FakeAvatar(FakeShape.circle, FakeAvatar.green),
              title: 'Travel desk',
              preview: 'Your flight is on time.',
              time: '09:40',
              onTap: () {},
            ),
          ],
        ),
      );
      expect(
        tester.getSemantics(find.bySemanticsLabel('Lonora')),
        matchesSemantics(
          label: 'Lonora',
          isSelected: true,
          hasSelectedState: true,
          isButton: true,
          hasTapAction: true,
          isFocusable: true,
          hasFocusAction: true,
          isEnabled: true,
          hasEnabledState: true,
        ),
      );
      final row = tester.getRect(find.byKey(const ValueKey('preview')));
      final title = tester.getRect(find.text('Travel desk'));
      final preview = tester.getRect(find.text('Your flight is on time.'));
      expect(title.bottom, lessThanOrEqualTo(preview.top));
      expect(preview.bottom, lessThan(row.bottom));
      expect(find.text('09:40'), findsOneWidget);
      handle.dispose();
    });
  });

  group('FloatingTabBar in dark', () {
    testWidgets('no rim in dark, the hairline in light', (tester) async {
      for (final b in Brightness.values) {
        await _pump(
          tester,
          Align(
            alignment: Alignment.bottomCenter,
            child: FloatingTabBar(
              items: _tabs,
              selectedIndex: 0,
              onSelect: (_) {},
              actionIcon: const LnGlyph(LnGlyphs.attention),
              actionLabel: 'Attention',
            ),
          ),
          brightness: b,
        );
        final shapes = tester
            .widgetList<DecoratedBox>(
              find.descendant(
                of: find.byType(FloatingTabBar),
                matching: find.byType(DecoratedBox),
              ),
            )
            .map((d) => d.decoration)
            .whereType<ShapeDecoration>()
            .where((d) => d.color != null)
            .toList();
        expect(shapes, hasLength(2));
        for (final s in shapes) {
          final side = (s.shape as OutlinedBorder).side;
          expect(
            side.style,
            b == Brightness.dark ? BorderStyle.none : BorderStyle.solid,
          );
        }
      }
    });
  });

  group('showLnPopoverMenu', () {
    Future<void> openFrom(
      WidgetTester tester,
      AlignmentGeometry where, {
      TextDirection direction = TextDirection.ltr,
      Brightness brightness = Brightness.light,
      double rowHeight = LnSize.minTouch,
      String? selected,
      void Function(String?)? onResult,
      VoidCallback? onSelected,
    }) async {
      final key = GlobalKey();
      await _pump(
        tester,
        Align(
          alignment: where,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 40),
            child: Builder(
              builder: (context) => CircleIconButton(
                key: key,
                icon: const Icon(FIcons.plus),
                semanticLabel: 'New',
                onTap: () async {
                  final r = await showLnPopoverMenu<String>(
                    context,
                    anchorKey: key,
                    rowHeight: rowHeight,
                    selected: selected,
                    actions: [
                      LnMenuAction(
                        label: _t(context, 'New agent', 'وكيل جديد'),
                        icon: FIcons.bot,
                        value: 'agent',
                        onSelected: onSelected,
                      ),
                      LnMenuAction(
                        label: _t(context, 'New group', 'مجموعة جديدة'),
                        icon: FIcons.users,
                        value: 'group',
                      ),
                      LnMenuAction(
                        label: _t(context, 'Manage agents', 'إدارة الوكلاء'),
                        icon: FIcons.settings,
                        value: 'manage',
                      ),
                    ],
                  );
                  onResult?.call(r);
                },
              ),
            ),
          ),
        ),
        direction: direction,
        brightness: brightness,
      );
      await tester.tap(find.byKey(key));
      await tester.pumpAndSettle();
    }

    Rect cardRect(WidgetTester tester) =>
        tester.getRect(find.byType(LnMenuCard));

    for (final direction in TextDirection.values) {
      testWidgets('below the anchor, 4 dp away, end edges aligned at the end '
          'side (${direction.name})', (tester) async {
        final rtl = direction == TextDirection.rtl;
        await openFrom(
          tester,
          AlignmentDirectional.topEnd,
          direction: direction,
        );
        final anchor = tester.getRect(find.byType(CircleIconButton));
        final card = cardRect(tester);
        expect(card.top, anchor.bottom + 4);
        expect(card.width, 240);
        if (rtl) {
          expect(card.left, anchor.left);
        } else {
          expect(card.right, anchor.right);
        }
        expect(card.height, 3 * 48 + 12);
        // Rows: 48 dp, the icon 16 dp and the label 52 dp from the start edge.
        final icon = tester.getRect(find.byIcon(FIcons.bot));
        final label = tester.getRect(
          find.text(rtl ? 'وكيل جديد' : 'New agent'),
        );
        expect(icon.size, const Size.square(24));
        if (rtl) {
          expect(card.right - icon.right, 16);
          expect(card.right - label.right, 52);
        } else {
          expect(icon.left - card.left, 16);
          expect(label.left - card.left, 52);
        }
        expect(icon.top - card.top, 6 + 12);
      });
    }

    testWidgets('start edges aligned at the start side; above when there is '
        'no room below', (tester) async {
      await openFrom(tester, Alignment.bottomLeft);
      final anchor = tester.getRect(find.byType(CircleIconButton));
      final card = cardRect(tester);
      expect(card.left, anchor.left);
      expect(card.bottom, anchor.top - 4);
    });

    testWidgets('a negative gap overlaps the anchor; opened above, the card '
        'grows from its bottom edge', (tester) async {
      final key = GlobalKey();
      late BuildContext ctx;
      await _pump(
        tester,
        Builder(
          builder: (context) {
            ctx = context;
            return Stack(
              children: [
                Positioned(
                  left: 20,
                  right: 20,
                  bottom: 100,
                  height: 48,
                  child: SizedBox(key: key),
                ),
              ],
            );
          },
        ),
      );
      showLnPopoverMenu<String>(
        ctx,
        anchorKey: key,
        gap: -4,
        actions: const [
          LnMenuAction(label: 'Camera', icon: FIcons.camera, value: 'c'),
          LnMenuAction(label: 'Files', icon: FIcons.file, value: 'f'),
        ],
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 40));
      final scale = tester.widget<ScaleTransition>(
        find
            .ancestor(
              of: find.byType(LnMenuCard),
              matching: find.byType(ScaleTransition),
            )
            .first,
      );
      expect(scale.alignment, Alignment.bottomCenter);
      await tester.pumpAndSettle();
      final anchor = tester.getRect(find.byKey(key));
      expect(cardRect(tester).bottom, anchor.top + 4);
    });

    testWidgets('rows keep a 48 dp target and take a taller height', (
      tester,
    ) async {
      await openFrom(tester, Alignment.topRight, rowHeight: 40);
      expect(cardRect(tester).height, 3 * 48 + 12);
      await tester.tapAt(const Offset(10, 600));
      await tester.pumpAndSettle();
      await openFrom(tester, Alignment.topRight, rowHeight: 52);
      expect(cardRect(tester).height, 3 * 52 + 12);
    });

    testWidgets('no scrim; returns the value and calls onSelected; outside tap '
        'and back dismiss with null', (tester) async {
      final results = <String?>[];
      var selectedCalls = 0;
      await openFrom(
        tester,
        Alignment.topRight,
        onResult: results.add,
        onSelected: () => selectedCalls++,
      );
      final barrier = tester.widget<ModalBarrier>(
        find.byType(ModalBarrier).last,
      );
      expect(barrier.color, isNull);
      await tester.tap(find.text('New agent'));
      await tester.pumpAndSettle();
      expect(results, ['agent']);
      expect(selectedCalls, 1);
      expect(find.byType(LnMenuCard), findsNothing);

      await tester.tap(find.byType(CircleIconButton));
      await tester.pumpAndSettle();
      await tester.tapAt(const Offset(20, 700));
      await tester.pumpAndSettle();
      expect(results, ['agent', null]);

      await tester.tap(find.byType(CircleIconButton));
      await tester.pumpAndSettle();
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(results, ['agent', null, null]);
      expect(find.byType(LnMenuCard), findsNothing);
    });

    testWidgets('a picker checks the selected row; rows are labelled buttons', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await openFrom(tester, Alignment.topRight, selected: 'group');
      expect(find.byIcon(FIcons.check), findsOneWidget);
      final check = tester.getRect(find.byIcon(FIcons.check));
      final row = tester.getRect(find.text('New group'));
      expect(check.center.dy, closeTo(row.center.dy, 0.5));
      expect(
        tester.getSemantics(find.bySemanticsLabel('New group')),
        matchesSemantics(
          label: 'New group',
          isButton: true,
          hasSelectedState: true,
          isSelected: true,
          hasTapAction: true,
          isFocusable: true,
          hasFocusAction: true,
          isEnabled: true,
          hasEnabledState: true,
        ),
      );
      expect(
        tester
            .getSemantics(find.bySemanticsLabel('New agent'))
            .flagsCollection
            .isSelected,
        Tristate.isFalse,
      );
      handle.dispose();
    });

    for (final b in Brightness.values) {
      for (final d in TextDirection.values) {
        testWidgets('golden ${_variant(b, d)}', (tester) async {
          await withRealShadows(() async {
            await openFrom(
              tester,
              AlignmentDirectional.topEnd,
              direction: d,
              brightness: b,
              selected: 'agent',
            );
            await expectLater(
              find.byType(MaterialApp),
              matchesGoldenFile('goldens/round4_popover_${_variant(b, d)}.png'),
            );
          });
        });
      }
    }
  });

  group('showLnAnchoredMenu', () {
    List<LnReactionOption<String>> reactions(String? own) => [
      for (final e in ['👍', '❤️', '😂', '😮', '😢', '🙏'])
        LnReactionOption(
          value: e,
          semanticLabel: 'React with $e',
          selected: e == own,
          child: Text(
            e,
            style: const TextStyle(fontFamilyFallback: [_emojiFamily]),
          ),
        ),
    ];

    Future<void> openOn(
      WidgetTester tester, {
      required bool agent,
      double topPad = 0,
      String text = 'It crossed 140 this morning.',
      TextDirection direction = TextDirection.ltr,
      Brightness brightness = Brightness.light,
      void Function(String?)? onResult,
      VoidCallback? onCopy,
      bool header = true,
      bool withDelete = true,
    }) async {
      final key = GlobalKey();
      Widget bubble() =>
          agent ? MessageBubble.agent(text) : MessageBubble.user(text);
      await _pump(
        tester,
        Builder(
          builder: (context) => ListView(
            padding: EdgeInsets.fromLTRB(16, 120 + topPad, 16, 0),
            children: [
              Align(
                alignment: agent
                    ? AlignmentDirectional.centerStart
                    : AlignmentDirectional.centerEnd,
                child: GestureDetector(
                  onLongPress: () async {
                    final r = await showLnAnchoredMenu<String>(
                      context,
                      targetKey: key,
                      target: bubble(),
                      header: header
                          ? _t(context, 'Today, 08:56', 'اليوم، ٠٨:٥٦')
                          : null,
                      reactionsLabel: _t(context, 'Reactions', 'التفاعلات'),
                      reactions: reactions('❤️'),
                      moreReaction: LnReactionOption(
                        value: 'more',
                        semanticLabel: 'More reactions',
                        child: const Icon(FIcons.smilePlus),
                      ),
                      actions: [
                        LnMenuAction(
                          label: _t(context, 'Reply', 'رد'),
                          icon: LnIcons.reply,
                          value: 'reply',
                        ),
                        LnMenuAction(
                          label: _t(context, 'Copy', 'نسخ'),
                          icon: FIcons.copy,
                          value: 'copy',
                          onSelected: onCopy,
                        ),
                        LnMenuAction(
                          label: _t(context, 'Select text', 'حدد النص'),
                          icon: FIcons.textSelect,
                          value: 'select',
                        ),
                        if (withDelete)
                          LnMenuAction(
                            label: _t(context, 'Delete', 'حذف'),
                            icon: FIcons.trash2,
                            value: 'delete',
                            destructive: true,
                          ),
                      ],
                    );
                    onResult?.call(r);
                  },
                  child: KeyedSubtree(key: key, child: bubble()),
                ),
              ),
              // Behind the menu: shows the blur.
              const SizedBox(height: LnSpace.senderChangeGap),
              const Align(
                alignment: AlignmentDirectional.centerEnd,
                child: MessageBubble.user('Thanks, keep an eye on it.'),
              ),
              const SizedBox(height: LnSpace.senderChangeGap),
              const Align(
                alignment: AlignmentDirectional.centerStart,
                child: MessageBubble.agent(
                  'Will do. Your alert is set for 135 and 150.',
                ),
              ),
            ],
          ),
        ),
        direction: direction,
        brightness: brightness,
      );
      await tester.longPress(find.byKey(key));
      await tester.pumpAndSettle();
    }

    Rect pillRect(WidgetTester tester) => tester.getRect(
      find
          .ancestor(
            of: find.bySemanticsLabel('React with 👍'),
            matching: find.byType(SingleChildScrollView),
          )
          .first,
    );

    Rect liftedRect(WidgetTester tester) =>
        tester.getRect(find.byType(MessageBubble).last);

    for (final direction in TextDirection.values) {
      testWidgets('pill 6 dp above, card 6 dp below, both at the bubble\'s '
          'side (${direction.name})', (tester) async {
        final rtl = direction == TextDirection.rtl;
        await openOn(tester, agent: true, direction: direction);
        final bubble = liftedRect(tester);
        final original = tester.getRect(find.byType(MessageBubble).first);
        expect(bubble, original, reason: 'room enough: the bubble stays');
        final pill = pillRect(tester);
        final card = tester.getRect(find.byType(LnMenuCard));
        expect(pill.size, const Size(7 * 48 + 8, 52));
        expect(bubble.top - pill.bottom, 6);
        expect(card.top - bubble.bottom, 6);
        expect(card.width, 250);
        // Header + four 48 dp rows.
        expect(card.height, 12 + (8 + 16 + 6) + 4 * 48);
        if (rtl) {
          expect(pill.right, bubble.right);
          expect(card.right, bubble.right);
        } else {
          expect(pill.left, bubble.left);
          expect(card.left, bubble.left);
        }
        // Destructive in the error colour.
        final delete = tester.widget<Text>(find.text(rtl ? 'حذف' : 'Delete'));
        expect(delete.style!.color, LnPalette.light.error);
        // The header is the 12 dp line in the secondary ink (AA on the menu surface).
        final header = tester.widget<Text>(
          find.text(rtl ? 'اليوم، ٠٨:٥٦' : 'Today, 08:56'),
        );
        expect(header.style!.fontSize, 12);
        expect(header.style!.color, LnPalette.light.fgMuted);
      });
    }

    testWidgets('an owner bubble aligns pill and card to the end', (
      tester,
    ) async {
      await openOn(tester, agent: false);
      final bubble = liftedRect(tester);
      expect(pillRect(tester).right, bubble.right);
      expect(tester.getRect(find.byType(LnMenuCard)).right, bubble.right);
    });

    testWidgets('heavy blur and a light dim behind; no barrier colour', (
      tester,
    ) async {
      await openOn(tester, agent: true);
      final filter = tester.widget<BackdropFilter>(
        find.byType(BackdropFilter).last,
      );
      expect(
        filter.filter,
        ImageFilter.blur(sigmaX: 24, sigmaY: 24, tileMode: TileMode.clamp),
      );
      expect(
        tester.widget<ModalBarrier>(find.byType(ModalBarrier).last).color,
        isNull,
      );
    });

    testWidgets('near the bottom the bubble moves up so the card fits', (
      tester,
    ) async {
      await openOn(tester, agent: true, topPad: 600);
      final bubble = liftedRect(tester);
      final original = tester.getRect(find.byType(MessageBubble).first);
      expect(bubble.top, lessThan(original.top));
      final card = tester.getRect(find.byType(LnMenuCard));
      // Inside the safe area (16 dp bottom inset) with the 8 dp margin.
      expect(card.bottom, 852 - 16 - 8);
      expect(card.top - bubble.bottom, 6);
      expect(bubble.top - pillRect(tester).bottom, 6);
    });

    testWidgets('a bubble taller than the screen is cut; pill and card stay '
        'visible', (tester) async {
      await openOn(
        tester,
        agent: true,
        text: List.filled(60, 'A long line of the agent answer.').join(' '),
      );
      final shown = tester.getRect(
        find
            .ancestor(
              of: find.byType(MessageBubble).last,
              matching: find.byType(ClipRect),
            )
            .first,
      );
      final pill = pillRect(tester);
      final card = tester.getRect(find.byType(LnMenuCard));
      expect(pill.top, 32 + 8);
      expect(card.bottom, 852 - 16 - 8);
      expect(shown.top - pill.bottom, 6);
      expect(card.top - shown.bottom, 6);
      expect(
        shown.height,
        lessThan(tester.getSize(find.byType(MessageBubble).last).height),
      );
    });

    testWidgets('a message scrolled partly above the screen keeps the part '
        'that was on screen when it is cut', (tester) async {
      final key = GlobalKey();
      late BuildContext ctx;
      // 800 dp tall, its top 500 dp above the screen: only its lower 300 dp showed.
      Widget message() => SizedBox(
        width: 200,
        height: 800,
        child: Column(
          children: [
            const SizedBox(height: 100, child: Text('hidden top')),
            const Spacer(),
            const SizedBox(height: 100, child: Text('pressed part')),
          ],
        ),
      );
      await _pump(
        tester,
        Builder(
          builder: (context) {
            ctx = context;
            return Stack(
              children: [
                Positioned(
                  left: 16,
                  top: -500,
                  child: KeyedSubtree(key: key, child: message()),
                ),
              ],
            );
          },
        ),
      );
      showLnAnchoredMenu<String>(
        ctx,
        targetKey: key,
        target: message(),
        header: 'Today, 08:56',
        reactions: reactions(null),
        actions: const [
          LnMenuAction(label: 'Reply', icon: LnIcons.reply, value: 'reply'),
          LnMenuAction(label: 'Copy', icon: FIcons.copy, value: 'copy'),
        ],
      );
      await tester.pumpAndSettle();
      final window = tester.getRect(
        find
            .ancestor(
              of: find.text('pressed part').last,
              matching: find.byType(ClipRect),
            )
            .first,
      );
      final pill = pillRect(tester);
      final card = tester.getRect(find.byType(LnMenuCard));
      expect(pill.top, 32 + 8);
      expect(window.top - pill.bottom, 6);
      expect(card.top - window.bottom, 6);
      expect(card.bottom, lessThanOrEqualTo(852 - 16 - 8));
      // The part that was on screen is in the window; the hidden top is cut away.
      final pressed = tester.getRect(find.text('pressed part').last);
      expect(pressed.top, greaterThanOrEqualTo(window.top));
      expect(pressed.bottom, lessThanOrEqualTo(window.bottom));
      expect(
        tester.getRect(find.text('hidden top').last).bottom,
        lessThanOrEqualTo(window.top),
      );
    });

    for (final b in Brightness.values) {
      // The destructive row's red is the palette's error colour, checked with the palette.
      testWidgets('the time header and the rows meet AA contrast (${b.name})', (
        tester,
      ) async {
        final handle = tester.ensureSemantics();
        await openOn(tester, agent: true, brightness: b, withDelete: false);
        await expectLater(tester, meetsGuideline(textContrastGuideline));
        handle.dispose();
      });
    }

    testWidgets('returns the reaction or action; outside tap and back give '
        'null; onSelected runs after closing', (tester) async {
      final results = <String?>[];
      var copies = 0;
      await openOn(
        tester,
        agent: true,
        onResult: results.add,
        onCopy: () => copies++,
      );
      await tester.tap(find.bySemanticsLabel('React with 😂'));
      await tester.pumpAndSettle();
      expect(results, ['😂']);

      await tester.longPress(find.byType(MessageBubble).first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Copy'));
      await tester.pumpAndSettle();
      expect(results, ['😂', 'copy']);
      expect(copies, 1);

      await tester.longPress(find.byType(MessageBubble).first);
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel('More reactions'));
      await tester.pumpAndSettle();
      expect(results.last, 'more');

      await tester.longPress(find.byType(MessageBubble).first);
      await tester.pumpAndSettle();
      await tester.tapAt(const Offset(380, 800));
      await tester.pumpAndSettle();
      expect(results.last, isNull);

      await tester.longPress(find.byType(MessageBubble).first);
      await tester.pumpAndSettle();
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(results, ['😂', 'copy', 'more', null, null]);
      expect(find.byType(LnMenuCard), findsNothing);
    });

    testWidgets('semantics: a modal with a dismiss barrier, a labelled '
        'reaction group and labelled buttons', (tester) async {
      final handle = tester.ensureSemantics();
      await openOn(tester, agent: true);
      expect(find.bySemanticsLabel('Dismiss'), findsOneWidget);
      expect(find.bySemanticsLabel('Reactions'), findsOneWidget);
      final scope = find.semantics.byLabel('Popup menu').evaluate().single;
      expect(scope.flagsCollection.scopesRoute, isTrue);
      expect(scope.flagsCollection.namesRoute, isTrue);
      expect(
        tester.getSemantics(find.bySemanticsLabel('React with ❤️')),
        matchesSemantics(
          label: 'React with ❤️',
          isButton: true,
          hasSelectedState: true,
          isSelected: true,
          hasTapAction: true,
          isFocusable: true,
          hasFocusAction: true,
          isEnabled: true,
          hasEnabledState: true,
        ),
      );
      expect(
        tester.getSemantics(find.bySemanticsLabel('Delete')),
        matchesSemantics(
          label: 'Delete',
          isButton: true,
          hasSelectedState: true,
          hasTapAction: true,
          isFocusable: true,
          hasFocusAction: true,
          isEnabled: true,
          hasEnabledState: true,
        ),
      );
      // The page behind is blocked.
      expect(
        find.semantics.byLabel(RegExp('^It crossed')),
        findsOne,
        reason: 'only the lifted copy is reachable',
      );
      handle.dispose();
    });

    for (final b in Brightness.values) {
      for (final d in TextDirection.values) {
        testWidgets('golden ${_variant(b, d)}', (tester) async {
          await withRealShadows(() async {
            await openOn(
              tester,
              agent: true,
              topPad: 160,
              direction: d,
              brightness: b,
              text: d == TextDirection.rtl
                  ? 'تجاوز 140 صباح اليوم بارتفاع 3.2 %. سأنبهك إن عاد دون 135.'
                  : 'It crossed 140 this morning, up 3.2 %. I will alert you '
                        'if it falls back under 135.',
            );
            await expectLater(
              find.byType(MaterialApp),
              matchesGoldenFile(
                'goldens/round4_anchored_menu_${_variant(b, d)}.png',
              ),
            );
          });
        });
      }
    }
  });

  group('LnDrawerScaffold', () {
    Future<LnDrawerController> pumpDrawer(
      WidgetTester tester, {
      TextDirection direction = TextDirection.ltr,
      Brightness brightness = Brightness.light,
      bool reduced = false,
      Widget? page,
    }) async {
      final controller = LnDrawerController();
      addTearDown(controller.dispose);
      setGoldenViewport(tester);
      await tester.pumpWidget(
        lnTestApp(
          direction: direction,
          brightness: brightness,
          padding: _insets,
          child: MediaQuery(
            data: const MediaQueryData(
              size: goldenSize,
              padding: _insets,
              viewPadding: _insets,
              systemGestureInsets: EdgeInsets.symmetric(horizontal: 24),
            ).copyWith(disableAnimations: reduced),
            child: LnDrawerScaffold(
              controller: controller,
              drawerLabel: 'Chats',
              closeLabel: 'Close chats',
              drawer: const KeyedSubtree(
                key: ValueKey('drawer'),
                child: _DrawerList(),
              ),
              child: KeyedSubtree(
                key: const ValueKey('page'),
                child: page ?? _ConversationPage(onMenu: controller.toggle),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      return controller;
    }

    Rect pageRect(WidgetTester tester) =>
        tester.getRect(find.byKey(const ValueKey('page')));

    for (final direction in TextDirection.values) {
      testWidgets('opens on the start side: the page moves by W − 82 toward '
          'the end (${direction.name})', (tester) async {
        final rtl = direction == TextDirection.rtl;
        final controller = await pumpDrawer(tester, direction: direction);
        expect(pageRect(tester).left, 0);
        expect(find.byKey(const ValueKey('drawer')), findsNothing);
        expect(controller.isOpen, isFalse);

        final opened = <bool>[];
        controller.addListener(() => opened.add(controller.isOpen));
        await tester.tap(find.byType(MenuPillButton));
        await tester.pumpAndSettle();
        expect(controller.isOpen, isTrue);
        expect(opened, [true]);
        expect(controller.progress.value, 1);
        const width = 393.0 - 82;
        expect(pageRect(tester).left, rtl ? -width : width);
        final drawer = tester.getRect(find.byKey(const ValueKey('drawer')));
        expect(drawer.width, width);
        expect(rtl ? drawer.right : drawer.left, rtl ? 393 : 0);
      });
    }

    testWidgets('progress is linear: half way the drawer is at 95 % and the '
        'veil at 30 %', (tester) async {
      final controller = await pumpDrawer(tester);
      final seen = <double>[];
      controller.progress.addListener(
        () => seen.add(controller.progress.value),
      );
      controller.open();
      await tester.pump();
      await tester.pump(LnMotion.drawer ~/ 2);
      final p = controller.progress.value;
      expect(p, inExclusiveRange(0, 1));
      expect(pageRect(tester).left, closeTo((393 - 82) * p, 0.01));
      final drawer = tester.getRect(find.byKey(const ValueKey('drawer')));
      expect(drawer.width, closeTo((393 - 82) * (0.9 + 0.1 * p), 0.01));
      final veil = tester
          .widgetList<ColoredBox>(find.byType(ColoredBox))
          .map((b) => b.color)
          .where((c) => c.a > 0 && c.a < 1)
          .toList();
      expect(
        veil.any((c) => (c.a - 0.6 * p).abs() < 0.01),
        isTrue,
        reason: 'a veil of the canvas colour at 0.6·p',
      );
      await tester.pumpAndSettle();
      expect(seen.last, 1);
      expect(seen, orderedEquals([...seen]..sort()));
    });

    testWidgets(
      'a tap on the card closes it, so does a drag toward the start',
      (tester) async {
        final controller = await pumpDrawer(tester);
        controller.open();
        await tester.pumpAndSettle();
        await tester.tapAt(const Offset(393 - 40, 400));
        await tester.pumpAndSettle();
        expect(controller.isOpen, isFalse);
        expect(pageRect(tester).left, 0);

        controller.open();
        await tester.pumpAndSettle();
        await tester.dragFrom(
          const Offset(393 - 40, 400),
          const Offset(-200, 0),
        );
        await tester.pumpAndSettle();
        expect(controller.isOpen, isFalse);
        expect(controller.progress.value, 0);
      },
    );

    for (final direction in TextDirection.values) {
      testWidgets('a drag from the start edge (inside the gesture inset) opens '
          'it (${direction.name})', (tester) async {
        final rtl = direction == TextDirection.rtl;
        final controller = await pumpDrawer(tester, direction: direction);
        // 24 dp system gesture inset + the 20 dp strip.
        final start = Offset(rtl ? 393 - 30 : 30, 400);
        final gesture = await tester.startGesture(start);
        await gesture.moveBy(Offset(rtl ? -40 : 40, 0));
        await gesture.moveBy(Offset(rtl ? -60 : 60, 0));
        await tester.pump();
        expect(controller.progress.value, greaterThan(0));
        expect(controller.isOpen, isFalse, reason: 'not released yet');
        await gesture.moveBy(Offset(rtl ? -120 : 120, 0));
        await gesture.up();
        await tester.pumpAndSettle();
        expect(controller.isOpen, isTrue);
        expect(controller.progress.value, 1);
      });
    }

    testWidgets('the edge strip yields to swipe to reply on a message under '
        'it', (tester) async {
      var replies = 0;
      final controller = await pumpDrawer(
        tester,
        page: Align(
          alignment: AlignmentDirectional.centerStart,
          child: Padding(
            padding: const EdgeInsetsDirectional.only(start: 16),
            child: MessageBubble.agent(
              'An agent message that wraps onto a second line here',
              onSwipeReply: () => replies++,
              replyLabel: 'Reply',
            ),
          ),
        ),
      );
      final bubble = tester.getRect(find.byType(MessageBubble));
      // Inside both the strip (24–44 dp, after the gesture inset) and the bubble.
      final gesture = await tester.startGesture(Offset(30, bubble.center.dy));
      for (var i = 0; i < 9; i++) {
        await gesture.moveBy(const Offset(10, 0));
        await tester.pump();
      }
      expect(controller.progress.value, 0);
      await gesture.up();
      await tester.pumpAndSettle();
      expect(replies, 1);
      expect(controller.isOpen, isFalse);

      // Beside the message, the same drag opens the drawer.
      await tester.dragFrom(
        Offset(30, bubble.bottom + 60),
        const Offset(200, 0),
      );
      await tester.pumpAndSettle();
      expect(controller.isOpen, isTrue);
    });

    testWidgets('back during an edge drag closes the drawer and keeps the '
        'page', (tester) async {
      final controller = LnDrawerController();
      addTearDown(controller.dispose);
      final nav = GlobalKey<NavigatorState>();
      setGoldenViewport(tester);
      await tester.pumpWidget(
        lnTestApp(
          padding: _insets,
          child: Navigator(
            key: nav,
            onGenerateRoute: (_) => MaterialPageRoute<void>(
              builder: (_) => const ColoredBox(color: Color(0xFF0000FF)),
            ),
          ),
        ),
      );
      nav.currentState!.push(
        MaterialPageRoute<void>(
          builder: (_) => LnDrawerScaffold(
            controller: controller,
            drawerLabel: 'Chats',
            closeLabel: 'Close chats',
            drawer: const SizedBox.expand(),
            child: const SizedBox.expand(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final gesture = await tester.startGesture(const Offset(10, 400));
      await gesture.moveBy(const Offset(30, 0));
      await gesture.moveBy(const Offset(100, 0));
      await tester.pump();
      expect(controller.progress.value, greaterThan(0));
      expect(controller.isOpen, isFalse);
      expect(nav.currentState!.canPop(), isTrue);
      await nav.currentState!.maybePop();
      await tester.pump();
      await gesture.up();
      await tester.pumpAndSettle();
      expect(find.byType(LnDrawerScaffold), findsOneWidget);
      expect(controller.progress.value, 0);
      // Closed, back leaves the page as usual.
      await nav.currentState!.maybePop();
      await tester.pumpAndSettle();
      expect(find.byType(LnDrawerScaffold), findsNothing);
    });

    testWidgets('a drag outside the strip does not open it', (tester) async {
      final controller = await pumpDrawer(tester);
      await tester.dragFrom(const Offset(200, 400), const Offset(200, 0));
      await tester.pumpAndSettle();
      expect(controller.progress.value, 0);
    });

    testWidgets('Android back closes the drawer first', (tester) async {
      final controller = await pumpDrawer(tester);
      controller.open();
      await tester.pumpAndSettle();
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(controller.isOpen, isFalse);
      expect(find.byType(LnDrawerScaffold), findsOneWidget);
    });

    testWidgets('reduced motion jumps', (tester) async {
      final controller = await pumpDrawer(tester, reduced: true);
      controller.open();
      await tester.pump();
      expect(controller.progress.value, 1);
      expect(pageRect(tester).left, 393 - 82);
      controller.close();
      await tester.pump();
      expect(controller.progress.value, 0);
    });

    testWidgets('semantics: a named drawer region, the card a close button, '
        'the page hidden while open', (tester) async {
      final handle = tester.ensureSemantics();
      final controller = await pumpDrawer(tester);
      expect(find.semantics.byLabel('Close chats'), findsNothing);
      expect(find.semantics.byLabel(RegExp('^Chats, 3 unread')), findsOne);
      controller.open();
      await tester.pumpAndSettle();
      final region = tester.getSemantics(find.byKey(const ValueKey('drawer')));
      var node = region;
      var named = false;
      while (true) {
        if (node.label == 'Chats' &&
            node.flagsCollection.scopesRoute &&
            node.flagsCollection.namesRoute) {
          named = true;
          break;
        }
        if (node.parent == null) break;
        node = node.parent!;
      }
      expect(named, isTrue);
      expect(
        tester.getSemantics(find.bySemanticsLabel('Close chats')),
        matchesSemantics(
          label: 'Close chats',
          isButton: true,
          hasTapAction: true,
          hasDismissAction: true,
        ),
      );
      expect(find.semantics.byLabel(RegExp('^Chats, 3 unread')), findsNothing);
      // The dismiss action closes it.
      tester.semantics.performAction(
        find.semantics.byLabel('Close chats'),
        SemanticsAction.dismiss,
      );
      await tester.pumpAndSettle();
      expect(controller.isOpen, isFalse);
      handle.dispose();
    });

    testWidgets('focus moves into the drawer and the page drops its focus', (
      tester,
    ) async {
      final field = FocusNode();
      addTearDown(field.dispose);
      final controller = await pumpDrawer(
        tester,
        page: Center(
          child: Material(child: TextField(focusNode: field)),
        ),
      );
      field.requestFocus();
      await tester.pump();
      expect(field.hasFocus, isTrue);
      controller.open();
      await tester.pumpAndSettle();
      expect(field.hasFocus, isFalse);
      final drawerScope = FocusScope.of(
        tester.element(find.byType(_DrawerList)),
      );
      expect(drawerScope.hasFocus, isTrue);
    });

    for (final b in Brightness.values) {
      for (final d in TextDirection.values) {
        testWidgets('golden open ${_variant(b, d)}', (tester) async {
          await withRealShadows(() async {
            final controller = await pumpDrawer(
              tester,
              direction: d,
              brightness: b,
            );
            controller.open();
            await tester.pumpAndSettle();
            await expectLater(
              find.byType(MaterialApp),
              matchesGoldenFile('goldens/round4_drawer_${_variant(b, d)}.png'),
            );
          });
        });
      }
    }

    testWidgets('golden half way dark_rtl', (tester) async {
      await withRealShadows(() async {
        final controller = await pumpDrawer(
          tester,
          direction: TextDirection.rtl,
          brightness: Brightness.dark,
        );
        await tester.dragFrom(
          const Offset(393 - 30, 400),
          const Offset(-160, 0),
        );
        await tester.pump();
        expect(controller.progress.value, inExclusiveRange(0.3, 0.7));
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/round4_drawer_half_dark_rtl.png'),
        );
        await tester.pumpAndSettle();
      });
    });
  });

  group('Composer hold-to-talk', () {
    Future<(TextEditingController, List<String>)> pumpComposer(
      WidgetTester tester, {
      String text = '',
      bool inputEnabled = true,
    }) async {
      final controller = TextEditingController(text: text);
      addTearDown(controller.dispose);
      final events = <String>[];
      await _pump(
        tester,
        Align(
          alignment: Alignment.bottomCenter,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Composer(
              controller: controller,
              placeholder: 'Message Lonora',
              inputEnabled: inputEnabled,
              onAttach: () => events.add('attach'),
              onMic: () => events.add('mic'),
              onSend: (_) => events.add('send'),
              holdToTalk: ComposerHoldToTalk(
                placeholder: 'Hold to talk, tap to type',
                onStart: () => events.add('start'),
                onMove: (o) =>
                    events.add('move ${o.dx.round()},${o.dy.round()}'),
                onEnd: () => events.add('end'),
                onCancel: () => events.add('cancel'),
              ),
            ),
          ),
        ),
      );
      return (controller, events);
    }

    TextField field(WidgetTester tester) =>
        tester.widget<TextField>(find.byType(TextField));

    testWidgets('armed: the hold hint; a long press anywhere holds and '
        'reports moves until the finger lifts', (tester) async {
      final (_, events) = await pumpComposer(tester);
      expect(field(tester).decoration!.hintText, 'Hold to talk, tap to type');
      final gesture = await tester.startGesture(
        tester.getCenter(find.byType(TextField)),
      );
      await tester.pump(kLongPressTimeout + const Duration(milliseconds: 50));
      expect(events, ['start']);
      await gesture.moveBy(const Offset(-30, -12));
      await tester.pump();
      await gesture.up();
      await tester.pump();
      expect(events, ['start', 'move -30,-12', 'end']);
      // No paste menu, no focus.
      expect(field(tester).focusNode!.hasFocus, isFalse);
    });

    testWidgets('a hold the system cancels reports onCancel', (tester) async {
      final (_, events) = await pumpComposer(tester);
      final gesture = await tester.startGesture(
        tester.getCenter(find.byType(TextField)),
      );
      await tester.pump(kLongPressTimeout + const Duration(milliseconds: 50));
      await gesture.cancel();
      await tester.pumpAndSettle();
      expect(events, ['start', 'cancel']);
    });

    testWidgets('a tap focuses the field and the composer\'s own placeholder '
        'returns; focused, a long press is the field\'s again', (tester) async {
      final (_, events) = await pumpComposer(tester);
      await tester.tap(find.byType(TextField));
      await tester.pumpAndSettle();
      expect(field(tester).focusNode!.hasFocus, isTrue);
      expect(field(tester).decoration!.hintText, 'Message Lonora');
      await tester.longPress(find.byType(TextField));
      await tester.pumpAndSettle();
      expect(events, isEmpty);
    });

    testWidgets('a long press on «+» or the mic holds too; their taps stay', (
      tester,
    ) async {
      final (_, events) = await pumpComposer(tester);
      await tester.longPress(find.bySemanticsLabel('Add attachment'));
      await tester.pumpAndSettle();
      await tester.longPress(find.bySemanticsLabel('Voice input'));
      await tester.pumpAndSettle();
      expect(events, ['start', 'end', 'start', 'end']);
      events.clear();
      await tester.tap(find.bySemanticsLabel('Add attachment'));
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel('Voice input'));
      await tester.pumpAndSettle();
      expect(events, ['attach', 'mic']);
    });

    testWidgets('with text there is no hold', (tester) async {
      final (_, events) = await pumpComposer(tester, text: 'draft');
      expect(field(tester).decoration!.hintText, 'Message Lonora');
      await tester.longPress(find.bySemanticsLabel('Add attachment'));
      await tester.pumpAndSettle();
      await tester.longPress(find.byType(TextField));
      await tester.pumpAndSettle();
      expect(events.where((e) => e != 'attach'), isEmpty);
    });

    testWidgets('text set by code disarms the hold; the field\'s own long '
        'press returns', (tester) async {
      final (controller, events) = await pumpComposer(tester);
      // A draft restored after mount, shared text, dictation: not typed, the field unfocused.
      controller.text = 'draft restored';
      await tester.pump();
      expect(field(tester).decoration!.hintText, 'Message Lonora');
      final gesture = await tester.startGesture(
        tester.getCenter(find.byType(TextField)),
      );
      await tester.pump(kLongPressTimeout + const Duration(milliseconds: 50));
      await gesture.up();
      await tester.pumpAndSettle();
      expect(events, isEmpty);
      // The field took the long press: it selects and focuses.
      expect(field(tester).focusNode!.hasFocus, isTrue);
      expect(controller.selection.isValid, isTrue);

      // Cleared by code while unfocused, the hold is armed again.
      field(tester).focusNode!.unfocus();
      controller.clear();
      await tester.pump();
      expect(field(tester).decoration!.hintText, 'Hold to talk, tap to type');
      await tester.longPress(find.byType(TextField));
      await tester.pumpAndSettle();
      expect(events, ['start', 'end']);
    });

    testWidgets('a new controller with text starts disarmed', (tester) async {
      final events = <String>[];
      Widget composer(TextEditingController c) => Align(
        alignment: Alignment.bottomCenter,
        child: Composer(
          controller: c,
          placeholder: 'Message Lonora',
          onMic: () {},
          holdToTalk: ComposerHoldToTalk(onStart: () => events.add('start')),
        ),
      );
      final empty = TextEditingController();
      final full = TextEditingController(text: 'draft');
      addTearDown(empty.dispose);
      addTearDown(full.dispose);
      await _pump(tester, composer(empty));
      await _pump(tester, composer(full));
      await tester.longPress(find.byType(TextField));
      await tester.pumpAndSettle();
      expect(events, isEmpty);
      // The new controller's changes are followed: emptied, it arms.
      FocusManager.instance.primaryFocus?.unfocus();
      full.clear();
      await tester.pump();
      await tester.longPress(find.byType(TextField));
      await tester.pumpAndSettle();
      expect(events, ['start']);
    });

    testWidgets('the recording bar slot keeps the composer mounted: the hold '
        'reports to the end, and no new hold starts while it shows', (
      tester,
    ) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      final events = <String>[];
      final recording = ValueNotifier<bool>(false);
      addTearDown(recording.dispose);
      await _pump(
        tester,
        Align(
          alignment: Alignment.bottomCenter,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: ValueListenableBuilder<bool>(
              valueListenable: recording,
              builder: (context, rec, _) => Composer(
                controller: controller,
                placeholder: 'Message',
                onMic: () {},
                recordingBar: rec
                    ? ComposerRecordingBar(
                        elapsed: const Duration(seconds: 1),
                        hint: 'Slide to cancel',
                        locked: true,
                        onCancel: () => events.add('tap cancel'),
                        onSend: () => events.add('tap send'),
                      )
                    : null,
                holdToTalk: ComposerHoldToTalk(
                  onStart: () {
                    events.add('start');
                    recording.value = true;
                  },
                  onMove: (_) => events.add('move'),
                  onEnd: () => events.add('end'),
                  onCancel: () => events.add('cancel'),
                ),
              ),
            ),
          ),
        ),
      );
      final composer = tester.getRect(find.byType(Composer));
      final gesture = await tester.startGesture(
        tester.getCenter(find.byType(TextField)),
      );
      await tester.pump(kLongPressTimeout + const Duration(milliseconds: 50));
      await tester.pump();
      // The bar stands in for the pill, bottom-aligned with it; the field is hidden and inert.
      expect(find.byType(ComposerRecordingBar), findsOneWidget);
      final bar = tester.getRect(find.byType(ComposerRecordingBar));
      expect(bar.bottom, composer.bottom);
      expect(find.byType(TextField).hitTestable(), findsNothing);
      await gesture.moveBy(const Offset(-40, 0));
      await tester.pump();
      await gesture.up();
      await tester.pump();
      expect(events, ['start', 'move', 'end']);

      // Locked: the bar's buttons work and a long press starts nothing new.
      await tester.longPress(find.text('00:01'));
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel('Send voice note'));
      await tester.pumpAndSettle();
      expect(events, ['start', 'move', 'end', 'tap send']);
    });

    testWidgets('a hold keeps reporting when recording disables the input', (
      tester,
    ) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      final events = <String>[];
      var recording = false;
      late StateSetter setOuter;
      await _pump(
        tester,
        StatefulBuilder(
          builder: (context, setState) {
            setOuter = setState;
            return Align(
              alignment: Alignment.bottomCenter,
              child: Composer(
                controller: controller,
                placeholder: 'Message',
                inputEnabled: !recording,
                onMic: () {},
                holdToTalk: ComposerHoldToTalk(
                  onStart: () {
                    events.add('start');
                    setOuter(() => recording = true);
                  },
                  onMove: (_) => events.add('move'),
                  onEnd: () => events.add('end'),
                ),
              ),
            );
          },
        ),
      );
      final gesture = await tester.startGesture(
        tester.getCenter(find.byType(TextField)),
      );
      await tester.pump(kLongPressTimeout + const Duration(milliseconds: 50));
      await tester.pump();
      expect(recording, isTrue);
      await gesture.moveBy(const Offset(0, -40));
      await tester.pump();
      await gesture.up();
      await tester.pump();
      expect(events, ['start', 'move', 'end']);
    });

    testWidgets('no semantics long-press action (it would end at once)', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpComposer(tester);
      final data = tester
          .getSemantics(find.byType(Composer))
          .getSemanticsData();
      expect(data.hasAction(SemanticsAction.longPress), isFalse);
      handle.dispose();
    });

    testWidgets('the reply bar is its own pill 7 dp above the composer', (
      tester,
    ) async {
      var closed = 0;
      await _pump(
        tester,
        Align(
          alignment: Alignment.bottomCenter,
          child: Composer(
            controller: TextEditingController(),
            placeholder: 'Message',
            replyBar: ComposerReplyBar(
              text: 'It crossed 140 this morning.',
              onClose: () => closed++,
            ),
          ),
        ),
      );
      final bar = tester.getRect(find.byType(ComposerReplyBar));
      final pill = tester.getRect(
        find
            .descendant(
              of: find.byType(Composer),
              matching: find.byType(TextField),
            )
            .first,
      );
      expect(bar.height, LnSize.composerHeight);
      // The composer pill starts 7 dp under the bar.
      final composerPill = tester.getRect(
        find
            .ancestor(
              of: find.byType(TextField),
              matching: find.byType(Container),
            )
            .last,
      );
      expect(composerPill.top - bar.bottom, 7);
      expect(pill.top, greaterThan(bar.bottom));
      final quote = tester.widget<Text>(
        find.text('It crossed 140 this morning.'),
      );
      expect(quote.style!.fontSize, 16);
      expect(quote.style!.color, LnPalette.light.fgMuted);
      await tester.tap(find.bySemanticsLabel('Cancel reply'));
      await tester.pumpAndSettle();
      expect(closed, 1);
    });
  });

  group('ComposerRecordingBar', () {
    testWidgets('Latin mm:ss with two minute digits', (tester) async {
      for (final (elapsed, shown) in [
        (const Duration(seconds: 5), '00:05'),
        (const Duration(seconds: 65, milliseconds: 900), '01:05'),
        (const Duration(minutes: 12), '12:00'),
        (const Duration(seconds: -3), '00:00'),
      ]) {
        await _pump(
          tester,
          Center(child: ComposerRecordingBar(elapsed: elapsed)),
          direction: TextDirection.rtl,
        );
        expect(find.text(shown), findsOneWidget);
      }
    });

    for (final direction in TextDirection.values) {
      testWidgets('cancel at the start, send at the end, the hint 8 dp above '
          '(${direction.name})', (tester) async {
        final rtl = direction == TextDirection.rtl;
        await _pump(
          tester,
          const Align(
            alignment: Alignment.bottomCenter,
            child: Padding(
              padding: EdgeInsets.all(20),
              child: ComposerRecordingBar(
                elapsed: Duration(seconds: 5),
                levels: [0.2, 0.6, 0.9],
                hint: 'Release to cancel',
              ),
            ),
          ),
          direction: direction,
        );
        final bar = tester.getRect(find.byType(ComposerRecordingBar));
        final x = tester.getRect(find.byIcon(FIcons.x));
        final arrow = tester.getRect(find.byType(LnGlyph));
        final pillTop = bar.bottom - 48;
        expect(
          tester.getRect(find.text('Release to cancel')).bottom,
          pillTop - 8,
        );
        // Circles 24 dp in from the pill's ends: centred in 48 dp slots at the ends.
        if (rtl) {
          expect(bar.right - x.center.dx, 24);
          expect(arrow.center.dx - bar.left, 24);
        } else {
          expect(x.center.dx - bar.left, 24);
          expect(bar.right - arrow.center.dx, 24);
        }
        expect(find.text('00:05'), findsOneWidget);
      });
    }

    testWidgets('holding: the circles are not buttons; locked: cancel, '
        'pause and send are', (tester) async {
      final handle = tester.ensureSemantics();
      final taps = <String>[];
      Widget bar({required bool locked}) => Align(
        alignment: Alignment.bottomCenter,
        child: ComposerRecordingBar(
          elapsed: const Duration(seconds: 1),
          locked: locked,
          onCancel: () => taps.add('cancel'),
          onSend: () => taps.add('send'),
          onPause: () => taps.add('pause'),
        ),
      );
      await _pump(tester, bar(locked: false));
      await tester.tap(find.bySemanticsLabel('Send voice note'));
      await tester.pumpAndSettle();
      expect(taps, isEmpty);
      expect(find.bySemanticsLabel('Pause'), findsNothing);
      await _pump(tester, bar(locked: true));
      await tester.tap(find.bySemanticsLabel('Cancel recording'));
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel('Pause'));
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel('Send voice note'));
      await tester.pumpAndSettle();
      expect(taps, ['cancel', 'pause', 'send']);
      expect(
        tester.getSemantics(find.bySemanticsLabel('Recording length')),
        matchesSemantics(label: 'Recording length', value: '00:01'),
      );
      handle.dispose();
    });

    testWidgets('every button and the reply bar\'s ✕ is a 48 dp target', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await _pump(
        tester,
        Align(
          alignment: Alignment.bottomCenter,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ComposerReplyBar(text: 'Quoted', onClose: () {}),
                const SizedBox(height: 20),
                ComposerRecordingBar(
                  elapsed: const Duration(seconds: 5),
                  locked: true,
                  onCancel: () {},
                  onSend: () {},
                  onPause: () {},
                ),
              ],
            ),
          ),
        ),
      );
      for (final label in [
        'Cancel recording',
        'Pause',
        'Send voice note',
        'Cancel reply',
      ]) {
        expect(
          tester.getSize(
            find
                .ancestor(
                  of: find.bySemanticsLabel(label),
                  matching: find.byType(LnTappable),
                )
                .first,
          ),
          const Size.square(48),
          reason: label,
        );
      }
      // The visuals keep their place: the circles' centres 24 dp in.
      final bar = tester.getRect(
        find
            .descendant(
              of: find.byType(ComposerRecordingBar),
              matching: find.byType(DecoratedBox),
            )
            .first,
      );
      expect(bar.height, 48);
      expect(
        tester.getRect(find.byIcon(FIcons.x).last).center.dx - bar.left,
        24,
      );
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      handle.dispose();
    });

    testWidgets('the armed cancel circle turns red', (tester) async {
      await _pump(
        tester,
        const Align(
          alignment: Alignment.bottomCenter,
          child: ComposerRecordingBar(
            elapsed: Duration.zero,
            cancelArmed: true,
          ),
        ),
      );
      await tester.pumpAndSettle();
      final circle = tester.widget<AnimatedContainer>(
        find.ancestor(
          of: find.byIcon(FIcons.x),
          matching: find.byType(AnimatedContainer),
        ),
      );
      expect(
        (circle.decoration! as BoxDecoration).color,
        LnPalette.light.error,
      );
    });
  });

  group('kit sheet goldens', () {
    for (final b in Brightness.values) {
      for (final d in TextDirection.values) {
        testWidgets('composer and chrome ${_variant(b, d)}', (tester) async {
          await withRealShadows(() async {
            await _pump(
              tester,
              Builder(
                builder: (context) => ListView(
                  padding: const EdgeInsets.fromLTRB(20, 48, 20, 24),
                  children: [
                    Row(
                      children: [
                        MenuPillButton(semanticLabel: 'Chats', onTap: () {}),
                        const SizedBox(width: 8),
                        MenuPillButton(
                          semanticLabel: 'Chats',
                          unreadCount: 3,
                          onTap: () {},
                        ),
                        const SizedBox(width: 8),
                        MenuPillButton(
                          semanticLabel: 'Chats',
                          unreadCount: 120,
                          onTap: () {},
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    Composer(
                      controller: TextEditingController(),
                      placeholder: _t(context, 'Message Lonora', 'راسل لونورا'),
                      onMic: () {},
                      holdToTalk: ComposerHoldToTalk(
                        placeholder: _t(
                          context,
                          'Hold to talk, tap to type',
                          'اضغط مطولاً للتحدث، انقر للكتابة',
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Composer(
                      controller: TextEditingController(),
                      placeholder: _t(context, 'Message Lonora', 'راسل لونورا'),
                      onMic: () {},
                      replyBar: ComposerReplyBar(
                        text: _t(
                          context,
                          'It crossed 140 this morning, up 3.2 %.',
                          'تجاوز 140 صباح اليوم بارتفاع 3.2 %.',
                        ),
                        onClose: () {},
                      ),
                    ),
                    const SizedBox(height: 16),
                    ComposerReplyBar(
                      icon: FIcons.pencil,
                      title: _t(context, 'Editing message', 'تعديل الرسالة'),
                      text: _t(context, 'See you at 9', 'أراك في 9'),
                      onClose: () {},
                    ),
                    const SizedBox(height: 16),
                    ComposerRecordingBar(
                      elapsed: const Duration(seconds: 5),
                      levels: const [
                        0.1,
                        0.3,
                        0.7,
                        0.5,
                        0.9,
                        0.4,
                        0.2,
                        0.6,
                        0.8,
                        0.3,
                        0.5,
                        0.2,
                        0.4,
                      ],
                      cancelArmed: true,
                      hint: _t(
                        context,
                        'Release to cancel',
                        'ارفع إصبعك للإلغاء',
                      ),
                    ),
                    const SizedBox(height: 16),
                    ComposerRecordingBar(
                      elapsed: const Duration(seconds: 61),
                      locked: true,
                      onCancel: () {},
                      onSend: () {},
                      onPause: () {},
                      hint: _t(context, '‹ Slide to cancel', '‹ اسحب للإلغاء'),
                    ),
                    const SizedBox(height: 16),
                    ColoredBox(
                      color: context.ln.colors.drawerSurface,
                      child: Column(
                        children: [
                          ChatListRow.compact(
                            avatar: const FakeAvatar(
                              FakeShape.circle,
                              FakeAvatar.violet,
                            ),
                            title: _t(context, 'Lonora', 'لونورا'),
                            current: true,
                            onTap: () {},
                          ),
                          ChatListRow.compact(
                            avatar: const FakeAvatar(
                              FakeShape.square,
                              FakeAvatar.green,
                            ),
                            title: _t(context, 'Market Watch', 'مراقب السوق'),
                            preview: _t(
                              context,
                              'NVDA crossed 140.',
                              'تجاوز سهم إنفيديا 140.',
                            ),
                            time: '10:12',
                            unreadCount: 2,
                            onTap: () {},
                          ),
                          ChatListRow.compact(
                            avatar: const FakeAvatar(
                              FakeShape.hexagon,
                              FakeAvatar.cyan,
                            ),
                            title: 'Crypto Desk',
                            unreadDot: true,
                            muted: true,
                            pinned: true,
                            onTap: () {},
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              direction: d,
              brightness: b,
            );
            await tester.pumpAndSettle();
            await expectLater(
              find.byType(MaterialApp),
              matchesGoldenFile('goldens/round4_kit_${_variant(b, d)}.png'),
            );
          });
        });
      }
    }
  });
}
