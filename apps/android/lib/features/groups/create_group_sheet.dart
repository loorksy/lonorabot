// «مجموعة جديدة» in a stacked sheet, and the same form as the /groups/new page (deep links):
// ✕, the title and an «إنشاء» pill in the header; the member field (the picked agents as chips
// with ✕, the search typed after them, the «2/12» count at its end); the agents as check rows;
// then Lonora's own details: the name (drafted from the picked agents until the owner types one,
// ≤ 80), the purpose (≤ 160) and the coordinator (a member; the first picked by default).
// «إنشاء» sends `POST /groups/create` (apps/mobile/app/new-group.tsx, Lonora Web's NewGroupPage)
// and the group's conversation opens. Leaving with edits asks first.
import 'dart:math' as math;

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart'
    show InputBorder, InputDecoration, Material, MaterialType, TextField;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/app_state.dart';
import '../agents/profile/agent_strings.dart';
import '../chats/chat_rows.dart';
import '../chats/chats_strings.dart';
import 'form_sheet.dart';
import 'group_actions.dart';
import 'leave_guard.dart';
import 'member_picker.dart';

/// Opens the create-group sheet over [context]'s root navigator, with [memberIds] picked
/// («مجموعة من المحددين»). On success the sheet closes and the group's conversation opens.
Future<void> showCreateGroupSheet(
  BuildContext context, {
  List<String> memberIds = const [],
}) async {
  registerChatsStrings();
  registerAgentStrings(context.l10n);
  final dirty = ValueNotifier(false);
  try {
    await showFormSheet<void>(
      context,
      dirty: dirty,
      showHandle: true,
      builder: (_) =>
          NewGroupForm(memberIds: memberIds, dirty: dirty, inSheet: true),
    );
  } finally {
    dirty.dispose();
  }
}

/// The new-group form: in the stacked sheet ([inSheet]) or on the /groups/new page.
class NewGroupForm extends StatefulWidget {
  const NewGroupForm({
    super.key,
    required this.memberIds,
    this.dirty,
    this.inSheet = false,
  });

  final List<String> memberIds;

  /// Set while the form holds edits or is creating the group (it turns the sheet's
  /// drag-to-close off).
  final ValueNotifier<bool>? dirty;

  /// In a stacked sheet: success closes it first, and the list scrolls with the sheet's drag.
  final bool inSheet;

  @override
  State<NewGroupForm> createState() => _NewGroupFormState();
}

class _NewGroupFormState extends State<NewGroupForm> {
  final _name = TextEditingController();
  final _purpose = TextEditingController();
  final _query = TextEditingController();
  late List<String> _members;
  String? _lead;
  bool _busy = false;
  String? _error;

  /// The owner typed a name: picks no longer redraft it.
  bool _nameTouched = false;

  /// What the form opened with («مجموعة من المحددين» drafts it): leaving it unchanged asks
  /// nothing.
  late final String _initialName;
  late final List<String> _initialMembers;

  @override
  void initState() {
    super.initState();
    final agents = context.read().shell.agents;
    _members = widget.memberIds
        .where(agents.containsKey)
        .take(groupMemberLimit)
        .toList();
    _lead = _members.firstOrNull;
    _draftName(agents);
    _initialName = _name.text;
    _initialMembers = [..._members];
    for (final c in [_name, _purpose, _query]) {
      c.addListener(_changed);
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _purpose.dispose();
    _query.dispose();
    super.dispose();
  }

  bool get _dirty =>
      _name.text != _initialName ||
      _purpose.text.isNotEmpty ||
      _members.join(',') != _initialMembers.join(',') ||
      (_members.isNotEmpty && _lead != _members.first);

  bool get _valid => _name.text.trim().isNotEmpty && _members.isNotEmpty;

  void _changed() {
    _syncDirty();
    if (mounted) setState(() {});
  }

  /// A drag would drop the edits, or close the sheet while the group is being created.
  void _syncDirty() => widget.dirty?.value = _dirty || _busy;

  /// The name from the picked agents, in the app's language (initState cannot depend on the
  /// tree's Localizations), until the owner types one.
  void _draftName(Map<String, Agent> agents) {
    if (_nameTouched) return;
    _name.text = _members.isEmpty
        ? ''
        : groupDraftName([
            for (final id in _members) agents[id]?.name ?? '',
          ], L10n.instance.lang);
  }

  void _setMembers(List<String> ids) {
    setState(() {
      _members = ids;
      if (_lead == null || !ids.contains(_lead)) _lead = ids.firstOrNull;
      _draftName(context.read().shell.agents);
    });
    _changed();
  }

  Future<void> _create() async {
    if (!_valid || _busy) return;
    FocusManager.instance.primaryFocus?.unfocus();
    final lead = _lead != null && _members.contains(_lead)
        ? _lead
        : _members.first;
    setState(() => (_busy = true, _error = null));
    _syncDirty();
    final router = GoRouter.of(context);
    final navigator = Navigator.of(context);
    final action = CreateGroupAction(
      name: _name.text,
      purpose: _purpose.text,
      memberIds: _members,
      leadAgentId: lead,
    );
    await context.dispatchAndWait(action);
    if (!mounted) return;
    final failure = action.failure;
    final thread = action.threadId;
    if (failure != null || thread == null || thread.isEmpty) {
      setState(() {
        _busy = false;
        _error = context.l10n.errorText(
          failure is ApiError ? failure.code : null,
        );
      });
      _syncDirty();
      return;
    }
    if (widget.inSheet) navigator.pop();
    router.go(Routes.thread(thread));
  }

  Future<void> _chooseLead(Map<String, Agent> agents) async {
    HapticFeedback.selectionClick();
    await showLnActionMenu<void>(
      context,
      title: context.t('groups_coordinator'),
      actions: [
        for (final id in _members)
          if (agents[id] != null)
            LnMenuAction(
              label: agents[id]!.name,
              icon: id == _lead ? FIcons.check : null,
              onSelected: () {
                setState(() => _lead = id);
                _changed();
              },
            ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    registerChatsStrings();
    registerAgentStrings(context.l10n);
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final shell = context.select((AppState s) => s.shell);
    final candidates = groupCandidates(shell.orderedAgents);
    final lead = _lead != null && _members.contains(_lead) ? _lead : null;
    final leadAgent = lead == null ? null : shell.agents[lead];

    Widget sectionTitle(String text) => Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter,
        LnSpace.xl,
        LnSpace.pageGutter,
        LnSpace.xs,
      ),
      child: Semantics(
        header: true,
        child: Text(text, style: ln.text.body.copyWith(color: c.fgMuted)),
      ),
    );

    final list = ListView(
      controller: widget.inSheet
          ? LnStackedSheet.scrollControllerOf(context)
          : null,
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      // A sheet does not shrink for the keyboard: its height is room to scroll.
      padding: EdgeInsets.only(
        top: LnSpace.sm,
        bottom:
            LnSpace.xl +
            math.max(
              MediaQuery.viewPaddingOf(context).bottom,
              MediaQuery.viewInsetsOf(context).bottom,
            ),
      ),
      children: [
        if (_error != null)
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(
              LnSpace.pageGutter,
              0,
              LnSpace.pageGutter,
              LnSpace.xs,
            ),
            child: Semantics(
              liveRegion: true,
              child: Text(
                _error!,
                style: ln.text.caption.copyWith(color: c.error),
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
          child: MemberField(
            members: [
              for (final id in _members)
                if (shell.agents[id] != null) shell.agents[id]!,
            ],
            query: _query,
            hint: l10n.t('ag_searchAgents'),
            count: '${_members.length}/$groupMemberLimit',
            enabled: !_busy,
            onRemove: (id) =>
                _setMembers(_members.where((m) => m != id).toList()),
          ),
        ),
        const SizedBox(height: LnSpace.xs),
        if (shell.agents.isEmpty && !shell.loaded && shell.lastError != null)
          ErrorState(
            title: l10n.errorText(shell.lastError),
            retryLabel: l10n.t('sh_retry'),
            onRetry: () => context.dispatch(RefreshShellAction(silent: false)),
          )
        else if (shell.agents.isEmpty && !shell.loaded)
          SkeletonRows(
            count: 3,
            animate: !(MediaQuery.maybeDisableAnimationsOf(context) ?? false),
            semanticLabel: context.t('sh_loading'),
          )
        else
          MemberPicker(
            agents: candidates,
            selected: _members,
            query: _query.text,
            enabled: !_busy,
            onChanged: _setMembers,
          ),
        if (_members.isEmpty)
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(
              LnSpace.pageGutter,
              LnSpace.xs,
              LnSpace.pageGutter,
              0,
            ),
            child: Text(
              l10n.t('chooseMembers'),
              style: ln.text.caption.copyWith(color: c.fgMuted),
            ),
          ),
        sectionTitle(l10n.t('details')),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
          child: StadiumField(
            controller: _name,
            hint: l10n.t('name'),
            enabled: !_busy,
            maxLength: 80,
            textInputAction: TextInputAction.next,
            onChanged: (_) => _nameTouched = true,
          ),
        ),
        const SizedBox(height: LnSpace.sm),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
          child: StadiumField(
            controller: _purpose,
            hint: l10n.t('skillsPurpose'),
            enabled: !_busy,
            maxLength: 160,
          ),
        ),
        if (leadAgent != null) ...[
          const SizedBox(height: LnSpace.xs),
          _CoordinatorRow(
            agent: leadAgent,
            enabled: !_busy && _members.length > 1,
            onTap: () => _chooseLead(shell.agents),
          ),
        ],
      ],
    );

    return LeaveGuard(
      dirty: _dirty,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          LnSheetHeader(
            title: l10n.t('newGroup'),
            closeLabel: l10n.t('close'),
            action: _busy
                ? const SizedBox.square(
                    dimension: LnSize.minTouch,
                    child: Center(child: LnSpinner(size: 18)),
                  )
                : HeaderPillButton(
                    label: l10n.t('create'),
                    onPressed: _valid ? _create : null,
                  ),
          ),
          Expanded(child: list),
        ],
      ),
    );
  }
}

/// The member field: the picked agents as chips (a tap on one removes it) followed by the search
/// typed after them, on a 52 dp rounded field; the [count] («2/12») at its end.
class MemberField extends StatelessWidget {
  const MemberField({
    super.key,
    required this.members,
    required this.query,
    required this.hint,
    required this.count,
    required this.onRemove,
    this.enabled = true,
  });

  final List<Agent> members;
  final TextEditingController query;
  final String hint;
  final String count;
  final ValueChanged<String> onRemove;
  final bool enabled;

  /// The field's least height, and its corner radius.
  static const double minHeight = 52;
  static const double radius = 26;

  /// The search's width after chips (it shares the last chip row when there is room).
  static const double queryMinWidth = 72;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final ambient = Directionality.of(context);
    return Container(
      constraints: const BoxConstraints(minHeight: minHeight),
      padding: const EdgeInsetsDirectional.fromSTEB(LnSpace.md, 2, 14, 2),
      decoration: BoxDecoration(
        color: c.fill1,
        borderRadius: const BorderRadius.all(Radius.circular(radius)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) => Wrap(
                spacing: LnSpace.xs,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  for (final agent in members)
                    MemberChip(
                      agent: agent,
                      enabled: enabled,
                      onRemove: () => onRemove(agent.id),
                    ),
                  SizedBox(
                    width: members.isEmpty
                        ? constraints.maxWidth
                        : math.min(queryMinWidth, constraints.maxWidth),
                    height: LnSize.minTouch,
                    child: Center(
                      child: Material(
                        type: MaterialType.transparency,
                        child: ValueListenableBuilder<TextEditingValue>(
                          valueListenable: query,
                          builder: (context, value, _) => TextField(
                            controller: query,
                            enabled: enabled,
                            maxLines: 1,
                            textInputAction: TextInputAction.search,
                            textDirection: textDirectionFor(
                              value.text,
                              ambient,
                            ),
                            style: ln.text.body.copyWith(color: c.fg),
                            cursorColor: c.brand,
                            // After chips the hint is not drawn, but it still
                            // names the field for screen readers.
                            decoration: InputDecoration(
                              isCollapsed: true,
                              filled: false,
                              border: InputBorder.none,
                              contentPadding: const EdgeInsets.symmetric(
                                vertical: (LnSize.minTouch - 24) / 2,
                              ),
                              hintText: hint,
                              hintStyle: ln.text.body.copyWith(
                                color: members.isEmpty
                                    ? c.fgSubtle
                                    : const Color(0x00000000),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          SizedBox(
            height: LnSize.minTouch,
            child: Center(
              child: Text(
                count,
                style: ln.text.caption.copyWith(color: c.fgMuted),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// A picked agent in [MemberField]: a 32 dp chip (radius 8) with its 20 dp avatar, its name and a
/// ✕, in a 48 dp touch band; a tap removes it.
class MemberChip extends StatelessWidget {
  const MemberChip({
    super.key,
    required this.agent,
    required this.onRemove,
    this.enabled = true,
  });

  final Agent agent;
  final VoidCallback onRemove;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: enabled ? onRemove : null,
      semanticLabel: context.t('ag_removeMember', [agent.name]),
      excludeChildSemantics: true,
      child: SizedBox(
        height: LnSize.minTouch,
        child: Center(
          widthFactor: 1,
          child: Container(
            height: LnSize.chipHeight,
            padding: const EdgeInsetsDirectional.fromSTEB(6, 0, 8, 0),
            decoration: BoxDecoration(
              color: c.fill3,
              borderRadius: const BorderRadius.all(Radius.circular(8)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                memberAvatar(agent, 20),
                const SizedBox(width: 6),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 140),
                  child: Text(
                    agent.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: ln.text.body.copyWith(color: c.fgMuted),
                  ),
                ),
                const SizedBox(width: 6),
                Icon(FIcons.x, size: 18, color: c.fgMuted),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The coordinator: the lead's avatar and name, «المنسق», and the up-down chevrons that open the
/// members to choose from.
class _CoordinatorRow extends StatelessWidget {
  const _CoordinatorRow({
    required this.agent,
    required this.enabled,
    required this.onTap,
  });

  final Agent agent;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final title = context.t('groups_coordinator');
    return LnTappable(
      onTap: enabled ? onTap : null,
      semanticLabel: '$title, ${agent.name}',
      excludeChildSemantics: true,
      child: Opacity(
        opacity: enabled ? 1 : LnPalette.disabledOpacity,
        child: SizedBox(
          height: MemberPicker.rowHeight,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
            child: Row(
              children: [
                memberAvatar(agent, 40),
                const SizedBox(width: MemberPicker.textGap),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        agent.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: ln.text.body.copyWith(color: c.fgWarm),
                      ),
                      Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: ln.text.caption.copyWith(color: c.fgMuted),
                      ),
                    ],
                  ),
                ),
                Icon(FIcons.chevronsUpDown, size: 18, color: c.fgMuted),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
