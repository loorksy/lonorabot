// «المهارات» (/agent/:id/skills): one agent's current skill catalog, composed from the kit.
// Capabilities follow Lonora's other clients (apps/mobile/app/skills.tsx, apps/web
// SkillsPages.tsx): the catalog with source and availability (paged by 50), enable / disable of the
// owner's installed skills, details with edit, version history and restore, add a skill, block an
// exact version (permanent, confirmed), delete (confirmed) and the list of blocked versions. Skills
// never grant trading authority.
import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../agents/profile/agent_page.dart';
import '../agents/profile/agent_strings.dart';
import '../settings/settings_common.dart';
import 'skill_sheets.dart';
import 'skills_data.dart';
import 'skills_strings.dart';

class SkillsScreen extends StatefulWidget {
  const SkillsScreen({super.key, required this.agentId});
  final String agentId;

  @override
  State<SkillsScreen> createState() => _SkillsScreenState();
}

class _SkillsScreenState extends State<SkillsScreen> {
  List<SkillEntry>? _items;
  int? _next;
  SkillControls? _controls;
  Map<String, SkillResource> _installed = const {};
  Object? _error;
  bool _loadingMore = false;
  final Set<String> _switching = {};

  String get _id => widget.agentId;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final results = await Future.wait<Object>([
        fetchSkillCatalog(_id),
        fetchSkillControls(_id),
        fetchInstalledSkills(_id),
      ]);
      if (!mounted) return;
      final page = results[0] as SkillCatalogPage;
      setState(() {
        _items = page.items;
        _next = page.nextOffset;
        _controls = results[1] as SkillControls;
        _installed = {
          for (final r in results[2] as List<SkillResource>) r.id: r,
        };
        _error = null;
      });
    } catch (error) {
      if (error is! SessionRequestCancelled && mounted) {
        setState(() => _error = error);
      }
    }
  }

  Future<void> _more() async {
    final next = _next;
    if (next == null || _loadingMore) return;
    setState(() => _loadingMore = true);
    try {
      final page = await fetchSkillCatalog(_id, offset: next);
      if (!mounted) return;
      final known = {for (final i in _items ?? const <SkillEntry>[]) i.id};
      setState(() {
        _items = [
          ...?_items,
          for (final i in page.items)
            if (!known.contains(i.id)) i,
        ];
        _next = page.nextOffset;
      });
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _loadingMore = false);
    }
  }

  Future<void> _toggle(SkillResource skill, bool enabled) async {
    HapticFeedback.selectionClick();
    setState(() => _switching.add(skill.id));
    try {
      final saved = await saveSkill(skill, {
        ...skill.payload,
        'enabled': enabled,
      });
      if (!mounted) return;
      setState(() => _installed = {..._installed, saved.id: saved});
      LnToast.show(
        context,
        context.t(enabled ? 'sk_enabled' : 'sk_disabled'),
        kind: LnToastKind.positive,
      );
      unawaited(_load());
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _switching.remove(skill.id));
    }
  }

  Future<void> _open(SkillEntry entry) async {
    final controls = _controls;
    if (controls == null) return;
    final changed = await showLnSheet<bool>(
      context,
      maxHeightFraction: 0.94,
      title: context.t('skillsDetails'),
      // An editable skill closes only by Close or back, which confirm unsaved edits.
      isDismissible: !entry.editable,
      enableDrag: !entry.editable,
      builder: (_) =>
          SkillDetailsSheet(agentId: _id, entry: entry, controls: controls),
    );
    if (changed == true) await _load();
  }

  Future<void> _create() async {
    final created = await showLnSheet<bool>(
      context,
      maxHeightFraction: 0.94,
      title: context.t('skillsAdd'),
      builder: (_) => SkillCreateSheet(agentId: _id),
    );
    if (created == true) await _load();
  }

  /// «+»: add a skill by hand, or import one from a .md, .txt or .json file.
  Future<void> _add() async {
    final l10n = context.l10n;
    await showLnActionMenu<void>(
      context,
      actions: [
        LnMenuAction(
          label: l10n.t('skillsAdd'),
          icon: FIcons.plus,
          onSelected: _create,
        ),
        LnMenuAction(
          label: l10n.t('sk_import'),
          icon: FIcons.fileUp,
          onSelected: _import,
        ),
      ],
    );
  }

  Future<void> _import() async {
    final picked = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['md', 'txt', 'json'],
    );
    final file = picked.firstOrNull;
    final path = file?.path;
    if (file == null || path == null || !mounted) return;
    final l10n = context.l10n;
    try {
      if (await File(path).length() > maxSkillImportBytes) {
        if (mounted) {
          LnToast.show(
            context,
            l10n.t('sk_importTooLarge'),
            kind: LnToastKind.notice,
          );
        }
        return;
      }
      final text = await File(path).readAsString();
      await createSkill(
        _id,
        importedSkillPayload(
          file.name,
          text,
          fallbackDescription: l10n.t('sk_importedDescription'),
        ),
      );
      if (!mounted) return;
      LnToast.show(context, l10n.t('sk_imported'), kind: LnToastKind.positive);
      await _load();
    } on FileSystemException {
      if (mounted) showErrorToast(context, 'request_failed');
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    }
  }

  Future<void> _blockOther() async {
    final controls = _controls;
    if (controls == null) return;
    final blocked = await showLnSheet<bool>(
      context,
      title: context.t('skillsBlockOther'),
      builder: (_) => ExactBlockSheet(agentId: _id, controls: controls),
    );
    if (blocked == true) await _load();
  }

  String _availability(L10n l10n, SkillEntry e) {
    final source = l10n.t(switch (e.source) {
      'builtin' => 'skillsBuiltin',
      'legacy' => 'skillsLegacy',
      _ => 'skillsOwner',
    });
    final state = l10n.t(e.available ? 'skillsAvailable' : 'skillsUnavailable');
    final code = e.code;
    final reason = code == null
        ? null
        : l10n.t(
            skillAvailabilityCodes.contains(code) ? code : 'skillsUnavailable',
          );
    return [
      '$source · $state',
      if (e.description.isNotEmpty) isolate(e.description),
      ?reason,
    ].join('\n');
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    registerAgentStrings(l10n);
    registerSkillsStrings(l10n);
    final ln = context.ln;
    final agentName = context.select((AppState s) => s.shell.agents[_id]?.name);
    final items = _items;
    final controls = _controls;
    Widget body;
    if (items == null || controls == null) {
      final error = _error;
      body = error == null
          ? const SettingsSkeleton(groups: [5, 1])
          : error is ApiError && error.isNotFound
          ? EmptyState(icon: FIcons.userX, title: l10n.t('agentMissing'))
          : LoadFailure(error: error, onRetry: _load);
    } else {
      final muted = ln.text.footnote.copyWith(color: ln.colors.fgMuted);
      body = LnRefresh(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(bottom: pageBottomPadding(context)),
          children: [
            SettingsNote(l10n.t('skillsCatalogHint')),
            if (items.isEmpty)
              EmptyState(icon: FIcons.layers, title: l10n.t('skillsNone'))
            else
              LnSection(
                title: l10n.t('skillsCurrentCatalog'),
                children: [
                  for (final e in items)
                    WrapTile(
                      icon: e.available ? FIcons.layers : FIcons.circleOff,
                      title: isolate(e.title),
                      subtitle: _availability(l10n, e),
                      trailing: switch (_installed[e.resourceId]) {
                        final r? when e.editable => LnSwitch(
                          value: r.enabled,
                          // Each switch names its skill for a screen reader.
                          semanticLabel:
                              '${l10n.t('skillsEnabled')} · ${e.title}',
                          onChanged: _switching.contains(r.id)
                              ? null
                              : (v) => _toggle(r, v),
                        ),
                        _ => Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(ltr(e.version ?? '—'), style: muted),
                            const TileChevron(),
                          ],
                        ),
                      },
                      onTap: () => _open(e),
                    ),
                ],
              ),
            if (_next != null)
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(
                  LnSpace.pageGutter,
                  LnSpace.sm,
                  LnSpace.pageGutter,
                  0,
                ),
                child: BlockButton(
                  label: l10n.t('skillsMore'),
                  variant: BlockButtonVariant.secondary,
                  loading: _loadingMore,
                  onPressed: _more,
                ),
              ),
            const SectionGap(),
            LnSection(
              title: l10n.t('skillsRevocations'),
              children: [
                if (controls.revoked.isEmpty)
                  WrapTile(
                    icon: FIcons.shieldCheck,
                    title: l10n.t('skillsNoRevocations'),
                  )
                else
                  for (final r in controls.revoked)
                    WrapTile(
                      icon: FIcons.ban,
                      title: skillCoordinates(r.skillId, r.version),
                      subtitle: [
                        l10n.t(
                          skillBlockReasons[r.reason] ?? 'skillsReasonOwner',
                        ),
                        if (r.revokedAt != null)
                          formatDate('d MMM y HH:mm', l10n.lang, r.revokedAt!),
                      ].join(dotSeparator),
                    ),
                WrapTile(
                  icon: FIcons.ban,
                  title: l10n.t('skillsBlockOther'),
                  trailing: const TileChevron(),
                  onTap: _blockOther,
                ),
              ],
            ),
          ],
        ),
      );
    }
    return AgentPage(
      title: agentName == null
          ? l10n.t('skills')
          : '${l10n.t('skills')} · ${isolate(agentName)}',
      fallback: Routes.agent(_id),
      trailing: CircleIconButton(
        icon: const Icon(FIcons.plus),
        semanticLabel: l10n.t('skillsAdd'),
        onTap: items == null ? null : _add,
      ),
      body: body,
    );
  }
}
