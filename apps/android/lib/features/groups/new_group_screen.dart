// «مجموعة جديدة» (name field, member rows with check circles, member search and limit, a Create
// stadium; Lonora's fields from apps/mobile/app/new-group.tsx and Lonora Web's NewGroupPage): name
// (≤ 80), purpose (≤ 160), members (at least one), the coordinator (a member; the first chosen by
// default), then `POST /groups/create` and the group's conversation opens. Leaving with edits asks
// first.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/app_state.dart';
import '../chats/chat_rows.dart';
import '../chats/chat_widgets.dart';
import '../chats/chats_strings.dart';
import 'group_actions.dart';
import 'leave_guard.dart';
import 'member_picker.dart';

class NewGroupScreen extends StatefulWidget {
  const NewGroupScreen({super.key, required this.memberIds});
  final List<String> memberIds;

  @override
  State<NewGroupScreen> createState() => _NewGroupScreenState();
}

class _NewGroupScreenState extends State<NewGroupScreen> {
  final _name = TextEditingController();
  final _purpose = TextEditingController();
  final _query = TextEditingController();
  late List<String> _members;
  String? _lead;
  bool _busy = false;
  String? _error;

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
    // «مجموعة من المحددين» arrives with the picked agents: the name is drafted from them, in the
    // app's language (initState cannot depend on the tree's Localizations).
    if (_members.isNotEmpty) {
      _name.text = groupDraftName([
        for (final id in _members) agents[id]!.name,
      ], L10n.instance.lang);
      _lead = _members.first;
    }
    _initialName = _name.text;
    _initialMembers = [..._members];
  }

  bool get _dirty =>
      _name.text != _initialName ||
      _purpose.text.isNotEmpty ||
      _members.join(',') != _initialMembers.join(',') ||
      (_members.isNotEmpty && _lead != _members.first);

  @override
  void dispose() {
    _name.dispose();
    _purpose.dispose();
    _query.dispose();
    super.dispose();
  }

  bool get _valid => _name.text.trim().isNotEmpty && _members.isNotEmpty;

  Future<void> _create() async {
    if (!_valid || _busy) return;
    final lead = _lead != null && _members.contains(_lead)
        ? _lead
        : _members.first;
    setState(() {
      _busy = true;
      _error = null;
    });
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
      return;
    }
    context.go(Routes.thread(thread));
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
              onSelected: () => setState(() => _lead = id),
            ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    registerChatsStrings();
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final shell = context.select((AppState s) => s.shell);
    final candidates = groupCandidates(shell.orderedAgents);
    final lead = _lead != null && _members.contains(_lead)
        ? _lead
        : (_members.isEmpty ? null : _members.first);
    final insets = MediaQuery.viewInsetsOf(context).bottom;
    final bottomPad = insets > 0
        ? insets
        : MediaQuery.viewPaddingOf(context).bottom;

    Widget sectionTitle(String text, {String? trailing}) => Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter,
        20,
        LnSpace.pageGutter,
        6,
      ),
      child: Row(
        children: [
          Expanded(
            child: Semantics(
              header: true,
              child: Text(
                text,
                style: ln.text.captionStrong.copyWith(color: c.fgMuted),
              ),
            ),
          ),
          if (trailing != null)
            Text(trailing, style: ln.text.caption.copyWith(color: c.fgMuted)),
        ],
      ),
    );

    final form = ListView(
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      padding: EdgeInsets.only(
        top: ScreenHeader.heightOf(context) + 12,
        bottom: 16,
      ),
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
          child: LnTextField(
            controller: _name,
            label: l10n.t('name'),
            autofocus: _members.isEmpty,
            enabled: !_busy,
            textInputAction: TextInputAction.next,
            inputFormatters: [LengthLimitingTextInputFormatter(80)],
            onChanged: (_) => setState(() {}),
          ),
        ),
        const SizedBox(height: 12),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
          child: LnTextField(
            controller: _purpose,
            label: l10n.t('skillsPurpose'),
            enabled: !_busy,
            inputFormatters: [LengthLimitingTextInputFormatter(160)],
            onChanged: (_) => setState(() {}),
          ),
        ),
        sectionTitle(
          l10n.t('members'),
          trailing: '${_members.length}/$groupMemberLimit',
        ),
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.pageGutter,
            0,
            LnSpace.pageGutter,
            6,
          ),
          child: SearchPill(
            controller: _query,
            hint: l10n.t('sh_search'),
            height: 40,
            onChanged: (_) => setState(() {}),
          ),
        ),
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
            onChanged: (ids) => setState(() {
              _members = ids;
              if (_lead == null || !ids.contains(_lead)) {
                _lead = ids.isEmpty ? null : ids.first;
              }
            }),
          ),
        if (_members.isEmpty)
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(
              LnSpace.pageGutter,
              8,
              LnSpace.pageGutter,
              0,
            ),
            child: Text(
              l10n.t('chooseMembers'),
              style: ln.text.caption.copyWith(color: c.fgMuted),
            ),
          ),
        if (lead != null && shell.agents[lead] != null) ...[
          sectionTitle(l10n.t('groups_coordinator')),
          PickRow(
            avatar: ChatRowAvatar(
              row: ChatRow(
                key: rowKey(ChatRowKind.agent, lead),
                kind: ChatRowKind.agent,
                id: lead,
                agent: shell.agents[lead],
                name: shell.agents[lead]!.name,
              ),
              agents: const {},
              size: 40,
            ),
            title: shell.agents[lead]!.name,
            subtitle: l10n.t('groups_coordinator'),
            trailing: Icon(FIcons.chevronsUpDown, size: 18, color: c.fgMuted),
            enabled: !_busy && _members.length > 1,
            onTap: () => _chooseLead(shell.agents),
          ),
        ],
      ],
    );

    return LeaveGuard(
      dirty: _dirty,
      child: ColoredBox(
        color: c.bg,
        child: Column(
          children: [
            Expanded(
              child: Stack(
                children: [
                  Positioned.fill(child: form),
                  Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    child: PageHeader(title: l10n.t('newGroup'), close: true),
                  ),
                ],
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(
                  LnSpace.pageGutter,
                  8,
                  LnSpace.pageGutter,
                  0,
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
              padding: EdgeInsets.fromLTRB(
                LnSpace.pageGutter,
                8,
                LnSpace.pageGutter,
                bottomPad + 12,
              ),
              child: BlockButton(
                label: l10n.t('create'),
                loading: _busy,
                onPressed: _valid && !_busy ? _create : null,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
