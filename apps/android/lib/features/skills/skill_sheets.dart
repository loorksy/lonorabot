// The skill sheets: details (facts, instructions, edit/enable/save for the owner's own skills,
// version history and restore, block this exact version, delete), add a skill, and block an
// exact version by identifier. Ports of apps/mobile/components/skills/{skill-details,
// skill-create,exact-version-block}.tsx and apps/web SkillsPages.tsx `useSkillHistory`.
// Composed from the kit.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../agents/profile/agent_page.dart';
import '../agents/settings/avatar_editor.dart' show confirmDiscard;
import '../routines/routines_data.dart' show clock;
import '../settings/settings_common.dart';
import 'skills_data.dart';

/// `id · version`, left to right.
String skillCoordinates(String id, String? version) =>
    ltr('$id · ${version ?? '—'}');

/// Asks for a block reason, then confirms the permanent block. Returns the reason.
Future<String?> askBlockReason(
  BuildContext context,
  String id,
  String version,
) async {
  final l10n = context.l10n;
  var reason = 'owner_revoked';
  final chosen = await showLnSheet<String>(
    context,
    title: l10n.t('skillsBlockConfirm'),
    builder: (sheet) => StatefulBuilder(
      builder: (sheet, setSheet) => SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              skillCoordinates(id, version),
              style: sheet.ln.text.captionStrong,
            ),
            const SizedBox(height: LnSpace.xs),
            Text(
              l10n.t('skillsBlockWarning'),
              style: sheet.ln.text.caption.copyWith(
                color: sheet.ln.colors.fgMuted,
              ),
            ),
            const SizedBox(height: LnSpace.md),
            LnSection(
              padding: EdgeInsets.zero,
              title: l10n.t('skillsBlockReason'),
              children: [
                for (final MapEntry(:key, :value) in skillBlockReasons.entries)
                  ChoiceTile(
                    title: l10n.t(value),
                    selected: reason == key,
                    onSelect: () => setSheet(() => reason = key),
                  ),
              ],
            ),
            const SizedBox(height: LnSpace.lg),
            BlockButton(
              label: l10n.t('skillsBlockVersion'),
              variant: BlockButtonVariant.destructive,
              onPressed: () => Navigator.of(sheet).pop(reason),
            ),
          ],
        ),
      ),
    ),
  );
  if (chosen == null || !context.mounted) return null;
  final ok = await showLnConfirm(
    context,
    title: l10n.t('skillsBlockConfirm'),
    message: l10n.t('skillsBlockWarning'),
    confirmLabel: l10n.t('sk_block'),
    cancelLabel: l10n.t('cancelAction'),
    destructive: true,
  );
  return ok ? chosen : null;
}

/// The details of one catalog entry. Pops true when something changed.
class SkillDetailsSheet extends StatefulWidget {
  const SkillDetailsSheet({
    super.key,
    required this.agentId,
    required this.entry,
    required this.controls,
  });

  final String agentId;
  final SkillEntry entry;
  final SkillControls controls;

  @override
  State<SkillDetailsSheet> createState() => _SkillDetailsSheetState();
}

class _SkillDetailsSheetState extends State<SkillDetailsSheet> {
  SkillEntry? _detail;
  SkillResource? _resource;
  Object? _error;
  bool _busy = false;
  bool _changed = false;
  bool _enabled = true;

  /// The skill's first required tool (the Web's «الأداة»); the rest of the list is kept.
  String _tool = '';
  final _title = TextEditingController();
  final _description = TextEditingController();
  final _content = TextEditingController();
  final _version = TextEditingController();

  @override
  void initState() {
    super.initState();
    for (final c in [_title, _description, _content, _version]) {
      c.addListener(() => setState(() {}));
    }
    _load();
  }

  @override
  void dispose() {
    for (final c in [_title, _description, _content, _version]) {
      c.dispose();
    }
    super.dispose();
  }

  /// The manifest's title and description (the Web editor's Name and Description).
  static String _manifestText(SkillResource? r, String key) {
    final v = r?.manifest?[key];
    return v is String ? v : '';
  }

  void _adopt(SkillResource r) {
    _content.text = r.content;
    _version.text = asVersion(r.manifest?['version']) ?? '';
    _title.text = _manifestText(r, 'title');
    _description.text = _manifestText(r, 'description');
    _enabled = r.enabled;
    _tool = _firstTool(r);
  }

  Future<void> _load() async {
    final entry = widget.entry;
    try {
      final results = await Future.wait<Object?>([
        fetchSkillDetail(widget.agentId, entry.id),
        if (entry.resourceId != null) fetchSkillResource(entry.resourceId!),
      ]);
      if (!mounted) return;
      final detail = results[0] as SkillEntry;
      final resource = results.length > 1 ? results[1] as SkillResource? : null;
      setState(() {
        _detail = detail;
        _resource = resource?.agentId == widget.agentId ? resource : null;
        _content.text = _resource?.content ?? detail.content ?? '';
        _version.text =
            asVersion(_resource?.manifest?['version']) ?? detail.version ?? '';
        _title.text = _manifestText(_resource, 'title');
        _description.text = _manifestText(_resource, 'description');
        _enabled = _resource?.enabled ?? true;
        _tool = _firstTool(_resource);
        _error = null;
      });
    } catch (error) {
      if (mounted) setState(() => _error = error);
    }
  }

  static String? asVersion(Object? v) => v is String ? v : null;

  static List<String> _tools(SkillResource? r) => [
    for (final t in asList(r?.manifest?['required_tools'])) '$t',
  ];

  static String _firstTool(SkillResource? r) {
    final tools = _tools(r);
    return tools.isEmpty ? '' : tools.first;
  }

  Future<void> _pickTool() async {
    final l10n = context.l10n;
    final options = {
      for (final MapEntry(:key, :value) in skillToolLabels.entries)
        key: l10n.t(value),
      if (_tool.isNotEmpty && !skillToolLabels.containsKey(_tool))
        _tool: ltr(_tool),
    };
    final chosen = await showLnSheet<String>(
      context,
      title: l10n.t('sk_tool'),
      builder: (sheet) => SingleChildScrollView(
        child: LnSection(
          padding: EdgeInsets.zero,
          children: [
            for (final MapEntry(:key, :value) in options.entries)
              ChoiceTile(
                title: value,
                selected: _tool == key,
                onSelect: () => Navigator.of(sheet).pop(key),
              ),
          ],
        ),
      ),
    );
    if (chosen != null && mounted) setState(() => _tool = chosen);
  }

  bool get _editable => _resource != null && widget.entry.editable;

  bool get _dirty {
    final r = _resource;
    if (r == null) return false;
    return _content.text != r.content ||
        _enabled != r.enabled ||
        (r.manifest != null &&
            (_tool != _firstTool(r) ||
                _version.text != asVersion(r.manifest!['version']) ||
                _title.text != _manifestText(r, 'title') ||
                _description.text != _manifestText(r, 'description')));
  }

  bool get _versionValid =>
      _resource?.manifest == null ||
      (semanticVersion.hasMatch(_version.text) && _version.text.length <= 64);

  /// A manifest skill keeps a title (the Web's required Name).
  bool get _titleValid =>
      _resource?.manifest == null || _title.text.trim().isNotEmpty;

  bool get _canSave =>
      _dirty && _versionValid && _titleValid && _content.text.trim().isNotEmpty;

  /// Close, Android back and the sheet's own dismissal: unsaved edits are confirmed first.
  Future<void> _close() async {
    if (_busy) return;
    if (_dirty && !await confirmDiscard(context)) return;
    if (mounted) Navigator.of(context).pop(_changed);
  }

  Future<void> _save() async {
    final r = _resource;
    if (r == null || _busy || !_canSave) return;
    setState(() => _busy = true);
    try {
      final manifest = r.manifest;
      final saved = await saveSkill(r, {
        ...r.payload,
        'content': _content.text,
        'enabled': _enabled,
        'manifest': manifest == null
            ? null
            : {
                ...manifest,
                'version': _version.text,
                'title': _title.text.trim(),
                // apps/web SkillsPages.tsx `withFields`: an empty description reads the title.
                'description': _description.text.trim().isEmpty
                    ? _title.text.trim()
                    : _description.text.trim(),
                'required_tools': keepTools(_tools(r), _tool),
              },
      });
      if (!mounted) return;
      setState(() {
        _resource = saved;
        _changed = true;
        _adopt(saved);
      });
      LnToast.show(context, context.t('sk_saved'), kind: LnToastKind.positive);
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _history() async {
    final r = _resource;
    if (r == null) return;
    final l10n = context.l10n;
    List<SkillVersion> versions;
    try {
      versions = (await fetchSkillVersions(r.id))
          .where((v) => !v.current)
          .toList();
    } catch (error) {
      if (mounted) showErrorToast(context, error);
      return;
    }
    if (!mounted) return;
    final version = await showLnSheet<int>(
      context,
      title: l10n.t('sk_history'),
      builder: (sheet) => versions.isEmpty
          ? Padding(
              padding: const EdgeInsets.symmetric(vertical: LnSpace.lg),
              child: Text(
                l10n.t('sk_noVersions'),
                textAlign: TextAlign.center,
                style: sheet.ln.text.body.copyWith(
                  color: sheet.ln.colors.fgMuted,
                ),
              ),
            )
          : SingleChildScrollView(
              child: LnSection(
                padding: EdgeInsets.zero,
                children: [
                  for (final v in versions)
                    WrapTile(
                      icon: FIcons.history,
                      title: l10n.t('sk_versionN', [v.version]),
                      subtitle: v.createdAt == null
                          ? null
                          : '${formatDate('d MMM y', l10n.lang, v.createdAt!)} ${clock(v.createdAt!.hour, v.createdAt!.minute)}',
                      trailing: Text(
                        l10n.t('sk_restore'),
                        style: sheet.ln.text.captionStrong.copyWith(
                          color: sheet.ln.colors.selection,
                        ),
                      ),
                      onTap: () => Navigator.of(sheet).pop(v.version),
                    ),
                ],
              ),
            ),
    );
    if (version == null || !mounted) return;
    final left = r.version;
    try {
      final restored = await restoreSkill(r.id, version, r.version);
      if (!mounted) return;
      setState(() {
        _resource = restored;
        _changed = true;
        _adopt(restored);
      });
      LnToast.show(
        context,
        l10n.t('sk_restored', [version]),
        kind: LnToastKind.positive,
        action: (
          l10n.t('sh_undo'),
          () async {
            try {
              final back = await restoreSkill(r.id, left, restored.version);
              if (!mounted) return;
              setState(() {
                _resource = back;
                _adopt(back);
              });
            } catch (error) {
              if (mounted) showErrorToast(context, error);
            }
          },
        ),
      );
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    }
  }

  Future<void> _block(String version) async {
    final reason = await askBlockReason(context, widget.entry.id, version);
    if (reason == null || !mounted) return;
    setState(() => _busy = true);
    try {
      await blockSkillVersion(
        widget.agentId,
        skillId: widget.entry.id,
        version: version,
        revision: widget.controls.revision,
        reason: reason,
      );
      if (!mounted) return;
      LnToast.show(
        context,
        context.t('sk_blocked'),
        kind: LnToastKind.positive,
      );
      Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        setState(() => (_busy = false, _changed = true));
        showErrorToast(context, error);
      }
    }
  }

  Future<void> _delete() async {
    final r = _resource;
    if (r == null || _busy) return;
    final l10n = context.l10n;
    final ok = await showLnConfirm(
      context,
      title: l10n.t('skillsDeleteConfirm'),
      message: l10n.t('skillsDeleteWarning'),
      confirmLabel: l10n.t('delete'),
      cancelLabel: l10n.t('cancelAction'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() => _busy = true);
    try {
      await deleteSkill(r.id);
      if (!mounted) return;
      LnToast.show(context, l10n.t('sk_deleted'), kind: LnToastKind.positive);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final ln = context.ln;
    final c = ln.colors;
    final entry = widget.entry;
    final detail = _detail;
    final manifest = detail?.manifest ?? entry.manifest;
    final version = detail?.version ?? entry.version;
    final blocked = widget.controls.blocks(entry.id, version);
    final muted = ln.text.caption.copyWith(color: c.fgMuted);
    final title = detail?.title ?? entry.title;
    final titleDirection = textDirectionFor(title, Directionality.of(context));

    String? activation;
    String? risk;
    if (manifest.isNotEmpty) {
      final act = asMap(manifest['activation']);
      final triggers = act['triggers'];
      activation = l10n.t(
        act['mode'] != 'explicit' && triggers is List && triggers.isNotEmpty
            ? 'skillsTriggered'
            : 'skillsExplicit',
      );
      risk = l10n.t(switch (manifest['risk_class']) {
        'read_only' => 'skillsReadOnly',
        'state_mutating' => 'skillsStateChange',
        'external_action' => 'skillsExternal',
        _ => 'skillsFinancial',
      });
    }
    final deps = [for (final d in asList(manifest['dependencies'])) '$d'];
    final tools = [for (final t in asList(manifest['required_tools'])) '$t'];

    return PopScope(
      // Back after a save still reports the change, so the list reloads.
      canPop: !_busy && !_dirty && !_changed,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _close();
      },
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // The title, and the coordinates under it, align by the title's own direction, as
            // the description does.
            Text(title, textDirection: titleDirection, style: ln.text.headline),
            const SizedBox(height: LnSpace.xxs),
            Text(
              skillCoordinates(entry.id, version),
              textDirection: titleDirection,
              style: muted,
            ),
            if ((detail?.description ?? entry.description).isNotEmpty) ...[
              const SizedBox(height: LnSpace.xs),
              ContentText(
                detail?.description ?? entry.description,
                style: ln.text.body.copyWith(color: c.fgMuted),
              ),
            ],
            const SizedBox(height: LnSpace.md),
            if (detail == null)
              _error == null
                  ? const Center(child: LnSpinner())
                  : LoadFailure(error: _error!, onRetry: _load)
            else ...[
              if (activation != null)
                LnSection(
                  padding: EdgeInsets.zero,
                  children: [
                    WrapTile(
                      icon: FIcons.zap,
                      title: l10n.t('skillsActivation'),
                      subtitle: activation,
                    ),
                    WrapTile(icon: FIcons.shield, title: risk!),
                    if (deps.isNotEmpty)
                      WrapTile(
                        icon: FIcons.gitFork,
                        title: l10n.t('skillsDependencies'),
                        subtitle: ltr(deps.join(', ')),
                      ),
                    if (tools.isNotEmpty)
                      WrapTile(
                        icon: FIcons.wrench,
                        title: l10n.t('skillsTools'),
                        subtitle: ltr(tools.join(', ')),
                      ),
                  ],
                ),
              const SizedBox(height: LnSpace.md),
              if (_editable) ...[
                if (_resource!.manifest != null) ...[
                  ContentField(
                    controller: _title,
                    label: l10n.t('name'),
                    error: _titleValid ? null : l10n.t('ag_titleRequired'),
                    maxLength: 160,
                    enabled: !_busy,
                    padding: EdgeInsets.zero,
                  ),
                  ContentField(
                    controller: _description,
                    label: l10n.t('description'),
                    minLines: 2,
                    maxLines: 4,
                    maxLength: 1000,
                    enabled: !_busy,
                    padding: const EdgeInsets.only(top: LnSpace.sm),
                  ),
                  ContentField(
                    controller: _version,
                    label: l10n.t('skillsVersion'),
                    helper: l10n.t('skillsVersionHint'),
                    error: _versionValid
                        ? null
                        : l10n.t('skillsVersionInvalid'),
                    ltrOnly: true,
                    maxLength: 64,
                    enabled: !_busy,
                    padding: const EdgeInsets.only(top: LnSpace.sm),
                  ),
                ],
                ContentField(
                  controller: _content,
                  label: l10n.t('skillsInstructions'),
                  minLines: 6,
                  maxLines: 14,
                  maxLength: 16000,
                  enabled: !_busy,
                  padding: const EdgeInsets.only(top: LnSpace.sm),
                ),
                const SizedBox(height: LnSpace.sm),
                LnSection(
                  padding: EdgeInsets.zero,
                  children: [
                    if (_resource!.manifest != null)
                      WrapTile(
                        icon: FIcons.wrench,
                        title: l10n.t('sk_tool'),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              skillToolLabels.containsKey(_tool)
                                  ? l10n.t(skillToolLabels[_tool]!)
                                  : ltr(_tool),
                              style: muted,
                            ),
                            const TileChevron(),
                          ],
                        ),
                        enabled: !_busy,
                        onTap: _pickTool,
                      ),
                    SwitchTile(
                      title: l10n.t('skillsEnabled'),
                      value: _enabled,
                      onChanged: _busy
                          ? null
                          : (v) => setState(() => _enabled = v),
                    ),
                  ],
                ),
                const SizedBox(height: LnSpace.md),
                BlockButton(
                  label: l10n.t('save'),
                  loading: _busy,
                  onPressed: _canSave ? _save : null,
                ),
                const SizedBox(height: LnSpace.xs),
                BlockButton(
                  label: l10n.t('sk_history'),
                  icon: FIcons.history,
                  variant: BlockButtonVariant.secondary,
                  onPressed: _busy ? null : _history,
                ),
              ] else ...[
                if (entry.builtin)
                  Padding(
                    padding: const EdgeInsets.only(bottom: LnSpace.xs),
                    child: Text(l10n.t('skillsBuiltinReadOnly'), style: muted),
                  ),
                Text(
                  l10n.t('skillsInstructions'),
                  style: ln.text.captionStrong,
                ),
                const SizedBox(height: LnSpace.xxs),
                ContentText(detail.content ?? '', style: ln.text.body),
              ],
              const SizedBox(height: LnSpace.xs),
              if (blocked)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: LnSpace.sm),
                  child: Text(
                    l10n.t('skillsAlreadyBlocked'),
                    textAlign: TextAlign.center,
                    style: muted,
                  ),
                )
              else if (version != null && !entry.id.endsWith('@installed'))
                BlockButton(
                  label: l10n.t('skillsBlockVersion'),
                  icon: FIcons.ban,
                  variant: BlockButtonVariant.secondary,
                  onPressed: _busy ? null : () => _block(version),
                ),
              if (_resource != null && !entry.builtin) ...[
                const SizedBox(height: LnSpace.xs),
                BlockButton(
                  label: l10n.t('skillsDelete'),
                  icon: FIcons.trash2,
                  variant: BlockButtonVariant.destructive,
                  onPressed: _busy ? null : _delete,
                ),
              ],
            ],
            const SizedBox(height: LnSpace.xs),
            BlockButton(
              label: l10n.t('close'),
              variant: BlockButtonVariant.secondary,
              onPressed: _busy ? null : _close,
            ),
          ],
        ),
      ),
    );
  }
}

Map<String, dynamic> asMap(Object? v) =>
    v is Map ? v.cast<String, dynamic>() : const {};

List<Object?> asList(Object? v) => v is List ? v : const [];

/// «إضافة مهارة»: identifier, title, purpose, version and instructions. Pops true once created.
class SkillCreateSheet extends StatefulWidget {
  const SkillCreateSheet({super.key, required this.agentId});

  final String agentId;

  @override
  State<SkillCreateSheet> createState() => _SkillCreateSheetState();
}

class _SkillCreateSheetState extends State<SkillCreateSheet> {
  final _id = TextEditingController();
  final _title = TextEditingController();
  final _purpose = TextEditingController();
  final _version = TextEditingController(text: '1.0.0');
  final _content = TextEditingController();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    for (final c in [_id, _title, _purpose, _version, _content]) {
      c.addListener(() => setState(() {}));
    }
  }

  @override
  void dispose() {
    for (final c in [_id, _title, _purpose, _version, _content]) {
      c.dispose();
    }
    super.dispose();
  }

  bool get _valid =>
      skillIdentifier.hasMatch(_id.text) &&
      semanticVersion.hasMatch(_version.text) &&
      _version.text.length <= 64 &&
      _title.text.trim().isNotEmpty &&
      _purpose.text.trim().isNotEmpty &&
      _content.text.trim().isNotEmpty;

  Future<void> _create() async {
    if (!_valid || _busy) return;
    setState(() => _busy = true);
    try {
      await createSkill(
        widget.agentId,
        newSkillPayload(
          id: _id.text,
          title: _title.text,
          purpose: _purpose.text,
          version: _version.text,
          content: _content.text,
        ),
      );
      if (!mounted) return;
      LnToast.show(
        context,
        context.t('sk_created'),
        kind: LnToastKind.positive,
      );
      Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final ln = context.ln;
    const gap = EdgeInsets.only(top: LnSpace.sm);
    final badId = _id.text.isNotEmpty && !skillIdentifier.hasMatch(_id.text);
    final badVersion = !semanticVersion.hasMatch(_version.text);
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            l10n.t('skillsCreateHint'),
            style: ln.text.caption.copyWith(color: ln.colors.fgMuted),
          ),
          ContentField(
            controller: _id,
            label: l10n.t('skillsIdentifier'),
            helper: l10n.t('skillsIdentifierHint'),
            error: badId ? l10n.t('sk_invalidId') : null,
            ltrOnly: true,
            maxLength: 80,
            enabled: !_busy,
            padding: gap,
          ),
          ContentField(
            controller: _title,
            label: l10n.t('ag_titleField'),
            maxLength: 160,
            enabled: !_busy,
            padding: gap,
          ),
          ContentField(
            controller: _purpose,
            label: l10n.t('skillsPurpose'),
            minLines: 2,
            maxLines: 4,
            maxLength: 1000,
            enabled: !_busy,
            padding: gap,
          ),
          ContentField(
            controller: _version,
            label: l10n.t('skillsVersion'),
            error: badVersion ? l10n.t('skillsVersionInvalid') : null,
            ltrOnly: true,
            maxLength: 64,
            enabled: !_busy,
            padding: gap,
          ),
          ContentField(
            controller: _content,
            label: l10n.t('skillsInstructions'),
            minLines: 5,
            maxLines: 12,
            maxLength: 16000,
            enabled: !_busy,
            padding: gap,
          ),
          const SizedBox(height: LnSpace.lg),
          BlockButton(
            label: l10n.t('skillsCreate'),
            loading: _busy,
            onPressed: _valid ? _create : null,
          ),
        ],
      ),
    );
  }
}

/// «حظر إصدار محدد»: an identifier and an exact version, then the reason and the confirmation.
/// Pops true once blocked.
class ExactBlockSheet extends StatefulWidget {
  const ExactBlockSheet({
    super.key,
    required this.agentId,
    required this.controls,
  });

  final String agentId;
  final SkillControls controls;

  @override
  State<ExactBlockSheet> createState() => _ExactBlockSheetState();
}

class _ExactBlockSheetState extends State<ExactBlockSheet> {
  final _id = TextEditingController();
  final _version = TextEditingController();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _id.addListener(() => setState(() {}));
    _version.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _id.dispose();
    _version.dispose();
    super.dispose();
  }

  bool get _valid =>
      skillIdentifier.hasMatch(_id.text) &&
      semanticVersion.hasMatch(_version.text) &&
      _version.text.length <= 64;

  Future<void> _block() async {
    final id = _id.text;
    final version = _version.text;
    final reason = await askBlockReason(context, id, version);
    if (reason == null || !mounted) return;
    setState(() => _busy = true);
    try {
      await blockSkillVersion(
        widget.agentId,
        skillId: id,
        version: version,
        revision: widget.controls.revision,
        reason: reason,
      );
      if (!mounted) return;
      LnToast.show(
        context,
        context.t('sk_blocked'),
        kind: LnToastKind.positive,
      );
      Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final already = widget.controls.blocks(_id.text, _version.text);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ContentField(
          controller: _id,
          label: l10n.t('skillsIdentifier'),
          ltrOnly: true,
          maxLength: 80,
          enabled: !_busy,
          padding: EdgeInsets.zero,
        ),
        ContentField(
          controller: _version,
          label: l10n.t('skillsVersion'),
          hint: '1.0.0',
          ltrOnly: true,
          maxLength: 64,
          enabled: !_busy,
          error: already ? l10n.t('skillsAlreadyBlocked') : null,
          padding: const EdgeInsets.only(top: LnSpace.sm),
        ),
        const SizedBox(height: LnSpace.lg),
        BlockButton(
          label: l10n.t('skillsBlockVersion'),
          variant: BlockButtonVariant.destructive,
          loading: _busy,
          onPressed: _valid && !already ? _block : null,
        ),
      ],
    );
  }
}
