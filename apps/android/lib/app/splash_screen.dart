import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../design/design.dart';
import '../l10n/l10n.dart';
import 'routes.dart';

/// Continues the native launch surface (same background, same centered Lonora mark) while
/// the stored session is restored, so the hand-off from the system splash is seamless.
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key, this.notFound = false});
  final bool notFound;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    return Scaffold(
      backgroundColor: ln.colors.bg,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Image.asset(
              'assets/brand/logo.png',
              width: 96,
              height: 96,
              semanticLabel: 'Lonora',
            ),
            if (notFound) ...[
              const SizedBox(height: 24),
              Text(
                context.t('pageMissing'),
                style: ln.text.title.copyWith(color: ln.colors.fg),
              ),
              const SizedBox(height: 16),
              BlockButton(
                label: context.t('inbox'),
                onPressed: () => context.go(Routes.chats),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
