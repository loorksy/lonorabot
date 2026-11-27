// «إعدادات المجموعة» (composed from the kit; Lonora's content from
// apps/mobile/app/group-settings.tsx and Lonora Web's GroupPage): the members' cluster, name and
// purpose, the members (the coordinator first, «المنسق»), «إضافة وكيل», removing a member, the
// coordinator, the read-only participation, «فتح محادثة المجموعة». Saved with
// `PUT /groups/{id} {payload, version}`; a newer version (a 409 `version_conflict`, or the shell's
// refresh) is adopted while the fields the owner edited keep their edits. Leaving with unsaved
// edits asks first. A group has no avatar of its own (its members' faces are its avatar) and is
// never deleted or left from a client (Q1, Q44).
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../app/services.dart';
import '../../avatar/avatar.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../chats/chat_commands.dart';
import '../chats/chat_rows.dart';
import '../chats/chat_text.dart';
import '../chats/chat_widgets.dart';
import '../chats/chats_actions.dart';
import '../chats/chats_strings.dart';
import 'group_actions.dart';
import 'leave_guard.dart';
import 'member_picker.dart';

class GroupSettingsScreen extends StatefulWidget {
  const GroupSettingsScreen({super.key, required this.groupId});
  final String groupId;

  @override
  State<GroupSettingsScreen> createState() => _GroupSettingsScreenState();
}

class _GroupSettingsScreenState extends State<GroupSettingsScreen> {
  final _name = TextEditingController();
  final _purpose = TextEditingController();
  Group? _group;
  List<String> _members = const [];
  String? _lead;
  String? _loadError;
  bool _saving = false;
  bool _opening = false;
  bool _adopting = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _name.dispose();
    _purpose.dispose();
    super.dispose();
  }

  Json get _payload => asJson(_group?.raw['payload']);

  Future<void> _load() async {
    setState(() => _loadError = null);
    try {
      final group = Group.fromJson(
        asJson(await api.get('/groups/${Uri.encodeComponent(widget.groupId)}')),
      );
      if (!mounted) return;
      _apply(group);
    } on SessionRequestCancelled {
      return;
    } on ApiError catch (e) {
      if (mounted) {
        setState(() => _loadError = e.isNotFound ? 'group_not_found' : e.code);
      }
    }
  }

  void _apply(Group group) => setState(() {
    _group = group;
    _name.text = group.name;
    _purpose.text = groupPurpose(group);
    _members = [...group.memberIds];
    _lead = group.leadAgentId;
  });

  /// A newer version of the group (saved elsewhere): what the owner edited keeps the edit, the
  /// rest takes the newer values, and the next save carries the newer version.
  void _adopt(Group fresh) {
    final base = _group;
    if (base == null) return _apply(fresh);
    final name = _name.text.trim() != base.name ? _name.text : fresh.name;
    final purpose = _purpose.text.trim() != groupPurpose(base)
        ? _purpose.text
        : groupPurpose(fresh);
    final members = _members.join(',') != base.memberIds.join(',')
        ? _members
        : [...fresh.memberIds];
    final lead = _lead != base.leadAgentId ? _lead : fresh.leadAgentId;
    setState(() {
      _group = fresh;
      if (_name.text != name) _name.text = name;
      if (_purpose.text != purpose) _purpose.text = purpose;
      _members = members;
      _lead = lead;
    });
  }

  Future<void> _reload() async {
    try {
      final fresh = Group.fromJson(
        asJson(await api.get('/groups/${Uri.encodeComponent(widget.groupId)}')),
      );
      if (mounted) _adopt(fresh);
    } on SessionRequestCancelled {
      return;
    } on ApiError {
      // The next save reports what is wrong.
    }
  }

  bool get _dirty {
    final g = _group;
    if (g == null) return false;
    return _name.text.trim() != g.name ||
        _purpose.text.trim() != groupPurpose(g) ||
        _members.join(',') != g.memberIds.join(',') ||
        _lead != g.leadAgentId;
  }

  bool get _valid => _name.text.trim().isNotEmpty && _members.isNotEmpty;

  Future<void> _save() async {
    final group = _group;
    if (group == null || !_valid || _saving) return;
    setState(() => _saving = true);
    final lead = _lead != null && _members.contains(_lead) ? _lead : null;
    final payload = <String, dynamic>{
      ..._payload,
      'name': _name.text.trim(),
      'purpose': _purpose.text.trim(),
      'member_ids': _members,
      'lead_agent_id': lead,
    };
    final action = UpdateGroupAction(group, payload);
    final ok = await runChatsAction(context, action);
    if (!mounted) return;
    setState(() => _saving = false);
    final saved = action.saved;
    if (ok && saved != null) {
      _apply(saved);
      LnToast.show(context, context.t('saved'), kind: LnToastKind.positive);
    }
    final failure = action.failure;
    // Changed elsewhere (said by the toast): take the newer version, keep the edits.
    if (failure is ApiError && failure.code == 'version_conflict') {
      await _reload();
    }
  }

  Future<void> _openChat() async {
    // Opening the chat replaces this page: unsaved edits are asked about first.
    if (_dirty && !await confirmLeaveEdits(context)) return;
    if (!mounted) return;
    setState(() => _opening = true);
    final action = OpenGroupThreadAction(widget.groupId);
    final ok = await runChatsAction(context, action);
    if (!mounted) return;
    setState(() => _opening = false);
    final id = action.threadId;
    if (ok && id != null && id.isNotEmpty) context.go(Routes.thread(id));
  }

  Future<void> _addAgents(List<Agent> candidates) async {
    final l10n = context.l10n;
    final outside = candidates.where((a) => !_members.contains(a.id)).toList();
    var picked = <String>[];
    await showLnSheet<void>(
      context,
      title: l10n.t('groups_addAgent'),
      builder: (sheet) => StatefulBuilder(
        builder: (sheet, setSheet) => Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Flexible(
              child: SingleChildScrollView(
                child: MemberPicker(
                  agents: outside,
                  selected: picked,
                  // No cap on an existing group's members (GroupCreate, mandate P1).
                  limit: null,
                  onChanged: (ids) => setSheet(() => picked = ids),
                ),
              ),
            ),
            const SizedBox(height: 12),
            BlockButton(
              label: l10n.t('groups_add'),
              onPressed: picked.isEmpty
                  ? null
                  : () {
                      setState(() => _members = [..._members, ...picked]);
                      Navigator.of(sheet).pop();
                    },
            ),
          ],
        ),
      ),
    );
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
    final agents = context.select((AppState s) => s.shell.agents);
    final shellGroup = context.select(
      (AppState s) => s.shell.groups[widget.groupId],
    );
    final group = _group;
    if (group != null &&
        shellGroup != null &&
        shellGroup.version > group.version &&
        !_saving &&
        !_adopting) {
      _adopting = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _adopting = false;
        final current = _group;
        if (mounted &&
            current != null &&
            shellGroup.version > current.version) {
          _adopt(shellGroup);
        }
      });
    }
    final header = PageHeader(
      title: l10n.t('groupSettings'),
      trailing: group == null
          ? null
          : CircleIconButton(
              icon: _saving
                  ? const LnSpinner(size: 18)
                  : const Icon(FIcons.check),
              semanticLabel: l10n.t('save'),
              iconColor: _dirty && _valid ? c.fg : c.fgSubtle,
              onTap: _dirty && _valid && !_saving ? _save : null,
            ),
    );

    Widget body;
    if (group == null) {
      body = _loadError == null
          ? Padding(
              padding: EdgeInsets.only(top: ScreenHeader.heightOf(context) + 8),
              child: SkeletonRows(
                count: 4,
                animate:
                    !(MediaQuery.maybeDisableAnimationsOf(context) ?? false),
                semanticLabel: context.t('sh_loading'),
              ),
            )
          : ErrorState(
              title: _loadError == 'group_not_found'
                  ? l10n.t('groupMissing')
                  : l10n.errorText(_loadError),
              retryLabel: l10n.t('sh_retry'),
              onRetry: _load,
            );
    } else {
      final ordered = _lead != null && _members.contains(_lead)
          ? [_lead!, ..._members.where((id) => id != _lead)]
          : _members;
      final members = [for (final id in ordered) ?agents[id]];
      Widget sectionTitle(String text) => Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(
          LnSpace.pageGutter,
          20,
          LnSpace.pageGutter,
          6,
        ),
        child: Semantics(
          header: true,
          child: Text(
            text,
            style: ln.text.captionStrong.copyWith(color: c.fgMuted),
          ),
        ),
      );
      Widget agentAvatar(Agent a, double size) => ChatRowAvatar(
        row: ChatRow(
          key: rowKey(ChatRowKind.agent, a.id),
          kind: ChatRowKind.agent,
          id: a.id,
          agent: a,
          name: a.name,
        ),
        agents: const {},
        size: size,
      );
      final candidates = groupCandidates(context.read().shell.orderedAgents);
      final canAdd = candidates.any((a) => !_members.contains(a.id));
      body = ListView(
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        padding: EdgeInsets.only(
          top: ScreenHeader.heightOf(context) + 12,
          bottom: MediaQuery.viewPaddingOf(context).bottom + 32,
        ),
        children: [
          Center(
            child: LonoraGroupAvatar(
              members: [
                for (final a in members)
                  LonoraAvatarMember(
                    agentId: a.id,
                    face: a.avatar,
                    color: a.color,
                    tradesOnItsOwn: a.tradesOnItsOwn,
                  ),
              ],
              size: 72,
              animate: false,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            l10n.agentsWord(_members.length),
            textAlign: TextAlign.center,
            style: ln.text.caption.copyWith(color: c.fgMuted),
          ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
            child: LnTextField(
              controller: _name,
              label: l10n.t('name'),
              enabled: !_saving,
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
              enabled: !_saving,
              inputFormatters: [LengthLimitingTextInputFormatter(160)],
              onChanged: (_) => setState(() {}),
            ),
          ),
          sectionTitle(l10n.t('members')),
          for (final a in members)
            PickRow(
              key: ValueKey('member-${a.id}'),
              avatar: agentAvatar(a, 40),
              title: a.name,
              subtitle: a.id == _lead
                  ? l10n.t('groups_coordinator')
                  : agentRole(l10n, a),
              onTap: () => context.push(Routes.agent(a.id)),
              action: _members.length > 1
                  ? LnTappable(
                      onTap: _saving
                          ? null
                          : () => setState(() {
                              _members = _members
                                  .where((id) => id != a.id)
                                  .toList();
                              if (_lead == a.id) _lead = null;
                            }),
                      semanticLabel: '${l10n.t('groups_remove')}: ${a.name}',
                      child: SizedBox.square(
                        dimension: minTouchTarget,
                        child: Icon(FIcons.userMinus, size: 20, color: c.error),
                      ),
                    )
                  : null,
            ),
          if (canAdd)
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.pageGutter,
                8,
                LnSpace.pageGutter,
                0,
              ),
              child: BlockButton(
                label: l10n.t('groups_addAgent'),
                icon: FIcons.userRoundPlus,
                variant: BlockButtonVariant.secondary,
                onPressed: _saving ? null : () => _addAgents(candidates),
              ),
            ),
          if (_members.length > 1) ...[
            sectionTitle(l10n.t('groups_coordinator')),
            if (_lead != null &&
                _members.contains(_lead) &&
                agents[_lead] != null)
              PickRow(
                avatar: agentAvatar(agents[_lead]!, 40),
                title: agents[_lead]!.name,
                trailing: Icon(
                  FIcons.chevronsUpDown,
                  size: 18,
                  color: c.fgMuted,
                ),
                onTap: () => _chooseLead(agents),
              )
            else
              PickRow(
                avatar: SizedBox.square(
                  dimension: 40,
                  child: Icon(FIcons.crown, size: 20, color: c.fgMuted),
                ),
                title: l10n.t('groups_coordinator'),
                trailing: Icon(
                  FIcons.chevronsUpDown,
                  size: 18,
                  color: c.fgMuted,
                ),
                onTap: () => _chooseLead(agents),
              ),
          ],
          sectionTitle(l10n.t('participation')),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
            child: Text(
              l10n.t('mentionsOrLead'),
              style: ln.text.body.copyWith(color: c.fg),
            ),
          ),
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(
              LnSpace.pageGutter,
              12,
              LnSpace.pageGutter,
              20,
            ),
            child: Text(
              l10n.t('groups_note'),
              style: ln.text.caption.copyWith(color: c.fgMuted),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
            child: BlockButton(
              label: l10n.t('groups_openChat'),
              icon: FIcons.messageCircle,
              loading: _opening,
              onPressed: _opening ? null : _openChat,
            ),
          ),
        ],
      );
    }

    return LeaveGuard(
      dirty: _dirty,
      child: ColoredBox(
        color: c.bg,
        child: Stack(
          children: [
            Positioned.fill(child: body),
            Positioned(top: 0, left: 0, right: 0, child: header),
          ],
        ),
      ),
    );
  }
}
