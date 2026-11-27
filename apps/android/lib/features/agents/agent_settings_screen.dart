// «إعدادات الوكيل» (/agent/:id/settings): everything Lonora lets the owner change on one agent
// (apps/mobile/app/bot-settings.tsx, apps/web IdentityPage.tsx, AgentPage.tsx, PermissionMenu,
// NotifyPages `CommunicationPage`), composed from the kit. The avatar studio has a discard dialog
// and the instructions editor its own Save.
//
// Sections: identity (avatar studio, name, role, description), instructions, model, trading
// (Mandate through its card; market scope), notifications (per-agent delivery rules), links to
// memory, skills and routines, pause, delete (confirmed; the server's refusal shown).
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/app_state.dart';
import '../settings/settings_common.dart';
import 'profile/agent_data.dart';
import 'profile/agent_page.dart';
import 'profile/agent_strings.dart';
import 'settings/avatar_editor.dart';
import 'settings/delivery_section.dart';
import 'settings/mandate_section.dart';
import 'settings/market_section.dart';
import 'settings/model_section.dart';

class AgentSettingsScreen extends StatefulWidget {
  const AgentSettingsScreen({super.key, required this.agentId});
  final String agentId;

  @override
  State<AgentSettingsScreen> createState() => _AgentSettingsScreenState();
}

class _AgentSettingsScreenState extends State<AgentSettingsScreen> {
  final _name = TextEditingController();
  final _title = TextEditingController();
  final _description = TextEditingController();
  final _instructions = TextEditingController();

  /// Unsaved drafts of the delivery rules and the market scope (their sections report them).
  final _deliveryDirty = ValueNotifier(false);
  final _marketDirty = ValueNotifier(false);

  /// The agent the drafts started from (identity and instructions are compared with it).
  Agent? _base;
  Json? _live;
  Object? _error;
  bool _savingIdentity = false;
  bool _savingInstructions = false;
  bool _busy = false;

  String get _id => widget.agentId;

  @override
  void initState() {
    super.initState();
    for (final c in [_name, _title, _description, _instructions]) {
      c.addListener(_changed);
    }
    _deliveryDirty.addListener(_changed);
    _marketDirty.addListener(_changed);
    unawaited(_load());
  }

  @override
  void dispose() {
    for (final c in [_name, _title, _description, _instructions]) {
      c.dispose();
    }
    _deliveryDirty.dispose();
    _marketDirty.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  Future<void> _load() async {
    var agent = context.read().shell.agents[_id];
    if (agent == null) {
      try {
        agent = await fetchAgent(_id);
        if (!mounted) return;
        context.dispatch(UpsertAgentAction(agent));
      } catch (error) {
        if (error is! SessionRequestCancelled && mounted) {
          setState(() => _error = error);
        }
        return;
      }
    }
    _adopt(agent);
    try {
      final live = await fetchAgentState(_id);
      if (mounted) setState(() => _live = live);
    } catch (_) {}
  }

  /// Takes [agent] as the saved state; drafts the owner has not touched follow it.
  void _adopt(Agent agent) {
    final base = _base;
    void follow(TextEditingController c, String? old, String now) {
      if (base == null || c.text == old) c.text = now;
    }

    follow(_name, base?.name, agent.name);
    follow(_title, base?.title, agent.title);
    follow(_description, base?.description, agent.description);
    follow(_instructions, base?.instructions, agent.instructions);
    setState(() => (_base = agent, _error = null));
  }

  bool get _identityDirty {
    final b = _base;
    return b != null &&
        (_name.text.trim() != b.name ||
            _title.text != b.title ||
            _description.text != b.description);
  }

  bool get _instructionsDirty {
    final b = _base;
    return b != null && _instructions.text != b.instructions;
  }

  /// Anything the owner changed and has not saved.
  bool get _dirty =>
      _identityDirty ||
      _instructionsDirty ||
      _deliveryDirty.value ||
      _marketDirty.value;

  Future<void> _patch(Json body, String done, void Function(bool) busy) async {
    busy(true);
    try {
      final updated = await patchAgent(_id, body);
      if (!mounted) return;
      context.dispatch(UpsertAgentAction(updated));
      _adopt(updated);
      LnToast.show(context, context.t(done), kind: LnToastKind.positive);
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) busy(false);
    }
  }

  Future<void> _saveIdentity() async {
    final b = _base;
    if (b == null || _name.text.trim().isEmpty) return;
    await _patch(
      {
        if (_name.text.trim() != b.name) 'name': _name.text.trim(),
        if (_title.text != b.title) 'title': _title.text,
        if (_description.text != b.description)
          'description': _description.text,
      },
      'ag_identitySaved',
      (v) => setState(() => _savingIdentity = v),
    );
  }

  Future<void> _saveInstructions() => _patch(
    {'instructions': _instructions.text},
    'ag_instructionsSaved',
    (v) => setState(() => _savingInstructions = v),
  );

  Future<void> _setPaused(Agent agent, bool paused) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final updated = await patchAgent(agent.id, {'paused': paused});
      if (!mounted) return;
      context.dispatch(UpsertAgentAction(updated));
      _base = _base == null
          ? updated
          : Agent.fromJson({..._base!.raw, 'paused': updated.paused});
      LnToast.show(
        context,
        context.t(updated.paused ? 'ag_agentPaused' : 'ag_agentResumed'),
        kind: LnToastKind.positive,
      );
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete(Agent agent) async {
    final l10n = context.l10n;
    final ok = await showLnConfirm(
      context,
      title: l10n.t('ag_deleteAgentQ', [agent.name]),
      message: l10n.t('ag_deleteAgentBody'),
      confirmLabel: l10n.t('delete'),
      cancelLabel: l10n.t('cancelAction'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() => _busy = true);
    try {
      await deleteAgent(agent.id);
      if (!mounted) return;
      LnToast.show(
        context,
        l10n.t('ag_agentDeleted'),
        kind: LnToastKind.positive,
      );
      unawaited(context.dispatchAndWait(RefreshShellAction()));
      context.go(Routes.agents);
    } catch (error) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  Future<void> _back() async {
    if (_dirty && !await confirmDiscard(context)) {
      return;
    }
    if (mounted) leaveTo(context, Routes.agent(_id));
  }

  Widget _field(
    TextEditingController controller, {
    String? label,
    int maxLength = 160,
    int? minLines,
    int? maxLines = 1,
    String? hint,
    bool enabled = true,
  }) => ContentField(
    controller: controller,
    label: label,
    helper: hint,
    enabled: enabled,
    minLines: minLines,
    maxLines: maxLines,
    maxLength: maxLength,
  );

  Widget _button(
    String label,
    VoidCallback? onPressed, {
    bool loading = false,
  }) => Padding(
    padding: const EdgeInsetsDirectional.fromSTEB(
      LnSpace.pageGutter,
      LnSpace.sm,
      LnSpace.pageGutter,
      0,
    ),
    child: BlockButton(label: label, loading: loading, onPressed: onPressed),
  );

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    registerAgentStrings(l10n);
    final c = context.ln.colors;
    final agent = context.select((AppState s) => s.shell.agents[_id]);
    final base = _base;
    if (agent != null && base != null && !identical(agent.raw, base.raw)) {
      // A newer row from the server (realtime, another page): untouched drafts follow it.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && !identical(_base?.raw, agent.raw)) _adopt(agent);
      });
    }
    if (agent == null || base == null) {
      final error = _error;
      return AgentPage(
        title: l10n.t('agentSettings'),
        fallback: Routes.agents,
        body: error == null
            ? const SettingsSkeleton(groups: [3, 2, 2])
            : error is ApiError && error.isNotFound
            ? EmptyState(icon: FIcons.userX, title: l10n.t('agentMissing'))
            : LoadFailure(error: error, onRetry: _load),
      );
    }

    final readiness = asJson(_live?['trading_readiness']);
    final hasMode = showsTradingControl(
      agent,
      hasTradingAccount: readiness['has_trading_account'] is bool
          ? readiness['has_trading_account'] as bool
          : null,
    );
    final nameEmpty = _name.text.trim().isEmpty;
    final fixedPair =
        agent.scopeMode != 'flexible' && (agent.tradingSymbol ?? '').isNotEmpty;

    final children = <Widget>[
      // Identity.
      LnSection(
        title: l10n.t('ag_identity'),
        children: [
          WrapTile(
            title: l10n.t('avatarEdit'),
            subtitle: agent.isPersonal ? l10n.t('personalAgent') : null,
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                LonoraAvatar(
                  agentId: agent.id,
                  face: agent.avatar,
                  color: agent.color,
                  size: 36,
                  animate: false,
                ),
                const SizedBox(width: LnSpace.xs),
                const TileChevron(),
              ],
            ),
            onTap: () => showAvatarEditor(context, agent),
          ),
          if (fixedPair)
            WrapTile(
              icon: FIcons.chartCandlestick,
              title: l10n.t('symbol'),
              subtitle: l10n.t('immutableTradingPair'),
              trailing: Text(
                ltr(agent.tradingSymbol!),
                style: context.ln.text.body.copyWith(color: c.fgMuted),
              ),
            ),
        ],
      ),
      _field(
        _name,
        label: l10n.t('name'),
        maxLength: 80,
        enabled: !_savingIdentity,
      ),
      _field(
        _title,
        label: l10n.t('ag_roleField'),
        maxLength: 160,
        enabled: !_savingIdentity,
      ),
      _field(
        _description,
        label: l10n.t('description'),
        maxLength: 2000,
        minLines: 2,
        maxLines: 6,
        enabled: !_savingIdentity,
      ),
      _button(
        l10n.t('save'),
        _identityDirty && !nameEmpty ? _saveIdentity : null,
        loading: _savingIdentity,
      ),
      const SectionGap(),
      // Instructions: the editor and its own Save.
      PageSectionTitle(l10n.t('instructions')),
      _field(
        _instructions,
        hint: l10n.t('ag_instructionsHint'),
        maxLength: 16000,
        minLines: 6,
        maxLines: 14,
        enabled: !_savingInstructions,
      ),
      _button(
        l10n.t('save'),
        _instructionsDirty ? _saveInstructions : null,
        loading: _savingInstructions,
      ),
      const SectionGap(),
      ModelSection(agentId: agent.id),
      if (hasMode) ...[
        const SectionGap(),
        MandateSection(
          key: ValueKey('mandate:${agent.id}:${agent.tradingMode}'),
          agent: agent,
          unresolved: asInt(readiness['unresolved_count']),
        ),
      ],
      if (offersMarketScope(agent)) ...[
        const SectionGap(),
        MarketSection(
          key: ValueKey('market:${agent.id}:${agent.scopeRevision}'),
          agent: agent,
          dirty: _marketDirty,
        ),
      ],
      const SectionGap(),
      DeliverySection(agentId: agent.id, dirty: _deliveryDirty),
      const SectionGap(),
      LnSection(
        children: [
          WrapTile(
            icon: FIcons.brain,
            title: l10n.t('ag_memoryTab'),
            subtitle: l10n.t('memoryHint'),
            trailing: const TileChevron(),
            onTap: () => context.push(Routes.agentMemory(agent.id)),
          ),
          WrapTile(
            icon: FIcons.layers,
            title: l10n.t('skills'),
            subtitle: l10n.t('skillsHint'),
            trailing: const TileChevron(),
            onTap: () => context.push(Routes.agentSkills(agent.id)),
          ),
          WrapTile(
            icon: FIcons.clock,
            title: l10n.t('routines'),
            trailing: const TileChevron(),
            onTap: () => context.push(Routes.routines(agentId: agent.id)),
          ),
        ],
      ),
      if (!agent.isPersonal) ...[
        const SectionGap(),
        LnSection(
          children: [
            SwitchTile(
              icon: FIcons.pause,
              title: l10n.t('paused'),
              value: agent.paused,
              onChanged: _busy ? null : (v) => _setPaused(agent, v),
            ),
            LnListTile(
              icon: FIcons.trash2,
              title: l10n.t('ag_deleteAgent'),
              destructive: true,
              enabled: !_busy,
              onTap: () => _delete(agent),
            ),
          ],
        ),
      ],
    ];

    return PopScope(
      canPop: !_dirty,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: AgentPage(
        title: l10n.t('agentSettings'),
        fallback: Routes.agent(_id),
        onBack: _back,
        body: ListView(
          padding: EdgeInsets.only(
            top: LnSpace.xs,
            bottom: pageBottomPadding(context),
          ),
          children: children,
        ),
      ),
    );
  }
}
