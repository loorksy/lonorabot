// «ما أعرفه عنك» (/me/knowledge): what Lonora knows about the owner, and where each line came
// from (apps/mobile/app/owner.tsx, apps/web OwnerPage.tsx): every profile line with its origin
// («قلتَه», «لاحظه {name}», «من قبل»), corrected or deleted as the owner's own word
// (`POST /owner/profile/lines`); the learned waking habit with «انسَ هذه العادة»
// (`GET/DELETE /app-opens`); the whole profile as text (`PUT /owner/profile`); and the change log
// with a one-change undo (`GET /owner/profile/revisions`, `/memory/revisions/{id}/revert`).
// Each part loads on its own (apps/mobile/app/owner.tsx): a failed one shows its error where it
// would be, the others stay. Composed from the kit.
import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../app/routes.dart';
import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../agents/memory/memory_revisions.dart';
import '../agents/profile/agent_data.dart';
import '../agents/profile/agent_page.dart';
import '../agents/profile/agent_strings.dart';
import '../settings/settings_common.dart';

/// One line of the owner profile with its origin.
@immutable
class ProfileLine {
  const ProfileLine({
    required this.text,
    required this.origin,
    this.authorAgentName,
  });

  factory ProfileLine.fromJson(Json j) => ProfileLine(
    text: asStr(j['text']),
    origin: asStr(j['origin'], 'earlier'),
    authorAgentName: asString(j['author_agent_name']),
  );

  /// The stored line, with its markdown bullet if it has one.
  final String text;

  /// `you_said`, `observed` or `earlier`.
  final String origin;
  final String? authorAgentName;

  static final _bullet = RegExp(r'^[-*]\s+');

  /// The line's leading bullet, kept when it is corrected.
  String get bullet => _bullet.firstMatch(text)?[0] ?? '';

  /// What the owner reads: the line without its bullet.
  String get shown => text.replaceFirst(RegExp(r'^[-*]\s*'), '');
}

/// The words the owner typed, without a bullet of his own: the line's bullet is added once
/// (apps/mobile/app/owner.tsx `words`).
String correctionWords(String text) =>
    text.trim().replaceFirst(RegExp(r'^[-*]\s+'), '').trim();

class OwnerKnowledgeScreen extends StatefulWidget {
  const OwnerKnowledgeScreen({super.key});

  @override
  State<OwnerKnowledgeScreen> createState() => _OwnerKnowledgeScreenState();
}

class _OwnerKnowledgeScreenState extends State<OwnerKnowledgeScreen> {
  int? _linesVersion;
  List<ProfileLine>? _lines;
  Object? _linesError;
  bool _habitRead = false;
  String? _firstOpen;
  String _brief = '07:00';
  Object? _habitError;
  Json? _profile;
  Object? _profileError;
  List<MemoryRevision>? _revisions;
  Object? _revisionsError;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() => Future.wait([
    _read<Object?>(api.get('/owner/profile/lines'), (v, e) {
      _linesError = e;
      if (v == null) return;
      final lines = asJson(v);
      _linesVersion = asInt(lines['version']);
      _lines = asJsonList(lines['lines']).map(ProfileLine.fromJson).toList();
    }),
    _read<Object?>(api.get('/app-opens'), (v, e) {
      _habitError = e;
      if (v == null) return;
      final habit = asJson(v);
      _habitRead = true;
      _firstOpen = asString(habit['first_open']);
      _brief = asStr(habit['brief'], '07:00');
    }),
    _read<Object?>(api.get('/owner/profile'), (v, e) {
      _profileError = e;
      if (v != null) _profile = asJson(v);
    }),
    _read(fetchProfileRevisions(), (List<MemoryRevision>? v, e) {
      _revisionsError = e;
      if (v != null) _revisions = v;
    }),
  ]);

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

  /// A part that failed: its words and a retry, where it would be.
  WrapTile _failed(IconData icon, Object error) => WrapTile(
    icon: icon,
    title: errorMessage(context, error) ?? context.t('request_failed'),
    trailing: Icon(FIcons.rotateCw, color: context.ln.colors.fgMuted),
    onTap: _load,
  );

  /// A correction ([replacement]) or a deletion (null), recorded as the owner's own word.
  Future<void> _correct(ProfileLine line, String? replacement) async {
    final version = _linesVersion;
    if (version == null || _busy) return;
    setState(() => _busy = true);
    try {
      await api.post('/owner/profile/lines', {
        'version': version,
        'text': line.text,
        'replacement': replacement,
      });
      if (!mounted) return;
      LnToast.show(
        context,
        context.t(replacement == null ? 'ag_factRemoved' : 'ag_factCorrected'),
        kind: LnToastKind.positive,
      );
      await _load();
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _lineMenu(ProfileLine line) async {
    final l10n = context.l10n;
    final action = await showLnActionMenu<String>(
      context,
      title: isolate(line.shown),
      actions: [
        LnMenuAction(
          label: l10n.t('correctFact'),
          icon: FIcons.pencil,
          value: 'correct',
        ),
        LnMenuAction(
          label: l10n.t('deleteFact'),
          icon: FIcons.trash2,
          value: 'delete',
          destructive: true,
        ),
      ],
    );
    if (!mounted || action == null) return;
    if (action == 'delete') {
      final ok = await showLnConfirm(
        context,
        title: l10n.t('ag_deleteFactQ'),
        message: l10n.t('ag_deleteFactBody'),
        confirmLabel: l10n.t('delete'),
        cancelLabel: l10n.t('cancelAction'),
        destructive: true,
      );
      if (ok && mounted) await _correct(line, null);
      return;
    }
    final words = await showLnSheet<String>(
      context,
      title: l10n.t('correctFact'),
      builder: (_) => _CorrectionForm(initial: line.shown),
    );
    if (words != null && mounted) {
      await _correct(line, '${line.bullet}$words');
    }
  }

  Future<void> _forgetHabit() async {
    final l10n = context.l10n;
    final ok = await showLnConfirm(
      context,
      title: l10n.t('ag_forgetHabitQ'),
      message: l10n.t('ag_forgetHabitBody'),
      confirmLabel: l10n.t('ag_forget'),
      cancelLabel: l10n.t('cancelAction'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    try {
      final habit = asJson(await api.delete('/app-opens'));
      if (!mounted) return;
      setState(() {
        _firstOpen = asString(habit['first_open']);
        _brief = asStr(habit['brief'], '07:00');
      });
      LnToast.show(
        context,
        l10n.t('ag_habitForgotten'),
        kind: LnToastKind.positive,
      );
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    }
  }

  Future<void> _editText() async {
    final profile = _profile;
    if (profile == null) return;
    final saved = await showLnSheet<bool>(
      context,
      maxHeightFraction: 0.94,
      title: ownerProfileLabel('profile', context.l10n.lang),
      builder: (_) => _ProfileTextForm(profile: profile),
    );
    if (saved == true) await _load();
  }

  Future<void> _revert(MemoryRevision row) async {
    try {
      await revertRevision(
        row.id,
        row.document == 'owner_profile' ? asInt(_profile?['version']) : null,
      );
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

  String _origin(L10n l10n, ProfileLine line) => switch (line.origin) {
    'you_said' => l10n.t('youSaid'),
    'earlier' => l10n.t('earlier'),
    _ =>
      line.authorAgentName != null
          ? l10n.t('observedBy', const [], {
              'name': isolate(line.authorAgentName!),
            })
          : l10n.t('observed'),
  };

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    registerAgentStrings(l10n);
    final ln = context.ln;
    final lines = _lines;
    final linesError = _linesError;
    final habitError = _habitError;
    final revisions = _revisions;
    final revisionsError = _revisionsError;
    Widget body;
    if (linesError != null &&
        habitError != null &&
        _profileError != null &&
        revisionsError != null &&
        lines == null &&
        !_habitRead &&
        _profile == null &&
        revisions == null) {
      // Nothing at all could be read (offline, the server down).
      body = LoadFailure(error: linesError, onRetry: _load);
    } else if ((lines == null && linesError == null) ||
        (!_habitRead && habitError == null)) {
      // The profile lines and the habit come first.
      body = const SettingsSkeleton(groups: [4, 2]);
    } else {
      final habit = _firstOpen;
      final nothing =
          lines != null && lines.isEmpty && habit == null && habitError == null;
      body = LnRefresh(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(bottom: pageBottomPadding(context)),
          children: [
            SettingsNote(l10n.t('whatIKnowHint')),
            if (nothing)
              EmptyState(icon: FIcons.brain, title: l10n.t('nothingKnown'))
            else
              LnSection(
                title: ownerProfileLabel('profile', l10n.lang),
                children: [
                  if (habitError != null && !_habitRead)
                    _failed(FIcons.sunrise, habitError),
                  if (habit != null)
                    FullTile(
                      icon: FIcons.sunrise,
                      // Times of day: in the date digits of the interface language.
                      title: l10n.t('habitLine', const [], {
                        'firstOpen': ltr(dateDigits(habit, l10n.lang)),
                        'brief': ltr(dateDigits(_brief, l10n.lang)),
                      }),
                      subtitle: l10n.t('habitOrigin'),
                      trailing: Icon(FIcons.x, color: ln.colors.fgMuted),
                      enabled: !_busy,
                      onTap: _forgetHabit,
                    ),
                  if (lines == null && linesError != null)
                    _failed(FIcons.eye, linesError),
                  for (final line in lines ?? const <ProfileLine>[])
                    FullTile(
                      icon: line.origin == 'you_said'
                          ? FIcons.messageSquareQuote
                          : FIcons.eye,
                      title: isolate(line.shown),
                      subtitle: _origin(l10n, line),
                      trailing: Icon(FIcons.ellipsis, color: ln.colors.fgMuted),
                      enabled: !_busy,
                      onTap: () => _lineMenu(line),
                    ),
                ],
              ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.pageGutter,
                LnSpace.md,
                LnSpace.pageGutter,
                0,
              ),
              child: BlockButton(
                label: l10n.t('ag_editAsText'),
                icon: FIcons.pencil,
                variant: BlockButtonVariant.secondary,
                onPressed: _profile == null || _busy ? null : _editText,
              ),
            ),
            SettingsNote(
              ownerProfileLabel('shared', l10n.lang),
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.pageGutter,
                LnSpace.xs,
                LnSpace.pageGutter,
                0,
              ),
            ),
            if (_profile == null && _profileError != null)
              SettingsNote(
                errorMessage(context, _profileError!) ??
                    l10n.t('request_failed'),
                padding: const EdgeInsetsDirectional.fromSTEB(
                  LnSpace.pageGutter,
                  LnSpace.xs,
                  LnSpace.pageGutter,
                  0,
                ),
              ),
            const SectionGap(),
            if (revisions == null && revisionsError != null)
              LnSection(
                title: ownerProfileLabel('history', l10n.lang),
                children: [_failed(FIcons.history, revisionsError)],
              )
            else
              RevisionList(revisions: revisions ?? const [], onRevert: _revert),
          ],
        ),
      );
    }
    return AgentPage(
      title: l10n.t('whatIKnow'),
      fallback: Routes.me,
      body: body,
    );
  }
}

class _CorrectionForm extends StatefulWidget {
  const _CorrectionForm({required this.initial});

  final String initial;

  @override
  State<_CorrectionForm> createState() => _CorrectionFormState();
}

class _CorrectionFormState extends State<_CorrectionForm> {
  late final _text = TextEditingController(text: widget.initial);

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

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final words = correctionWords(_text.text);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ContentField(
          controller: _text,
          autofocus: true,
          minLines: 1,
          maxLines: 4,
          maxLength: 2000,
          // One line: the server keeps a correction on the line it replaces.
          inputFormatters: [FilteringTextInputFormatter.deny(RegExp('[\r\n]'))],
          padding: EdgeInsets.zero,
        ),
        const SizedBox(height: LnSpace.lg),
        BlockButton(
          label: l10n.t('saveCorrection'),
          onPressed: words.isEmpty
              ? null
              : () => Navigator.of(context).pop(words),
        ),
      ],
    );
  }
}

class _ProfileTextForm extends StatefulWidget {
  const _ProfileTextForm({required this.profile});

  final Json profile;

  @override
  State<_ProfileTextForm> createState() => _ProfileTextFormState();
}

class _ProfileTextFormState extends State<_ProfileTextForm> {
  late final _text = TextEditingController(
    text: asStr(widget.profile['content']),
  );
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

  Future<void> _save() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await api.put('/owner/profile', {
        'content': _text.text,
        'version': asInt(widget.profile['version']) ?? 1,
      });
      if (!mounted) return;
      LnToast.show(
        context,
        context.t('ag_profileSaved'),
        kind: LnToastKind.positive,
      );
      Navigator.of(context).pop(true);
    } catch (error) {
      // e.g. owner_profile_too_large with its limit, version_conflict.
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final limit = asInt(widget.profile['limit']);
    final count = _text.text.length;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ContentField(
            controller: _text,
            minLines: 8,
            maxLines: 18,
            enabled: !_busy,
            helper: limit == null ? null : ltr('$count / $limit'),
            error: limit != null && count > limit
                ? l10n.errorText('owner_profile_too_large')
                : null,
            padding: EdgeInsets.zero,
          ),
          const SizedBox(height: LnSpace.lg),
          BlockButton(
            label: l10n.t('save'),
            loading: _busy,
            onPressed: limit != null && count > limit ? null : _save,
          ),
        ],
      ),
    );
  }
}
