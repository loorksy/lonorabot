import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../design/design.dart';
import '../features/chats/chat_drawer.dart';
import '../features/chats/chats_home.dart';
import '../features/chats/chats_strings.dart';
import '../l10n/l10n.dart';
import '../state/actions/base.dart';
import '../state/app_state.dart';
import 'routes.dart';

/// The tab shell: content behind the floating translucent tab bar (Chats · Market · Me) with the
/// separate circle — in Lonora the "needs your attention" destination, carrying a dot while
/// something unseen waits.
///
/// The bar hides while the keyboard is open (the composer then sits on the keyboard).
///
/// With the last-conversation home ([HomeMode.lastChat]) the whole shell, its tab bar included,
/// is the page of an [LnDrawerScaffold] whose drawer is the chat list ([ChatDrawer]): the
/// conversation at the Chats tab's root opens it with its ☰ button or an edge drag. It closes
/// when the location or the tab changes (a chat opened from it, a notification, a link).
class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.shell, this.location = ''});

  final StatefulNavigationShell shell;

  /// The current location; a conversation draws its own fade under its composer.
  final String location;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  static const _attentionBranch = 3;

  final _drawer = LnDrawerController();

  StatefulNavigationShell get shell => widget.shell;

  @override
  void didUpdateWidget(HomeShell old) {
    super.didUpdateWidget(old);
    if (old.location != widget.location ||
        old.shell.currentIndex != widget.shell.currentIndex) {
      // Closed after this frame: the drawer's own state rebuilds as it starts closing.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _drawer.isOpen) unawaited(_drawer.close());
      });
    }
  }

  @override
  void dispose() {
    _drawer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final unread = context.select((AppState s) => s.shell.unreadTotal);
    final attentionDot = context.select(
      (AppState s) => s.shell.attentionUnseen > 0,
    );
    final drawerMode = context.select(
      (AppState s) => s.prefs.homeMode == HomeMode.lastChat,
    );
    final keyboard = MediaQuery.viewInsetsOf(context).bottom > 0;
    final index = shell.currentIndex;
    final uri = Uri.tryParse(widget.location) ?? Uri();
    // The conversation at the Chats tab's root in the last-conversation home.
    final onHome = drawerMode && index == 0 && uri.path == Routes.chats;
    final requested = uri.queryParameters['thread'];
    final homeThread = context.select(
      (AppState s) => onHome ? homeThreadId(s, requested: requested) : null,
    );
    final inConversation =
        uri.path.startsWith('${Routes.chats}/thread/') || homeThread != null;

    final page = Scaffold(
      backgroundColor: ln.colors.bg,
      resizeToAvoidBottomInset: false,
      body: Stack(
        children: [
          Positioned.fill(child: shell),
          if (!keyboard && !inConversation)
            const Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: IgnorePointer(child: BottomChromeFade()),
            ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: AnimatedSlide(
              offset: keyboard ? const Offset(0, 1.4) : Offset.zero,
              duration: LnMotion.medium,
              curve: LnMotion.emphasized,
              child: FloatingTabBar(
                selectedIndex: index == _attentionBranch ? -1 : index,
                onSelect: (i) => _go(i),
                items: [
                  LnTabItem(
                    icon: const LnGlyph(LnGlyphs.chats),
                    selectedIcon: const LnGlyph(LnGlyphs.chatsFilled),
                    label: context.t('sh_chats'),
                    badgeCount: unread > 0 ? unread : null,
                  ),
                  LnTabItem(
                    icon: const LnGlyph(LnGlyphs.market),
                    selectedIcon: const LnGlyph(LnGlyphs.marketFilled),
                    label: context.t('android_market'),
                  ),
                  LnTabItem(
                    icon: const LnGlyph(LnGlyphs.me),
                    selectedIcon: const LnGlyph(LnGlyphs.meFilled),
                    label: context.t('android_me'),
                  ),
                ],
                actionIcon: const LnGlyph(LnGlyphs.attention),
                actionSelectedIcon: const LnGlyph(LnGlyphs.attentionFilled),
                actionLabel: context.t('android_attention'),
                actionDot: attentionDot,
                actionSelected: index == _attentionBranch,
                onAction: () => _go(_attentionBranch),
              ),
            ),
          ),
        ],
      ),
    );
    if (!drawerMode) return page;
    registerChatsStrings();
    return ChatDrawerScope(
      controller: _drawer,
      // The drawer's surface also shows beyond the card's rounded corners.
      child: ColoredBox(
        color: ln.colors.drawerSurface,
        child: LnDrawerScaffold(
          controller: _drawer,
          drawerLabel: context.t('chats_drawer'),
          closeLabel: context.t('chats_closeDrawer'),
          enableEdgeDrag: homeThread != null && !keyboard,
          // Built only while it shows: closed, the drawer costs nothing.
          drawer: ValueListenableBuilder<double>(
            valueListenable: _drawer.progress,
            builder: (context, p, _) =>
                p > 0 ? const ChatDrawer() : const SizedBox.shrink(),
          ),
          child: page,
        ),
      ),
    );
  }

  void _go(int branch) =>
      shell.goBranch(branch, initialLocation: branch == shell.currentIndex);
}
