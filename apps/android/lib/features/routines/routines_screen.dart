// «المهام المجدولة» (/routines?agent=): an agent's routines, or every agent's, as the kit's
// ScheduleCard rows with the routine editor and detail. Capabilities follow Lonora's other clients
// (apps/mobile/app/routine.tsx, apps/web SchedulesPages.tsx): list, create, edit, pause/resume,
// delete, execution history.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../app/routes.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../agents/profile/agent_page.dart';
import '../agents/profile/agent_strings.dart';
import '../settings/settings_common.dart' show SettingsNote;
import 'routine_board.dart';
import 'routines_strings.dart';

class RoutinesScreen extends StatefulWidget {
  const RoutinesScreen({super.key, this.agentId});
  final String? agentId;

  @override
  State<RoutinesScreen> createState() => _RoutinesScreenState();
}

class _RoutinesScreenState extends State<RoutinesScreen> {
  final _board = GlobalKey<RoutineBoardState>();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    registerAgentStrings(l10n);
    registerRoutinesStrings(l10n);
    final id = widget.agentId;
    final agentName = context.select(
      (AppState s) => id == null ? null : s.shell.agents[id]?.name,
    );
    return AgentPage(
      title: agentName == null
          ? l10n.t('routines')
          : '${l10n.t('routines')} · ${isolate(agentName)}',
      fallback: id == null ? Routes.me : Routes.agent(id),
      trailing: CircleIconButton(
        icon: const Icon(FIcons.plus),
        semanticLabel: l10n.t('createRoutine'),
        onTap: () => _board.currentState?.create(),
      ),
      body: RoutineBoard(
        key: _board,
        agentId: id,
        header: [SettingsNote(l10n.t('routineHint'))],
      ),
    );
  }
}
