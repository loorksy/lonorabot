// Composite screens built from design-system components (chat list, and chat with an approval
// card) to check how the pieces sit together on a full screen. Placeholder shapes stand in for
// avatars and artwork. The simulated top inset (48 dp) stands in for the status bar; the bottom
// inset is 0.
//
// Regenerate with: flutter test --update-goldens test/design
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/design/design.dart';

import 'fonts.dart';
import 'harness.dart';

const _insets = EdgeInsets.only(top: 48);

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

Widget _tabBar() => FloatingTabBar(
  items: _tabs,
  selectedIndex: 0,
  onSelect: (_) {},
  actionIcon: const LnGlyph(LnGlyphs.attention),
  actionLabel: 'Needs your attention',
  onAction: () {},
);

/// First list row's top edge (dp from the screen top) on the chat-list screen.
const double chatListFirstRowTop = 111;

/// First message's top edge (dp from the screen top) on the chat screen.
const double chatFirstMessageTop = 152.5;

class ChatListComposite extends StatelessWidget {
  const ChatListComposite({super.key});

  static const _rows = [
    (
      FakeShape.circle,
      FakeAvatar.violet,
      'Lonora',
      'Your week so far: three alerts fired and nothing needs you.',
      '10:12',
    ),
    (
      FakeShape.square,
      FakeAvatar.orange,
      'Gold desk',
      "Gold is testing 2,350 again. I’ll tell you if it breaks.",
      '09:58',
    ),
    (
      FakeShape.hexagon,
      FakeAvatar.cyan,
      'Morning news',
      "Today’s brief: CPI at 8:30, then two Fed speakers.",
      '08:05',
    ),
    (
      null,
      null,
      'Trading desk',
      'Both stops are in place for the night.',
      'Thursday',
    ),
    (
      FakeShape.diamond,
      FakeAvatar.green,
      'Research',
      'I summarised the three filings you asked about.',
      'Thursday',
    ),
    (
      FakeShape.circle,
      FakeAvatar.slate,
      'FX watcher',
      "EURUSD is back inside yesterday’s range.",
      'Nov 22',
    ),
    (
      FakeShape.diamond,
      FakeAvatar.violet,
      'Earnings',
      'Two of your holdings report after the close today.',
      'Nov 21',
    ),
    (
      FakeShape.square,
      FakeAvatar.slate,
      'Macro calendar',
      'Next week: a rate decision on Wednesday, jobs on Friday.',
      'Nov 21',
    ),
  ];

  @override
  Widget build(BuildContext context) => Stack(
    children: [
      Positioned(
        top: chatListFirstRowTop,
        left: 0,
        right: 0,
        child: Column(
          children: [
            for (final (shape, color, title, preview, time) in _rows)
              ChatListRow(
                avatar: shape == null
                    ? const GroupAvatarPair(
                        first: FakeAvatar(FakeShape.square, FakeAvatar.orange),
                        second: FakeAvatar(FakeShape.hexagon, FakeAvatar.cyan),
                      )
                    : FakeAvatar(shape, color!),
                title: title,
                preview: preview,
                time: time,
                onTap: () {},
              ),
          ],
        ),
      ),
      ScreenHeader(
        leading: CircleIconButton(
          icon: const Icon(FIcons.search),
          semanticLabel: 'Search',
          onTap: () {},
        ),
        trailing: CircleIconButton(
          icon: const Icon(FIcons.plus),
          semanticLabel: 'New chat',
          onTap: () {},
        ),
      ),
      const Positioned(left: 0, right: 0, bottom: 0, child: BottomChromeFade()),
      Positioned(left: 0, right: 0, bottom: 0, child: _tabBar()),
    ],
  );
}

class ChatComposite extends StatefulWidget {
  const ChatComposite({super.key});

  @override
  State<ChatComposite> createState() => _ChatCompositeState();
}

class _ChatCompositeState extends State<ChatComposite> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottom = FloatingTabBar.occupiedHeight(context);
    return Stack(
      children: [
        Positioned(
          top: chatFirstMessageTop,
          left: LnSpace.pageGutter,
          right: LnSpace.pageGutter,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Align(
                alignment: AlignmentDirectional.centerEnd,
                child: MessageBubble.user(
                  'Buy 2 oz of gold if it dips below 2,340, and ask me before the order goes out.',
                ),
              ),
              BubbleGroup.spacer(sameSender: false),
              const Align(
                alignment: AlignmentDirectional.centerStart,
                child: MessageBubble.agent(
                  'Gold is at 2,338.40. Here’s the order.',
                ),
              ),
              BubbleGroup.spacer(sameSender: true),
              const Align(
                alignment: AlignmentDirectional.centerStart,
                child: ActionCard(
                  header: FakeChartIllustration(),
                  body: Text(
                    'Gold desk wants to buy 2 oz of XAUUSD at 2,338.40.',
                  ),
                  actions: [BlockButton(label: 'Approved')],
                ),
              ),
              const SizedBox(height: 8),
              InlineEventRow(
                icon: const Icon(FIcons.circleCheck),
                label: 'Order filled',
                alignment: InlineEventAlignment.start,
                onTap: () {},
              ),
              const SizedBox(height: 1),
              const Align(
                alignment: AlignmentDirectional.centerStart,
                child: MessageBubble.agent(
                  'Bought 2 oz at 2,338.40. The stop sits at 2,310 and I’ll watch it overnight.',
                ),
              ),
            ],
          ),
        ),
        ScreenHeader(
          leading: CircleIconButton(
            icon: const LnGlyph(LnGlyphs.menu),
            semanticLabel: 'Chats',
            onTap: () {},
          ),
          center: TitleCapsule(
            avatar: const FakeAvatar(FakeShape.square, FakeAvatar.orange),
            title: 'Gold desk',
            onTap: () {},
          ),
          trailing: CircleIconButton(
            icon: const Icon(FIcons.squareUser),
            semanticLabel: 'Profile',
            onTap: () {},
          ),
        ),
        Positioned(
          left: LnSpace.chromeGutter,
          right: LnSpace.chromeGutter,
          bottom: bottom + LnSpace.composerToBar,
          child: Composer(
            controller: _controller,
            placeholder: 'Message Gold desk…',
            onMic: () {},
          ),
        ),
        Positioned(left: 0, right: 0, bottom: 0, child: _tabBar()),
      ],
    );
  }
}

void main() {
  setUpAll(loadAppFonts);

  final screens = <String, Widget>{
    'chat_list': const ChatListComposite(),
    'chat': const ChatComposite(),
  };
  final variants = [
    (Brightness.light, TextDirection.ltr),
    (Brightness.dark, TextDirection.ltr),
    (Brightness.light, TextDirection.rtl),
  ];

  for (final MapEntry(key: name, value: screen) in screens.entries) {
    for (final (brightness, direction) in variants) {
      final variant = '${brightness.name}_${direction.name}';
      testWidgets('composite $name $variant', (tester) async {
        setGoldenViewport(tester);
        await withRealShadows(() async {
          await tester.pumpWidget(
            lnTestApp(
              child: screen,
              brightness: brightness,
              direction: direction,
              padding: _insets,
            ),
          );
          await tester.pump(const Duration(milliseconds: 600));
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile('goldens/composite_${name}_$variant.png'),
          );
        });
      });
    }
  }
}
