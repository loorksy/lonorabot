// One agent's model (apps/mobile/components/agent-model-settings.tsx, apps/web PermissionMenu
// ModelPage): the model answering now and this agent's usage (the ported @lonora/core lines),
// the owner's choice among the connected providers' models, back to the default model, and
// the ChatGPT plan's usage page. Only the owner assigns a model; it never grants authority.
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../core/json.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../settings/settings_common.dart';
import '../profile/agent_data.dart';
import '../profile/agent_page.dart';

class ModelSection extends StatefulWidget {
  const ModelSection({super.key, required this.agentId});

  final String agentId;

  @override
  State<ModelSection> createState() => _ModelSectionState();
}

class _ModelSectionState extends State<ModelSection> {
  Json? _summary;
  Object? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final summary = await fetchModelSummary(widget.agentId);
      if (mounted) setState(() => (_summary = summary, _error = null));
    } catch (error) {
      if (mounted) setState(() => _error = error);
    }
  }

  Future<void> _choose(Json? primary) async {
    final summary = _summary;
    if (summary == null || _busy) return;
    setState(() => _busy = true);
    try {
      await chooseAgentModel(
        widget.agentId,
        primary: primary,
        revision: asInt(asJson(summary['record'])['revision']) ?? 0,
      );
      await _load();
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pick() async {
    final summary = _summary;
    if (summary == null) return;
    final l10n = context.l10n;
    final text = agentModelText(l10n.lang);
    final primary = asJson(
      asJson(asJson(summary['record'])['preference'])['primary'],
    );
    final models = asJsonList(summary['available']);
    final chosen = await showLnSheet<Json>(
      context,
      title: text.chooseModel,
      builder: (sheet) => SingleChildScrollView(
        child: LnSection(
          padding: EdgeInsets.zero,
          footer: text.ownerOnly,
          children: [
            for (final m in models)
              ChoiceTile(
                title: ltr(asStr(m['name'], asStr(m['model']))),
                subtitle: ltr(asStr(m['provider'])),
                selected:
                    primary['provider'] == m['provider'] &&
                    primary['model'] == m['model'],
                onSelect: () =>
                    Navigator.of(sheet)
                        .pop({'provider': m['provider'], 'model': m['model']}),
              ),
          ],
        ),
      ),
    );
    if (chosen != null) await _choose(chosen);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final text = agentModelText(l10n.lang);
    final summary = _summary;
    if (summary == null) {
      final error = _error;
      return LnSection(
        title: text.title,
        children: [
          WrapTile(
            icon: FIcons.cpu,
            title: error == null
                ? l10n.t('sh_loading')
                : errorMessage(context, error) ?? l10n.t('request_failed'),
            trailing: error == null
                ? const LnSpinner(size: 18)
                : Icon(FIcons.rotateCw, color: context.ln.colors.fgMuted),
            onTap: error == null ? null : _load,
          ),
        ],
      );
    }
    final lines = agentModelLines(summary, l10n.lang);
    final available = asJsonList(summary['available']);
    return LnSection(
      title: text.title,
      children: [
        WrapTile(
          icon: FIcons.cpu,
          title: lines.first,
          subtitle: lines.skip(1).join('\n'),
        ),
        if (usesChatGptPlan(summary))
          WrapTile(
            icon: FIcons.externalLink,
            title: chatgptText(l10n.lang).manageUsage,
            onTap: () => openExternalUrl(context, Uri.parse(manageUsageUrl)),
          ),
        if (offersDefaultModel(summary))
          WrapTile(
            icon: FIcons.rotateCcw,
            title: text.backToDefault,
            enabled: !_busy,
            onTap: () {
              HapticFeedback.selectionClick();
              _choose(null);
            },
          ),
        WrapTile(
          icon: LnIcons.listChecks,
          title: text.chooseModel,
          subtitle: available.isEmpty ? text.noModels : text.ownerOnly,
          enabled: !_busy && available.isNotEmpty,
          trailing: _busy ? const LnSpinner(size: 18) : const TileChevron(),
          onTap: _pick,
        ),
      ],
    );
  }
}
