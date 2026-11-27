// «الذاكرة» (/agent/:id/memory): the agent's persistent memory and its knowledge: the memory,
// «manage edits» (the list of edits) and an empty state, composed from the kit. Capabilities follow
// Lonora's other clients (apps/mobile bot-settings memory field, apps/web Knowledge.tsx,
// KnowledgeSection + MemoryRevisions, ScratchpadSection, GoalsKnowledgePages): Lonora's memory is
// one versioned text the owner reads and edits (`GET/PUT /agents/{id}/memory`, ≤ 30000 characters);
// every change is attributed and can be undone on its own (`/memory/revisions/{id}/revert`);
// semantic retrieval sits under it; notes, links and the scratchpad live under Knowledge; light
// goals have their own tab. Each part loads on its own: a failed one shows its error where it would
// be, the others stay.
import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../routines/routines_data.dart' show clock;
import '../settings/settings_common.dart';
import 'memory/knowledge_section.dart';
import 'memory/memory_revisions.dart';
import 'memory/resource_sections.dart';
import 'memory/semantic_section.dart';
import 'profile/agent_data.dart';
import 'profile/agent_page.dart';
import 'profile/agent_strings.dart';

class AgentMemoryScreen extends StatefulWidget {
  const AgentMemoryScreen({super.key, required this.agentId});
  final String agentId;

  @override
  State<AgentMemoryScreen> createState() => _AgentMemoryScreenState();
}

enum MemoryTab { memory, knowledge, goals }

class _AgentMemoryScreenState extends State<AgentMemoryScreen> {
  MemoryTab _tab = MemoryTab.memory;
  AgentMemory? _memory;
  Object? _memoryError;
  List<MemoryRevision>? _revisions;
  Object? _revisionsError;
  List<KnowledgeItem>? _knowledge;
  Object? _knowledgeError;
  List<AgentResource>? _goals;
  Object? _goalsError;
  List<AgentResource>? _scratchpad;
  Object? _scratchpadError;
  bool _editing = false;
  bool _busy = false;
  final _draft = TextEditingController();

  String get _id => widget.agentId;

  @override
  void initState() {
    super.initState();
    _draft.addListener(() {
      if (_editing) setState(() {});
    });
    unawaited(_load());
  }

  @override
  void dispose() {
    _draft.dispose();
    super.dispose();
  }

  Future<void> _load() => Future.wait([
    _read(
      fetchMemory(_id),
      (v, e) => (_memory = v ?? _memory, _memoryError = e),
    ),
    _read(
      fetchMemoryRevisions(_id),
      (v, e) => (_revisions = v ?? _revisions, _revisionsError = e),
    ),
    _loadKnowledge(),
    _loadGoals(),
    _loadScratchpad(),
  ]);

  Future<void> _loadKnowledge() => _read(
    fetchKnowledge(_id),
    (v, e) => (_knowledge = v ?? _knowledge, _knowledgeError = e),
  );

  Future<void> _loadGoals() => _read(
    fetchAgentResources(goalsKind, _id),
    (v, e) => (_goals = v ?? _goals, _goalsError = e),
  );

  Future<void> _loadScratchpad() => _read(
    fetchAgentResources(scratchpadKind, _id),
    (v, e) => (_scratchpad = v ?? _scratchpad, _scratchpadError = e),
  );

  /// One part of the page: [store] gets its value, or null and the error.
  Future<void> _read<T>(
    Future<T> request,
    void Function(T? value, Object? error) store,
  ) async {
    try {
      final value = await request;
      if (mounted) setState(() => store(value, null));
    } catch (error) {
      if (error is! SessionRequestCancelled && mounted) {
        setState(() => store(null, error));
      }
    }
  }

  void _startEditing() {
    _draft.text = _memory?.content ?? '';
    setState(() => _editing = true);
  }

  Future<void> _save() async {
    final memory = _memory;
    if (memory == null || _busy) return;
    setState(() => _busy = true);
    try {
      final saved = await saveMemory(_id, _draft.text, memory.version);
      if (!mounted) return;
      setState(() => (_memory = saved, _editing = false));
      LnToast.show(
        context,
        context.t('ag_memorySaved'),
        kind: LnToastKind.positive,
      );
      unawaited(_load());
    } catch (error) {
      // e.g. memory_user_section_moved, version_conflict: the server's words.
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _revert(MemoryRevision row) async {
    try {
      await revertRevision(row.id, _memory?.version);
      if (!mounted) return;
      LnToast.show(
        context,
        ownerProfileLabel('restored', context.l10n.lang),
        kind: LnToastKind.positive,
      );
      await _load();
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    }
  }

  Future<void> _back() async {
    if (_editing &&
        _draft.text != (_memory?.content ?? '') &&
        !await _confirmDiscard()) {
      return;
    }
    if (mounted) leaveTo(context, Routes.agent(_id));
  }

  Future<bool> _confirmDiscard() {
    final l10n = context.l10n;
    return showLnConfirm(
      context,
      title: l10n.t('ag_discardQ'),
      message: l10n.t('ag_discardBody'),
      confirmLabel: l10n.t('ag_discard'),
      cancelLabel: l10n.t('ag_keepEditing'),
      destructive: true,
    );
  }

  Widget _memoryView(BuildContext context, AgentMemory memory) {
    final l10n = context.l10n;
    final ln = context.ln;
    final c = ln.colors;
    final text = memory.content.trim();
    final updated = memory.updatedAt;
    if (_editing) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ContentField(
            controller: _draft,
            minLines: 10,
            maxLines: 24,
            maxLength: 30000,
            enabled: !_busy,
            autofocus: true,
            helper: l10n.t('memoryHint'),
          ),
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(
              LnSpace.pageGutter,
              LnSpace.md,
              LnSpace.pageGutter,
              0,
            ),
            child: Row(
              children: [
                Expanded(
                  child: BlockButton(
                    label: l10n.t('cancelAction'),
                    variant: BlockButtonVariant.secondary,
                    onPressed: _busy
                        ? null
                        : () async {
                            if (_draft.text != memory.content &&
                                !await _confirmDiscard()) {
                              return;
                            }
                            if (mounted) setState(() => _editing = false);
                          },
                  ),
                ),
                const SizedBox(width: LnSpace.sm),
                Expanded(
                  child: BlockButton(
                    label: l10n.t('save'),
                    loading: _busy,
                    onPressed: _save,
                  ),
                ),
              ],
            ),
          ),
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
          child: LnCardSurface(
            child: text.isEmpty
                ? Padding(
                    padding: const EdgeInsets.symmetric(vertical: LnSpace.md),
                    child: EmptyState(
                      icon: FIcons.brain,
                      title: l10n.t('ag_memoryEmpty'),
                      body: l10n.t('memoryHint'),
                    ),
                  )
                : Padding(
                    padding: const EdgeInsets.all(LnSpace.cardPadding),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        ContentText(
                          text,
                          style: ln.text.body.copyWith(color: c.fg),
                        ),
                        if (updated != null) ...[
                          const SizedBox(height: LnSpace.sm),
                          Text(
                            l10n.t('ag_updatedAt', [
                              '${formatDate('d MMM y', l10n.lang, updated)} ${clock(updated.hour, updated.minute)}',
                            ]),
                            style: ln.text.footnote.copyWith(color: c.fgMuted),
                          ),
                        ],
                      ],
                    ),
                  ),
          ),
        ),
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.pageGutter,
            LnSpace.md,
            LnSpace.pageGutter,
            0,
          ),
          child: BlockButton(
            label: l10n.t('ag_editMemory'),
            icon: FIcons.pencil,
            variant: BlockButtonVariant.secondary,
            onPressed: _startEditing,
          ),
        ),
        if (text.isNotEmpty) SettingsNote(l10n.t('memoryHint')),
        const SectionGap(),
        if (_revisions == null && _revisionsError != null)
          LnSection(
            title: ownerProfileLabel('history', l10n.lang),
            children: [
              WrapTile(
                icon: FIcons.history,
                title:
                    errorMessage(context, _revisionsError!) ??
                    l10n.t('request_failed'),
                trailing: Icon(FIcons.rotateCw, color: c.fgMuted),
                onTap: _load,
              ),
            ],
          )
        else
          RevisionList(revisions: _revisions ?? const [], onRevert: _revert),
        const SectionGap(),
        SemanticSection(agentId: _id),
      ],
    );
  }

  /// A tab's content: [content] once [value] is read, else its skeleton or its failure.
  Widget _part<T>(T? value, Object? error, Widget Function(T value) content) {
    if (value != null) return content(value);
    if (error == null) return const SettingsSkeleton(groups: [4, 3]);
    return Padding(
      padding: const EdgeInsets.only(top: LnSpace.xxl),
      child: LoadFailure(error: error, onRetry: _load),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    registerAgentStrings(l10n);
    final agentName = context.select((AppState s) => s.shell.agents[_id]?.name);
    final memoryError = _memoryError;
    Widget body;
    if (_memory == null && memoryError is ApiError && memoryError.isNotFound) {
      body = EmptyState(icon: FIcons.userX, title: l10n.t('agentMissing'));
    } else {
      body = LnRefresh(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(bottom: pageBottomPadding(context)),
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.pageGutter,
                0,
                LnSpace.pageGutter,
                LnSpace.md,
              ),
              child: LnSegmented<MemoryTab>(
                segments: [
                  LnSegment(
                    value: MemoryTab.memory,
                    label: l10n.t('ag_memoryTab'),
                  ),
                  LnSegment(
                    value: MemoryTab.knowledge,
                    label: l10n.t('ag_knowledgeTab'),
                  ),
                  LnSegment(
                    value: MemoryTab.goals,
                    label: l10n.t('ag_goalsTab'),
                  ),
                ],
                selected: _tab,
                onChanged: (v) => setState(() => _tab = v),
              ),
            ),
            switch (_tab) {
              MemoryTab.memory => _part(
                _memory,
                memoryError,
                (m) => _memoryView(context, m),
              ),
              MemoryTab.knowledge => Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _part(
                    _knowledge,
                    _knowledgeError,
                    (items) => KnowledgeSection(
                      agentId: _id,
                      items: items,
                      onChanged: _loadKnowledge,
                    ),
                  ),
                  const SectionGap(),
                  _part(
                    _scratchpad,
                    _scratchpadError,
                    (rows) => ScratchpadSection(
                      agentId: _id,
                      rows: rows,
                      onChanged: _loadScratchpad,
                    ),
                  ),
                ],
              ),
              MemoryTab.goals => _part(
                _goals,
                _goalsError,
                (rows) => GoalsSection(
                  agentId: _id,
                  rows: rows,
                  onChanged: _loadGoals,
                ),
              ),
            },
          ],
        ),
      );
    }
    return PopScope(
      canPop: !_editing || _draft.text == (_memory?.content ?? ''),
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: AgentPage(
        title: agentName == null
            ? l10n.t('ag_memoryTab')
            : '${l10n.t('ag_memoryTab')} · ${isolate(agentName)}',
        fallback: Routes.agent(_id),
        onBack: _back,
        body: body,
      ),
    );
  }
}
