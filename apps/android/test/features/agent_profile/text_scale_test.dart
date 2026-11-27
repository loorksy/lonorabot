// Every work-package-E screen at text scale 1.3, in Arabic and English, lays out without an
// overflow (and its first sheet too, where one carries a form).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/features/agents/agent_memory_screen.dart';
import 'package:lonora/features/agents/agent_profile_screen.dart';
import 'package:lonora/features/agents/agent_settings_screen.dart';
import 'package:lonora/features/me/owner_knowledge_screen.dart';
import 'package:lonora/features/routines/routines_screen.dart';
import 'package:lonora/features/skills/skills_screen.dart';
import 'package:lonora/features/tasks/tasks_screen.dart';

import '../agent_settings/agent_memory_screen_test.dart' show scriptMemory;
import '../agent_settings/agent_settings_screen_test.dart' show scriptSettings;
import '../knowledge/owner_knowledge_screen_test.dart' show scriptKnowledge;
import '../routines/routines_screen_test.dart' show scriptRoutines;
import '../skills/skills_screen_test.dart' show scriptSkills;
import '../tasks/tasks_screen_test.dart' show scriptTasks;
import 'agent_profile_screen_test.dart' show scriptGold;
import 'wpe_harness.dart';

void main() {
  setUpAll(setUpWpeHarness);
  setUp(resetWpe);

  final screens = <String, (Widget, void Function())>{
    'profile': (const AgentProfileScreen(agentId: 'a-gold'), scriptGold),
    'settings': (const AgentSettingsScreen(agentId: 'a-gold'), scriptSettings),
    'memory': (const AgentMemoryScreen(agentId: 'a-gold'), scriptMemory),
    'skills': (const SkillsScreen(agentId: 'a-gold'), scriptSkills),
    'routines': (const RoutinesScreen(agentId: 'a-gold'), scriptRoutines),
    'tasks': (const TasksScreen(), scriptTasks),
    'knowledge': (const OwnerKnowledgeScreen(), scriptKnowledge),
  };

  for (final MapEntry(key: name, value: (screen, script)) in screens.entries) {
    for (final locale in ['ar', 'en']) {
      testWidgets('$name at 1.3 ($locale)', (tester) async {
        script();
        await pumpScreen(tester, screen, locale: locale, textScale: 1.3);
        expect(tester.takeException(), isNull);
        // Scroll through the whole page: every section lays out.
        final scrollable = find.byType(Scrollable).first;
        for (var i = 0; i < 8; i++) {
          await tester.drag(scrollable, const Offset(0, -500));
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
        }
      });
    }
  }

  testWidgets('routine editor at 1.3 (ar)', (tester) async {
    scriptRoutines();
    await pumpScreen(
      tester,
      const RoutinesScreen(agentId: 'a-gold'),
      textScale: 1.3,
    );
    await tester.tap(find.bySemanticsLabel('إنشاء مهمة مجدولة'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
