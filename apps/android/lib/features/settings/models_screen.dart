// «النماذج»: tile groups, choice tiles, a picker sheet and a confirmed save. Lonora's counterpart
// of apps/web ModelsPage.tsx (global routing: one model for text work or a model per capability,
// the voice routes with OpenAI's speech models, Lonora's model lists with verified metadata) and
// apps/mobile app/(settings)/models.tsx (routing and providers read), plus each agent's own model,
// which is chosen in that agent's settings. A provider's key is set in «مزوّدو النماذج».
import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import 'integrations/ext_common.dart';
import 'integrations/integrations_data.dart';
import 'integrations/providers_page.dart';
import 'models/model_picker.dart';
import 'models/models_data.dart';
import 'settings_common.dart';

class ModelsScreen extends StatefulWidget {
  const ModelsScreen({super.key});

  @override
  State<ModelsScreen> createState() => _ModelsScreenState();
}

class _ModelsScreenState extends State<ModelsScreen> {
  RoutingPolicy? _saved;
  RoutingPolicy? _draft;
  List<ProviderStatus> _providers = const [];
  List<ModelDescriptor> _models = const [];
  Map<String, Json> _agentModels = const {};
  Object? _error;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final (routing, providers) = await (
        fetchRouting(),
        fetchProviders(),
      ).wait;
      final models = await fetchConnectedModels(providers);
      if (!mounted) return;
      setState(() {
        // An unsaved change survives a refresh (pull, or back from the providers page).
        if (!_dirty) _draft = routing;
        _saved = routing;
        _providers = providers;
        _models = models;
        _error = null;
      });
      unawaited(_loadAgentModels());
    } on SessionRequestCancelled {
      return;
    } on ParallelWaitError<
      (RoutingPolicy?, List<ProviderStatus>?),
      (AsyncError?, AsyncError?)
    > catch (e) {
      final error = e.errors.$1?.error ?? e.errors.$2?.error;
      if (error is SessionRequestCancelled) return;
      _failed(error);
    } catch (e) {
      _failed(e);
    }
  }

  /// A failed refresh keeps the page on screen and says so; a first read shows the error.
  void _failed(Object? error) {
    if (!mounted || error == null) return;
    if (_draft != null) {
      showErrorToast(context, error);
    } else {
      setState(() => _error = error);
    }
  }

  /// Each agent's current model, for the per-agent rows; a summary that fails is left out.
  Future<void> _loadAgentModels() async {
    final agents = context.read().shell.orderedAgents;
    final entries = await Future.wait([
      for (final a in agents)
        fetchAgentModelSummary(a.id).then<MapEntry<String, Json>?>(
          (summary) => MapEntry(a.id, summary),
          onError: (Object _) => null,
        ),
    ]);
    if (!mounted) return;
    setState(
      () => _agentModels = {for (final e in entries.nonNulls) e.key: e.value},
    );
  }

  bool get _speech => _providers.any((p) => p.id == 'openai' && p.configured);

  bool get _dirty => _draft != null && _draft != _saved;

  Future<void> _pick({required String? capability}) async {
    final draft = _draft;
    if (draft == null) return;
    final current = capability == null
        ? draft.unified
        : draft.routes[capability];
    final picked = await showModelPicker(
      context,
      title: capability == null
          ? context.t('md_unifiedModel')
          : context.t('md_cap_$capability'),
      options: modelsFor(capability, _models, speech: _speech),
      current: current,
    );
    if (picked == null || !mounted) return;
    setState(
      () => _draft = capability == null
          ? draft.withUnified(picked.selection)
          : draft.withRoute(capability, picked.selection),
    );
  }

  Future<void> _save() async {
    final draft = _draft;
    if (draft == null || _saving) return;
    final ok = await showLnConfirm(
      context,
      title: context.t('md_saveRoutingQ'),
      message: context.t('md_routingNote'),
      confirmLabel: context.t('save'),
      cancelLabel: context.t('sh_cancel'),
    );
    if (!ok || !mounted) return;
    setState(() => _saving = true);
    try {
      final saved = await saveRouting(draft);
      if (!mounted) return;
      setState(() {
        _saved = saved;
        _draft = saved;
      });
      LnToast.show(context, context.t('ix_saved'), kind: LnToastKind.positive);
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _openProviders() async {
    await pushSettingsPage<void>(context, const ProvidersPage());
    if (mounted) await _load();
  }

  /// One route. With no model list to choose from, the routing is only shown (the Web hides
  /// its form): clearing the only global model would leave every agent without one.
  LnListTile _routeTile(String? capability, {required bool editable}) {
    final draft = _draft!;
    final value = capability == null ? draft.unified : draft.routes[capability];
    final voice = capability != null && voiceCapabilities.contains(capability);
    final subtitle = value == null
        ? context.t('md_chooseModel')
        : isolate(selectionLabel(value, _models));
    final title = capability == null
        ? context.t('md_unifiedModel')
        : context.t('md_cap_$capability');
    final icon = switch (capability) {
      null => FIcons.cpu,
      'conversation' => FIcons.messageSquare,
      'reasoning' => FIcons.brain,
      'research' => FIcons.search,
      'vision' => FIcons.eye,
      'realtime_voice' => FIcons.audioLines,
      'stt' => FIcons.mic,
      'tts' => FIcons.volume2,
      _ => FIcons.clock,
    };
    if (!editable) {
      return LnListTile(icon: icon, title: title, subtitle: subtitle);
    }
    return LnListTile(
      icon: icon,
      title: title,
      subtitle: subtitle,
      enabled: !_saving && (!voice || _speech || value != null),
      onTap: () => _pick(capability: capability),
    );
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final title = context.t('models');
    final draft = _draft;
    if (draft == null) {
      return SettingsPageScaffold(
        title: title,
        body: _error == null
            ? const PageLoading(groups: [2, 4])
            : LoadFailure(error: _error!, onRetry: _load),
      );
    }
    final c = context.ln.colors;
    final chevron = Icon(FIcons.chevronRight, color: c.chevron);
    final agents = context.select((AppState s) => s.shell.orderedAgents);
    final configured = _providers.where((p) => p.configured).length;
    final agentText = agentModelText(context.l10n.lang);
    final editable = _models.isNotEmpty;
    return SettingsPageScaffold(
      title: title,
      onRefresh: _load,
      children: [
        if (!editable) SettingsNote(context.t('md_noModels')),
        LnSection(
          title: context.t('md_globalRouting'),
          children: [
            if (!editable)
              LnListTile(
                icon: draft.isUnified ? FIcons.circleDot : FIcons.split,
                title: context.t('md_mode'),
                value: context.t(
                  draft.isUnified ? 'md_unifiedMode' : 'md_customMode',
                ),
              )
            else ...[
              ChoiceTile(
                title: context.t('md_unifiedMode'),
                icon: FIcons.circleDot,
                selected: draft.isUnified,
                enabled: !_saving,
                onSelect: () =>
                    setState(() => _draft = draft.withMode('unified')),
              ),
              ChoiceTile(
                title: context.t('md_customMode'),
                icon: FIcons.split,
                selected: !draft.isUnified,
                enabled: !_saving,
                onSelect: () =>
                    setState(() => _draft = draft.withMode('custom')),
              ),
            ],
          ],
        ),
        const SectionGap(),
        LnSection(
          footer: _speech ? null : context.t('md_voiceNeedsOpenAi'),
          children: [
            if (draft.isUnified) ...[
              _routeTile(null, editable: editable),
              for (final cap in voiceCapabilities)
                _routeTile(cap, editable: editable),
            ] else
              for (final cap in routeCapabilities)
                _routeTile(cap, editable: editable),
          ],
        ),
        SettingsNote(
          context.t('md_routingNote'),
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.pageGutter,
            LnSpace.xs,
            LnSpace.pageGutter,
            LnSpace.md,
          ),
        ),
        if (editable)
          Gutter(
            bottom: LnSpace.lg,
            child: BlockButton(
              label: context.t('md_saveRouting'),
              loading: _saving,
              onPressed: _dirty && !_saving ? _save : null,
            ),
          ),
        LnSection(
          title: context.t('md_perAgent'),
          footer: context.t('md_perAgentNote'),
          children: [
            for (final a in agents) _agentTile(a, agentText, chevron),
            if (agents.isEmpty)
              LnListTile(
                icon: FIcons.bot,
                title: context.t('agents'),
                onTap: () => context.push(Routes.agents),
              ),
          ],
        ),
        const SectionGap(),
        LnSection(
          children: [
            LnListTile(
              icon: FIcons.keyRound,
              title: context.t('ix_modelProviders'),
              value: configured > 0
                  ? '$configured'
                  : context.t('ix_notAddedYet'),
              onTap: _openProviders,
            ),
          ],
        ),
        if (_models.isNotEmpty) ...[
          const SectionGap(),
          LnSection(
            title: context.t('md_availableModels', [_models.length]),
            footer: context.t('ix_catalogNote'),
            children: [
              for (final m in _models)
                WrapTile(
                  title: isolate(m.label),
                  trailing: StatusChip(
                    label: context.t(
                      m.verified ? 'md_verified' : 'md_unverified',
                    ),
                    kind: m.verified
                        ? StatusChipKind.success
                        : StatusChipKind.neutral,
                  ),
                ),
            ],
          ),
        ],
      ],
    );
  }

  WrapTile _agentTile(Agent a, AgentModelText text, Widget chevron) {
    final summary = _agentModels[a.id];
    final name = modelName(asJson(summary?['current']));
    final record = asJson(summary?['record']);
    final chosenBy = record['chosen_by'];
    // The model card's rule (agentModelLines): who chose only counts while a model is chosen.
    final chosen =
        chosenBy != null && asJson(record['preference'])['primary'] != null;
    final by = !chosen
        ? null
        : chosenBy == 'owner'
        ? text.chosenByYou
        : text.inherited;
    return WrapTile(
      icon: FIcons.bot,
      title: isolate(a.name),
      subtitle: summary == null
          ? null
          // «your default model» starts the line: sentence case.
          : [name ?? sentenceStart(text.defaultModel), ?by].join(dotSeparator),
      trailing: chevron,
      onTap: () => context.push(Routes.agentSettings(a.id)),
    );
  }
}
