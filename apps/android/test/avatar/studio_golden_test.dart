// Layout golden of the embeddable studio (text renders in the test font).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/avatar/avatar.dart';

void main() {
  for (final brightness in Brightness.values) {
    testWidgets('studio grid, ${brightness.name}', (tester) async {
      tester.view.physicalSize = const Size(420, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: ThemeData(brightness: brightness),
          home: Scaffold(
            body: Padding(
              padding: const EdgeInsets.all(20),
              child: AvatarStudioGrid(
                agentId: 'agent-1',
                face: 'face-wink',
                color: '#06B6D4',
                onFaceChanged: (_) {},
                onColorChanged: (_) {},
              ),
            ),
          ),
        ),
      );
      await expectLater(
        find.byType(Scaffold),
        matchesGoldenFile('goldens/studio_${brightness.name}.png'),
      );
    });
  }
}
