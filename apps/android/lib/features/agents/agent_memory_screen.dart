// «الذاكرة» (/agent/:id/memory): the agent's persistent memory and its knowledge: the memory,
// «manage edits» (the list of edits) and an empty state, composed from the kit. Capabilities follow
// Lonora's other clients (apps/mobile bot-settings memory field, apps/web Knowledge.tsx,
// KnowledgeSection + MemoryRevisions, ScratchpadSection, GoalsKnowledgePages): Lonora's memory is
// one versioned text the owner reads and edits (`GET/PUT /agents/{id}/memory`, ≤ 30000 characters);
// every change is attributed and can be undone on its own (`/memory/revisions/{id}/revert`);
// semantic retrieval sits under it; notes, links and the scratchpad live under Knowledge; light
// goals have their own tab. Each part loads on its own: a failed one shows its error where it would
// be, the others stay.
//
// The page sits on the sub-page fill ([LnPalette.sheetPage]); the memory reads in one content card
// ([LnPalette.editorCard], radius 26). Under the Memory tab a stadium field «اطلب من … أن يتذكر»
// sends the owner's line to the agent's own conversation, where the agent decides what to keep.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart'
    show InputBorder, InputDecoration, Material, MaterialType, TextField;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/thread_actions.dart';
import '../../state/app_state.dart';
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
          child: MemoryCard(
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
                              revisionTime(updated, l10n.lang),
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
    final c = context.ln.colors;
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
        background: c.sheetPage,
        fallback: Routes.agent(_id),
        onBack: _back,
        body: _tab == MemoryTab.memory && !_editing && _memory != null
            ? Column(
                children: [
                  Expanded(child: body),
                  RememberField(agentId: _id, agentName: agentName ?? ''),
                ],
              )
            : body,
      ),
    );
  }
}

/// The memory's content card: [LnPalette.editorCard] at radius [LnRadius.group].
class MemoryCard extends StatelessWidget {
  const MemoryCard({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: context.ln.colors.editorCard,
      borderRadius: const BorderRadius.all(Radius.circular(LnRadius.group)),
    ),
    child: child,
  );
}

/// «اطلب من … أن يتذكر»: a 56 dp stadium on [LnPalette.editorCard] with a 44 dp send disc at its
/// end. Sending puts «تذكّر: …» in the agent's own conversation (`POST /agents/{id}/conversation`,
/// then the message), clears the field and says where it went.
class RememberField extends StatefulWidget {
  const RememberField({
    super.key,
    required this.agentId,
    required this.agentName,
  });

  final String agentId;
  final String agentName;

  /// The stadium's height and its send disc.
  static const double height = 56;
  static const double disc = 44;

  @override
  State<RememberField> createState() => _RememberFieldState();
}

class _RememberFieldState extends State<RememberField> {
  final _text = TextEditingController();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _text.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final text = _text.text.trim();
    if (text.isEmpty || _busy) return;
    final l10n = context.l10n;
    setState(() => _busy = true);
    try {
      final ensure = EnsureAgentThreadAction(widget.agentId);
      await context.dispatchAndWait(ensure);
      final thread = ensure.threadId;
      if (!mounted) return;
      if (thread == null || ensure.status.originalError != null) {
        showErrorToast(
          context,
          ensure.status.originalError ?? 'request_failed',
        );
        return;
      }
      context.dispatch(
        SendMessageAction(thread, {
          'content': l10n.t('ag_rememberMessage', [text]),
          'attachment_ids': <String>[],
        }),
      );
      _text.clear();
      FocusManager.instance.primaryFocus?.unfocus();
      LnToast.show(
        context,
        l10n.t('ag_rememberSent', [isolate(widget.agentName)]),
        kind: LnToastKind.positive,
      );
    } catch (error) {
      if (error is! SessionRequestCancelled && mounted) {
        showErrorToast(context, error);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final ambient = Directionality.of(context);
    final ready = _text.text.trim().isNotEmpty && !_busy;
    final keyboard = MediaQuery.viewInsetsOf(context).bottom > 0;
    return Padding(
      padding: EdgeInsets.fromLTRB(
        LnSpace.pageGutter,
        LnSpace.sm,
        LnSpace.pageGutter,
        keyboard
            ? LnSpace.xs
            : LnSpace.sm + MediaQuery.viewPaddingOf(context).bottom,
      ),
      child: Container(
        height: RememberField.height,
        padding: const EdgeInsetsDirectional.only(start: 20, end: 4),
        decoration: ShapeDecoration(
          color: c.editorCard,
          shape: const StadiumBorder(),
        ),
        child: Row(
          children: [
            Expanded(
              child: Material(
                type: MaterialType.transparency,
                child: TextField(
                  controller: _text,
                  enabled: !_busy,
                  maxLines: 1,
                  textCapitalization: TextCapitalization.sentences,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _send(),
                  textDirection: textDirectionFor(_text.text, ambient),
                  style: ln.text.body.copyWith(color: c.fg),
                  cursorColor: c.brand,
                  decoration: InputDecoration(
                    isCollapsed: true,
                    filled: false,
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.symmetric(
                      vertical: (RememberField.height - 24) / 2,
                    ),
                    hintText: l10n.t('ag_rememberHint', [
                      isolate(widget.agentName),
                    ]),
                    hintStyle: ln.text.body.copyWith(color: c.fgSubtle),
                  ),
                ),
              ),
            ),
            LnTappable(
              onTap: ready ? _send : null,
              haptic: true,
              semanticLabel: l10n.t('send'),
              excludeChildSemantics: true,
              child: SizedBox.square(
                dimension: LnSize.minTouch,
                child: Center(
                  child: AnimatedContainer(
                    duration: LnMotion.fast,
                    width: RememberField.disc,
                    height: RememberField.disc,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: ready ? c.sendDisc : c.sendDisabledDisc,
                      shape: BoxShape.circle,
                    ),
                    child: _busy
                        ? const LnSpinner(size: 18)
                        : Icon(
                            FIcons.arrowUp,
                            size: LnSize.chromeIcon,
                            color: ready ? c.sendArrow : c.sendDisabledArrow,
                          ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
