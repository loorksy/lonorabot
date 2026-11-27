import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/avatar/avatar.dart';
import 'package:lonora/avatar/src/avatar_painter.dart';

const _frame60 = Duration(microseconds: 16667);

Future<void> _app(WidgetTester tester, Widget child, {Locale? locale}) =>
    tester.pumpWidget(
      MaterialApp(
        locale: locale,
        supportedLocales: const [Locale('en'), Locale('ar')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: Scaffold(body: child),
      ),
    );

/// The scene of the [index]-th avatar on screen; every repaint request notifies it.
AvatarScene _scene(WidgetTester tester, [int index = 0]) {
  final paint = tester
      .widgetList<CustomPaint>(find.byType(CustomPaint))
      .where((p) => p.painter is AvatarPainter)
      .elementAt(index);
  return (paint.painter! as AvatarPainter).scene;
}

/// Counts repaints of the first avatar over [frames] 60 Hz frames.
Future<int> _repaints(WidgetTester tester, int frames) async {
  var count = 0;
  final scene = _scene(tester);
  void listener() => count++;
  scene.addListener(listener);
  for (var i = 0; i < frames; i++) {
    await tester.pump(_frame60);
  }
  scene.removeListener(listener);
  return count;
}

int get _tickers => SchedulerBinding.instance.transientCallbackCount;

void main() {
  testWidgets('animates at no more than 30 fps', (tester) async {
    await _app(tester, const Center(child: LonoraAvatar(agentId: 'agent-1')));
    await tester.pump();
    final count = await _repaints(tester, 60);
    expect(count, inInclusiveRange(25, 31));
  });

  testWidgets('animate: false draws a poster and schedules no frames', (
    tester,
  ) async {
    await _app(
      tester,
      ListView.builder(
        itemCount: 50,
        itemBuilder: (context, i) => ListTile(
          leading: LonoraAvatar(
            agentId: 'agent-$i',
            face: avatarFaces[i % 16].id,
            animate: false,
          ),
          title: Text('row $i'),
        ),
      ),
    );
    expect(_tickers, 0);
    expect(await _repaints(tester, 10), 0);
    await tester.fling(find.byType(ListView), const Offset(0, -600), 2000);
    await tester.pumpAndSettle();
    expect(_tickers, 0);
  });

  testWidgets('a disabled TickerMode pauses the avatar', (tester) async {
    await _app(
      tester,
      const TickerMode(
        enabled: false,
        child: Center(child: LonoraAvatar(agentId: 'agent-1')),
      ),
    );
    expect(await _repaints(tester, 20), 0);
    expect(_tickers, 0);
  });

  testWidgets('reduced motion shows the static poster', (tester) async {
    await tester.pumpWidget(
      const MediaQuery(
        data: MediaQueryData(disableAnimations: true),
        child: Directionality(
          textDirection: TextDirection.ltr,
          child: Center(child: LonoraAvatar(agentId: 'agent-1')),
        ),
      ),
    );
    expect(_tickers, 0);
    expect(await _repaints(tester, 10), 0);
  });

  testWidgets('backgrounding the app stops the ticker', (tester) async {
    await _app(tester, const Center(child: LonoraAvatar(agentId: 'agent-1')));
    await tester.pump(_frame60);
    expect(_tickers, greaterThan(0));
    for (final state in [
      AppLifecycleState.inactive,
      AppLifecycleState.hidden,
      AppLifecycleState.paused,
    ]) {
      tester.binding.handleAppLifecycleStateChanged(state);
    }
    await tester.pump();
    expect(_tickers, 0);
    for (final state in [
      AppLifecycleState.hidden,
      AppLifecycleState.inactive,
      AppLifecycleState.resumed,
    ]) {
      tester.binding.handleAppLifecycleStateChanged(state);
    }
    await tester.pump();
    expect(await _repaints(tester, 20), greaterThan(5));
  });

  testWidgets('pauses off screen and resumes when back on screen', (
    tester,
  ) async {
    Widget at(double left) => Stack(
      children: [
        Positioned(
          left: left,
          top: 10,
          child: const LonoraAvatar(key: ValueKey('a'), agentId: 'agent-1'),
        ),
      ],
    );
    await _app(tester, at(5000));
    await tester.pump(_frame60);
    await tester.pump(const Duration(milliseconds: 40));
    expect(_tickers, 0);
    expect(await _repaints(tester, 10), 0);
    await _app(tester, at(10));
    await tester.pump(const Duration(milliseconds: 600));
    expect(await _repaints(tester, 20), greaterThan(5));
  });

  testWidgets('touching the avatar never steals the row tap', (tester) async {
    var rowTaps = 0, avatarTaps = 0;
    await _app(
      tester,
      Center(
        child: GestureDetector(
          onTap: () => rowTaps++,
          child: const Padding(
            padding: EdgeInsets.all(20),
            child: LonoraAvatar(agentId: 'agent-1', size: 64),
          ),
        ),
      ),
    );
    await tester.tap(find.byType(LonoraAvatar));
    expect(rowTaps, 1);

    await _app(
      tester,
      Center(
        child: LonoraAvatar(
          agentId: 'agent-1',
          animate: false,
          onTap: () => avatarTaps++,
        ),
      ),
    );
    await tester.tap(find.byType(LonoraAvatar));
    expect(avatarTaps, 1);
  });

  testWidgets('a tap pokes the visor and spins the resting signals', (
    tester,
  ) async {
    await _app(
      tester,
      const Center(child: LonoraAvatar(agentId: 'agent-1', size: 96)),
    );
    await tester.pump(_frame60);
    final scene = _scene(tester);
    await tester.tap(find.byType(LonoraAvatar));
    expect(scene.poke, 0.8);
    for (var i = 0; i < 40; i++) {
      await tester.pump(const Duration(milliseconds: 33));
    }
    expect(scene.yaw.abs(), greaterThan(0.5));
    expect(scene.poke, lessThan(0.01));
  });

  testWidgets('state and face changes rebuild without errors', (tester) async {
    for (final state in LonoraAvatarState.values) {
      await _app(
        tester,
        LonoraAvatar(agentId: 'agent-1', state: state, face: 'face-wink'),
      );
      await tester.pump(const Duration(milliseconds: 33));
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('studio grid reports face and colour picks, in Arabic', (
    tester,
  ) async {
    String? face, color;
    await _app(
      tester,
      SingleChildScrollView(
        child: AvatarStudioGrid(
          agentId: 'agent-1',
          face: 'orb',
          color: '#8B5CF6',
          onFaceChanged: (v) => face = v,
          onColorChanged: (v) => color = v,
          previewSize: 0,
        ),
      ),
      locale: const Locale('ar'),
    );
    expect(find.text('الوجه'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('غمزة'));
    expect(face, 'face-wink');
    await tester.tap(find.bySemanticsLabel('اللون #EF4444'));
    expect(color, '#EF4444');
    expect(
      tester.getSemantics(find.bySemanticsLabel('الإشارات')),
      isSemantics(
        isChecked: true,
        isButton: true,
        isInMutuallyExclusiveGroup: true,
      ),
    );
  });

  testWidgets('group avatars: pair and overflow badge', (tester) async {
    const members = [
      LonoraAvatarMember(agentId: 'a'),
      LonoraAvatarMember(agentId: 'b'),
      LonoraAvatarMember(agentId: 'c'),
      LonoraAvatarMember(agentId: 'd'),
      LonoraAvatarMember(agentId: 'e'),
    ];
    await _app(
      tester,
      const Row(
        children: [
          LonoraGroupAvatar.pair(members: members, animate: false),
          LonoraGroupAvatar(members: members, animate: false),
        ],
      ),
    );
    final pair = find.byType(LonoraGroupAvatar).first;
    expect(tester.getSize(pair), const Size(55, 28));
    expect(
      find.descendant(of: pair, matching: find.byType(LonoraAvatar)),
      findsNWidgets(2),
    );
    expect(find.text('+3'), findsOneWidget);
  });
}
