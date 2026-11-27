import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/app/router.dart' show rootNavigatorKey;
import 'package:lonora/design/design.dart';
import 'package:lonora/features/voice/call_overlay.dart';
import 'package:lonora/features/voice/voice_api.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart';
import '../../platform/platform_harness.dart';
import 'voice_fakes.dart';

void main() {
  setUpAll(setUpPlatformTests);

  testWidgets(
    'the call page opens, minimizes to the pill, comes back and closes',
    (tester) async {
      setPlatformViewport(tester);
      final store = voiceStore();
      late FakeTransport transport;
      final api = FakeApi()
        ..on('GET /voice/status', (_) => {'transport_configured': true})
        ..on('GET /trading/approvals', (_) => const []);
      final controller = VoiceCallController(
        api: () => api,
        store: () => store,
        transport: (callbacks, client) =>
            transport = FakeTransport(callbacks, client),
        microphone: () async => MicPermission.granted,
        keepAwake: (_) async {},
        showOngoing: (_) async {},
        hideOngoing: () async {},
        endedLinger: const Duration(milliseconds: 500),
        approvalsEvery: const Duration(hours: 1),
      );
      platformL10n.setLocale(const Locale('en'));
      await tester.pumpWidget(
        StoreProvider<AppState>(
          store: store,
          child: MaterialApp(
            navigatorKey: rootNavigatorKey,
            locale: const Locale('en'),
            supportedLocales: L10n.supportedLocales,
            localizationsDelegates: [
              platformL10n.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
              ...FLocalizations.localizationsDelegates,
            ],
            theme: lnMaterialTheme(
              LnPalette.light,
              fontFamily: testFontFamily,
              fontFamilyFallback: testFontFallback,
            ),
            builder: (context, child) => LnTheme(
              data: testTheme(Brightness.light),
              child: FTheme(
                data: lnForuiTheme(LnPalette.light),
                child: FToaster(
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      child!,
                      CallPresenter(controller: controller),
                    ],
                  ),
                ),
              ),
            ),
            home: const Center(child: Text('conversation')),
          ),
        ),
      );

      await controller.start(agentId: 'a-sara', threadId: 't-sara');
      await settle(tester);
      expect(find.byType(VoiceCallView), findsOneWidget);
      expect(find.text('Calling…'), findsOneWidget);

      transport.callbacks.onConnected();
      await tester.pump(const Duration(seconds: 2));
      expect(find.textContaining('Voice call ·'), findsOneWidget);

      // Back minimizes: the conversation shows again with the pill on top.
      await tester.binding.handlePopRoute();
      await settle(tester);
      expect(find.byType(VoiceCallView), findsNothing);
      expect(find.byType(CallPill), findsOneWidget);
      expect(find.text('conversation'), findsOneWidget);
      expect(controller.state.minimized, isTrue);

      await tester.tap(find.byType(CallPill));
      await settle(tester);
      expect(find.byType(VoiceCallView), findsOneWidget);

      await tester.tap(find.bySemanticsLabel(platformL10n.t('endCall')));
      await tester.pump();
      await tester.pump();
      expect(find.text('Call ended'), findsOneWidget);
      expect(transport.closed, isTrue);
      await tester.pump(const Duration(milliseconds: 600));
      await settle(tester);
      expect(find.byType(VoiceCallView), findsNothing);
      expect(find.byType(CallPill), findsNothing);
      expect(controller.state.phase, CallPhase.idle);
    },
  );
}

/// The call page's avatar animates for ever: let transitions finish instead of settling.
Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 200));
  }
}
