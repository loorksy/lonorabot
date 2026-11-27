import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/features/voice/incoming_call.dart';
import 'package:lonora/features/voice/voice_api.dart';
import 'package:lonora/platform/navigation.dart';
import 'package:lonora/platform/notifications/local_notifications.dart';
import 'package:lonora/platform/notifications/notification_payload.dart';
import 'package:lonora/platform/updates/update_service.dart';
import 'package:lonora/platform/updates/update_sheet.dart';

import '../design/harness.dart';
import '../features/voice/voice_fakes.dart';
import 'platform_harness.dart';

void main() {
  setUpAll(setUpPlatformTests);

  group('notification taps', () {
    tearDown(LnNotifications.reset);

    test('a conversation tap opens its route; the call tap and «End call» reach the call', () {
      final opened = <NotificationPayload>[];
      var hangUps = 0, callTaps = 0;
      LnNotifications.onOpen = opened.add;
      LnNotifications.onHangUp = () => hangUps++;
      LnNotifications.onCallTap = () => callTaps++;
      LnNotifications.handleForTest(
        NotificationResponse(
          notificationResponseType:
              NotificationResponseType.selectedNotification,
          payload: const NotificationPayload.thread('t1', around: 4).encode(),
        ),
      );
      LnNotifications.handleForTest(
        NotificationResponse(
          notificationResponseType:
              NotificationResponseType.selectedNotification,
          payload: const NotificationPayload.call().encode(),
        ),
      );
      LnNotifications.handleForTest(
        const NotificationResponse(
          notificationResponseType:
              NotificationResponseType.selectedNotificationAction,
          actionId: hangUpActionId,
        ),
      );
      LnNotifications.handleForTest(
        const NotificationResponse(
          notificationResponseType:
              NotificationResponseType.selectedNotification,
          payload: '{"t":"thread","id":"../x"}',
        ),
      );
      expect(opened, [const NotificationPayload.thread('t1', around: 4)]);
      expect(opened.single.location, '/chats/thread/t1?around=4');
      expect((hangUps, callTaps), (1, 1));
    });
  });

  group('PlatformNavigation', () {
    tearDown(() {
      PlatformNavigation.override = null;
      PlatformNavigation.ready = () => true;
      PlatformNavigation.clear();
    });

    test('a location waits until the owner is signed in', () {
      final opened = <String>[];
      var signedIn = false;
      PlatformNavigation.override = opened.add;
      PlatformNavigation.ready = () => signedIn;
      PlatformNavigation.open('/chats/thread/t1');
      expect(opened, isEmpty);
      expect(PlatformNavigation.pending, '/chats/thread/t1');
      signedIn = true;
      expect(PlatformNavigation.flush(), isTrue);
      expect(opened, ['/chats/thread/t1']);
      expect(PlatformNavigation.pending, isNull);
      expect(PlatformNavigation.flush(), isFalse);
    });
  });

  group('IncomingCallController', () {
    late FakeApi api;
    late StreamController<LonoraEvent> events;
    late IncomingCallController incoming;
    late VoiceCallController calls;
    late FakeTransport? transport;
    final soon = DateTime.now().toUtc().add(const Duration(seconds: 40));

    setUp(() {
      api = FakeApi()
        ..on(
          'GET /voice/incoming/policy',
          (_) => {'enabled': true, 'device_id': 'dev-1', 'channel': 'call'},
        )
        ..on('GET /voice/incoming', (_) => const [])
        ..on('GET /voice/status', (_) => {'transport_configured': true})
        ..on('GET /trading/approvals', (_) => const []);
      events = StreamController.broadcast();
      transport = null;
      final store = voiceStore();
      calls = VoiceCallController(
        api: () => api,
        store: () => store,
        transport: (c, a) => transport = FakeTransport(c, a),
        microphone: () async => MicPermission.granted,
        keepAwake: (_) async {},
        showOngoing: (_) async {},
        hideOngoing: () async {},
        approvalsEvery: const Duration(hours: 1),
      );
      VoiceCalls.controller = calls;
      incoming = IncomingCallController(
        api: () => api,
        pollEvery: const Duration(hours: 1),
      );
      incoming.start(store, events.stream);
    });

    tearDown(() async {
      incoming.stop();
      await events.close();
      VoiceCalls.active.value = false;
    });

    Map<String, Object?> ringing() => {
      'id': 'ic-1',
      'agent_id': 'a-sara',
      'thread_id': 't-sara',
      'status': 'ringing',
      'reason': 'Gold broke 2,400',
      'expires_at': soon.toIso8601String(),
      'execution_authorized': false,
    };

    test(
      'the event rings; «Answer» accepts with the device, then joins',
      () async {
        await Future<void>.delayed(Duration.zero);
        events.add(
          LonoraEvent(
            cursor: 9,
            kind: 'voice.incoming.updated',
            payload: ringing(),
          ),
        );
        await Future<void>.delayed(Duration.zero);
        expect(incoming.call?['id'], 'ic-1');
        api.on(
          'POST /voice/incoming/ic-1/respond',
          (_) => {...ringing(), 'status': 'accepted'},
        );
        await incoming.respond(true);
        final respond = api.calls.lastWhere((c) => c.method == 'POST');
        expect(respond.body, {'action': 'accept', 'device_id': 'dev-1'});
        expect(incoming.call, isNull);
        expect(transport?.incomingCallId, 'ic-1');
        expect(calls.state.phase, CallPhase.calling);
        await calls.end();
      },
    );

    test(
      '«Decline» never joins; a call that authorizes something never joins',
      () async {
        await Future<void>.delayed(Duration.zero);
        events.add(
          LonoraEvent(
            cursor: 9,
            kind: 'voice.incoming.updated',
            payload: ringing(),
          ),
        );
        await Future<void>.delayed(Duration.zero);
        api.on(
          'POST /voice/incoming/ic-1/respond',
          (_) => {...ringing(), 'status': 'rejected'},
        );
        await incoming.respond(false);
        expect(transport, isNull);

        events.add(
          LonoraEvent(
            cursor: 10,
            kind: 'voice.incoming.updated',
            payload: ringing(),
          ),
        );
        await Future<void>.delayed(Duration.zero);
        api.on(
          'POST /voice/incoming/ic-1/respond',
          (_) => {
            ...ringing(),
            'status': 'accepted',
            'execution_authorized': true,
          },
        );
        await incoming.respond(true);
        expect(transport, isNull);
      },
    );

    test(
      'polls every few seconds and reads the policy again every half minute',
      () async {
        var now = DateTime.now();
        var enabled = false;
        final polled = FakeApi()
          ..on(
            'GET /voice/incoming/policy',
            (_) => {'enabled': enabled, 'device_id': 'dev-1'},
          )
          ..on('GET /voice/incoming', (_) => const []);
        final c = IncomingCallController(
          api: () => polled,
          pollEvery: const Duration(milliseconds: 10),
          clock: () => now,
        );
        c.start(voiceStore(), const Stream.empty());
        addTearDown(c.stop);
        int count(String path) =>
            polled.calls.where((x) => x.path == path).length;
        await Future<void>.delayed(const Duration(milliseconds: 45));
        // Calls are off: one policy read, no list reads.
        expect(count('/voice/incoming/policy'), 1);
        expect(count('/voice/incoming'), 0);
        // Switched on elsewhere: the next policy read finds it, then the list is polled.
        enabled = true;
        now = now.add(const Duration(seconds: 31));
        await Future<void>.delayed(const Duration(milliseconds: 45));
        expect(count('/voice/incoming/policy'), 2);
        expect(count('/voice/incoming'), greaterThanOrEqualTo(2));
      },
    );

    test('«Reply with a message» steps aside and opens the chat', () async {
      final opened = <String>[];
      PlatformNavigation.override = opened.add;
      addTearDown(() => PlatformNavigation.override = null);
      await Future<void>.delayed(Duration.zero);
      events.add(
        LonoraEvent(
          cursor: 9,
          kind: 'voice.incoming.updated',
          payload: ringing(),
        ),
      );
      await Future<void>.delayed(Duration.zero);
      incoming.replyWithMessage();
      expect(opened, ['/chats/thread/t-sara']);
      events.add(
        LonoraEvent(
          cursor: 10,
          kind: 'voice.incoming.updated',
          payload: ringing(),
        ),
      );
      await Future<void>.delayed(Duration.zero);
      expect(incoming.call, isNull, reason: 'stepped aside');
    });
  });

  testWidgets('«Check for updates»: the sheet, or why there is none', (
    tester,
  ) async {
    setPlatformViewport(tester);
    final service = UpdateService.instance..resetForTest();
    addTearDown(() {
      service
        ..resetForTest()
        ..isAndroid = (() => false);
    });
    final play = _Play();
    service
      ..isAndroid = (() => true)
      ..installer = (() async => 'com.android.vending')
      ..play = play;
    late BuildContext page;
    await tester.pumpWidget(
      platformApp(
        store: voiceStore(),
        locale: 'en',
        home: Builder(
          builder: (context) {
            page = context;
            return const BackdropPage(children: []);
          },
        ),
      ),
    );
    unawaited(checkForUpdates(page));
    await tester.pumpAndSettle();
    expect(find.text(platformL10n.t('pf_upToDate')), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();

    play.next = const UpdateInfo(
      versionName: '',
      versionCode: 14,
      viaStore: true,
    );
    unawaited(checkForUpdates(page));
    await tester.pumpAndSettle();
    expect(find.text(platformL10n.t('pf_updateAvailable')), findsOneWidget);
    // «Update» hands over to Play and closes the sheet; nothing installs.
    await tester.tap(find.text(platformL10n.t('pf_update')));
    await tester.pumpAndSettle();
    expect(find.text(platformL10n.t('pf_updateAvailable')), findsNothing);
    expect(play.downloads, 1);
    expect(play.restarts, 0);
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  });

  for (final v in [
    (dark: false, locale: 'ar', store: false, ready: false),
    (dark: true, locale: 'en', store: true, ready: false),
    (dark: false, locale: 'en', store: true, ready: true),
  ]) {
    testWidgets('update sheet ${v.locale}${v.ready ? ' (downloaded)' : ''}', (
      tester,
    ) async {
      setPlatformViewport(tester);
      UpdateService.instance.resetForTest();
      addTearDown(UpdateService.instance.resetForTest);
      late BuildContext page;
      await withRealShadows(() async {
        await tester.pumpWidget(
          platformApp(
            store: voiceStore(),
            dark: v.dark,
            locale: v.locale,
            home: Builder(
              builder: (context) {
                page = context;
                return const BackdropPage(children: []);
              },
            ),
          ),
        );
        // The real sheet, title included, as the notification's tap opens it.
        unawaited(
          showUpdateSheet(
            page,
            UpdateInfo(
              versionName: v.store ? '' : '1.2.0',
              versionCode: 12,
              viaStore: v.store,
              downloaded: v.ready,
              notes: v.store
                  ? null
                  : 'مكالمات أوضح، وإشعارات الخلفية، وإصلاحات.',
              downloadUrl: v.store
                  ? null
                  : Uri.parse('https://releases.example.com/l.apk'),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text(platformL10n.t('pf_updateAvailable')), findsOneWidget);
        expect(
          find.text(
            platformL10n.t(
              !v.store
                  ? 'download'
                  : v.ready
                  ? 'pf_restart'
                  : 'pf_update',
            ),
          ),
          findsOneWidget,
        );
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile(
            v.ready
                ? 'goldens/update_sheet_ready_light_en.png'
                : 'goldens/update_sheet_${v.dark ? 'dark' : 'light'}_${v.locale}.png',
          ),
        );
        await tester.tap(find.text(platformL10n.t('pf_updateLater')));
        await tester.pumpAndSettle();
        expect(find.text(platformL10n.t('pf_updateAvailable')), findsNothing);
      });
    });
  }
}

class _Play implements PlayUpdates {
  UpdateInfo? next;
  int downloads = 0;
  int restarts = 0;
  @override
  Future<UpdateInfo?> check() async => next;
  @override
  Future<bool> download() {
    downloads++;
    return Completer<bool>().future;
  }

  @override
  Future<void> restart() async => restarts++;
}
