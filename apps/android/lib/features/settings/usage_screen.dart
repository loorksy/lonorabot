// «الاستهلاك العام» and «تفاصيل الاستهلاك»: the settings page scaffold around the usage view.
// Lonora's counterpart of apps/web UsagePage.tsx (`UsagePage`, `UsageDetailPage`): period, cost
// and its change, month-to-date with its projection (no cap), the cost per hour/day chart,
// tokens, requests, cache, the ranking by agent (→ its detail) and by model, the all-time token
// totals of apps/mobile account.tsx, and the CSV export.
import 'package:flutter/widgets.dart';

import '../../l10n/l10n.dart';
import 'integrations/ext_common.dart';
import 'settings_common.dart';
import 'usage/usage_view.dart';

class UsageScreen extends StatelessWidget {
  const UsageScreen({super.key});

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    return SettingsPageScaffold(
      title: context.t('us_title'),
      body: UsageView(
        onOpenAgent: (id, name) => pushSettingsPage<void>(
          context,
          UsageDetailPage(agentId: id, agentName: name),
        ),
      ),
    );
  }
}

/// One agent's usage: its share of the total, the chart and its models. [agentName] is the
/// ranked name, for an agent the shell no longer lists.
class UsageDetailPage extends StatelessWidget {
  const UsageDetailPage({super.key, required this.agentId, this.agentName});

  final String agentId;
  final String? agentName;

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    return SettingsPageScaffold(
      title: context.t('us_detailTitle'),
      body: UsageView(agentId: agentId, agentName: agentName),
    );
  }
}
