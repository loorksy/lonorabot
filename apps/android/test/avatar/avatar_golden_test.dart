// Golden renders of the avatar. Compare by eye with the production Chromium captures in
// docs/visual/avatar-refinement/ (expressions-*px.png, original-default.png,
// shell-colors.png, transition-mid-animation.png). Regenerate with
// `flutter test --update-goldens test/avatar`.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/avatar/avatar.dart';

const _dark = Color(0xFF0D0E11);
const _light = Color(0xFFFFFFFF);
const _shells = ['#8B5CF6', '#06B6D4', '#FFFFFF'];

/// The identity the production Chromium captures used (scripts/capture-avatar-refinement.mjs).
const _reviewId = 'geometry-review';

Future<void> _show(
  WidgetTester tester,
  Widget child, {
  Color background = _dark,
  Size view = const Size(1800, 1200),
  Brightness brightness = Brightness.dark,
}) async {
  tester.view.physicalSize = view;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(brightness: brightness),
      home: Align(
        alignment: Alignment.topLeft,
        child: RepaintBoundary(
          key: const ValueKey('golden'),
          child: ColoredBox(
            color: background,
            child: Padding(padding: const EdgeInsets.all(12), child: child),
          ),
        ),
      ),
    ),
  );
}

/// Advances animated avatars frame by frame (the widget caps dt at 0.1 s per frame).
Future<void> _run(WidgetTester tester, Duration duration) async {
  const step = Duration(milliseconds: 33);
  for (var t = Duration.zero; t < duration; t += step) {
    await tester.pump(step);
  }
}

Widget _grid(List<Widget> items, int columns, double cell) => SizedBox(
  width: columns * cell,
  child: Wrap(
    children: [
      for (final item in items)
        SizedBox(
          width: cell,
          height: cell,
          child: Center(child: item),
        ),
    ],
  ),
);

Finder get _golden => find.byKey(const ValueKey('golden'));

void main() {
  for (final size in [44.0, 64.0, 128.0]) {
    testWidgets('all faces at ${size.toInt()} px on three shells', (
      tester,
    ) async {
      await _show(
        tester,
        Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final shell in _shells)
              Padding(
                padding: const EdgeInsets.only(right: 16),
                child: _grid(
                  [
                    for (final face in avatarFaces)
                      LonoraAvatar(
                        agentId: _reviewId,
                        face: face.id,
                        color: shell,
                        size: size,
                        animate: false,
                      ),
                  ],
                  4,
                  size + 12,
                ),
              ),
          ],
        ),
      );
      await expectLater(
        _golden,
        matchesGoldenFile('goldens/faces_${size.toInt()}.png'),
      );
    });
  }

  testWidgets('faces on a light background', (tester) async {
    await _show(
      tester,
      Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final shell in ['#8B5CF6', '#64748B'])
            _grid(
              [
                for (final face in avatarFaces)
                  LonoraAvatar(
                    agentId: _reviewId,
                    face: face.id,
                    color: shell,
                    size: 64,
                    animate: false,
                  ),
              ],
              4,
              76,
            ),
        ],
      ),
      background: _light,
      brightness: Brightness.light,
    );
    await expectLater(_golden, matchesGoldenFile('goldens/faces_light_64.png'));
  });

  testWidgets('rest pose (signal bars) at 256 px', (tester) async {
    await _show(
      tester,
      const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          LonoraAvatar(
            agentId: _reviewId,
            color: '#8B5CF6',
            size: 256,
            animate: false,
          ),
          SizedBox(width: 16),
          LonoraAvatar(
            agentId: _reviewId,
            face: 'face-smile',
            color: '#8B5CF6',
            size: 256,
            animate: false,
          ),
        ],
      ),
    );
    await expectLater(_golden, matchesGoldenFile('goldens/rest_256.png'));
  });

  testWidgets('every state mid-animation at 96 px', (tester) async {
    await _show(
      tester,
      _grid(
        [
          for (final state in LonoraAvatarState.values)
            LonoraAvatar(
              agentId: 'agent-1',
              color: '#3B82F6',
              state: state,
              size: 96,
            ),
        ],
        5,
        108,
      ),
    );
    await _run(tester, const Duration(milliseconds: 1200));
    await expectLater(_golden, matchesGoldenFile('goldens/states_96.png'));
  });

  testWidgets('every state as a static poster at 44 px', (tester) async {
    await _show(
      tester,
      _grid(
        [
          for (final state in LonoraAvatarState.values)
            LonoraAvatar(
              agentId: 'agent-1',
              color: '#10B981',
              state: state,
              animate: false,
            ),
        ],
        10,
        52,
      ),
      background: _light,
      brightness: Brightness.light,
    );
    await expectLater(_golden, matchesGoldenFile('goldens/states_44.png'));
  });

  testWidgets('expression switch and state morph mid-transition', (
    tester,
  ) async {
    Widget avatars(String face, LonoraAvatarState state) => Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        LonoraAvatar(
          agentId: _reviewId,
          face: face,
          color: '#8B5CF6',
          size: 128,
        ),
        const SizedBox(width: 16),
        LonoraAvatar(
          agentId: _reviewId,
          color: '#8B5CF6',
          state: state,
          size: 128,
        ),
      ],
    );
    await _show(tester, avatars('face-smile', LonoraAvatarState.idle));
    await _run(tester, const Duration(milliseconds: 300));
    await tester.pumpWidget(
      MaterialApp(
        debugShowCheckedModeBanner: false,
        home: Align(
          alignment: Alignment.topLeft,
          child: RepaintBoundary(
            key: const ValueKey('golden'),
            child: ColoredBox(
              color: _dark,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: avatars('face-wink', LonoraAvatarState.searching),
              ),
            ),
          ),
        ),
      ),
    );
    // The production Chromium capture waited 420 ms plus screenshot latency.
    await _run(tester, const Duration(milliseconds: 500));
    await expectLater(_golden, matchesGoldenFile('goldens/morph_mid.png'));
  });

  testWidgets('trades on its own: ring and crown, light and dark', (
    tester,
  ) async {
    Widget row(Brightness brightness, Color background) => Theme(
      data: ThemeData(brightness: brightness),
      child: ColoredBox(
        color: background,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final size in [28.0, 44.0, 64.0, 96.0])
                Padding(
                  padding: const EdgeInsets.all(10),
                  child: LonoraAvatar(
                    agentId: 'agent-1',
                    face: 'face-happy',
                    size: size,
                    tradesOnItsOwn: true,
                    animate: false,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
    await _show(
      tester,
      Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [row(Brightness.light, _light), row(Brightness.dark, _dark)],
      ),
    );
    await expectLater(_golden, matchesGoldenFile('goldens/trades_ring.png'));
  });

  testWidgets('group avatars: cluster and pair', (tester) async {
    const members = [
      LonoraAvatarMember(agentId: 'agent-1'),
      LonoraAvatarMember(agentId: 'bot_42', face: 'face-happy'),
      LonoraAvatarMember(agentId: 'a', face: 'face-wink', color: '#EF4444'),
      LonoraAvatarMember(agentId: 'x', color: '#10B981'),
      LonoraAvatarMember(agentId: 'y', face: 'face-laugh'),
    ];
    await _show(
      tester,
      Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final count in [0, 1, 2, 3, 5]) ...[
            LonoraGroupAvatar(
              members: members.take(count).toList(),
              animate: false,
            ),
            const SizedBox(width: 16),
          ],
          LonoraGroupAvatar.pair(
            members: members.take(2).toList(),
            animate: false,
          ),
          const SizedBox(width: 16),
          LonoraGroupAvatar.pair(
            members: members.skip(2).take(2).toList(),
            animate: false,
          ),
        ],
      ),
      background: _light,
      brightness: Brightness.light,
    );
    await expectLater(_golden, matchesGoldenFile('goldens/groups.png'));
  });
}
