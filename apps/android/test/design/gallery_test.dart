// Golden gallery of every design-system component in light/dark × LTR/RTL at 393 × 852 (DPR 2).
//
// Regenerate with: flutter test --update-goldens test/design
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/design/design.dart';

import 'fonts.dart';
import 'harness.dart';

/// Picks the Arabic string in RTL so goldens exercise real Arabic shaping.
String t(BuildContext context, String en, String ar) =>
    Directionality.of(context) == TextDirection.rtl ? ar : en;

Widget _label(BuildContext context, String text) => Padding(
  padding: const EdgeInsetsDirectional.fromSTEB(16, 14, 16, 6),
  child: Text(
    text.toUpperCase(),
    style: context.ln.text.smallStrong.copyWith(
      color: context.ln.colors.fgSubtle,
    ),
  ),
);

const _bar = [
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
    showDot: true,
  ),
];

class _ChromePage extends StatelessWidget {
  const _ChromePage();

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    return Stack(
      children: [
        ListView(
          padding: EdgeInsets.zero,
          children: [
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
            const SizedBox(height: 8),
            ScreenHeader(
              leading: CircleIconButton(
                icon: const LnGlyph(LnGlyphs.menu),
                semanticLabel: 'Menu',
                onTap: () {},
              ),
              center: TitleCapsule(
                avatar: const FakeAvatar(FakeShape.square, FakeAvatar.orange),
                title: t(context, 'Gold desk', 'مكتب الذهب'),
                onTap: () {},
              ),
              trailing: CircleIconButton(
                icon: const Icon(FIcons.squareUser),
                semanticLabel: 'Profile',
                badge: true,
                onTap: () {},
              ),
            ),
            LargeTitleHeader(
              title: t(context, 'Market', 'السوق'),
              trailing: Text(t(context, 'Paper account', 'حساب تجريبي')),
            ),
            _label(context, 'Badges'),
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(horizontal: 16),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  const UnreadPill(count: 3),
                  const UnreadPill(count: 120),
                  const UnreadPill(count: 7, muted: true),
                  const DotBadge(),
                  StatusChip(
                    label: t(context, 'Running', 'قيد التشغيل'),
                    kind: StatusChipKind.running,
                  ),
                  StatusChip(
                    label: t(context, 'Waiting', 'بانتظارك'),
                    kind: StatusChipKind.waiting,
                  ),
                  const StatusChip(label: 'Done', kind: StatusChipKind.success),
                  const StatusChip(label: 'Failed', kind: StatusChipKind.error),
                  const StatusChip(label: 'Paper', kind: StatusChipKind.brand),
                  const StatusChip(label: 'Idle'),
                ],
              ),
            ),
            _label(context, 'Glyphs'),
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(horizontal: 16),
              child: Wrap(
                spacing: 14,
                runSpacing: 10,
                children: [
                  for (final g in LnGlyphs.values) LnGlyph(g, color: c.fg),
                ],
              ),
            ),
            _label(context, 'Typing · jump · spinner'),
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(horizontal: 16),
              child: Row(
                children: [
                  const TypingBubble(),
                  const SizedBox(width: 16),
                  JumpToLatestButton(
                    visible: true,
                    unreadCount: 4,
                    onTap: () {},
                  ),
                  const SizedBox(width: 16),
                  const LnSpinner(),
                ],
              ),
            ),
            _label(context, 'Tab bar · action selected'),
            FloatingTabBar(
              items: _bar,
              selectedIndex: -1,
              onSelect: (_) {},
              actionIcon: const LnGlyph(LnGlyphs.attention),
              actionSelectedIcon: const LnGlyph(LnGlyphs.attentionFilled),
              actionSelected: true,
              actionLabel: 'Attention',
              onAction: () {},
            ),
          ],
        ),
        const Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          child: BottomChromeFade(),
        ),
        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          child: FloatingTabBar(
            items: [
              _bar[0],
              const LnTabItem(
                icon: LnGlyph(LnGlyphs.market),
                selectedIcon: LnGlyph(LnGlyphs.marketFilled),
                label: 'Market',
                badgeCount: 2,
              ),
              _bar[2],
            ],
            selectedIndex: 0,
            onSelect: (_) {},
            actionIcon: const LnGlyph(LnGlyphs.attention),
            actionLabel: 'Attention',
            actionDot: true,
            onAction: () {},
          ),
        ),
      ],
    );
  }
}

class _ConversationPage extends StatelessWidget {
  const _ConversationPage();

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsetsDirectional.symmetric(
      horizontal: 16,
      vertical: 12,
    ),
    children: [
      DateSeparator(label: t(context, 'Today', 'اليوم')),
      Align(
        alignment: AlignmentDirectional.centerEnd,
        child: MessageBubble(
          sender: BubbleSender.user,
          text: t(
            context,
            'Watch NVDA and ping me above 140.',
            'راقب سهم إنفيديا وأخبرني فوق 140.',
          ),
          quote: BubbleQuote(
            author: t(context, 'Lonora', 'لونورا'),
            text: t(
              context,
              'Want me to set a price alert?',
              'هل أضبط تنبيه سعر؟',
            ),
          ),
        ),
      ),
      BubbleGroup.spacer(sameSender: false),
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: MessageBubble.agent(
          t(context, 'Done. I will alert you once.', 'تم. سأنبهك مرة واحدة.'),
          editedLabel: t(context, 'edited', 'معدلة'),
        ),
      ),
      BubbleGroup.spacer(sameSender: true),
      const TypingBubble(),
      BubbleGroup.spacer(sameSender: true),
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: ActionCard(
          header: const FakeChartIllustration(),
          body: Text(
            t(
              context,
              'Gold desk wants to buy 2 oz of XAUUSD at 2,338.40.',
              'يريد مكتب الذهب شراء 2 أونصة من XAUUSD عند 2,338.40.',
            ),
          ),
          actions: [
            BlockButton(
              label: t(context, 'Approve', 'موافقة'),
              onPressed: () {},
            ),
            BlockButton(
              label: t(context, 'Reject', 'رفض'),
              variant: BlockButtonVariant.secondary,
              onPressed: () {},
            ),
          ],
        ),
      ),
      const SizedBox(height: 8),
      InlineEventRow(
        icon: const Icon(FIcons.moonStar),
        label: t(context, 'Memory updated', 'تم تحديث الذاكرة'),
        detail: t(context, '2 changes', 'تغييران'),
        emphasized: true,
        onTap: () {},
      ),
      InlineEventRow(
        icon: const Icon(FIcons.phone),
        label: t(context, 'Call ended', 'انتهت المكالمة'),
        alignment: InlineEventAlignment.start,
        onTap: () {},
      ),
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: MessageBubble.agent(t(context, 'Short.', 'قصير.')),
      ),
    ],
  );
}

class _CardsPage extends StatefulWidget {
  const _CardsPage();

  @override
  State<_CardsPage> createState() => _CardsPageState();
}

class _CardsPageState extends State<_CardsPage> {
  final _empty = TextEditingController();
  final _text = TextEditingController(text: 'Buy 10 AAPL at market');
  final _multi = TextEditingController(text: 'Line one\nLine two\nLine three');

  @override
  void dispose() {
    _empty.dispose();
    _text.dispose();
    _multi.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.symmetric(vertical: 12),
    children: [
      Padding(
        padding: const EdgeInsetsDirectional.symmetric(horizontal: 16),
        child: Align(
          alignment: AlignmentDirectional.centerStart,
          child: ScheduleCard(
            title: t(context, 'Daily market brief', 'ملخص السوق اليومي'),
            onMenu: () {},
            fields: [
              ScheduleField(
                t(context, 'When', 'متى'),
                t(context, 'Every weekday at 8:00 AM', 'كل يوم عمل 8:00 ص'),
              ),
              ScheduleField(
                t(context, 'Lonora will', 'سيقوم لونورا'),
                t(context, 'Summarise overnight moves', 'بتلخيص تحركات الليل'),
              ),
            ],
            action: BlockButton(label: t(context, 'Created', 'تم الإنشاء')),
          ),
        ),
      ),
      _label(context, 'Block buttons'),
      Padding(
        padding: const EdgeInsetsDirectional.symmetric(horizontal: 16),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: BlockButton(label: 'Primary', onPressed: () {}),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: BlockButton(
                    label: 'Brand',
                    variant: BlockButtonVariant.brand,
                    onPressed: () {},
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: BlockButton(
                    label: 'Secondary',
                    variant: BlockButtonVariant.secondary,
                    onPressed: () {},
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: BlockButton(
                    label: 'Delete',
                    variant: BlockButtonVariant.destructive,
                    onPressed: () {},
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                const Expanded(child: BlockButton(label: 'Approved')),
                const SizedBox(width: 8),
                Expanded(
                  child: BlockButton(
                    label: 'Saving',
                    loading: true,
                    onPressed: () {},
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
      _label(context, 'Composer'),
      Padding(
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: LnSpace.chromeGutter,
        ),
        child: Column(
          children: [
            Composer(
              controller: _empty,
              placeholder: t(context, 'Message Lonora', 'راسل لونورا'),
              onMic: () {},
            ),
            const SizedBox(height: 10),
            Composer(
              controller: _text,
              placeholder: 'Message Lonora',
              onSend: (_) {},
              onMic: () {},
            ),
            const SizedBox(height: 10),
            Composer(
              controller: _empty,
              placeholder: 'Message Lonora',
              running: true,
              onStop: () {},
            ),
            const SizedBox(height: 10),
            Composer(
              controller: _multi,
              placeholder: 'Message Lonora',
              onSend: (_) {},
              replyBar: ComposerReplyBar(
                title: t(context, 'Replying to Lonora', 'رد على لونورا'),
                text: 'Done. I will alert you once.',
                onClose: () {},
              ),
              attachments: Row(
                children: [
                  ComposerAttachmentChip(
                    label: 'statement.pdf',
                    progress: 0.6,
                    onRemove: () {},
                  ),
                  const SizedBox(width: 8),
                  Flexible(
                    child: ComposerAttachmentChip(
                      label: 'chart.png',
                      failed: true,
                      onRemove: () {},
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    ],
  );
}

class _ListPage extends StatelessWidget {
  const _ListPage();

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.symmetric(vertical: 8),
    children: [
      ChatListRow(
        avatar: const FakeAvatar(FakeShape.circle, FakeAvatar.violet),
        title: t(context, 'Market Watch', 'مراقب السوق'),
        preview: t(
          context,
          'NVDA crossed 140, up 3.2% today.',
          'تجاوز سهم إنفيديا 140 بارتفاع 3.2٪ اليوم.',
        ),
        time: '10:12',
        unreadCount: 3,
        onTap: () {},
      ),
      ChatListRow(
        avatar: const FakeAvatar(FakeShape.hexagon, FakeAvatar.cyan),
        title: 'Crypto Desk',
        preview: 'BTC funding flipped negative overnight.',
        time: '09:40',
        pinned: true,
        muted: true,
        unreadCount: 12,
        onTap: () {},
      ),
      ChatListRow(
        avatar: const FakeAvatar(FakeShape.diamond, FakeAvatar.green),
        title: 'Dividend Scout',
        preview: 'Three payers worth a look this week',
        previewKind: ChatPreviewKind.draft,
        previewPrefix: t(context, 'Draft:', 'مسودة:'),
        time: 'Thursday',
        onTap: () {},
      ),
      ChatListRow(
        avatar: const FakeAvatar(FakeShape.square, FakeAvatar.orange),
        title: 'Portfolio',
        preview: 'Rebalance to 60/40',
        previewKind: ChatPreviewKind.failed,
        previewPrefix: t(context, 'Not sent:', 'لم تُرسل:'),
        time: 'Nov 22',
        onTap: () {},
      ),
      ChatListRow(
        avatar: const FakeAvatar(FakeShape.circle, FakeAvatar.slate),
        title: 'Earnings Bot',
        preview: 'Reading the 10-Q…',
        previewKind: ChatPreviewKind.active,
        time: 'Nov 22',
        unreadDot: true,
        onTap: () {},
      ),
      ChatListRow(
        avatar: const GroupAvatarPair(
          first: FakeAvatar(FakeShape.circle, FakeAvatar.violet),
          second: FakeAvatar(FakeShape.hexagon, FakeAvatar.cyan),
        ),
        title: 'Trading desk',
        preview: 'Gold desk: both stops are in place for the night.',
        time: 'Nov 21',
        selectionMode: true,
        selected: true,
        onTap: () {},
      ),
      ChatListRow(
        avatar: const FakeAvatar(FakeShape.diamond, FakeAvatar.slate),
        title: 'Macro',
        preview: 'CPI comes out Wednesday.',
        time: 'Nov 20',
        selectionMode: true,
        onTap: () {},
      ),
      _label(context, 'Skeleton'),
      const SkeletonRows(count: 2, animate: false),
      _label(context, 'Network strip'),
      NetworkStrip(
        status: NetworkStripStatus.offline,
        label: t(context, 'No connection', 'لا يوجد اتصال'),
        applyTopInset: false,
      ),
      const SizedBox(height: 4),
      const NetworkStrip(
        status: NetworkStripStatus.connecting,
        label: 'Connecting…',
        applyTopInset: false,
      ),
      const SizedBox(height: 4),
      const NetworkStrip(
        status: NetworkStripStatus.reconnected,
        label: 'Back online',
        applyTopInset: false,
      ),
    ],
  );
}

class _ExplorePage extends StatelessWidget {
  const _ExplorePage();

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.symmetric(vertical: 12),
    children: [
      SizedBox(
        height: LnSize.wideTileHeight,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsetsDirectional.symmetric(horizontal: 16),
          children: [
            WideTile(
              label: t(
                context,
                'Compare brokers for the lowest fees',
                'قارن الوسطاء لأقل الرسوم',
              ),
              leading: const Icon(FIcons.sparkles),
              color: const Color(0xFF7C3AED),
              onTap: () {},
            ),
            const SizedBox(width: LnSpace.tileGap),
            ExploreTile.wide(
              label: 'Gold this week',
              color: const Color(0xFFEA580C),
              onTap: () {},
            ),
          ],
        ),
      ),
      const SizedBox(height: LnSpace.tileGap),
      SizedBox(
        height: LnSize.exploreTile,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsetsDirectional.symmetric(horizontal: 16),
          children: [
            ExploreTile(
              label: t(context, 'Watch my portfolio', 'راقب محفظتي'),
              foreground: context.ln.colors.fg,
              gradient: const LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Color(0xFFE4E0FB), Color(0xFFF2F0FD)],
              ),
              onTap: () {},
            ),
            const SizedBox(width: LnSpace.tileGap),
            ExploreTile(
              label: 'Earnings this week',
              leading: const Icon(FIcons.calendar),
              color: const Color(0xFF0284C7),
              onTap: () {},
            ),
            const SizedBox(width: LnSpace.tileGap),
            ExploreTile(
              label: 'Set a price alert',
              color: const Color(0xFF059669),
              onTap: () {},
            ),
          ],
        ),
      ),
      const SizedBox(height: 27),
      SectionHeader(title: t(context, 'Suggestions', 'مقترحات'), onTap: () {}),
      const SizedBox(height: 4),
      Padding(
        padding: const EdgeInsetsDirectional.symmetric(horizontal: 16),
        child: Column(
          children: [
            RecommendationCard(
              title: t(
                context,
                'Review my open positions',
                'راجع صفقاتي المفتوحة',
              ),
              subtitle: t(
                context,
                'Check each stop and what changed since yesterday',
                'تحقق من كل وقف وما تغيّر منذ الأمس',
              ),
              leading: const Icon(FIcons.wallet),
              onTap: () {},
            ),
            const SizedBox(height: 8),
            RecommendationCard(
              title: 'Summarise the latest filings',
              subtitle: 'Read the 10-Q and flag what matters',
              leading: const Icon(FIcons.fileText),
              onTap: () {},
            ),
          ],
        ),
      ),
      SizedBox(
        height: 250,
        child: EmptyState(
          icon: FIcons.messageCircle,
          title: t(context, 'No chats yet', 'لا توجد محادثات بعد'),
          body: 'Start a conversation with an agent.',
          actionLabel: 'New chat',
          onAction: () {},
        ),
      ),
      SizedBox(
        height: 250,
        child: ErrorState(
          title: "Couldn't load",
          body: 'Check your connection.',
          retryLabel: 'Retry',
          onRetry: () {},
        ),
      ),
    ],
  );
}

class _SettingsPage extends StatelessWidget {
  const _SettingsPage();

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.symmetric(vertical: 12),
    children: [
      LnSection(
        title: t(context, 'Preferences', 'التفضيلات'),
        footer: 'Applies to every conversation.',
        children: [
          LnListTile(
            icon: FIcons.globe,
            title: t(context, 'Language', 'اللغة'),
            value: 'English',
            onTap: () {},
          ),
          LnListTile(
            icon: FIcons.moon,
            title: 'Dark mode',
            subtitle: 'Follow system',
            trailing: LnSwitch(value: true, onChanged: (_) {}),
          ),
          LnListTile(
            icon: FIcons.bell,
            title: 'Notifications',
            trailing: LnSwitch(value: false, onChanged: (_) {}),
          ),
          LnListTile(
            icon: LnIcons.logOut,
            title: t(context, 'Sign out', 'تسجيل الخروج'),
            destructive: true,
            onTap: () {},
          ),
        ],
      ),
      const SizedBox(height: 20),
      Padding(
        padding: const EdgeInsetsDirectional.symmetric(horizontal: 16),
        child: Column(
          children: [
            LnTextField(
              label: t(context, 'Server URL', 'عنوان الخادم'),
              hint: 'https://',
              helper: 'Your Lonora server.',
              textDirection: TextDirection.ltr,
            ),
            const SizedBox(height: 12),
            const LnTextField(
              label: 'API key',
              hint: 'sk-…',
              error: 'Key is required.',
              autocorrect: false,
              enableSuggestions: false,
              enableIMEPersonalizedLearning: false,
              textDirection: TextDirection.ltr,
            ),
            const SizedBox(height: 16),
            LnSegmented<int>(
              segments: [
                LnSegment(value: 0, label: t(context, 'System', 'النظام')),
                const LnSegment(value: 1, label: 'Light'),
                const LnSegment(value: 2, label: 'Dark'),
              ],
              selected: 1,
              onChanged: (_) {},
            ),
          ],
        ),
      ),
    ],
  );
}

/// Kit pieces promoted from the Market tab: chip strip, wide tile with a body, Explore skeleton.
class _KitTilesPage extends StatelessWidget {
  const _KitTilesPage();

  @override
  Widget build(BuildContext context) {
    final white = context.ln.colors.onAccent;
    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 12),
      children: [
        LnChipStrip(
          children: [
            LnChoiceChip(
              label: t(context, 'All', 'الكل'),
              selected: true,
              onTap: () {},
            ),
            LnChoiceChip(
              label: t(context, 'Open', 'مفتوحة'),
              icon: FIcons.clock,
              selected: false,
              onTap: () {},
            ),
            LnChoiceChip(
              label: 'EURUSD',
              textDirection: TextDirection.ltr,
              selected: false,
              onTap: () {},
            ),
          ],
        ),
        const SizedBox(height: 12),
        SizedBox(
          height: LnSize.wideTileHeight,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsetsDirectional.symmetric(horizontal: 16),
            children: [
              WideTile(
                label: t(context, 'Paper account', 'حساب تجريبي'),
                color: context.ln.colors.brand,
                onTap: () {},
                body: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(FIcons.wallet, size: 20),
                        const SizedBox(width: 8),
                        Text(
                          t(context, 'Paper account', 'حساب تجريبي'),
                          style: context.ln.text.footnoteStrong.copyWith(
                            color: white,
                          ),
                        ),
                      ],
                    ),
                    const Spacer(),
                    Text(
                      '12,400.00 USD',
                      textDirection: TextDirection.ltr,
                      style: context.ln.text.largeTitle.copyWith(color: white),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        ExploreSkeleton(
          semanticLabel: t(context, 'Loading', 'جارٍ التحميل'),
          cards: 2,
          animate: false,
        ),
      ],
    );
  }
}

/// Integration states: multi-line and hugging event rows, files-only composer, offline error.
class _KitStatesPage extends StatefulWidget {
  const _KitStatesPage();

  @override
  State<_KitStatesPage> createState() => _KitStatesPageState();
}

class _KitStatesPageState extends State<_KitStatesPage> {
  final _empty = TextEditingController();

  @override
  void dispose() {
    _empty.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.symmetric(vertical: 12),
    children: [
      InlineEventRow(
        icon: const Icon(FIcons.circleAlert),
        label: t(
          context,
          'The broker refused the order because the market is closed for the day.',
          'رفض الوسيط الأمر لأن السوق مغلق لهذا اليوم.',
        ),
        alignment: InlineEventAlignment.start,
        showChevron: false,
        maxLines: 3,
      ),
      Row(
        children: [
          Flexible(
            child: InlineEventRow(
              icon: const Icon(FIcons.loader),
              label: t(context, 'Working', 'يعمل'),
              alignment: InlineEventAlignment.start,
              hug: true,
              onTap: () {},
            ),
          ),
          const SizedBox(width: 8),
          Text(
            t(context, 'Stop', 'إيقاف'),
            style: context.ln.text.captionStrong.copyWith(
              color: context.ln.colors.error,
            ),
          ),
        ],
      ),
      const SizedBox(height: 12),
      Padding(
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: LnSpace.chromeGutter,
        ),
        child: Composer(
          controller: _empty,
          placeholder: t(context, 'Message Lonora', 'راسل لونورا'),
          sendWithoutText: true,
          onSend: (_) {},
          attachments: ComposerAttachmentChip(
            label: 'statement.pdf',
            onRemove: () {},
          ),
        ),
      ),
      SizedBox(
        height: 260,
        child: ErrorState(
          icon: FIcons.wifiOff,
          title: t(context, 'No connection', 'لا يوجد اتصال'),
          body: t(context, 'Check your network.', 'تحقق من الشبكة.'),
          retryLabel: t(context, 'Retry', 'أعد المحاولة'),
          onRetry: () {},
        ),
      ),
    ],
  );
}

void main() {
  setUpAll(loadAppFonts);

  final pages = <String, Widget>{
    'chrome': const _ChromePage(),
    'conversation': const _ConversationPage(),
    'cards': const _CardsPage(),
    'list': const _ListPage(),
    'explore': const _ExplorePage(),
    'settings': const _SettingsPage(),
    'kit_tiles': const _KitTilesPage(),
    'kit_states': const _KitStatesPage(),
  };

  for (final MapEntry(key: name, value: page) in pages.entries) {
    for (final brightness in Brightness.values) {
      for (final direction in TextDirection.values) {
        final variant = '${brightness.name}_${direction.name}';
        testWidgets('gallery $name $variant', (tester) async {
          setGoldenViewport(tester);
          await withRealShadows(() async {
            await tester.pumpWidget(
              lnTestApp(
                child: page,
                brightness: brightness,
                direction: direction,
              ),
            );
            await tester.pump(const Duration(milliseconds: 600));
            await expectLater(
              find.byType(MaterialApp),
              matchesGoldenFile('goldens/gallery_${name}_$variant.png'),
            );
          });
        });
      }
    }
  }
}
