// Shared settings rows and states (settings_common.dart): one-line WrapTile / ChoiceTile rows reach
// the 48 dp touch target as LnListTile's do; a choice / switch row reads its state on its own
// node; a failed first load is the kit's ErrorState.
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
    testWidgets('one-line WrapTile and ChoiceTile rows are 48 dp; a hint keeps '
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
      expect(row('Built-in').height, LnSize.minTouch);
      expect(row('Dark').height, LnSize.minTouch);
      expect(row('Light').height, LnSize.minTouch);
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
