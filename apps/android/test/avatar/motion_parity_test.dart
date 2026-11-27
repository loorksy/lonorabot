// Number-for-number parity of the Dart port with the production JavaScript engine.
// Vectors: test/avatar/fixtures/js_vectors.json, produced by
// `node --experimental-strip-types test/avatar/tool/generate_js_vectors.mjs`.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/avatar/avatar.dart';

late final Map<String, dynamic> vectors;

double _d(Object? v) => (v as num).toDouble();

void _close(double actual, Object? expected, String what) {
  final e = _d(expected);
  expect(
    (actual - e).abs() <= 1e-7 * (1 + e.abs()),
    isTrue,
    reason: '$what: dart $actual vs js $e',
  );
}

void _bars(List<AvatarBar> actual, List<dynamic> expected, String what) {
  expect(actual, hasLength(expected.length), reason: what);
  for (var i = 0; i < actual.length; i++) {
    final a = actual[i], e = expected[i] as Map<String, dynamic>;
    _close(a.cx, e['cx'], '$what[$i].cx');
    _close(a.cy, e['cy'], '$what[$i].cy');
    _close(a.len, e['L'], '$what[$i].L');
    _close(a.th, e['th'], '$what[$i].th');
    _close(a.k, e['k'], '$what[$i].k');
    _close(a.w, e['w'], '$what[$i].w');
    _close(a.o, e['o'], '$what[$i].o');
    if (e.containsKey('r')) {
      _close(a.r, e['r'], '$what[$i].r');
      _close(a.g, e['g'], '$what[$i].g');
      _close(a.b, e['b'], '$what[$i].b');
    }
  }
}

LonoraAvatarState _state(Object? id) => LonoraAvatarState.fromId(id as String);

void main() {
  setUpAll(() {
    vectors = jsonDecode(
      File('test/avatar/fixtures/js_vectors.json').readAsStringSync(),
    ) as Map<String, dynamic>;
  });

  test('state ids, faces and palette match the sources', () {
    expect(LonoraAvatarState.values.map((s) => s.id), [
      'thinking',
      'executing',
      'inspecting',
      'writing',
      'searching',
      'working',
      'listening',
      'reviewing',
      'waiting',
      'angry',
      'sending',
      'speaking',
      'success',
      'error',
      'warning',
      'analyzing',
      'learning',
      'sleeping',
      'celebrating',
      'connecting',
    ]);
    expect(LonoraAvatarState.idle, LonoraAvatarState.waiting);
    expect(LonoraAvatarState.fromId('nope'), LonoraAvatarState.waiting);
    expect(avatarFaces.map((f) => f.id), avatarFaceIds);
    expect(avatarFaces, hasLength(16));
    expect(resolveAvatarFace('face-wink'), 'face-wink');
    expect(resolveAvatarFace('robot'), 'orb');
    expect(resolveAvatarFace(null), 'orb');
    expect(avatarPalette.map((c) => c.hex), [
      '#FFFFFF',
      '#8B5CF6',
      '#10B981',
      '#F97316',
      '#06B6D4',
      '#3B82F6',
      '#EAB308',
      '#8D6E63',
      '#EF4444',
      '#EC4899',
      '#64748B',
    ]);
    expect(defaultAvatarColor, '#8B5CF6');
  });

  test('facial tokens and anchors', () {
    final t = vectors['faceTokens'] as Map<String, dynamic>;
    final stroke = t['stroke'] as Map<String, dynamic>;
    _close(FaceTokens.strokePrimary, stroke['primary'], 'primary');
    _close(FaceTokens.strokeCurvedEye, stroke['curvedEye'], 'curvedEye');
    _close(FaceTokens.strokeSecondary, stroke['secondary'], 'secondary');
    _close(FaceTokens.strokeEyebrow, stroke['eyebrow'], 'eyebrow');
    _close(FaceTokens.strokeAccent, stroke['accent'], 'accent');
    _close(FaceTokens.strokeIndicator, stroke['indicator'], 'indicator');
    final shape = t['shape'] as Map<String, dynamic>;
    _close(FaceTokens.mouthRadius, shape['mouthRadius'], 'mouthRadius');
    _close(FaceTokens.eyeArcRadius, shape['eyeArcRadius'], 'eyeArcRadius');
    final optical = t['optical'] as Map<String, dynamic>;
    _close(FaceTokens.eyeArcCorrection, optical['eyeArcCorrection'], 'eyeArc');
    _close(FaceTokens.mouthCorrection, optical['mouthCorrection'], 'mouthCorr');
    final spacing = t['spacing'] as Map<String, dynamic>;
    _close(FaceTokens.browLine, spacing['browLine'], 'browLine');
    _close(FaceTokens.mouthLine, spacing['mouthLine'], 'mouthLine');
    final safe =
        (vectors['facialGeometry'] as Map<String, dynamic>)['facialSafeArea']
            as Map<String, dynamic>;
    _close(FacialGeometry.safeArea.$1, safe['x'], 'safe.x');
    _close(FacialGeometry.safeArea.$2, safe['y'], 'safe.y');
    _close(FacialGeometry.safeArea.$3, safe['width'], 'safe.w');
    _close(FacialGeometry.safeArea.$4, safe['height'], 'safe.h');
  });

  test('personality hash is identical to web/Expo', () {
    final all = vectors['personality'] as Map<String, dynamic>;
    for (final entry in all.entries) {
      final p = avatarPersonality(entry.key);
      final e = entry.value as Map<String, dynamic>;
      final id = 'personality(${entry.key})';
      _close(p.phase, e['phase'], '$id.phase');
      expect(p.direction, e['direction'], reason: '$id.direction');
      expect(p.pattern, e['pattern'], reason: '$id.pattern');
      _close(p.tempo, e['tempo'], '$id.tempo');
      _close(p.cycleSeconds, e['cycleSeconds'], '$id.cycle');
      _close(p.spinSeconds, e['spinSeconds'], '$id.spin');
      _close(p.gazeXFrequency, e['gazeXFrequency'], '$id.gxf');
      _close(p.gazeYFrequency, e['gazeYFrequency'], '$id.gyf');
      _close(p.gazeXAmplitude, e['gazeXAmplitude'], '$id.gxa');
      _close(p.gazeYAmplitude, e['gazeYAmplitude'], '$id.gya');
    }
  });

  test('shell colour resolution (explicit and hashed) is identical', () {
    for (final raw in vectors['colors'] as List<dynamic>) {
      final e = raw as Map<String, dynamic>;
      final c = resolveAvatarColor(
        e['identity'] as String,
        e['explicit'] as String?,
      );
      final why = 'color(${e['identity']}, ${e['explicit']})';
      expect(c.id, e['id'], reason: why);
      expect(c.hex, e['hex'], reason: why);
      expect(c.dark, e['dark'], reason: why);
      expect(c.eyeColor, e['eyeColor'], reason: why);
    }
  });

  test('poseAt matches for every state, face and reaction', () {
    for (final raw in vectors['poses'] as List<dynamic>) {
      final e = raw as Map<String, dynamic>;
      final bars = poseAt(
        _state(e['state']),
        _d(e['u']),
        identity: e['identity'] as String,
        face: e['face'] as String,
        reactionProgress: _d(e['reaction']),
      );
      _bars(
        bars,
        e['bars'] as List<dynamic>,
        'poseAt(${e['state']}, ${e['u']}, ${e['identity']}, ${e['face']}, ${e['reaction']})',
      );
    }
  });

  test('planMorph and morphSegment match', () {
    for (final raw in vectors['plans'] as List<dynamic>) {
      final e = raw as Map<String, dynamic>;
      final from = poseAt(_state(e['from']), 0.2, identity: 'agent-1');
      final to = poseAt(_state(e['to']), 0, identity: 'agent-1');
      final plan = planMorph(from, to);
      final p = e['plan'] as Map<String, dynamic>;
      final why = '${e['from']}→${e['to']}';
      expect(plan.perm, p['perm'], reason: '$why perm');
      expect(plan.flip, p['flip'], reason: '$why flip');
      expect(plan.rank, p['rank'], reason: '$why rank');
      expect(plan.bow, p['bow'], reason: '$why bow');
      final times = [0, 0.1, 0.35, 0.6, 0.94];
      final steps = e['steps'] as List<dynamic>;
      for (var s = 0; s < times.length; s++) {
        final step = steps[s] as List<dynamic>;
        for (var i = 0; i < avatarParticles; i++) {
          final out = AvatarBar();
          final eased = morphSegment(
            from[i],
            to,
            plan,
            i,
            times[s].toDouble(),
            out,
          );
          final x = step[i] as Map<String, dynamic>;
          _close(eased, x['e'], '$why t=${times[s]} e[$i]');
          _bars([out], [x], '$why t=${times[s]} [$i]');
        }
      }
    }
  });

  test('AvatarMotion frames match the native sampler', () {
    for (final raw in vectors['motions'] as List<dynamic>) {
      final run = raw as Map<String, dynamic>;
      final motion = AvatarMotion(
        _state(run['state']),
        run['identity'] as String,
        run['face'] as String,
      );
      // Every frame is computed; every third one is compared (as recorded).
      final frames = <List<AvatarBar>>[];
      var count = 0;
      for (final op in run['ops'] as List<dynamic>) {
        final o = op as List<dynamic>;
        switch (o[0]) {
          case 'frame':
            for (var i = 0; i < (o[2] as int); i++) {
              final shown = motion.frame(
                _d(o[1]),
                reduced: o.length > 3 && o[3] == true,
              );
              if (count++ % 3 == 0) frames.add(shown);
            }
          case 'state':
            motion.setState(_state(o[1]));
          case 'face':
            motion.setFace(o[1] as String);
          case 'identity':
            motion.setIdentity(o[1] as String);
          case 'react':
            motion.react();
        }
      }
      final expected = run['frames'] as List<dynamic>;
      expect(frames, hasLength(expected.length));
      for (var f = 0; f < frames.length; f++) {
        _bars(
          frames[f],
          expected[f] as List<dynamic>,
          '${run['identity']} frame $f',
        );
      }
    }
  });

  test('reaction, idle pose, turn, face transform, loops, points', () {
    for (final raw in vectors['reactions'] as List<dynamic>) {
      final e = raw as Map<String, dynamic>, v = e['value'] as Map;
      final r = faceReaction(
        _d(e['p']),
        e['face'] as String,
        e['identity'] as String,
      );
      final why = 'reaction(${e['face']}, ${e['p']}, ${e['identity']})';
      _close(r.gazeX, v['gazeX'], '$why.gazeX');
      _close(r.gazeY, v['gazeY'], '$why.gazeY');
      _close(r.yaw, v['yaw'], '$why.yaw');
      _close(r.scale, v['scale'], '$why.scale');
      _close(r.offsetY, v['offsetY'], '$why.offsetY');
      _close(r.tilt, v['tilt'], '$why.tilt');
      _close(r.blink, v['blink'], '$why.blink');
      _close(r.mouth, v['mouth'], '$why.mouth');
    }
    for (final raw in vectors['idle'] as List<dynamic>) {
      final e = raw as Map<String, dynamic>, v = e['value'] as Map;
      final p = idleAvatarPose(
        _d(e['t']),
        e['identity'] as String,
        e['face'] as String,
      );
      final why = 'idle(${e['t']}, ${e['identity']}, ${e['face']})';
      _close(p.gazeX, v['gazeX'], '$why.gazeX');
      _close(p.gazeY, v['gazeY'], '$why.gazeY');
      _close(p.yaw, v['yaw'], '$why.yaw');
    }
    for (final raw in vectors['turns'] as List<dynamic>) {
      final e = raw as Map<String, dynamic>, v = e['value'] as Map;
      final t = avatarTurn(_d(e['yaw']));
      _close(t.tx, v['tx'], 'turn.tx');
      _close(t.scaleX, v['scaleX'], 'turn.scaleX');
      _close(t.opacity, v['opacity'], 'turn.opacity');
    }
    for (final raw in vectors['transforms'] as List<dynamic>) {
      final e = raw as Map<String, dynamic>, v = e['value'] as Map;
      final t = faceTransform(_d(e['gx']), _d(e['gy']), _d(e['poke']));
      _close(t.tx, v['tx'], 'ft.tx');
      _close(t.ty, v['ty'], 'ft.ty');
      _close(t.rot, v['rot'], 'ft.rot');
      _close(t.skew, v['skew'], 'ft.skew');
      _close(t.sx, v['sx'], 'ft.sx');
      _close(t.sy, v['sy'], 'ft.sy');
    }
    final loops = vectors['loops'] as Map<String, dynamic>;
    for (final state in LonoraAvatarState.values) {
      _close(loopSeconds(state), loops[state.id], 'loop(${state.id})');
    }
    final points = segmentPoints(210, 190, 80, 30, 0.02, 8);
    final expected = vectors['segmentPoints'] as List<dynamic>;
    for (var i = 0; i < points.length; i++) {
      final e = expected[i] as List<dynamic>;
      _close(points[i].$1, e[0], 'pt[$i].x');
      _close(points[i].$2, e[1], 'pt[$i].y');
    }
  });

  test('avatarStateFor matches avatar-state.ts', () {
    for (final raw in vectors['states'] as List<dynamic>) {
      final e = raw as Map<String, dynamic>;
      final input = e['input'] as Map<String, dynamic>;
      final voice = input['voice'] as Map<String, dynamic>?;
      final state = avatarStateFor(
        working: input['working'] == true,
        waiting: input['waiting'] == true,
        error: input['error'] == true,
        voice: voice == null
            ? null
            : AvatarVoice(
                connected: voice['connected'] == true,
                speaking: voice['phase'] == 'speaking',
                muted: voice['muted'] == true,
                ending: voice['ending'] == true,
              ),
      );
      expect(state.id, e['value'], reason: '$input');
    }
    expect(activityPhaseAvatar['reading'], LonoraAvatarState.inspecting);
    expect(activityPhaseAvatar['failed'], LonoraAvatarState.error);
    expect(liveAvatarState(), LonoraAvatarState.waiting);
    expect(liveAvatarState(state: 'paused'), LonoraAvatarState.sleeping);
    expect(
      liveAvatarState(state: 'idle', phase: 'monitoring'),
      LonoraAvatarState.inspecting,
    );
  });
}
