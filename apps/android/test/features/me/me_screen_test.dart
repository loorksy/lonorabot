// Me tab: its entry cards and their layout, navigation (Settings is its own page), the usage
// card, goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/me
import 'package:async_redux/async_redux.dart';
import 'package:flutter/rendering.dart' show SemanticsAction;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FIcons, FTile, FTileGroup;
import 'package:go_router/go_router.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/me/me_screen.dart';
import 'package:lonora/state/app_state.dart';

import '../../design/harness.dart';
import '../settings_core/feature_harness.dart';

/// Me inside the floating tab bar, as the home shell shows it.
class _MeInShell extends StatelessWidget {
  const _MeInShell();

  @override
  Widget build(BuildContext context) => Stack(
    children: [
      const Positioned.fill(child: MeScreen()),
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
        child: FloatingTabBar(
          items: const [
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
          ],
          selectedIndex: 2,
          onSelect: (_) {},
          actionIcon: const LnGlyph(LnGlyphs.attention),
          actionLabel: 'Attention',
          onAction: () {},
        ),
      ),
    ],
  );
}

void main() {
  setUpAll(setUpFeatureTests);

  late GoRouter router;

  Future<(ScriptedApi, Store<AppState>)> pumpMe(
    WidgetTester tester, {
    String locale = 'ar',
    AppThemeMode theme = AppThemeMode.light,
    bool usageFails = false,
    List<OutgoingMessage> outbox = const [],
  }) async {
    final api = await setUpServices();
    api.on(
      'GET /owner/profile',
      (_) => profileJson(name: 'Ahmed', address: 'أبو خالد'),
    );
    api.on(
      'GET /usage/summary',
      (_) => usageFails
          ? throw ApiError.network()
          : {
              'input_tokens': 1284330,
              'output_tokens': 220415,
              'cached_tokens': 905112,
            },
    );
    final store = testStore(locale: locale, theme: theme, outbox: outbox);
    setFeatureViewport(tester);
    router = testRouter(const _MeInShell());
    await tester.pumpWidget(featureApp(store, router));
    await tester.pumpAndSettle();
    return (api, store);
  }

  testWidgets('shows the owner, the usage totals, every Lonora entry and '
      'Settings last', (tester) async {
    await pumpMe(tester, locale: 'en');
    expect(find.text('أبو خالد'), findsOneWidget);
    expect(find.text('1,284,330'), findsOneWidget);
    expect(find.text('220,415'), findsOneWidget);
    expect(find.text('905,112'), findsOneWidget);
    final titles = [
      'Agents',
      'Routines',
      'Tasks',
      'Files',
      'Charts',
      'What I know about you',
      'Integrations',
      'Global model routing',
      'What is running',
      'Settings',
    ];
    for (final title in titles) {
      await scrollTo(tester, find.text(title));
      expect(find.text(title), findsOneWidget, reason: title);
    }
    // The phone's preferences and sign-out are no longer rows of Me.
    for (final gone in [
      'Notifications and contact',
      'Language',
      'Appearance',
      'Clear cache',
      'About Lonora',
      'Sign out',
    ]) {
      expect(find.text(gone), findsNothing, reason: gone);
    }
  });

  testWidgets('entries open their pages; Settings is its own page', (
    tester,
  ) async {
    await pumpMe(tester, locale: 'en');
    await tester.tap(find.text('Agents'));
    await tester.pumpAndSettle();
    expect(find.text('stub:/agents'), findsOneWidget);
    router.pop();
    await tester.pumpAndSettle();
    await tester.tap(find.text('أبو خالد'));
    await tester.pumpAndSettle();
    expect(find.text('stub:/settings/account'), findsOneWidget);
    router.pop();
    await tester.pumpAndSettle();
    await scrollTo(tester, find.text('Settings'));
    await tapAndSettle(tester, find.text('Settings'));
    expect(find.text('stub:/settings'), findsOneWidget);
  });

  testWidgets('back from the account page, the card reads the profile again', (
    tester,
  ) async {
    final (api, _) = await pumpMe(tester, locale: 'en');
    expect(api.callsTo('GET', '/owner/profile'), hasLength(1));
    api.on(
      'GET /owner/profile',
      (_) => profileJson(name: 'Ahmed', address: 'Abu Khalid'),
    );
    await tester.tap(find.text('أبو خالد'));
    await tester.pumpAndSettle();
    router.pop();
    await tester.pumpAndSettle();
    expect(api.callsTo('GET', '/owner/profile'), hasLength(2));
    expect(find.text('Abu Khalid'), findsOneWidget);
    expect(find.text('أبو خالد'), findsNothing);
  });

  testWidgets('the owner card says that it opens the account', (tester) async {
    final semantics = tester.ensureSemantics();
    await pumpMe(tester, locale: 'en');
    // One merged node: what the card is, what a tap does, and the tap itself.
    final data = tester.getSemantics(find.text('أبو خالد')).getSemanticsData();
    expect(data.label, contains('owner@example.com'));
    expect(data.hint, 'Open the account');
    expect(data.hasAction(SemanticsAction.tap), isTrue);
    semantics.dispose();
  });

  for (final theme in [AppThemeMode.light, AppThemeMode.dark]) {
    testWidgets('the owner card is a full touch target; its initial is '
        'on-accent ink (${theme.name})', (tester) async {
      await pumpMe(tester, locale: 'en', theme: theme);
      final card = find.ancestor(
        of: find.text('أبو خالد'),
        matching: find.byType(FTile),
      );
      expect(
        tester.getSize(card).height,
        greaterThanOrEqualTo(LnSize.minTouch),
      );
      final initial = tester.widget<Text>(
        find.descendant(
          of: find.byType(OwnerInitialAvatar),
          matching: find.byType(Text),
        ),
      );
      final palette = theme == AppThemeMode.dark
          ? LnPalette.dark
          : LnPalette.light;
      expect(initial.style?.color, palette.onAccent);
    });
  }

  for (final locale in ['en', 'ar']) {
    testWidgets('no visible title: the owner card leads, 30 dp under the '
        'status bar; the cards sit 16 dp apart ($locale)', (tester) async {
      final semantics = tester.ensureSemantics();
      await pumpMe(tester, locale: locale);
      final me = locale == 'en' ? 'Me' : 'أنا';
      expect(find.text(me), findsNothing);
      // The tab's name is still the screen's first heading.
      final header = tester
          .getSemantics(find.bySemanticsLabel(me).first)
          .getSemanticsData();
      expect(header.flagsCollection.isHeader, isTrue);
      Rect card(String text) => tester.getRect(
        find
            .ancestor(of: find.text(text), matching: find.byType(FTileGroup))
            .first,
      );
      final owner = card('أبو خالد');
      // The status bar is 24 dp tall in the harness.
      expect(owner.top, 24 + 30);
      final usage = tester.getRect(
        find
            .ancestor(
              of: find.byIcon(FIcons.chartColumn),
              matching: find.byType(DecoratedBox),
            )
            .last,
      );
      final agents = card(locale == 'en' ? 'Agents' : 'الوكلاء');
      expect(usage.top - owner.bottom, LnSpace.md);
      expect(agents.top - usage.bottom, LnSpace.md);
      semantics.dispose();
    });

    testWidgets('the owner card: 48 dp initial 16 dp in, name 20/24 bold, '
        'email 14/20 in the secondary ink, 80 dp tall ($locale)', (
      tester,
    ) async {
      await pumpMe(tester, locale: locale);
      final tile = tester.getRect(
        find.ancestor(of: find.text('أبو خالد'), matching: find.byType(FTile)),
      );
      expect(tile.height, 80);
      final avatar = tester.getRect(find.byType(OwnerInitialAvatar));
      expect(avatar.size, const Size.square(48));
      final rtl = locale == 'ar';
      expect(rtl ? tile.right - avatar.right : avatar.left - tile.left, 16);
      final name = tester.widget<Text>(find.text('أبو خالد'));
      expect(name.style?.fontSize, 20);
      expect(name.style?.fontWeight, FontWeight.w700);
      final email = tester.widget<Text>(find.textContaining('owner@example'));
      final palette = LnPalette.light;
      expect(email.style?.fontSize, 14);
      expect(email.style?.color, palette.fgMuted);
      // The text starts 12 dp after the avatar.
      final text = tester.getRect(find.text('أبو خالد'));
      expect(rtl ? avatar.left - text.right : text.left - avatar.right, 12);
    });
  }

  testWidgets('usage failure offers a retry', (tester) async {
    final (api, _) = await pumpMe(tester, locale: 'en', usageFails: true);
    await scrollTo(tester, find.textContaining('Could not connect'));
    expect(find.textContaining('Could not connect'), findsOneWidget);
    expect(api.callsTo('GET', '/usage/summary'), hasLength(1));
    api.on(
      'GET /usage/summary',
      (_) => {'input_tokens': 10, 'output_tokens': 20, 'cached_tokens': 30},
    );
    await tapAndSettle(tester, find.textContaining('Could not connect'));
    expect(api.callsTo('GET', '/usage/summary'), hasLength(2));
    expect(find.textContaining('Could not connect'), findsNothing);
    expect(find.text('10'), findsOneWidget);
    expect(find.text('30'), findsOneWidget);
  });

  testWidgets('ms:C7 the tasks icon mirrors in Arabic; ms:C8 sign-out is on '
      'the account page, not on Me', (tester) async {
    await pumpMe(tester);
    await scrollTo(tester, find.byIcon(LnIcons.listChecks));
    expect(LnIcons.listChecks.matchTextDirection, isTrue);
    expect(
      Directionality.of(tester.element(find.byIcon(LnIcons.listChecks))),
      TextDirection.rtl,
    );
    expect(find.byIcon(FIcons.listChecks), findsNothing);
    await scrollTo(tester, find.text('الإعدادات'));
    expect(find.text('تسجيل الخروج'), findsNothing);
    expect(find.byIcon(LnIcons.logOut), findsNothing);
  });

  for (final direction in ['ar', 'en']) {
    testWidgets('ms:C6 the usage card sits on the list rows\' grid and wears '
        'the group card ($direction)', (tester) async {
      await pumpMe(tester, locale: direction);
      Finder inRow(Finder of, IconData icon) => find.descendant(
        of: find.ancestor(of: of, matching: find.byType(Row)).first,
        matching: find.byIcon(icon),
      );
      final card = find.byIcon(FIcons.chartColumn);
      final cardChevron = inRow(card, FIcons.chevronRight);
      // The first row of the next card: «Agents».
      final row = find.ancestor(
        of: find.byIcon(FIcons.bot),
        matching: find.byType(FTile),
      );
      final rowIcon = find.byIcon(FIcons.bot);
      final rowChevron = find.descendant(
        of: row,
        matching: find.byIcon(FIcons.chevronRight),
      );
      expect(tester.getRect(card).left, tester.getRect(rowIcon).left);
      expect(tester.getSize(card), const Size.square(LnSize.tileIcon));
      expect(tester.getSize(card), tester.getSize(rowIcon));
      expect(tester.getRect(cardChevron).left, tester.getRect(rowChevron).left);
      expect(
        IconTheme.of(tester.element(card)).color,
        IconTheme.of(tester.element(rowIcon)).color,
      );
      // The header is a list row's height; the card is the group's fill and radius.
      final header = find.ancestor(of: card, matching: find.byType(Padding));
      expect(tester.getSize(header.first).height, LnSize.tileRow);
      final box = tester.widget<DecoratedBox>(
        find.ancestor(of: card, matching: find.byType(DecoratedBox)).last,
      );
      final decoration = box.decoration as BoxDecoration;
      expect(decoration.color, LnPalette.light.fill3);
      expect(decoration.border, isNull);
      expect(
        decoration.borderRadius,
        const BorderRadius.all(Radius.circular(LnRadius.group)),
      );
    });
  }

  testWidgets('every Me target is labelled and at least 48 dp', (tester) async {
    final semantics = tester.ensureSemantics();
    await pumpMe(tester, locale: 'en');
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
    semantics.dispose();
  });

  testWidgets('text at 1.3× lays out without overflow', (tester) async {
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await pumpMe(tester);
    await tester.drag(find.byType(MeScreen), const Offset(0, -2000));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      await withRealShadows(() async {
        await pumpMe(tester, locale: v.locale, theme: v.theme);
        await expectLater(
          find.byType(MaterialAppProbe.type),
          matchesGoldenFile('goldens/me_${v.name}.png'),
        );
      });
    });
  }

  testWidgets('golden light_ar bottom', (tester) async {
    await withRealShadows(() async {
      await pumpMe(tester);
      await tester.drag(find.byType(MeScreen), const Offset(0, -2000));
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialAppProbe.type),
        matchesGoldenFile('goldens/me_light_ar_bottom.png'),
      );
    });
  });
}

/// The root to capture: the whole app surface.
abstract final class MaterialAppProbe {
  static const type = WidgetsApp;
}
