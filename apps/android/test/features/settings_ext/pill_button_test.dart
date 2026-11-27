// PillButton (ext_common.dart): the action at the end of a row is its own button node with the tap
// action, and never merges into its row's node.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/settings/integrations/ext_common.dart';
import 'package:lonora/features/settings/settings_common.dart';

import '../../design/fonts.dart';
import '../../design/harness.dart';

void main() {
  setUpAll(loadAppFonts);

  testWidgets('a row\'s pill is its own button; a disabled one takes no tap', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    var row = 0;
    var stop = 0;
    setGoldenViewport(tester);
    await tester.pumpWidget(
      lnTestApp(
        child: ListView(
          children: [
            LnSection(
              children: [
                WrapTile(
                  title: 'backtest.py',
                  onTap: () => row++,
                  trailing: PillButton(
                    label: 'Stop',
                    semanticLabel: 'Stop backtest.py',
                    destructive: true,
                    onTap: () => stop++,
                  ),
                ),
                const WrapTile(
                  title: 'stale.py',
                  trailing: PillButton(
                    label: 'Stop',
                    semanticLabel: 'Stop stale.py',
                    onTap: null,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
    await tester.pump();
    final pill = find.semantics.byLabel('Stop backtest.py');
    expect(
      pill.evaluate().single.getSemanticsData(),
      isSemantics(
        isButton: true,
        hasEnabledState: true,
        isEnabled: true,
        hasTapAction: true,
      ),
    );
    // The row reads its own title only, and keeps its own tap.
    expect(
      tester.getSemantics(find.text('backtest.py')),
      isSemantics(label: 'backtest.py', hasTapAction: true),
    );
    tester.semantics.tap(pill);
    await tester.pumpAndSettle();
    expect((row, stop), (0, 1));
    expect(
      find.semantics
          .byLabel('Stop stale.py')
          .evaluate()
          .single
          .getSemanticsData(),
      isSemantics(
        isButton: true,
        hasEnabledState: true,
        isEnabled: false,
        hasTapAction: false,
      ),
    );
    semantics.dispose();
  });
}
