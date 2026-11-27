// «الذاكرة الدلالية · اختيارية» (apps/web/src/pages/KnowledgeSection.tsx `SemanticKnowledge`):
// the owner's semantic retrieval setting, shared by every agent (enable + the global OpenAI
// embedding model, `GET/PUT /memory/semantic/config`), and «فهرسة الملاحظة», one knowledge note
// indexed for this agent (`POST /agents/{id}/memory/semantic {text}`), offered once retrieval
// is on with a model, as on the Web. Composed from the kit.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../core/api/api_error.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../settings/settings_common.dart';
import '../profile/agent_data.dart';
import '../profile/agent_page.dart';

class SemanticSection extends StatefulWidget {
  const SemanticSection({super.key, required this.agentId});

  final String agentId;

  @override
  State<SemanticSection> createState() => _SemanticSectionState();
}

class _SemanticSectionState extends State<SemanticSection>
    with AutomaticKeepAliveClientMixin {
  /// Kept while scrolled out of the page's list, so a draft is not lost.
  @override
  bool get wantKeepAlive => true;

  SemanticConfig? _saved;
  SemanticConfig? _draft;
  Object? _error;
  bool _busy = false;
  final _note = TextEditingController();

  @override
  void initState() {
    super.initState();
    _note.addListener(() => setState(() {}));
    _load();
  }

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (_error != null) setState(() => _error = null);
    try {
      final config = await fetchSemanticConfig();
      if (mounted) setState(() => (_saved = config, _draft = config));
    } catch (error) {
      if (error is! SessionRequestCancelled && mounted) {
        setState(() => _error = error);
      }
    }
  }

  Future<void> _pickModel() async {
    final l10n = context.l10n;
    final draft = _draft;
    if (draft == null) return;
    // A saved model stays selectable.
    final models = {...embeddingModels, ?_saved?.model};
    final chosen = await showLnSheet<String>(
      context,
      title: l10n.t('ag_semanticModel'),
      builder: (sheet) => SingleChildScrollView(
        child: LnSection(
          padding: EdgeInsets.zero,
          children: [
            for (final m in models)
              ChoiceTile(
                title: ltr(m),
                selected: draft.model == m,
                onSelect: () => Navigator.of(sheet).pop(m),
              ),
          ],
        ),
      ),
    );
    if (chosen != null && mounted) {
      setState(
        () => _draft = SemanticConfig(enabled: draft.enabled, model: chosen),
      );
    }
  }

  Future<void> _save() async {
    final draft = _draft;
    if (draft == null || _busy) return;
    setState(() => _busy = true);
    try {
      final saved = await saveSemanticConfig(draft);
      if (!mounted) return;
      setState(() => (_saved = saved, _draft = saved));
      LnToast.show(context, context.t('saved'), kind: LnToastKind.positive);
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _index() async {
    final text = _note.text;
    if (text.trim().isEmpty || _busy) return;
    setState(() => _busy = true);
    try {
      await addSemanticNote(widget.agentId, text);
      if (!mounted) return;
      _note.clear();
      LnToast.show(
        context,
        context.t('ag_noteIndexed'),
        kind: LnToastKind.positive,
      );
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final l10n = context.l10n;
    final c = context.ln.colors;
    final draft = _draft;
    final saved = _saved;
    if (draft == null || saved == null) {
      final error = _error;
      return LnSection(
        title: l10n.t('ag_semanticTitle'),
        children: [
          WrapTile(
            icon: FIcons.scanSearch,
            title: error == null
                ? l10n.t('sh_loading')
                : errorMessage(context, error) ?? l10n.t('request_failed'),
            trailing: error == null
                ? const LnSpinner(size: 18)
                : Icon(FIcons.rotateCw, color: c.fgMuted),
            onTap: error == null ? null : _load,
          ),
        ],
      );
    }
    final model = draft.model;
    final canSave = draft != saved && (!draft.enabled || model != null);
    final canIndex = saved.enabled && saved.model != null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        LnSection(
          title: l10n.t('ag_semanticTitle'),
          footer: l10n.t('ag_semanticHint'),
          children: [
            SwitchTile(
              icon: FIcons.scanSearch,
              title: l10n.t('ag_semanticEnable'),
              value: draft.enabled,
              onChanged: _busy
                  ? null
                  : (v) => setState(
                      () => _draft = SemanticConfig(enabled: v, model: model),
                    ),
            ),
            WrapTile(
              icon: FIcons.cpu,
              title: l10n.t('ag_semanticModel'),
              subtitle: model == null ? l10n.t('ag_chooseModel') : ltr(model),
              trailing: const TileChevron(),
              enabled: !_busy,
              onTap: _pickModel,
            ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
          child: BlockButton(
            label: l10n.t('save'),
            variant: BlockButtonVariant.secondary,
            loading: _busy,
            onPressed: canSave ? _save : null,
          ),
        ),
        ContentField(
          controller: _note,
          label: l10n.t('ag_semanticNote'),
          minLines: 3,
          maxLines: 8,
          maxLength: 24000,
          enabled: !_busy && canIndex,
        ),
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.pageGutter,
            LnSpace.sm,
            LnSpace.pageGutter,
            0,
          ),
          child: BlockButton(
            label: l10n.t('ag_indexNote'),
            variant: BlockButtonVariant.secondary,
            onPressed: canIndex && _note.text.trim().isNotEmpty && !_busy
                ? _index
                : null,
          ),
        ),
      ],
    );
  }
}
