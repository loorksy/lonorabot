// «التعليمات» (/agent/:id/instructions): the agent's instructions in a full-page editor. One editor
// card fills the page under the header; the header's ✓ saves (`PATCH /agents/{id}
// {instructions}`, the same write as the field in Agent Settings, which stays) and is enabled
// only while the text differs from the saved one. Leaving with unsaved text asks first.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart'
    show InputDecoration, Material, MaterialType, TextField;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/shell_actions.dart';
import '../settings/settings_common.dart'
    show LoadFailure, SettingsSkeleton, showErrorToast;
import 'profile/agent_data.dart';
import 'profile/agent_page.dart';
import 'profile/agent_strings.dart';
import 'settings/avatar_editor.dart' show confirmDiscard;

/// The longest instructions the server accepts (`AgentUpdate.instructions`).
const int instructionsMaxLength = 16000;

class AgentInstructionsScreen extends StatefulWidget {
  const AgentInstructionsScreen({super.key, required this.agentId});

  final String agentId;

  @override
  State<AgentInstructionsScreen> createState() =>
      _AgentInstructionsScreenState();
}

class _AgentInstructionsScreenState extends State<AgentInstructionsScreen> {
  final _text = TextEditingController();

  /// The saved instructions the draft is compared with.
  String? _saved;
  Object? _error;
  bool _busy = false;

  String get _id => widget.agentId;

  bool get _dirty => _saved != null && _text.text != _saved;

  @override
  void initState() {
    super.initState();
    _text.addListener(() => setState(() {}));
    final agent = context.read().shell.agents[_id];
    if (agent != null) {
      _adopt(agent);
    } else {
      unawaited(_load());
    }
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  void _adopt(Agent agent) {
    _saved = agent.instructions;
    _text.text = agent.instructions;
  }

  Future<void> _load() async {
    if (_error != null) setState(() => _error = null);
    try {
      final agent = await fetchAgent(_id);
      if (!mounted) return;
      context.dispatch(UpsertAgentAction(agent));
      setState(() => _adopt(agent));
    } catch (error) {
      if (error is! SessionRequestCancelled && mounted) {
        setState(() => _error = error);
      }
    }
  }

  Future<void> _save() async {
    if (!_dirty || _busy) return;
    setState(() => _busy = true);
    try {
      final updated = await patchAgent(_id, {'instructions': _text.text});
      if (!mounted) return;
      context.dispatch(UpsertAgentAction(updated));
      _saved = updated.instructions;
      LnToast.show(
        context,
        context.t('ag_instructionsSaved'),
        kind: LnToastKind.positive,
      );
      leaveTo(context, Routes.agent(_id));
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _back() async {
    if (_dirty && !await confirmDiscard(context)) return;
    if (mounted) leaveTo(context, Routes.agent(_id));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    registerAgentStrings(l10n);
    final c = context.ln.colors;
    final error = _error;
    final Widget body;
    if (_saved == null) {
      body = error == null
          ? const SettingsSkeleton(groups: [1])
          : error is ApiError && error.isNotFound
          ? EmptyState(icon: FIcons.userX, title: l10n.t('agentMissing'))
          : LoadFailure(error: error, onRetry: _load);
    } else {
      body = Padding(
        padding: EdgeInsets.fromLTRB(
          LnSpace.pageGutter,
          LnSpace.xxs,
          LnSpace.pageGutter,
          LnSpace.md + MediaQuery.viewPaddingOf(context).bottom,
        ),
        child: InstructionsEditor(
          controller: _text,
          hint: l10n.t('ag_instructionsHint'),
          enabled: !_busy,
        ),
      );
    }
    return PopScope(
      canPop: !_dirty,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: AgentPage(
        title: l10n.t('instructions'),
        background: c.sheetPage,
        fallback: Routes.agent(_id),
        onBack: _back,
        trailing: _saved == null
            ? null
            : ConfirmCircle(
                semanticLabel: l10n.t('save'),
                busy: _busy,
                onTap: _dirty ? _save : null,
              ),
        body: body,
      ),
    );
  }
}

/// The editor card: [LnPalette.editorCard] at radius [LnRadius.group] filling its box, 16 dp
/// inside, the hint in the tertiary ink. The text reads in its own direction (an English
/// instruction in the Arabic interface reads left to right); input stops at
/// [instructionsMaxLength].
class InstructionsEditor extends StatelessWidget {
  const InstructionsEditor({
    super.key,
    required this.controller,
    required this.hint,
    this.enabled = true,
  });

  final TextEditingController controller;
  final String hint;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final ambient = Directionality.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: c.editorCard,
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.group)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(LnSpace.md),
        child: Material(
          type: MaterialType.transparency,
          child: ValueListenableBuilder<TextEditingValue>(
            valueListenable: controller,
            builder: (context, value, _) => TextField(
              controller: controller,
              enabled: enabled,
              expands: true,
              maxLines: null,
              keyboardType: TextInputType.multiline,
              textCapitalization: TextCapitalization.sentences,
              textAlignVertical: TextAlignVertical.top,
              textDirection: textDirectionFor(value.text, ambient),
              inputFormatters: [
                LengthLimitingTextInputFormatter(instructionsMaxLength),
              ],
              style: ln.text.body.copyWith(color: c.fg),
              cursorColor: c.brand,
              decoration: InputDecoration.collapsed(
                hintText: hint,
                hintStyle: ln.text.body.copyWith(color: c.fgSubtle),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
