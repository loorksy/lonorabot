// Behaviour of the design-kit items of integration 3 (K11–K16, Q1–Q13 of the lead's list): hint
// direction, the 48 dp tile title, the composer's input switch, the date separator, chat-row
// direction, translucent tonal fills, switch / segmented / chip / toast contrast, sheet title inset
// and the RTL-mirrored icons. K10 is in tappable_test.dart (the tab bar's in overlays_test.dart), K15
// in jump_to_latest_test.dart, Q2, Q11 and Q12 in test/l10n.
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/design/design.dart';

import 'fonts.dart';
import 'harness.dart';

Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  TextDirection direction = TextDirection.ltr,
  Brightness brightness = Brightness.light,
}) async {
  setGoldenViewport(tester);
  await tester.pumpWidget(
    lnTestApp(child: child, direction: direction, brightness: brightness),
  );
  await tester.pump();
}

double _luminance(Color c) => c.computeLuminance();

/// WCAG contrast of [fg] drawn over [bg] (both composited over [page] first).
double _contrast(Color fg, Color bg, {Color page = const Color(0xFFFFFFFF)}) {
  final b = Color.alphaBlend(bg, page);
  final f = Color.alphaBlend(fg, b);
  final hi = _luminance(f) > _luminance(b) ? _luminance(f) : _luminance(b);
  final lo = _luminance(f) > _luminance(b) ? _luminance(b) : _luminance(f);
  return (hi + 0.05) / (lo + 0.05);
}

const _palettes = [LnPalette.light, LnPalette.dark];

void main() {
  setUpAll(loadAppFonts);

  group('K11 LnTextField hint direction', () {
    testWidgets('the hint follows the given direction, the text its own', (
      tester,
    ) async {
      await _pump(
        tester,
        const Column(
          children: [
            LnTextField(
              key: ValueKey('split'),
              label: 'الحساب',
              hint: 'رقم الحساب',
              textDirection: TextDirection.ltr,
              hintTextDirection: TextDirection.rtl,
            ),
            LnTextField(
              key: ValueKey('plain'),
              hint: 'https://',
              textDirection: TextDirection.ltr,
            ),
          ],
        ),
        direction: TextDirection.rtl,
      );
      TextField field(String key) => tester.widget<TextField>(
        find.descendant(
          of: find.byKey(ValueKey(key)),
          matching: find.byType(TextField),
        ),
      );
      expect(field('split').textDirection, TextDirection.ltr);
      expect(field('split').decoration!.hintTextDirection, TextDirection.rtl);
      // Without it the hint keeps the text's direction, as before.
      expect(field('plain').decoration!.hintTextDirection, TextDirection.ltr);
      // The Arabic hint sits at the right, under its right-aligned label.
      final hint = tester.getRect(find.text('رقم الحساب'));
      final label = tester.getRect(find.text('الحساب'));
      expect(hint.right, moreOrLessEquals(label.right, epsilon: 20));
    });
  });

  group('K12 MinTouchTileTitle', () {
    testWidgets('lifts a one-line FTile to 48 dp like LnListTile, in and out '
        'of a group', (tester) async {
      await _pump(
        tester,
        ListView(
          children: [
            LnSection(
              children: [
                LnListTile(title: 'Kit row', onTap: () {}),
                FTile(
                  title: const MinTouchTileTitle(child: Text('Own row')),
                  onPress: () {},
                ),
              ],
            ),
            FTile(
              title: const MinTouchTileTitle(child: Text('Alone')),
              onPress: () {},
            ),
          ],
        ),
      );
      double height(String title) => tester
          .getSize(
            find
                .ancestor(
                  of: find.text(title),
                  matching: find.byWidgetPredicate((w) => w is FTappable),
                )
                .first,
          )
          .height;
      expect(height('Kit row'), LnSize.minTouch);
      expect(height('Own row'), height('Kit row'));
      expect(height('Alone'), greaterThanOrEqualTo(LnSize.minTouch));
      // The title stays at the start, centred in the row.
      final row = tester.getRect(
        find
            .ancestor(
              of: find.text('Own row'),
              matching: find.byWidgetPredicate((w) => w is FTappable),
            )
            .first,
      );
      expect(tester.getRect(find.text('Own row')).center.dy, row.center.dy);
    });
  });

  group('K13 Composer.inputEnabled', () {
    testWidgets('false disables the field and «+», the trailing slot stays', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      final controller = TextEditingController(text: 'draft');
      addTearDown(controller.dispose);
      var attached = 0;
      final sent = <String>[];
      await _pump(
        tester,
        Center(
          child: Composer(
            controller: controller,
            placeholder: 'Message',
            inputEnabled: false,
            onAttach: () => attached++,
            onSend: sent.add,
          ),
        ),
      );
      expect(
        find.semantics
            .byFlag(SemanticsFlag.isTextField)
            .evaluate()
            .single
            .getSemanticsData(),
        isSemantics(isTextField: true, hasEnabledState: true, isEnabled: false),
      );
      expect(
        find.semantics
            .byLabel('Add attachment')
            .evaluate()
            .single
            .getSemanticsData(),
        isSemantics(isButton: true, hasEnabledState: true, isEnabled: false),
      );
      tester.semantics.tap(find.semantics.byLabel('Send'));
      await tester.pump();
      expect(sent, ['draft']);
      expect(attached, 0);
      handle.dispose();
    });

    testWidgets('a recording mic stays in the slot while the input is off', (
      tester,
    ) async {
      await _pump(
        tester,
        Center(
          child: Composer(
            controller: TextEditingController(),
            placeholder: 'Message',
            inputEnabled: false,
            micButton: const SizedBox(key: ValueKey('recorder')),
          ),
        ),
      );
      expect(find.byKey(const ValueKey('recorder')), findsOneWidget);
      expect(tester.widget<TextField>(find.byType(TextField)).enabled, false);
    });

    testWidgets('it defaults to enabled, and a disabled composer wins', (
      tester,
    ) async {
      await _pump(
        tester,
        Column(
          children: [
            Composer(
              key: const ValueKey('on'),
              controller: TextEditingController(),
              placeholder: 'Message',
            ),
            Composer(
              key: const ValueKey('off'),
              controller: TextEditingController(),
              placeholder: 'Message',
              enabled: false,
              inputEnabled: true,
            ),
          ],
        ),
      );
      bool enabled(String key) => tester
          .widget<TextField>(
            find.descendant(
              of: find.byKey(ValueKey(key)),
              matching: find.byType(TextField),
            ),
          )
          .enabled!;
      expect(enabled('on'), true);
      expect(enabled('off'), false);
    });
  });

  group('K14 / Q3 DateSeparator', () {
    testWidgets('bottom shortens only the space below the label', (
      tester,
    ) async {
      await _pump(
        tester,
        const Column(
          children: [
            DateSeparator(key: ValueKey('a'), label: 'Today'),
            DateSeparator(
              key: ValueKey('b'),
              label: 'Yesterday',
              bottom: LnSpace.md - 5,
            ),
          ],
        ),
      );
      final a = tester.getRect(find.byKey(const ValueKey('a')));
      final b = tester.getRect(find.byKey(const ValueKey('b')));
      expect(a.height - b.height, 5);
      expect(tester.getRect(find.text('Today')).top - a.top, LnSpace.md);
      expect(tester.getRect(find.text('Yesterday')).top - b.top, LnSpace.md);
      expect(b.bottom - tester.getRect(find.text('Yesterday')).bottom, 11);
    });

    for (final p in _palettes) {
      testWidgets('the label uses the secondary ink (${p.brightness.name})', (
        tester,
      ) async {
        await _pump(
          tester,
          const DateSeparator(label: 'Today'),
          brightness: p.brightness,
        );
        final paragraph = tester.renderObject<RenderParagraph>(
          find.text('Today'),
        );
        final color = paragraph.text.style!.color!;
        expect(color, p.fgMuted);
        // Was the tertiary ink: 1.9:1 (light) / 2.7:1 (dark) on the page.
        expect(
          _contrast(color, p.bg, page: p.bg),
          greaterThan(p.isDark ? 7 : 4.3),
        );
      });
    }
  });

  group('K16 ChatListRow reading direction', () {
    Future<void> pumpRow(
      WidgetTester tester, {
      required String title,
      required String preview,
      String? prefix,
    }) => _pump(
      tester,
      Align(
        alignment: Alignment.topCenter,
        child: ChatListRow(
          avatar: const SizedBox.expand(),
          title: title,
          preview: preview,
          previewPrefix: prefix,
          time: '10:12',
        ),
      ),
      direction: TextDirection.rtl,
    );

    RenderParagraph paragraphOf(WidgetTester tester, String text) =>
        tester.renderObject<RenderParagraph>(find.textContaining(text));

    testWidgets('an English preview reads left to right in the Arabic '
        'interface, ellipsis at its end', (tester) async {
      const long =
          'I created Gold desk for the morning session and set its first routines';
      await pumpRow(tester, title: 'Atlas desk', preview: long);
      final preview = paragraphOf(tester, 'I created');
      expect(preview.textDirection, TextDirection.ltr);
      expect(preview.didExceedMaxLines, isTrue);
      // Aligned with the Arabic interface's start (the right edge).
      expect(preview.textAlign, TextAlign.right);
      // The run starts at the left of its line: the cut (and the ellipsis) is at its right end.
      final first = preview.getBoxesForSelection(
        const TextSelection(baseOffset: 0, extentOffset: 1),
      );
      expect(first.single.left, lessThan(6));
      final title = paragraphOf(tester, 'Atlas desk');
      expect(title.textDirection, TextDirection.ltr);
      expect(title.textAlign, TextAlign.right);
    });

    testWidgets('an Arabic preview keeps the interface direction', (
      tester,
    ) async {
      await pumpRow(tester, title: 'مكتب الذهب', preview: 'أنشأت روتين الصباح');
      expect(paragraphOf(tester, 'أنشأت').textDirection, TextDirection.rtl);
      expect(paragraphOf(tester, 'مكتب').textDirection, TextDirection.rtl);
      await pumpRow(
        tester,
        title: 'مكتب الذهب',
        preview: 'أنشأت روتين الصباح',
        prefix: 'مسودة:',
      );
      expect(paragraphOf(tester, 'مسودة').textDirection, TextDirection.rtl);
    });

    testWidgets('an English speaker and message read as one English line', (
      tester,
    ) async {
      // Was «…Rates decision at 14:0 :Morning news» (the line forced right to left).
      await pumpRow(
        tester,
        title: 'Trading desk',
        preview:
            'Rates decision at 14:00 GMT, then the plan for the London session',
        prefix: 'Morning news:',
      );
      final line = paragraphOf(tester, 'Morning news:');
      expect(line.textDirection, TextDirection.ltr);
      expect(line.text.toPlainText(), startsWith('Morning news: Rates'));
      expect(line.didExceedMaxLines, isTrue);
      final first = line.getBoxesForSelection(
        const TextSelection(baseOffset: 0, extentOffset: 1),
      );
      expect(first.single.left, lessThan(6));
    });

    testWidgets('an Arabic prefix before an English message: each in its own '
        'direction, the prefix at the start', (tester) async {
      await pumpRow(
        tester,
        title: 'Gold desk',
        preview:
            'Hello there, the plan for the London session is ready to review',
        prefix: 'أنت:',
      );
      final prefix = find.text('أنت:');
      final message = find.textContaining('Hello there');
      expect(
        tester.renderObject<RenderParagraph>(prefix).textDirection,
        TextDirection.rtl,
      );
      final body = tester.renderObject<RenderParagraph>(message);
      expect(body.textDirection, TextDirection.ltr);
      expect(body.didExceedMaxLines, isTrue);
      // The prefix leads at the right; the message sits to its left, cut at its own end.
      expect(
        tester.getRect(message).right,
        lessThanOrEqualTo(tester.getRect(prefix).left),
      );
    });
  });

  group('Q1 tonal fills, dividers and field borders read on cards', () {
    for (final p in _palettes) {
      test('they stay translucent (${p.brightness.name})', () {
        final theme = lnForuiTheme(p);
        final secondary = theme.buttonStyles.secondary.decoration;
        expect(secondary.resolve({}).color, p.fill3);
        expect(
          theme.buttonStyles.primary.decoration.resolve({
            WidgetState.disabled,
          }).color,
          p.fill3,
        );
        expect(theme.dividerStyles.horizontalStyle.color, p.border);
        final border =
            theme.textFieldStyle.border.resolve({}) as OutlineInputBorder;
        expect(border.borderSide.color, p.border);
        // forui's width and shape are kept.
        final forui = FTextFieldStyle.inherit(
          colors: theme.colors,
          typography: theme.typography,
          style: theme.style,
        ).border.resolve({}) as OutlineInputBorder;
        expect(border.borderSide.width, forui.borderSide.width);
        expect(border.borderRadius, forui.borderRadius);
        // Focused and error borders are forui's.
        final focused = theme.textFieldStyle.border.resolve({
          WidgetState.focused,
        }) as OutlineInputBorder;
        expect(focused.borderSide.color, theme.colors.primary);
        // Over the page the fill is the solid value forui derives its other states from.
        expect(Color.alphaBlend(p.fill3, p.bg), theme.colors.secondary);
      });
    }

    test('a dark tonal button on a card lands at #2C2C2C, on the page at '
        '#222222', () {
      const d = LnPalette.dark;
      final fill = lnForuiTheme(d).buttonStyles.secondary.decoration
          .resolve({})
          .color!;
      expect(Color.alphaBlend(fill, d.surface).toARGB32(), 0xFF2C2C2C);
      expect(Color.alphaBlend(fill, d.bg).toARGB32(), 0xFF222222);
    });
  });

  group('Q4 LnSwitch dark off state', () {
    test('the dark off switch has a visible thumb and track', () {
      const d = LnPalette.dark;
      final style = lnForuiTheme(d).switchStyle;
      final track = style.trackColor.resolve({});
      final thumb = style.thumbColor.resolve({});
      expect(track, d.fgSubtle);
      expect(thumb, d.fg);
      for (final page in [d.bg, d.surface]) {
        expect(_contrast(thumb, track, page: page), greaterThan(3));
        expect(_contrast(thumb, page, page: page), greaterThan(3));
      }
      // The on and disabled states are forui's.
      final forui = FSwitchStyle.inherit(
        colors: lnForuiColors(d),
        style: lnForuiTheme(d).style,
      );
      for (final states in [
        {WidgetState.selected},
        {WidgetState.disabled},
        {WidgetState.disabled, WidgetState.selected},
      ]) {
        expect(
          style.trackColor.resolve(states),
          forui.trackColor.resolve(states),
        );
        expect(
          style.thumbColor.resolve(states),
          forui.thumbColor.resolve(states),
        );
      }
    });

    test('the light switch keeps forui\'s look', () {
      const l = LnPalette.light;
      final style = lnForuiTheme(l).switchStyle;
      expect(style.trackColor.resolve({}), lnForuiColors(l).border);
      expect(style.thumbColor.resolve({}), l.bg);
    });
  });

  group('Q5 LnSegmented', () {
    for (final p in _palettes) {
      testWidgets('the selected segment uses the segmentedSelected fill '
          '(${p.brightness.name})', (tester) async {
        await _pump(
          tester,
          LnSegmented<int>(
            segments: const [
              LnSegment(value: 0, label: 'Active'),
              LnSegment(value: 1, label: 'Done'),
            ],
            selected: 0,
            onChanged: (_) {},
          ),
          brightness: p.brightness,
        );
        final bar = tester.widget<TabBar>(find.byType(TabBar));
        final fill = (bar.indicator! as BoxDecoration).color!;
        expect(fill, p.segmentedSelected);
        // The thumb reads raised: lighter than (dark) or as light as (light) its track.
        final track = lnForuiColors(p).muted;
        final thumb = Color.alphaBlend(fill, track);
        if (p.isDark) {
          expect(
            thumb.computeLuminance(),
            greaterThan(track.computeLuminance()),
          );
        } else {
          expect(thumb, const Color(0xFFFFFFFF));
        }
      });
    }

    test('segmentedSelected is white (light) / 24 % white (dark)', () {
      expect(LnPalette.light.segmentedSelected, const Color(0xFFFFFFFF));
      expect(LnPalette.dark.segmentedSelected, const Color(0x3DFFFFFF));
    });
  });

  group('Q6 StatusChip label contrast', () {
    for (final p in _palettes) {
      testWidgets('every label reads ≥ 4.5:1 on its fill '
          '(${p.brightness.name})', (tester) async {
        const kinds = [
          StatusChipKind.neutral,
          StatusChipKind.running,
          StatusChipKind.waiting,
          StatusChipKind.success,
          StatusChipKind.error,
          StatusChipKind.brand,
        ];
        await _pump(
          tester,
          Column(
            children: [
              for (final k in kinds) StatusChip(label: k.name, kind: k),
            ],
          ),
          brightness: p.brightness,
        );
        for (final k in kinds) {
          final ink = tester
              .renderObject<RenderParagraph>(find.text(k.name))
              .text
              .style!
              .color!;
          final accent = switch (k) {
            StatusChipKind.running => p.selection,
            StatusChipKind.waiting => p.pending,
            StatusChipKind.success => p.success,
            StatusChipKind.error => p.error,
            _ => p.brand,
          };
          final tint = k == StatusChipKind.neutral
              ? p.fill2
              : accent.withValues(alpha: p.isDark ? 0.18 : 0.12);
          // The page, a raised card and (light) the #F2F2F2 grey tile.
          for (final page in [
            p.bg,
            p.surface,
            if (!p.isDark) const Color(0xFFF2F2F2),
          ]) {
            expect(
              _contrast(ink, tint, page: page),
              greaterThanOrEqualTo(4.5),
              reason: '${k.name} on ${page.toARGB32().toRadixString(16)}',
            );
          }
        }
      });
    }
  });

  group('Q7 text-safe greens', () {
    test(
      'success and positive text read ≥ 4.5:1 on white and the grey tile',
      () {
        const l = LnPalette.light;
        for (final ink in [l.successText, l.positiveText]) {
          for (final page in const [Color(0xFFFFFFFF), Color(0xFFF2F2F2)]) {
            expect(_contrast(ink, page, page: page), greaterThanOrEqualTo(4.5));
          }
        }
        // Dark mode keeps the base greens (they already read on the dark page).
        const d = LnPalette.dark;
        expect(d.successText, d.success);
        expect(d.positiveText, d.positive);
        for (final ink in [d.successText, d.positiveText]) {
          expect(_contrast(ink, d.bg, page: d.bg), greaterThanOrEqualTo(4.5));
        }
      },
    );
  });

  group('Q8 toast action', () {
    test('reads ≥ 4.5:1 on the toast in both modes', () {
      for (final p in _palettes) {
        expect(
          _contrast(p.toastAction, p.inverseSurface, page: p.bg),
          greaterThanOrEqualTo(4.5),
        );
      }
    });
  });

  group('Q9 sheet title inset', () {
    for (final direction in TextDirection.values) {
      testWidgets('the title starts at the body\'s inset (${direction.name})', (
        tester,
      ) async {
        await _pump(
          tester,
          Builder(
            builder: (context) => Center(
              child: GestureDetector(
                onTap: () => showLnSheet<void>(
                  context,
                  title: 'Sheet title',
                  builder: (_) => const Text('Sheet body'),
                ),
                child: const Text('open'),
              ),
            ),
          ),
          direction: direction,
        );
        await tester.tap(find.text('open'));
        await tester.pumpAndSettle();
        final title = tester.getRect(find.text('Sheet title'));
        final body = tester.getRect(find.text('Sheet body'));
        expect(title.left, body.left);
        expect(title.right, body.right);
        expect(title.left, 16);
      });

      testWidgets('an action menu title starts where its rows\' content does '
          '(${direction.name})', (tester) async {
        await _pump(
          tester,
          Builder(
            builder: (context) => Center(
              child: GestureDetector(
                onTap: () => showLnActionMenu<int>(
                  context,
                  title: 'Conversation',
                  actions: const [
                    LnMenuAction(label: 'Pin', icon: FIcons.pin, value: 1),
                    LnMenuAction(label: 'Plain row', value: 2),
                  ],
                ),
                child: const Text('open'),
              ),
            ),
          ),
          direction: direction,
        );
        await tester.tap(find.text('open'));
        await tester.pumpAndSettle();
        final rtl = direction == TextDirection.rtl;
        double start(Rect r) => rtl ? goldenSize.width - r.right : r.left;
        final title = tester.getRect(find.text('Conversation'));
        // The title's Text spans the sheet; its glyphs start at the paragraph's start.
        expect(start(title), 23);
        expect(start(tester.getRect(find.byIcon(FIcons.pin))), 23);
        expect(start(tester.getRect(find.text('Plain row'))), 23);
      });
    }
  });

  group('Q13 LnIcons', () {
    test('are forui\'s Lucide glyphs that follow the reading direction', () {
      const pairs = [
        (LnIcons.list, FIcons.list),
        (LnIcons.listChecks, FIcons.listChecks),
        (LnIcons.listTodo, FIcons.listTodo),
        (LnIcons.logOut, FIcons.logOut),
        (LnIcons.reply, FIcons.reply),
        (LnIcons.undo2, FIcons.undo2),
      ];
      for (final (mirrored, lucide) in pairs) {
        expect(mirrored.codePoint, lucide.codePoint);
        expect(mirrored.fontFamily, lucide.fontFamily);
        expect(mirrored.fontPackage, lucide.fontPackage);
        expect(mirrored.matchTextDirection, isTrue);
      }
    });

    bool mirrored(WidgetTester tester, Finder icon) =>
        tester
            .renderObject<RenderBox>(
              find.descendant(of: icon, matching: find.byType(RichText)),
            )
            .getTransformTo(null)
            .storage[0] <
        0;

    for (final direction in TextDirection.values) {
      testWidgets('an LnListTile prefix and the reply bar flip only in RTL '
          '(${direction.name})', (tester) async {
        await _pump(
          tester,
          Column(
            children: [
              const LnSection(
                children: [LnListTile(title: 'Sign out', icon: LnIcons.logOut)],
              ),
              ComposerReplyBar(
                title: 'Replying',
                text: 'Hello',
                onClose: () {},
              ),
            ],
          ),
          direction: direction,
        );
        final rtl = direction == TextDirection.rtl;
        expect(
          mirrored(
            tester,
            find.byWidgetPredicate(
              (w) => w is Icon && w.icon == LnIcons.logOut,
            ),
          ),
          rtl,
        );
        expect(
          mirrored(
            tester,
            find.byWidgetPredicate((w) => w is Icon && w.icon == LnIcons.reply),
          ),
          rtl,
        );
      });
    }
  });

  group('F4 kit side: localized loading and unread labels', () {
    testWidgets('SkeletonRows and UnreadPill speak the caller\'s words', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await _pump(
        tester,
        const Column(
          children: [
            UnreadPill(count: 3, semanticLabel: '3 غير مقروءة'),
            SkeletonRows(
              count: 1,
              animate: false,
              semanticLabel: 'جارٍ التحميل',
            ),
          ],
        ),
        direction: TextDirection.rtl,
      );
      expect(find.bySemanticsLabel('3 غير مقروءة'), findsOneWidget);
      expect(find.bySemanticsLabel('جارٍ التحميل'), findsOneWidget);
      expect(find.bySemanticsLabel(RegExp('unread|Loading')), findsNothing);
      handle.dispose();
    });

    testWidgets('the English defaults stay for the gallery', (tester) async {
      final handle = tester.ensureSemantics();
      await _pump(
        tester,
        const Column(
          children: [
            UnreadPill(count: 3),
            SkeletonRows(count: 1, animate: false),
          ],
        ),
      );
      expect(find.bySemanticsLabel('3 unread'), findsOneWidget);
      expect(find.bySemanticsLabel('Loading'), findsOneWidget);
      handle.dispose();
    });
  });
}
