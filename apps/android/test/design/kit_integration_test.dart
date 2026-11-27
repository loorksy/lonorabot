// Behaviour of the design-kit integration items (K1–K9 of the lead's integration list): RTL chevrons,
// text-field pass-throughs, touch targets, ErrorState icon, tokens, confirm layout, chips and tiles,
// accessibility nodes and the composer's trailing slot.
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
}) async {
  setGoldenViewport(tester);
  await tester.pumpWidget(lnTestApp(child: child, direction: direction));
  await tester.pump();
}

/// The brief's largest text scale for every screen.
void _scaleText(WidgetTester tester) {
  tester.platformDispatcher.textScaleFactorTestValue = 1.3;
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
}

/// Whether the chevron drawn under [scope] points left on screen: its glyph (Lucide's chevronLeft or
/// chevronRight) combined with every mirroring between the glyph and the screen (Lucide chevrons mirror
/// themselves in RTL through `matchTextDirection`).
bool _chevronPointsLeft(WidgetTester tester, Finder scope) {
  final icon = find.descendant(
    of: scope,
    matching: find.byWidgetPredicate(
      (w) =>
          w is Icon &&
          (w.icon == FIcons.chevronRight || w.icon == FIcons.chevronLeft),
    ),
  );
  expect(icon, findsOneWidget);
  final glyphLeft = tester.widget<Icon>(icon).icon == FIcons.chevronLeft;
  final glyph = tester.renderObject<RenderBox>(
    find.descendant(of: icon, matching: find.byType(RichText)),
  );
  final mirrored = glyph.getTransformTo(null).storage[0] < 0;
  return glyphLeft != mirrored;
}

void main() {
  setUpAll(loadAppFonts);

  group('K1 forward chevrons point to the reading end', () {
    final cases = <String, Widget>{
      'LnListTile': LnSection(
        children: [LnListTile(title: 'Language', onTap: () {})],
      ),
      'SectionHeader': SectionHeader(title: 'Recommendation', onTap: () {}),
      'InlineEventRow': InlineEventRow(
        icon: const Icon(FIcons.moonStar),
        label: 'Memory updated',
        onTap: () {},
      ),
    };
    for (final MapEntry(key: name, value: widget) in cases.entries) {
      for (final direction in TextDirection.values) {
        testWidgets('$name ${direction.name}', (tester) async {
          await _pump(
            tester,
            ListView(children: [widget]),
            direction: direction,
          );
          expect(
            _chevronPointsLeft(tester, find.byWidget(widget)),
            direction == TextDirection.rtl,
          );
        });
      }
    }
  });

  group('K2 LnTextField', () {
    testWidgets('passes input flags, direction and length to its field', (
      tester,
    ) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await _pump(
        tester,
        ListView(
          children: [
            LnTextField(
              controller: controller,
              hint: 'https://',
              autocorrect: false,
              enableSuggestions: false,
              enableIMEPersonalizedLearning: false,
              textDirection: TextDirection.ltr,
              maxLength: 5,
            ),
          ],
        ),
        direction: TextDirection.rtl,
      );
      final field = tester.widget<TextField>(find.byType(TextField));
      expect(field.autocorrect, isFalse);
      expect(field.enableSuggestions, isFalse);
      expect(field.enableIMEPersonalizedLearning, isFalse);
      expect(field.maxLength, 5);
      expect(
        tester.widget<EditableText>(find.byType(EditableText)).textDirection,
        TextDirection.ltr,
      );
      // The hint reads left to right inside the Arabic interface.
      expect(
        tester.widget<Text>(find.text('https://')).textDirection,
        TextDirection.ltr,
      );

      await tester.enterText(find.byType(TextField), 'abcdefgh');
      await tester.pump();
      expect(controller.text, 'abcde');
      expect(find.text('5/5'), findsNothing);
    });

    testWidgets('keeps the platform defaults when not asked', (tester) async {
      await _pump(tester, ListView(children: const [LnTextField()]));
      final field = tester.widget<TextField>(find.byType(TextField));
      expect(field.autocorrect, isTrue);
      expect(field.enableSuggestions, isTrue);
      expect(field.enableIMEPersonalizedLearning, isTrue);
      expect(field.textDirection, isNull);
      expect(field.maxLength, isNull);
    });
  });

  group('K3 touch targets', () {
    test('the minimum touch target token is 48 dp', () {
      expect(LnSize.minTouch, 48);
    });

    for (final direction in TextDirection.values) {
      testWidgets(
        'a one-line LnListTile is at least 48 dp tall (${direction.name})',
        (tester) async {
          await _pump(
            tester,
            ListView(
              children: [
                LnSection(
                  children: [
                    LnListTile(
                      title: 'Language',
                      value: 'English',
                      onTap: () {},
                    ),
                    const LnListTile(title: 'Version', value: '1.0'),
                  ],
                ),
              ],
            ),
            direction: direction,
          );
          final tappable = find.ancestor(
            of: find.text('Language'),
            matching: find.byWidgetPredicate((w) => w is FTappable),
          );
          expect(
            tester.getSize(tappable.first).height,
            greaterThanOrEqualTo(48),
          );
          expect(
            tester
                .getSize(
                  find.ancestor(
                    of: find.text('Version'),
                    matching: find.byType(LnListTile),
                  ),
                )
                .height,
            greaterThanOrEqualTo(48),
          );
        },
      );
    }

    testWidgets('only one-line LnListTiles grow: two-line rows keep forui\'s '
        'height', (tester) async {
      await _pump(
        tester,
        ListView(
          children: [
            LnSection(
              children: [
                LnListTile(title: 'Language', onTap: () {}),
                LnListTile(
                  title: 'Dark mode',
                  subtitle: 'Follow system',
                  onTap: () {},
                ),
                FTile(
                  title: const Text('Dark mode'),
                  subtitle: const Text('Follow system'),
                  onPress: () {},
                ),
              ],
            ),
          ],
        ),
      );
      // Each row's pressable box (inside forui's divider margin).
      final rows = find.byWidgetPredicate((w) => w is FTappable);
      expect(rows, findsNWidgets(3));
      final [one, two, plain] = [for (var i = 0; i < 3; i++) rows.at(i)]
          .map(tester.getRect)
          .toList();
      expect(one.height, LnSize.minTouch);
      expect(two.height, plain.height);
      // Every other tile keeps forui 0.15.1's own padding (no theme-wide growth).
      final theme = FTheme.of(tester.element(find.byType(LnSection)));
      for (final style in [theme.tileStyle, theme.tileGroupStyle.tileStyle]) {
        expect(
          style.contentStyle.padding,
          const EdgeInsetsDirectional.fromSTEB(15, 13, 10, 13),
        );
      }
      // The title sits in the middle of the taller row.
      expect(tester.getRect(find.text('Language')).center.dy, one.center.dy);
    });

    testWidgets(
      'LnTextField reports the same baseline in dry and real layout',
      (tester) async {
        await _pump(
          tester,
          ListView(
            children: const [
              Row(
                key: ValueKey('row'),
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: [
                  Text('Label', style: TextStyle(fontSize: 40)),
                  Expanded(child: LnTextField(hint: 'x')),
                ],
              ),
            ],
          ),
        );
        // The field sets the row's depth below the baseline, so a dry baseline off by the band's
        // padding changes the row's dry height.
        final row = tester.renderObject<RenderBox>(
          find.byKey(const ValueKey('row')),
        );
        expect(row.getDryLayout(row.constraints), row.size);
      },
    );

    testWidgets('LnTextField keeps its box and takes taps in a 48 dp band', (
      tester,
    ) async {
      final focus = FocusNode();
      addTearDown(focus.dispose);
      await _pump(
        tester,
        Padding(
          padding: const EdgeInsets.only(top: 100),
          child: Column(
            children: [LnTextField(hint: 'Name', focusNode: focus)],
          ),
        ),
      );
      final box = tester.getRect(find.byType(InputDecorator));
      // The visible field stays forui's height (shorter than the target).
      expect(box.height, lessThan(48));
      expect(tester.getSize(find.byType(LnTextField)).height, 48);

      // Outside the band: nothing.
      await tester.tapAt(Offset(box.center.dx, box.top - 10));
      await tester.pump();
      expect(focus.hasFocus, isFalse);

      // In the band above the box.
      await tester.tapAt(Offset(box.center.dx, box.top - 3));
      await tester.pump();
      expect(focus.hasFocus, isTrue);

      focus.unfocus();
      await tester.pump();
      // In the band below the box.
      await tester.tapAt(Offset(box.center.dx, box.bottom + 3));
      await tester.pump();
      expect(focus.hasFocus, isTrue);
    });

    testWidgets('a tappable InlineEventRow is at least 48 dp tall', (
      tester,
    ) async {
      var taps = 0;
      await _pump(
        tester,
        ListView(
          children: [
            InlineEventRow(
              icon: const Icon(FIcons.moonStar),
              label: 'Memory updated',
              onTap: () => taps++,
            ),
          ],
        ),
      );
      final row = find.byType(InlineEventRow);
      expect(tester.getSize(row).height, greaterThanOrEqualTo(48));
      await tester.tapAt(tester.getRect(row).topCenter + const Offset(0, 2));
      expect(taps, 1);
    });

    testWidgets('an InlineEventRow without a tap is text, not a button', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      await _pump(
        tester,
        ListView(
          children: const [
            InlineEventRow(
              icon: Icon(FIcons.phone),
              label: 'Call completed',
              detail: '2 min',
            ),
          ],
        ),
      );
      expect(
        tester.getSemantics(find.bySemanticsLabel('Call completed, 2 min')),
        isSemantics(label: 'Call completed, 2 min', isButton: false),
      );
      semantics.dispose();
    });

    testWidgets('InlineEventRow wraps to maxLines and hugs its label', (
      tester,
    ) async {
      const long =
          'The broker refused the order because the market is closed for the day';
      await _pump(
        tester,
        ListView(
          children: [
            const InlineEventRow(
              icon: Icon(FIcons.info),
              label: long,
              alignment: InlineEventAlignment.start,
              showChevron: false,
              maxLines: 3,
            ),
            Row(
              children: [
                Flexible(
                  child: InlineEventRow(
                    icon: const Icon(FIcons.loader),
                    label: 'Working',
                    alignment: InlineEventAlignment.start,
                    showChevron: false,
                    hug: true,
                    onTap: () {},
                  ),
                ),
                const Text('Stop'),
              ],
            ),
          ],
        ),
      );
      final text = find.descendant(
        of: find.ancestor(
          of: find.byIcon(FIcons.info),
          matching: find.byType(InlineEventRow),
        ),
        matching: find.byType(RichText),
      );
      final lines = tester.renderObject<RenderParagraph>(text.last);
      expect(lines.size.height, greaterThan(20 * 1.5));
      expect(tester.widget<RichText>(text.last).maxLines, 3);
      // The action follows the label instead of being pushed to the far end.
      final working = tester.getRect(find.text('Working'));
      final stop = tester.getRect(find.text('Stop'));
      expect(stop.left - working.right, lessThan(LnSpace.md));
    });

    testWidgets('a start-aligned InlineEventRow fills its line by default, so '
        'it starts at the start edge in any Column', (tester) async {
      for (final direction in TextDirection.values) {
        await _pump(
          tester,
          Column(
            children: [
              InlineEventRow(
                icon: const Icon(FIcons.phone),
                label: 'Call completed',
                alignment: InlineEventAlignment.start,
                onTap: () {},
              ),
              const InlineEventRow(
                icon: Icon(FIcons.phone),
                label: 'Read only',
                alignment: InlineEventAlignment.start,
              ),
            ],
          ),
          direction: direction,
        );
        final rtl = direction == TextDirection.rtl;
        // Indent 16, icon slot 22, gap 4.5.
        const start = 16 + 22 + 4.5;
        for (final label in ['Call completed', 'Read only']) {
          final text = tester.getRect(find.text(label));
          expect(
            rtl ? goldenSize.width - text.right : text.left,
            moreOrLessEquals(start),
            reason: '$label ${direction.name}',
          );
        }
      }
    });

    testWidgets('a one-line label sits at the same height whatever maxLines', (
      tester,
    ) async {
      await _pump(
        tester,
        ListView(
          children: [
            for (final lines in [1, 3])
              InlineEventRow(
                key: ValueKey(lines),
                icon: const Icon(FIcons.loader),
                label: 'Working $lines',
                alignment: InlineEventAlignment.start,
                maxLines: lines,
                onTap: () {},
              ),
          ],
        ),
      );
      double offset(int lines) =>
          tester.getRect(find.text('Working $lines')).top -
          tester.getRect(find.byKey(ValueKey(lines))).top;
      expect(offset(3), offset(1));
    });

    testWidgets('no overflow at 1.3 text scale', (tester) async {
      _scaleText(tester);
      for (final direction in TextDirection.values) {
        await _pump(
          tester,
          ListView(
            children: [
              LnSection(
                children: [
                  LnListTile(
                    title: 'Language',
                    icon: FIcons.languages,
                    value: 'English',
                    onTap: () {},
                  ),
                  LnListTile(
                    title: 'Dark mode',
                    subtitle: 'Follow system',
                    trailing: LnSwitch(value: true, onChanged: (_) {}),
                  ),
                ],
              ),
              const Padding(
                padding: EdgeInsets.all(LnSpace.pageGutter),
                child: LnTextField(
                  label: 'Server address',
                  hint: 'https://lonora.example',
                  helper: 'The address of your Lonora server',
                  prefix: Icon(FIcons.globe),
                  textDirection: TextDirection.ltr,
                  maxLength: 200,
                ),
              ),
              InlineEventRow(
                icon: const Icon(FIcons.moonStar),
                label: 'Memory updated',
                detail: '2 changes',
                onTap: () {},
              ),
              Row(
                children: [
                  Flexible(
                    child: InlineEventRow(
                      icon: const Icon(FIcons.info),
                      label: 'The broker refused the order because the market is closed',
                      alignment: InlineEventAlignment.start,
                      maxLines: 2,
                      hug: true,
                      onTap: () {},
                    ),
                  ),
                  const Text('Stop'),
                ],
              ),
            ],
          ),
          direction: direction,
        );
        expect(tester.takeException(), isNull, reason: direction.name);
        expect(
          tester
              .getSize(
                find.ancestor(
                  of: find.text('Language'),
                  matching: find.byWidgetPredicate((w) => w is FTappable),
                ),
              )
              .height,
          greaterThan(LnSize.minTouch),
        );
      }
    });
  });

  group('K4 ErrorState', () {
    testWidgets('shows the warning by default and the given icon', (
      tester,
    ) async {
      await _pump(
        tester,
        Column(
          children: [
            Expanded(
              child: ErrorState(
                title: 'Could not load',
                retryLabel: 'Retry',
                onRetry: () {},
              ),
            ),
            Expanded(
              child: ErrorState(
                title: 'No connection',
                retryLabel: 'Retry',
                icon: FIcons.wifiOff,
                onRetry: () {},
              ),
            ),
          ],
        ),
      );
      expect(find.byIcon(FIcons.triangleAlert), findsOneWidget);
      expect(find.byIcon(FIcons.wifiOff), findsOneWidget);
    });
  });

  group('K5 tokens', () {
    test('requested colour roles carry the requested values', () {
      const l = LnPalette.light;
      const d = LnPalette.dark;
      expect(l.onAccent, const Color(0xFFFFFFFF));
      expect(d.onAccent, const Color(0xFFFFFFFF));
      expect(l.link, const Color(0xFF2276EC));
      expect(d.link, const Color(0xFF69A4F8));
      expect(l.inverseSurface, const Color(0xF2141414));
      expect(d.inverseSurface, const Color(0xFF3A3A3C));
      expect(l.onInverse, const Color(0xFFFFFFFF));
      expect(l.onInverseMuted, const Color(0xB3FFFFFF));
      expect(l.inverseFill, const Color(0x26FFFFFF));
      expect(l.toastAction, const Color(0xFFB4B3FF));
      expect(d.toastAction, const Color(0xFFB4B3FF));
      expect(LnPalette.inkWhite, const Color(0xFFFFFFFF));
      expect(LnPalette.inkWhiteMuted, const Color(0x99FFFFFF));
      expect(LnPalette.inkWhiteSubtle, const Color(0x4DFFFFFF));
      expect(LnPalette.disabledOpacity, 0.45);
      expect(l.reactionSelected, l.selection.withValues(alpha: 0.14));
      expect(d.reactionSelected, d.selection.withValues(alpha: 0.28));
      expect(l.reactionSelectedBorder, l.selection.withValues(alpha: 0.5));
      expect(l.jumpFlash, l.selection.withValues(alpha: 0.12));
      expect(LnSize.reactionPickerEmoji, 26);
      expect(LnSize.reactionListEmoji, 24);
    });

    test('agent hub gradients follow the five agent palettes', () {
      expect(
        [
          for (final p in LnAgentPalette.values)
            (p.hubStart.toARGB32(), p.hubEnd.toARGB32()),
        ],
        [
          (0xFF143352, 0xFF183D62),
          (0xFF422424, 0xFF502B2B),
          (0xFF453021, 0xFF533A28),
          (0xFF3B322B, 0xFF473C34),
          (0xFF333333, 0xFF3D3D3D),
        ],
      );
    });

    test('the toaster is drawn from the inverse tokens', () {
      for (final p in [LnPalette.light, LnPalette.dark]) {
        final toast = lnForuiTheme(p).toasterStyle.toastStyle;
        expect(toast.decoration.color, p.inverseSurface);
        expect(toast.titleTextStyle.color, p.onInverse);
        expect(toast.descriptionTextStyle.color, p.onInverseMuted);
      }
    });
  });

  group('K6 showLnConfirm', () {
    Future<List<Rect>> open(
      WidgetTester tester,
      String confirm,
      String cancel, {
      TextDirection direction = TextDirection.ltr,
    }) async {
      await _pump(
        tester,
        direction: direction,
        Center(
          child: Builder(
            builder: (context) => BlockButton(
              label: 'Open',
              expand: false,
              onPressed: () => showLnConfirm(
                context,
                title: 'Cancel this watch?',
                confirmLabel: confirm,
                cancelLabel: cancel,
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      return [
        tester.getRect(
          find.ancestor(of: find.text(confirm), matching: find.byType(FButton)),
        ),
        tester.getRect(
          find.ancestor(of: find.text(cancel), matching: find.byType(FButton)),
        ),
      ];
    }

    testWidgets('keeps short labels on one row', (tester) async {
      final [confirm, cancel] = await open(tester, 'Delete', 'Cancel');
      expect(confirm.center.dy, cancel.center.dy);
      expect(confirm.left, greaterThan(cancel.right));
    });

    testWidgets('stacks labels that do not fit, confirm on top', (
      tester,
    ) async {
      final [confirm, cancel] = await open(
        tester,
        'Cancel the watch for good',
        'Keep watching it',
      );
      expect(confirm.bottom, lessThanOrEqualTo(cancel.top));
    });

    for (final (confirmLabel, cancelLabel, direction) in [
      ('Delete this conversation for everyone', 'Cancel', TextDirection.ltr),
      (
        'حذف المحادثة نهائيًا من جميع الأجهزة المرتبطة بالحساب الآن',
        'إلغاء',
        TextDirection.rtl,
      ),
    ]) {
      testWidgets('wraps a label wider than the dialog at 1.3 text scale '
          '(${direction.name})', (tester) async {
        _scaleText(tester);
        final [confirm, cancel] = await open(
          tester,
          confirmLabel,
          cancelLabel,
          direction: direction,
        );
        expect(confirm.bottom, lessThanOrEqualTo(cancel.top));
        final dialog = tester.getRect(find.byType(FDialog));
        expect(dialog.left, lessThanOrEqualTo(confirm.left));
        expect(confirm.right, lessThanOrEqualTo(dialog.right));
        final label = tester.renderObject<RenderParagraph>(
          find.descendant(
            of: find.text(confirmLabel),
            matching: find.byType(RichText),
          ),
        );
        expect(label.didExceedMaxLines, isFalse);
        expect(label.size.height, greaterThan(label.preferredLineHeight * 1.5));
      });
    }
  });

  group('K7 chips and tiles', () {
    testWidgets('LnChoiceChip: 36 dp chip in a 48 dp target, selection', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      var taps = 0;
      await _pump(
        tester,
        Column(
          children: [
            LnChipStrip(
              children: [
                LnChoiceChip(label: 'All', selected: true, onTap: () => taps++),
                LnChoiceChip(
                  label: 'Open',
                  selected: false,
                  icon: FIcons.clock,
                  onTap: () {},
                ),
              ],
            ),
          ],
        ),
      );
      expect(tester.getSize(find.byType(LnChipStrip)).height, 48);
      final chip = find.ancestor(
        of: find.text('All'),
        matching: find.byType(LnChoiceChip),
      );
      expect(tester.getSize(chip).height, 48);
      expect(
        tester
            .getSize(
              find.descendant(
                of: chip,
                matching: find.byType(AnimatedContainer),
              ),
            )
            .height,
        LnChoiceChip.height,
      );
      expect(
        tester.getSemantics(find.bySemanticsLabel('All')),
        isSemantics(label: 'All', isButton: true, isSelected: true),
      );
      // The 48 dp target reaches above the 36 dp chip.
      await tester.tapAt(tester.getRect(chip).topCenter + const Offset(0, 2));
      expect(taps, 1);
      semantics.dispose();
    });

    testWidgets('WideTile body replaces the label and takes the foreground', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      await _pump(
        tester,
        Center(
          child: WideTile(
            label: 'Paper account, 12,400 USD',
            color: const Color(0xFF214E82),
            onTap: () {},
            body: const Text('12,400 USD'),
          ),
        ),
      );
      expect(find.text('Paper account, 12,400 USD'), findsNothing);
      expect(
        find.bySemanticsLabel('Paper account, 12,400 USD'),
        findsOneWidget,
      );
      expect(tester.getSize(find.byType(WideTile)), const Size(296, 128));
      final style = tester
          .widget<RichText>(
            find.descendant(
              of: find.text('12,400 USD'),
              matching: find.byType(RichText),
            ),
          )
          .text
          .style;
      expect(style?.color, LnPalette.inkWhite);
      semantics.dispose();
    });

    testWidgets('ExploreSkeleton is one localized loading node', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      await _pump(
        tester,
        ListView(
          children: const [
            ExploreSkeleton(semanticLabel: 'جارٍ التحميل', animate: false),
          ],
        ),
      );
      expect(find.bySemanticsLabel('جارٍ التحميل'), findsOneWidget);
      semantics.dispose();
    });
  });

  group('K8 accessibility', () {
    testWidgets('a trailing action on a tappable LnListTile is its own node', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      var row = 0;
      var removed = 0;
      await _pump(
        tester,
        ListView(
          children: [
            LnSection(
              children: [
                LnListTile(
                  title: 'news.example',
                  onTap: () => row++,
                  trailingIsAction: true,
                  // Labelled the way the settings pages' pill buttons are: semantics that are not
                  // a container of their own, which used to merge into the row's node.
                  trailing: Semantics(
                    button: true,
                    label: 'Remove',
                    excludeSemantics: true,
                    child: LnTappable(
                      onTap: () => removed++,
                      child: const SizedBox.square(dimension: 48),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      );
      expect(
        tester.getSemantics(find.bySemanticsLabel('news.example')),
        isSemantics(label: 'news.example', isButton: true, hasTapAction: true),
      );
      expect(
        tester.getSemantics(find.bySemanticsLabel('Remove')),
        isSemantics(label: 'Remove', isButton: true),
      );
      await tester.tap(find.bySemanticsLabel('Remove'));
      await tester.pumpAndSettle();
      expect((row, removed), (0, 1));
      semantics.dispose();
    });

    testWidgets('an informative trailing reads with its tappable row', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      await _pump(
        tester,
        ListView(
          children: [
            LnSection(
              children: [
                LnListTile(
                  title: 'Status',
                  onTap: () {},
                  trailing: const Text('Connected'),
                ),
                LnListTile(
                  title: 'Models',
                  onTap: () {},
                  trailing: const Icon(FIcons.chevronRight),
                ),
              ],
            ),
          ],
        ),
      );
      expect(find.bySemanticsLabel('Connected'), findsNothing);
      expect(
        tester.getSemantics(find.text('Status')),
        isSemantics(
          label: 'Status\nConnected',
          isButton: true,
          hasTapAction: true,
        ),
      );
      // A chevron leaves no empty node under its row.
      final models = tester.getSemantics(find.text('Models'));
      expect(models.label, 'Models');
      expect(models.childrenCount, 0);
      semantics.dispose();
    });

    testWidgets('ChatListRow composes its label from localized parts', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      await _pump(
        tester,
        ListView(
          children: [
            ChatListRow(
              avatar: const SizedBox.square(dimension: 44),
              title: 'مراقب السوق',
              preview: 'تجاوز السهم 140',
              time: '10:12',
              unreadCount: 3,
              pinned: true,
              muted: true,
              unreadLabel: '3 رسائل غير مقروءة',
              pinnedLabel: 'مثبتة',
              mutedLabel: 'مكتومة',
              onTap: () {},
            ),
          ],
        ),
        direction: TextDirection.rtl,
      );
      expect(
        find.bySemanticsLabel(
          'مراقب السوق, 3 رسائل غير مقروءة, تجاوز السهم 140, 10:12, مثبتة, مكتومة',
        ),
        findsOneWidget,
      );
      semantics.dispose();
    });
  });

  group('K9 composer and selection mark', () {
    testWidgets('the caller\'s mic sits in the trailing slot', (tester) async {
      final semantics = tester.ensureSemantics();
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      var held = 0;
      await _pump(
        tester,
        Center(
          child: Composer(
            controller: controller,
            placeholder: 'Message',
            onSend: (_) {},
            micButton: Semantics(
              button: true,
              label: 'Hold to record',
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onLongPress: () => held++,
                child: const SizedBox.square(dimension: 36),
              ),
            ),
          ),
        ),
      );
      expect(find.bySemanticsLabel('Hold to record'), findsOneWidget);
      // No second, inert mic under it.
      expect(find.bySemanticsLabel('Voice input'), findsNothing);
      final slot = tester.getRect(find.bySemanticsLabel('Hold to record'));
      final pill = tester.getRect(find.byType(Composer));
      expect(slot.center.dy, pill.center.dy);
      await tester.longPress(find.bySemanticsLabel('Hold to record'));
      expect(held, 1);

      controller.text = 'hi';
      await tester.pumpAndSettle();
      expect(find.bySemanticsLabel('Hold to record'), findsNothing);
      expect(find.bySemanticsLabel('Send'), findsOneWidget);
      semantics.dispose();
    });

    testWidgets('a disabled composer shows its own inert mic, not the '
        'caller\'s', (tester) async {
      final semantics = tester.ensureSemantics();
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      var taps = 0;
      await _pump(
        tester,
        Center(
          child: Composer(
            controller: controller,
            placeholder: 'Message',
            enabled: false,
            onSend: (_) {},
            micButton: Semantics(
              button: true,
              label: 'Hold to record',
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => taps++,
                onLongPress: () => taps++,
                child: const SizedBox.square(dimension: 36),
              ),
            ),
          ),
        ),
      );
      expect(find.bySemanticsLabel('Hold to record'), findsNothing);
      final mic = find.bySemanticsLabel('Voice input');
      expect(
        tester.getSemantics(mic),
        isSemantics(
          label: 'Voice input',
          isButton: true,
          hasEnabledState: true,
          isEnabled: false,
        ),
      );
      await tester.tap(mic, warnIfMissed: false);
      await tester.longPress(mic, warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(taps, 0);
      semantics.dispose();
    });

    testWidgets('files alone can be sent from an empty field', (tester) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      String? sent;
      await _pump(
        tester,
        Center(
          child: Composer(
            controller: controller,
            placeholder: 'Message',
            running: true,
            sendWithoutText: true,
            onMic: () {},
            onStop: () {},
            onSend: (text) => sent = text,
          ),
        ),
      );
      expect(find.bySemanticsLabel('Stop'), findsNothing);
      expect(find.bySemanticsLabel('Voice input'), findsNothing);
      expect(tester.widget<SendDisc>(find.byType(SendDisc)).enabled, isTrue);
      await tester.tap(find.bySemanticsLabel('Send'));
      await tester.pumpAndSettle();
      expect(sent, '');
    });

    testWidgets('SelectionMark shows a check only when selected', (
      tester,
    ) async {
      await _pump(
        tester,
        const Row(
          children: [
            SelectionMark(selected: true),
            SelectionMark(selected: false),
          ],
        ),
      );
      expect(find.byIcon(FIcons.check), findsOneWidget);
      expect(
        tester.widget<Icon>(find.byIcon(FIcons.check)).color,
        LnPalette.light.onAccent,
      );
    });
  });
}
