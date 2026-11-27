// Shared settings rows and states (settings_common.dart): one-line WrapTile / ChoiceTile rows reach
// the grouped card's 52 dp rows as LnListTile's do; a choice / switch row reads its state on its
// own node; section gaps, notes and the in-place row picker; a failed first load is the kit's
// ErrorState.
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/settings/settings_common.dart';

import '../../design/harness.dart';
import 'feature_harness.dart';

void main() {
  setUpAll(setUpFeatureTests);

  for (final direction in TextDirection.values) {
    testWidgets('one-line WrapTile and ChoiceTile rows are 52 dp; a hint keeps '
        'forui\'s height (${direction.name})', (tester) async {
      setGoldenViewport(tester);
      await tester.pumpWidget(
        lnTestApp(
          direction: direction,
          // One row per group: a row's tile is then the row alone (no divider).
          child: ListView(
            children: [
              for (final row in <FTileMixin>[
                const WrapTile(icon: FIcons.globe, title: 'Built-in'),
                ChoiceTile(title: 'Dark', selected: true, onSelect: () {}),
                ChoiceTile(title: 'Light', selected: false, onSelect: () {}),
                const WrapTile(
                  icon: FIcons.globe,
                  title: 'Hinted',
                  subtitle: 'A hint',
                ),
                FTile(
                  prefix: const Icon(FIcons.globe),
                  title: const Text('Plain', maxLines: 2),
                  subtitle: const Text('A hint', maxLines: 4),
                ),
              ])
                LnSection(children: [row]),
            ],
          ),
        ),
      );
      await tester.pump();
      Rect row(String title) => tester.getRect(
        find.ancestor(of: find.text(title), matching: find.byType(FTile)),
      );
      expect(row('Built-in').height, LnSize.tileRow);
      expect(row('Dark').height, LnSize.tileRow);
      expect(row('Light').height, LnSize.tileRow);
      expect(row('Hinted').height, row('Plain').height);
      // The title stays in the middle of the taller row.
      expect(
        tester.getCenter(find.text('Built-in')).dy,
        row('Built-in').center.dy,
      );
    });
  }

  for (final direction in TextDirection.values) {
    testWidgets(
      'a choice row reads its selection and a switch row its state on '
      'the row\'s own node (${direction.name})',
      (tester) async {
        final semantics = tester.ensureSemantics();
        var picked = 0;
        final flips = <bool>[];
        setGoldenViewport(tester);
        await tester.pumpWidget(
          lnTestApp(
            direction: direction,
            child: ListView(
              children: [
                LnSection(
                  children: [
                    ChoiceTile(title: 'Dark', selected: true, onSelect: () {}),
                    ChoiceTile(
                      title: 'Light',
                      selected: false,
                      onSelect: () => picked++,
                    ),
                  ],
                ),
                LnSection(
                  children: [
                    SwitchTile(
                      title: 'Sounds',
                      value: true,
                      onChanged: flips.add,
                    ),
                    SwitchTile(title: 'Badges', value: false, onChanged: null),
                  ],
                ),
              ],
            ),
          ),
        );
        await tester.pump();
        SemanticsData row(String title) =>
            tester.getSemantics(find.text(title)).getSemanticsData();
        expect(
          row('Dark'),
          isSemantics(
            label: 'Dark',
            isButton: true,
            hasTapAction: true,
            hasSelectedState: true,
            isSelected: true,
            isInMutuallyExclusiveGroup: true,
          ),
        );
        expect(
          row('Light'),
          isSemantics(
            label: 'Light',
            hasTapAction: true,
            hasSelectedState: true,
            isSelected: false,
            isInMutuallyExclusiveGroup: true,
          ),
        );
        expect(
          row('Sounds'),
          isSemantics(
            label: 'Sounds',
            hasTapAction: true,
            hasToggledState: true,
            isToggled: true,
          ),
        );
        expect(
          row('Badges'),
          isSemantics(
            label: 'Badges',
            hasTapAction: false,
            hasToggledState: true,
            isToggled: false,
          ),
        );
        tester.semantics.tap(find.semantics.byLabel('Light'));
        tester.semantics.tap(find.semantics.byLabel('Sounds'));
        await tester.pumpAndSettle();
        expect(picked, 1);
        expect(flips, [false]);
        semantics.dispose();
      },
    );
  }

  testWidgets('sections are 32 dp apart on pages; a note lines up '
      'with the rows\' text, 32 dp from both edges', (tester) async {
    setGoldenViewport(tester);
    await tester.pumpWidget(
      lnTestApp(
        direction: TextDirection.rtl,
        child: ListView(
          children: [
            const SectionGap(),
            const SectionGap(height: LnSpace.md),
            const SettingsNote(
              'A note long enough to wrap onto a second line '
              'at this width, so both of its edges show.',
            ),
          ],
        ),
      ),
    );
    final gaps = tester.widgetList<SizedBox>(
      find.descendant(
        of: find.byType(SectionGap),
        matching: find.byType(SizedBox),
      ),
    );
    expect([for (final g in gaps) g.height], [LnSpace.xxl, LnSpace.md]);
    final note = tester.getRect(find.byType(Text));
    expect(note.left, greaterThanOrEqualTo(32));
    expect(note.right, 393 - 32);
  });

  for (final direction in TextDirection.values) {
    testWidgets('a row picker opens at the row\'s end edge and returns the '
        'choice (${direction.name})', (tester) async {
      setGoldenViewport(tester);
      final row = GlobalKey();
      String? chosen;
      await tester.pumpWidget(
        lnTestApp(
          direction: direction,
          child: Builder(
            builder: (context) => ListView(
              children: [
                LnSection(
                  children: [
                    LnListTile(
                      key: row,
                      title: 'Theme',
                      value: 'Dark',
                      picker: true,
                      onTap: () async => chosen = await showRowPicker<String>(
                        context,
                        row: row,
                        label: 'Theme',
                        selected: 'dark',
                        actions: const [
                          LnMenuAction(label: 'Light', value: 'light'),
                          LnMenuAction(label: 'Dark', value: 'dark'),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      );
      await tester.tap(find.text('Theme'));
      await tester.pumpAndSettle();
      final menu = tester.getRect(find.byType(LnMenuCard));
      final rect = tester.getRect(find.byKey(row));
      expect(
        direction == TextDirection.ltr ? menu.right : menu.left,
        direction == TextDirection.ltr ? rect.right : rect.left,
      );
      expect(menu.top, rect.bottom + 4);
      await tester.tap(find.text('Light'));
      await tester.pumpAndSettle();
      expect(chosen, 'light');
    });
  }

  for (final (name, error, icon) in [
    ('offline', ApiError.network(), FIcons.wifiOff),
    (
      'refused',
      ApiError(status: 500, code: 'request_failed'),
      FIcons.triangleAlert,
    ),
  ]) {
    testWidgets('a failed first load is the kit error state ($name)', (
      tester,
    ) async {
      await setUpServices();
      var retried = 0;
      setFeatureViewport(tester);
      await tester.pumpWidget(
        featureApp(
          testStore(locale: 'en'),
          testRouter(LoadFailure(error: error, onRetry: () => retried++)),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.widget<ErrorState>(find.byType(ErrorState)).icon, icon);
      await tapAndSettle(tester, find.text('Retry'));
      expect(retried, 1);
    });
  }
}
