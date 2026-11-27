// The avatar studio sheet: Lonora's own studio (lib/avatar) with Cancel / Save and a
// discard-changes confirmation. Lonora's avatar is a face and a shell colour only (`Agent.avatar`,
// `Agent.color`; lonora-api-contract §8.2): there is no shape, so the studio shows Face and Colour.
// Saving patches only those two fields (apps/mobile/components/avatar-picker.tsx,
// «يحفظ الوجه واللون مباشرة»).
import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../../avatar/avatar.dart';
import '../../../core/models/models.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../../state/actions/shell_actions.dart';
import '../../settings/settings_common.dart' show showErrorToast;
import '../profile/agent_data.dart';
import '../profile/agent_strings.dart';

/// Asks whether to drop unsaved changes; true when the owner discards them.
Future<bool> confirmDiscard(BuildContext context) {
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

/// Opens the studio for [agent]; completes with the saved agent, or null when nothing changed.
Future<Agent?> showAvatarEditor(BuildContext context, Agent agent) {
  registerAgentStrings(context.l10n);
  return showLnSheet<Agent>(
    context,
    // Only Cancel, Save and Android back close it, so a change is never lost by a stray tap.
    isDismissible: false,
    enableDrag: false,
    maxHeightFraction: 0.92,
    padding: EdgeInsets.zero,
    builder: (_) => AvatarEditor(agent: agent),
  );
}

class AvatarEditor extends StatefulWidget {
  const AvatarEditor({super.key, required this.agent});

  final Agent agent;

  @override
  State<AvatarEditor> createState() => _AvatarEditorState();
}

class _AvatarEditorState extends State<AvatarEditor> {
  late String _face = resolveAvatarFace(widget.agent.avatar);
  late String _color =
      widget.agent.color ??
      resolveAvatarColor(widget.agent.id, widget.agent.color).hex;
  bool _busy = false;

  bool get _dirty =>
      _face != resolveAvatarFace(widget.agent.avatar) ||
      _color.toLowerCase() !=
          (widget.agent.color ??
                  resolveAvatarColor(widget.agent.id, widget.agent.color).hex)
              .toLowerCase();

  Future<void> _cancel() async {
    if (_busy) return;
    if (_dirty && !await confirmDiscard(context)) return;
    if (mounted) Navigator.of(context).pop();
  }

  /// Back to the default face and colour (apps/mobile avatar-picker.tsx «إعادة الضبط»); saved
  /// only by Save.
  void _reset() {
    HapticFeedback.selectionClick();
    setState(() => (_face = 'orb', _color = defaultAvatarColor));
  }

  Future<void> _save() async {
    if (_busy) return;
    if (!_dirty) {
      Navigator.of(context).pop();
      return;
    }
    setState(() => _busy = true);
    try {
      final updated = await patchAgent(widget.agent.id, {
        'avatar': _face,
        'color': _color,
      });
      if (!mounted) return;
      context.dispatch(UpsertAgentAction(updated));
      LnToast.show(
        context,
        context.t('ag_avatarSaved'),
        kind: LnToastKind.positive,
      );
      Navigator.of(context).pop(updated);
    } catch (error) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorToast(context, error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final l10n = context.l10n;
    Widget textButton(
      String label,
      VoidCallback onTap, {
      bool strong = false,
    }) => LnTappable(
      onTap: _busy ? null : onTap,
      semanticLabel: label,
      excludeChildSemantics: true,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 48, minWidth: 64),
        child: Center(
          child: Text(
            label,
            style: (strong ? ln.text.title : ln.text.body).copyWith(
              color: strong ? ln.colors.fg : ln.colors.fgMuted,
            ),
          ),
        ),
      ),
    );
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _cancel();
      },
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsetsDirectional.symmetric(
              horizontal: LnSpace.xs,
            ),
            child: Row(
              children: [
                textButton(l10n.t('avatarCancel'), _cancel),
                Expanded(
                  child: Semantics(
                    header: true,
                    child: Text(
                      l10n.t('avatarEdit'),
                      textAlign: TextAlign.center,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: ln.text.headline,
                    ),
                  ),
                ),
                _busy
                    ? const SizedBox(
                        width: 64,
                        height: 48,
                        child: Center(child: LnSpinner(size: 18)),
                      )
                    : textButton(l10n.t('save'), _save, strong: true),
              ],
            ),
          ),
          Flexible(
            child: SingleChildScrollView(
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.pageGutter,
                0,
                LnSpace.pageGutter,
                LnSpace.lg,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  AvatarStudioGrid(
                    agentId: widget.agent.id,
                    face: _face,
                    color: _color,
                    enabled: !_busy,
                    palette: ln.colors,
                    onFaceChanged: (face) {
                      HapticFeedback.selectionClick();
                      setState(() => _face = face);
                    },
                    onColorChanged: (color) {
                      HapticFeedback.selectionClick();
                      setState(() => _color = color);
                    },
                  ),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          l10n.t('avatarStudioSaveHint'),
                          style: ln.text.footnote.copyWith(
                            color: ln.colors.fgMuted,
                          ),
                        ),
                      ),
                      textButton(l10n.t('avatarReset'), _reset),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
