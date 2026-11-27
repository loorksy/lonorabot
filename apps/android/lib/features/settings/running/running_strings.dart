import '../../../l10n/l10n.dart';

/// Android-only labels of «What is running». The workspace part reuses the Expo app's
/// `running_*` keys; the agents' runs (cancelled with the same `POST /runs/{id}/cancel` the
/// conversation's Stop uses) and the stop-all confirmation are Android's.
void registerRunningStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('rn_agentsAtWork')) return;
  target.register(_runningStrings);
}

const Map<String, List<String>> _runningStrings = {
  'rn_agentsAtWork': ['الوكلاء أثناء العمل', 'Agents at work'],
  'rn_noAgentWorking': [
    'لا يعمل أي وكيل الآن.',
    'No agent is working right now.',
  ],
  'rn_runsNote': [
    'الإيقاف يلغي هذا العمل وما بدأه من خطوات.',
    'Stopping cancels this work and the steps it started.',
  ],
  'rn_workspace': ['مساحة العمل', 'Workspace'],
  'rn_stopAllQ': ['إيقاف كل العمليات؟', 'Stop every process?'],
  'rn_stopAllBody': [
    'تتوقف كل عملية يشغّلها وكلاؤك في مساحة العمل.',
    'Every process your agents run in the workspace is stopped.',
  ],
};
