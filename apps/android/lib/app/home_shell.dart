import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../design/design.dart';
import '../l10n/l10n.dart';
import '../state/actions/base.dart';
import '../state/app_state.dart';
import 'routes.dart';

/// The tab shell: content behind the floating translucent tab bar (Chats · Market · Me) with the
/// separate circle — in Lonora the "needs your attention" destination, carrying a dot while
/// something unseen waits.
///
/// The bar hides while the keyboard is open (the composer then sits on the keyboard).
class HomeShell extends StatelessWidget {
  const HomeShell({super.key, required this.shell, this.location = ''});

  final StatefulNavigationShell shell;

  /// The current location; a conversation draws its own fade under its composer.
  final String location;

  static const _attentionBranch = 3;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final unread = context.select((AppState s) => s.shell.unreadTotal);
    final attentionDot = context.select(
      (AppState s) => s.shell.attentionUnseen > 0,
    );
    final keyboard = MediaQuery.viewInsetsOf(context).bottom > 0;
    final index = shell.currentIndex;
    final inConversation = location.startsWith('${Routes.chats}/thread/');

    return Scaffold(
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
  }

  void _go(int branch) =>
      shell.goBranch(branch, initialLocation: branch == shell.currentIndex);
}
