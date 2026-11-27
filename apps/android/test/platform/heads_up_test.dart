import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/platform/heads_up/heads_up_banner.dart';
import 'package:lonora/platform/heads_up/heads_up_controller.dart';
import 'package:lonora/platform/heads_up/heads_up_rules.dart';
import 'package:lonora/platform/navigation.dart';
import 'package:lonora/state/app_state.dart';

import '../design/harness.dart';
import '../features/voice/voice_fakes.dart';
import 'platform_fixtures.dart';
import 'platform_harness.dart';

const groupBanner = HeadsUpBanner(
  threadId: 't-desk',
  groupId: 'g-desk',
  agentId: 'a-omar',
  who: 'Omar:',
  text: 'Gold broke above the weekly range; I moved the alert to 2,415.',
  kind: HeadsUpKind.message,
  key: 'm1',
);

Store<AppState> shellStore() => Store<AppState>(
  initialState: AppState(
    session: const SessionState(status: SessionStatus.signedIn),
    shell: demoShell(),
  ),
);

void main() {
  setUpAll(setUpPlatformTests);

  group('HeadsUpController timing', () {
    testWidgets('5.2 s, held while pressed, 2.4 s after release', (
      tester,
    ) async {
      final c = HeadsUpController();
      c.show(groupBanner);
      expect(c.current.value?.banner, same(groupBanner));
      await tester.pump(const Duration(milliseconds: 5100));
      expect(c.current.value, isNotNull);
      c.hold(true);
      await tester.pump(const Duration(seconds: 30));
      expect(c.current.value, isNotNull);
      c.hold(false);
      await tester.pump(const Duration(milliseconds: 2300));
      expect(c.current.value, isNotNull);
      await tester.pump(const Duration(milliseconds: 200));
      expect(c.current.value, isNull);
    });

    testWidgets('a newer banner replaces the shown one and restarts the time', (
      tester,
    ) async {
      final c = HeadsUpController();
      c.show(groupBanner);
      await tester.pump(const Duration(seconds: 4));
      const next = HeadsUpBanner(
        threadId: 't-sara',
        text: 'x',
        kind: HeadsUpKind.message,
        key: 'm2',
      );
      c.show(next);
      await tester.pump(const Duration(seconds: 4));
      expect(c.current.value?.banner, same(next));
      expect(c.current.value?.serial, 2);
      c.dismiss();
      expect(c.current.value, isNull);
    });
  });

  group('HeadsUpController reads', () {
    late FakeApi api;
    setUp(() async {
      await sl.reset();
      api = FakeApi();
      sl.registerSingleton<ApiClient>(api);
    });
    tearDown(() => sl.reset());

    test(
      "a refused model's banner names the failure and provider (parameters)",
      () async {
        final store = Store<AppState>(
          initialState: AppState(
            session: const SessionState(
              status: SessionStatus.signedIn,
              server: 'https://lonora.example.com',
              owner: Owner(id: 'owner-1', email: 'o@example.com'),
            ),
            shell: demoShell(),
          ),
        );
        final c = HeadsUpController();
        c.start(store, const Stream.empty());
        addTearDown(c.stop);
        store.dispatch(
          _SetAttention([
            attentionJson(
              'm1',
              code: 'model_access_failed',
              importance: 'critical',
              agentId: 'a-sara',
              threadId: 't-sara',
              at: DateTime.now(),
              parameters: const {'reason': 'auth', 'provider_name': 'Acme'},
            ),
          ]),
        );
        await Future<void>.delayed(Duration.zero);
        final text = c.current.value?.banner.text ?? '';
        expect(text, contains('Acme'));
        expect(text, isNot(platformL10n.t('attention.model_access_failed')));
      },
    );

    test("quiet hours in another zone carry that zone's offset; the phone's own zone does not", () async {
      api.on(
        'GET /owner/profile',
        (_) => {
          'reach_me': {
            'quiet_start_minute': 22 * 60,
            'quiet_end_minute': 7 * 60,
            'timezone': 'Europe/Paris',
          },
        },
      );
      final c = HeadsUpController()
        ..phoneZone = (() async => 'Asia/Riyadh')
        ..zoneOffset = ((zone, _) async => zone == 'Europe/Paris' ? 60 : null);
      await c.refreshRules(force: true);
      expect(c.rules.quiet?.offsetMinutes, 60);

      c.phoneZone = () async => 'Europe/Paris';
      await c.refreshRules(force: true);
      expect(c.rules.quiet?.timezone, 'Europe/Paris');
      expect(c.rules.quiet?.offsetMinutes, isNull);
    });
  });

  group("HeadsUpController and this phone's notification prefs", () {
    setUp(() async {
      await sl.reset();
      sl.registerSingleton<ApiClient>(FakeApi());
    });
    tearDown(() => sl.reset());

    /// A controller started at [t0] on the demo shell with [notify]; [events] feeds it.
    (HeadsUpController, Store<AppState>, StreamController<LonoraEvent>) start(
      NotifyPrefs notify,
    ) {
      final store = Store<AppState>(
        initialState: AppState(
          session: const SessionState(
            status: SessionStatus.signedIn,
            server: 'https://lonora.example.com',
            owner: Owner(id: 'owner-1', email: 'o@example.com'),
          ),
          shell: demoShell(),
          prefs: PrefsState(notify: notify),
        ),
      );
      final events = StreamController<LonoraEvent>();
      final c = HeadsUpController(clock: () => t0)..start(store, events.stream);
      addTearDown(() {
        c.stop();
        events.close();
      });
      return (c, store, events);
    }

    final reply = messageCreated(
      thread: 't-desk',
      id: 'm1',
      agentId: 'a-omar',
      content: 'Gold broke above the weekly range.',
    );
    final urgent = attentionJson(
      'x1',
      importance: 'critical',
      agentId: 'a-sara',
      threadId: 't-sara',
    );

    test('by default a reply shows its words and speaker', () async {
      final (c, _, events) = start(const NotifyPrefs());
      events.add(reply);
      await Future<void>.delayed(Duration.zero);
      expect(
        c.current.value?.banner.text,
        'Gold broke above the weekly range.',
      );
      expect(c.current.value?.banner.who, 'Omar:');
    });

    test(
      'in-app notifications off: no reply banner; urgent items still show',
      () async {
        final (c, store, events) = start(const NotifyPrefs(inApp: false));
        events.add(reply);
        await Future<void>.delayed(Duration.zero);
        expect(c.current.value, isNull);
        store.dispatch(_SetAttention([urgent]));
        await Future<void>.delayed(Duration.zero);
        expect(c.current.value?.banner.kind, HeadsUpKind.attention);
        expect(c.current.value?.banner.threadId, 't-sara');
      },
    );

    test(
      'text preview off: «New message», no speaker, on every banner',
      () async {
        final (c, store, events) = start(const NotifyPrefs(preview: false));
        events.add(reply);
        await Future<void>.delayed(Duration.zero);
        final banner = c.current.value!.banner;
        expect(banner.text, platformL10n.t('newMessage'));
        expect(banner.who, isNull);
        expect(banner.threadId, 't-desk');
        store.dispatch(_SetAttention([urgent]));
        await Future<void>.delayed(Duration.zero);
        expect(c.current.value?.banner.kind, HeadsUpKind.attention);
        expect(c.current.value?.banner.text, platformL10n.t('newMessage'));
      },
    );
  });

  testWidgets('tap opens the conversation; swipe up dismisses', (tester) async {
    setPlatformViewport(tester);
    final opened = <String>[];
    PlatformNavigation.override = opened.add;
    addTearDown(() => PlatformNavigation.override = null);
    final c = HeadsUpController();
    await tester.pumpWidget(
      platformApp(
        store: shellStore(),
        locale: 'en',
        home: BackdropPage(children: [HeadsUpLayer(controller: c)]),
      ),
    );
    c.show(groupBanner);
    await tester.pumpAndSettle();
    expect(find.text('Desk'), findsOneWidget);
    expect(find.textContaining('Omar:', findRichText: true), findsOneWidget);
    await tester.tap(find.text('Reply'));
    await tester.pumpAndSettle();
    expect(opened, ['/chats/thread/t-desk']);
    expect(c.current.value, isNull);

    c.show(groupBanner);
    await tester.pumpAndSettle();
    await tester.drag(find.text('Desk'), const Offset(0, -60));
    await tester.pumpAndSettle();
    expect(c.current.value, isNull);
    c.dismiss();
  });

  for (final locale in ['ar', 'en']) {
    testWidgets('text at 1.3×: the banner fits ($locale)', (tester) async {
      setPlatformViewport(tester);
      tester.platformDispatcher.textScaleFactorTestValue = 1.3;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final store = shellStore();
      await tester.pumpWidget(
        platformApp(
          store: store,
          locale: locale,
          home: BackdropPage(
            children: [
              Positioned(
                top: 120,
                left: 16,
                right: 16,
                child: HeadsUpBannerView(
                  title: 'Research desk with a rather long name',
                  who: 'Omar:',
                  text: locale == 'ar'
                      ? 'اخترق الذهب نطاق الأسبوع؛ نقلت التنبيه إلى 2,415 وسأتابع الإغلاق اليومي ثم أعود إليك.'
                      : 'Gold broke above the weekly range; I moved the alert to 2,415 and will follow the daily close.',
                  kind: HeadsUpKind.attention,
                  avatar: HeadsUpAvatar(
                    agent: store.state.shell.agents['a-sara'],
                  ),
                ),
              ),
            ],
          ),
        ),
      );
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  }

  for (final v in platformVariants) {
    testWidgets('heads-up golden ${v.name}', (tester) async {
      setPlatformViewport(tester);
      final c = HeadsUpController();
      final store = shellStore();
      await withRealShadows(() async {
        await tester.pumpWidget(
          platformApp(
            store: store,
            dark: v.dark,
            locale: v.locale,
            home: Builder(
              builder: (context) => BackdropPage(
                children: [
                  HeadsUpLayer(controller: c),
                  Positioned(
                    top: 260,
                    left: 16,
                    right: 16,
                    child: HeadsUpBannerView(
                      title: 'Sara',
                      text: v.locale == 'ar'
                          ? 'موافقة مطلوبة على صفقة شراء الذهب'
                          : 'Approval needed for the gold buy order',
                      kind: HeadsUpKind.attention,
                      avatar: HeadsUpAvatar(
                        agent: store.state.shell.agents['a-sara'],
                      ),
                    ),
                  ),
                  Positioned(
                    top: 360,
                    left: 16,
                    right: 16,
                    child: HeadsUpBannerView(
                      title: 'Omar',
                      text: v.locale == 'ar'
                          ? 'تم: أغلقت مركز EURUSD عند \u200e+0.4%\u200e ربح.'
                          : 'Done: closed the EURUSD position at +0.4%.',
                      avatar: HeadsUpAvatar(
                        agent: store.state.shell.agents['a-omar'],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
        c.show(
          v.locale == 'ar'
              ? const HeadsUpBanner(
                  threadId: 't-desk',
                  groupId: 'g-desk',
                  agentId: 'a-omar',
                  who: 'Omar:',
                  text: 'اخترق الذهب نطاق الأسبوع؛ نقلت التنبيه إلى 2,415 وسأتابع الإغلاق اليومي.',
                  kind: HeadsUpKind.message,
                  key: 'm1',
                )
              : groupBanner,
        );
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/heads_up_${v.name}.png'),
        );
        c.dismiss();
        await tester.pumpAndSettle();
      });
    });
  }
}

class _SetAttention extends ReduxAction<AppState> {
  _SetAttention(this.items);
  final List<Map<String, Object?>> items;
  @override
  AppState reduce() =>
      state.copyWith(shell: state.shell.copyWith(attention: items));
}
