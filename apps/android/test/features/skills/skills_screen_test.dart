// Skills: the catalog with availability, enable/disable of an owner skill, details with edit and
// version restore, add a skill, block an exact version (reason + confirmation), delete; goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/skills
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/skills/skills_data.dart';
import 'package:lonora/features/skills/skills_screen.dart';

import '../agent_profile/wpe_harness.dart';

const ownerManifest = {
  'id': 'london-brief',
  'version': '1.2.0',
  'title': 'London brief',
  'description': 'Writes the pre-London gold brief.',
  'source': 'owner',
  'activation': {'mode': 'explicit', 'triggers': []},
  'risk_class': 'read_only',
  'required_tools': ['web_search'],
  'dependencies': ['chart-analysis'],
};

Map<String, Object?> ownerResource({bool enabled = true, int version = 3}) => {
  'id': 'res-1',
  'agent_id': 'a-gold',
  'version': version,
  'payload': {
    'name': 'london-brief',
    'content': 'Start with the overnight range, then the levels.',
    'enabled': enabled,
    'manifest': ownerManifest,
  },
};

void scriptSkills() {
  fakeApi
    ..on(
      'GET /agents/a-gold/skills/catalog',
      (_, query) => {
        'agent_id': 'a-gold',
        'total': 3,
        'next_offset': null,
        'items': [
          {
            'id': 'chart-analysis',
            'version': '1.4.3',
            'title': 'Chart Analysis',
            'description': 'Inspect broker-backed charts, candles and supported indicators.',
            'source': 'builtin',
            'available': true,
            'code': null,
            'manifest': {
              'activation': {'mode': 'explicit', 'triggers': []},
              'risk_class': 'read_only',
              'required_tools': ['chart_inspect'],
              'dependencies': [],
            },
            'resource_id': null,
          },
          {
            'id': 'london-brief',
            'version': '1.2.0',
            'title': 'London brief',
            'description': 'Writes the pre-London gold brief.',
            'source': 'owner',
            'available': true,
            'code': null,
            'manifest': ownerManifest,
            'resource_id': 'res-1',
          },
          {
            'id': 'news-scan',
            'version': '0.9.0',
            'title': 'News scan',
            'description': 'Scans headlines for gold drivers.',
            'source': 'owner',
            'available': false,
            'code': 'skill_version_revoked',
            'manifest': {},
            'resource_id': null,
          },
        ],
      },
    )
    ..on(
      'GET /agents/a-gold/skills/revocations',
      (_, _) => {
        'agent_id': 'a-gold',
        'revision': 4,
        'revoked': [
          {
            'skill_id': 'news-scan',
            'version': '0.9.0',
            'reason': 'regression',
            'revoked_at': '2026-11-21T09:30:00+00:00',
          },
        ],
      },
    )
    ..on('GET /skills', (_, _) => [ownerResource()])
    ..on('GET /skills/res-1', (_, _) => ownerResource())
    ..on(
      'GET /agents/a-gold/skills/catalog/london-brief',
      (_, _) => {
        'id': 'london-brief',
        'version': '1.2.0',
        'title': 'London brief',
        'description': 'Writes the pre-London gold brief.',
        'source': 'owner',
        'available': true,
        'manifest': ownerManifest,
        'resource_id': 'res-1',
        'content': 'Start with the overnight range, then the levels.',
      },
    )
    ..on(
      'GET /agents/a-gold/skills/catalog/chart-analysis',
      (_, _) => {
        'id': 'chart-analysis',
        'version': '1.4.3',
        'title': 'Chart Analysis',
        'description': 'Inspect broker-backed charts.',
        'source': 'builtin',
        'available': true,
        'manifest': {
          'activation': {'mode': 'explicit', 'triggers': []},
          'risk_class': 'read_only',
          'required_tools': ['chart_inspect'],
          'dependencies': [],
        },
        'content': 'Read the chart before any analysis.',
      },
    );
}

Future<void> pumpSkills(WidgetTester tester, {String locale = 'en'}) =>
    pumpScreen(tester, const SkillsScreen(agentId: 'a-gold'), locale: locale);

void main() {
  setUpAll(setUpWpeHarness);
  setUp(resetWpe);

  test('a new skill is read-only instructions loaded on request', () {
    final payload = newSkillPayload(
      id: 'cpi-days',
      title: ' CPI days ',
      purpose: 'Stay flat around CPI.',
      version: '1.0.0',
      content: 'Close before the release.',
    );
    final manifest = payload['manifest'] as Map<String, Object?>;
    expect(manifest['risk_class'], 'read_only');
    expect(manifest['activation'], {'mode': 'explicit', 'triggers': []});
    expect(manifest['title'], 'CPI days');
    expect(manifest['required_tools'], isEmpty);
    expect(skillIdentifier.hasMatch('cpi-days'), isTrue);
    expect(skillIdentifier.hasMatch('CPI days'), isFalse);
    expect(semanticVersion.hasMatch('1.0.0'), isTrue);
    expect(semanticVersion.hasMatch('01.0.0'), isFalse);
  });

  test('an imported file is data; the tool choice keeps the rest', () {
    final json = importedSkillPayload(
      'gold.json',
      '{"name": "Gold Brief", "description": "Pre-London", "instructions": "Levels first."}',
      fallbackDescription: 'Imported skill',
    );
    expect(json['name'], 'gold-brief');
    expect(json['content'], 'Levels first.');
    final manifest = json['manifest'] as Map<String, Object?>;
    expect(manifest['title'], 'Gold Brief');
    expect(manifest['description'], 'Pre-London');
    expect(manifest['risk_class'], 'read_only');
    final md = importedSkillPayload(
      'موجز الذهب.md',
      '# Brief\nLevels first.',
      fallbackDescription: 'Imported skill',
    );
    expect(md['content'], '# Brief\nLevels first.');
    expect(
      (md['manifest'] as Map<String, Object?>)['description'],
      'Imported skill',
    );
    expect(skillIdentifier.hasMatch(md['name']! as String), isTrue);
    expect(
      (md['name']! as String).startsWith('skill-'),
      isTrue,
      reason: 'a title with no Latin letters gets a random id',
    );
    // The form edits the first tool only.
    expect(keepTools(['web_search', 'chart_inspect'], 'artifact_read'), [
      'artifact_read',
      'chart_inspect',
    ]);
    expect(keepTools(['web_search', 'chart_inspect'], ''), ['chart_inspect']);
    expect(keepTools(['web_search'], 'web_search'), ['web_search']);
  });

  testWidgets('lists the catalog with source and availability', (tester) async {
    scriptSkills();
    await pumpSkills(tester);
    expect(find.textContaining('Chart Analysis'), findsOneWidget);
    expect(find.textContaining('Built-in · Available'), findsOneWidget);
    expect(
      find.textContaining('This version is blocked for this agent'),
      findsOneWidget,
    );
    expect(find.textContaining('news-scan · 0.9.0'), findsOneWidget);
  });

  testWidgets('switches an owner skill off', (tester) async {
    scriptSkills();
    fakeApi.on('PUT /skills/res-1', (body, _) => ownerResource(enabled: false));
    await pumpSkills(tester);
    await tester.tap(find.byType(LnSwitch).first);
    await tester.pumpAndSettle();
    final call = fakeApi.callsTo('PUT', '/skills/res-1').single;
    final body = call.body! as Map<String, Object?>;
    expect(body['version'], 3);
    expect((body['payload']! as Map)['enabled'], isFalse);
    await settleToasts(tester);
  });

  testWidgets('restores an earlier version from the details', (tester) async {
    scriptSkills();
    fakeApi
      ..on(
        'GET /skills/res-1/versions',
        (_, _) => [
          {'version': 3, 'current': true, 'created_at': '2026-11-25T10:00:00Z'},
          {
            'version': 2,
            'current': false,
            'created_at': '2026-11-20T10:00:00Z',
          },
        ],
      )
      ..on('POST /skills/res-1/restore', (_, _) => ownerResource(version: 4));
    await pumpSkills(tester);
    await tapAndSettle(tester, find.textContaining('London brief').first);
    expect(find.text('Skill details'), findsOneWidget);
    final history = find.text('Version history');
    await tester.scrollUntilVisible(
      history,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, history);
    await tapAndSettle(tester, find.text('Version 2'));
    expect(fakeApi.callsTo('POST', '/skills/res-1/restore').single.body, {
      'version': 2,
      'expected_version': 3,
    });
    await settleToasts(tester);
  });

  testWidgets('a blocked version\'s date reads in Arabic-Indic digits; its '
      'version number stays Latin', (tester) async {
    scriptSkills();
    await pumpSkills(tester, locale: 'ar');
    final date = find.textContaining('٢١');
    await tester.scrollUntilVisible(
      date,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    final line = tester.widget<Text>(date).data!;
    expect(line, contains('٠٩:٣٠'));
    // Only the date is Arabic-Indic: the line holds no Latin digit.
    expect(line, isNot(matches(RegExp('[0-9]'))));
    expect(find.textContaining('0.9.0'), findsWidgets);
  });

  testWidgets('blocks a built-in version only after reason and confirm', (
    tester,
  ) async {
    scriptSkills();
    fakeApi.on('POST /agents/a-gold/skills/revocations', (_, _) => {});
    await pumpSkills(tester);
    await tapAndSettle(tester, find.textContaining('Chart Analysis').first);
    expect(
      find.text(
        'Built-in instructions are read only. You can block an exact version for this agent.',
      ),
      findsOneWidget,
    );
    final block = find.text('Block this version');
    await tester.scrollUntilVisible(
      block,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, block);
    await tapAndSettle(tester, find.text('Unsafe'));
    await tapAndSettle(tester, find.text('Block this version').last);
    expect(
      fakeApi.callsTo('POST', '/agents/a-gold/skills/revocations'),
      isEmpty,
    );
    await tapAndSettle(tester, find.text('Block'));
    expect(
      fakeApi.callsTo('POST', '/agents/a-gold/skills/revocations').single.body,
      {
        'skill_id': 'chart-analysis',
        'version': '1.4.3',
        'expected_revision': 4,
        'reason': 'unsafe',
      },
    );
    await settleToasts(tester);
  });

  testWidgets('adds a skill', (tester) async {
    scriptSkills();
    fakeApi.on('POST /skills', (body, _) => ownerResource());
    await pumpSkills(tester);
    await tapAndSettle(tester, find.bySemanticsLabel('Add a skill'));
    expect(find.text('Import a skill'), findsOneWidget);
    await tapAndSettle(tester, find.text('Add a skill').last);
    final fields = find.byType(EditableText);
    await tester.enterText(fields.at(0), 'cpi-days');
    await tester.enterText(fields.at(1), 'CPI days');
    await tester.enterText(fields.at(2), 'Stay flat around CPI.');
    await tester.enterText(fields.at(4), 'Close before the release.');
    await tester.pump();
    final create = find.text('Create skill');
    await tester.scrollUntilVisible(
      create,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tapAndSettle(tester, create);
    final body = fakeApi.callsTo('POST', '/skills').single.body! as Map;
    expect(body['agent_id'], 'a-gold');
    expect((body['payload'] as Map)['name'], 'cpi-days');
    await settleToasts(tester);
  });

  /// The details sheet of the owner skill «London brief».
  Future<void> openLondonBrief(WidgetTester tester) async {
    await pumpSkills(tester);
    await tapAndSettle(tester, find.textContaining('London brief').first);
  }

  Finder field(String text) => find.byWidgetPredicate(
    (w) => w is EditableText && w.controller.text == text,
  );

  Future<void> reveal(WidgetTester tester, Finder finder) async {
    await tester.scrollUntilVisible(
      finder,
      200,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.ensureVisible(finder);
    await tester.pumpAndSettle();
  }

  testWidgets(
    'wf:C1 the title block and description align by their own direction',
    (tester) async {
      scriptSkills();
      await pumpSkills(tester, locale: 'ar');
      await tapAndSettle(tester, find.textContaining('London brief').first);
      final sheet = find.byType(SingleChildScrollView).last;
      // Text widgets only: the edit fields below hold the same words.
      Finder inSheet(Finder f) => find.descendant(of: sheet, matching: f);
      Finder shown(String text) =>
          find.byWidgetPredicate((w) => w is Text && w.data == text);
      final title = inSheet(shown('London brief'));
      final coordinates = inSheet(find.textContaining('london-brief')).first;
      expect(tester.widget<Text>(title).textDirection, TextDirection.ltr);
      expect(tester.widget<Text>(coordinates).textDirection, TextDirection.ltr);
      final description = inSheet(shown('Writes the pre-London gold brief.'));
      expect(tester.widget<Text>(description).textDirection, TextDirection.ltr);
    },
  );

  testWidgets('saves an owner skill with its name, description and version', (
    tester,
  ) async {
    scriptSkills();
    fakeApi.on('PUT /skills/res-1', (_, _) => ownerResource(version: 4));
    await openLondonBrief(tester);
    await tester.enterText(field('London brief'), 'London open brief');
    await tester.enterText(field('Writes the pre-London gold brief.'), '');
    await tester.enterText(field('1.2.0'), '1.3.0');
    await tester.pump();
    final save = find.text('Save');
    await reveal(tester, save);
    await tapAndSettle(tester, save);
    final body = fakeApi.callsTo('PUT', '/skills/res-1').single.body! as Map;
    expect(body['version'], 3);
    final payload = body['payload'] as Map;
    expect(
      payload['content'],
      'Start with the overnight range, then the levels.',
    );
    expect(payload['enabled'], isTrue);
    expect(payload['manifest'], {
      ...ownerManifest,
      'version': '1.3.0',
      'title': 'London open brief',
      // An empty description reads the title (apps/web `withFields`).
      'description': 'London open brief',
      'required_tools': ['web_search'],
    });
    await settleToasts(tester);
  });

  testWidgets('a skill with no name cannot be saved', (tester) async {
    scriptSkills();
    await openLondonBrief(tester);
    await tester.enterText(field('London brief'), ' ');
    await tester.pump();
    expect(find.text('Enter a title.'), findsOneWidget);
    final save = find.ancestor(
      of: find.text('Save'),
      matching: find.byType(BlockButton),
    );
    expect(tester.widget<BlockButton>(save).onPressed, isNull);
  });

  testWidgets('unsaved skill edits are confirmed before the sheet closes', (
    tester,
  ) async {
    scriptSkills();
    await openLondonBrief(tester);
    await tester.enterText(
      field('Start with the overnight range, then the levels.'),
      'Levels first.',
    );
    await tester.pump();
    // A tap beside the sheet does not drop the edit.
    await tester.tapAt(const Offset(20, 60));
    await tester.pumpAndSettle();
    expect(find.text('Skill details'), findsOneWidget);
    final close = find.text('Close');
    await reveal(tester, close);
    await tapAndSettle(tester, close);
    expect(find.text('Discard the changes?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Keep editing'));
    expect(find.text('Skill details'), findsOneWidget);
    await tapAndSettle(tester, close);
    await tapAndSettle(tester, find.text('Discard'));
    expect(find.text('Skill details'), findsNothing);
    expect(fakeApi.callsTo('PUT', '/skills/res-1'), isEmpty);
  });

  testWidgets('deleting an owner skill is confirmed', (tester) async {
    scriptSkills();
    fakeApi.on('DELETE /skills/res-1', (_, _) => {'deleted': true});
    await openLondonBrief(tester);
    final delete = find.text('Delete skill');
    await reveal(tester, delete);
    await tapAndSettle(tester, delete);
    expect(find.text('Delete this installed skill?'), findsOneWidget);
    expect(fakeApi.callsTo('DELETE', '/skills/res-1'), isEmpty);
    await tapAndSettle(tester, find.text('Delete'));
    expect(fakeApi.callsTo('DELETE', '/skills/res-1'), hasLength(1));
    await settleToasts(tester);
  });

  testWidgets('each skill switch names its skill', (tester) async {
    scriptSkills();
    await pumpSkills(tester);
    final label = tester.widget<LnSwitch>(find.byType(LnSwitch)).semanticLabel;
    expect(label, contains('Enabled'));
    expect(label, contains('London brief'));
  });

  testWidgets('offline first load offers a retry', (tester) async {
    scriptSkills();
    var offline = true;
    final catalog = fakeApi.handlers['GET /agents/a-gold/skills/catalog']!;
    fakeApi.on('GET /agents/a-gold/skills/catalog', (body, query) {
      if (offline) throw ApiError.network();
      return catalog(body, query);
    });
    await pumpSkills(tester);
    expect(
      find.text(
        'Could not connect to the server. Check its address and your network.',
      ),
      findsOneWidget,
    );
    offline = false;
    await tapAndSettle(tester, find.text('Retry'));
    expect(find.textContaining('Chart Analysis'), findsOneWidget);
  });

  for (final v in goldenVariants) {
    testWidgets('golden ${v.name}', (tester) async {
      await withRealShadows(() async {
        scriptSkills();
        await pumpScreen(
          tester,
          const SkillsScreen(agentId: 'a-gold'),
          brightness: v.brightness,
          locale: v.locale,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/skills_${v.name}.png'),
        );
      });
    });
  }

  testWidgets('golden details light_ar', (tester) async {
    await withRealShadows(() async {
      scriptSkills();
      await pumpSkills(tester, locale: 'ar');
      await tester.tap(find.textContaining('London brief').first);
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/skill_details_light_ar.png'),
      );
    });
  });
}
