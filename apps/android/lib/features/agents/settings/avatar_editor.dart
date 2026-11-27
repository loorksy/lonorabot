// The avatar studio: Lonora's own avatar (lib/avatar) on a stacked-sheet page. Lonora's avatar is a
// face and a shell colour only (`Agent.avatar`, `Agent.color`; lonora-api-contract §8.2): there is
// no shape, so the page holds the live preview, a colour ring that opens the shell colours in a
// popover, the face grid, and Reset. The header has the leading circle (✕, or › when the studio is
// the second page of a sheet), the title and the ✓ circle.
//
// From the profile and Agent Settings the studio is its own sheet: ✓ patches only the two fields
// (apps/mobile/components/avatar-picker.tsx, «يحفظ الوجه واللون مباشرة»), and leaving with changes
// asks first. The create-agent sheet shows the same page and keeps the choice as a draft.
import 'dart:math' as math;

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../avatar/avatar.dart';
import '../../../core/models/models.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../../state/actions/shell_actions.dart';
import '../../settings/settings_common.dart' show showErrorToast;
import '../profile/agent_data.dart';
import '../profile/agent_page.dart' show ConfirmCircle;
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

/// Opens the studio for [agent] in a stacked sheet; completes with the saved agent, or null when
/// nothing changed. Only ✕, ✓ and Android back close it, so a change is never lost by a stray
/// drag.
Future<Agent?> showAvatarEditor(BuildContext context, Agent agent) {
  registerAgentStrings(context.l10n);
  return showLnStackedSheet<Agent>(
    context,
    enableDrag: false,
    builder: (_) => AvatarEditor(agent: agent),
  );
}

/// The saved shell colour of [agent] as a hex (its hash colour when it has none).
String agentColorHex(Agent agent) =>
    agent.color ?? resolveAvatarColor(agent.id, agent.color).hex;

/// The studio sheet of an existing agent: ✓ saves the face and colour.
class AvatarEditor extends StatefulWidget {
  const AvatarEditor({super.key, required this.agent});

  final Agent agent;

  @override
  State<AvatarEditor> createState() => _AvatarEditorState();
}

class _AvatarEditorState extends State<AvatarEditor> {
  late String _face = resolveAvatarFace(widget.agent.avatar);
  late String _color = agentColorHex(widget.agent);
  bool _busy = false;

  bool get _dirty =>
      _face != resolveAvatarFace(widget.agent.avatar) ||
      _color.toLowerCase() != agentColorHex(widget.agent).toLowerCase();

  Future<void> _cancel() async {
    if (_busy) return;
    if (_dirty && !await confirmDiscard(context)) return;
    if (mounted) Navigator.of(context).pop();
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
  Widget build(BuildContext context) => PopScope(
    canPop: false,
    onPopInvokedWithResult: (didPop, _) {
      if (!didPop) _cancel();
    },
    child: AvatarStudio(
      agentId: widget.agent.id,
      face: _face,
      color: _color,
      busy: _busy,
      note: context.t('avatarStudioSaveHint'),
      onFaceChanged: (face) => setState(() => _face = face),
      onColorChanged: (color) => setState(() => _color = color),
      // Back to the default face and colour (apps/mobile avatar-picker.tsx «إعادة الضبط»);
      // saved only by ✓.
      onReset: () => setState(
        () => (_face = avatarFaces.first.id, _color = defaultAvatarColor),
      ),
      onConfirm: _save,
      onLeave: _cancel,
    ),
  );
}

/// What the studio's leading circle shows.
enum AvatarStudioLeading {
  /// ✕: the studio is the sheet.
  close,

  /// ›: the studio is a second page of a sheet.
  back,
}

/// The studio page: header (leading circle, title, ✓), live preview, colour ring, face grid,
/// Reset. The caller keeps the draft [face] and [color] (a palette hex).
class AvatarStudio extends StatelessWidget {
  const AvatarStudio({
    super.key,
    required this.agentId,
    required this.face,
    required this.color,
    required this.onFaceChanged,
    required this.onColorChanged,
    required this.onConfirm,
    required this.onLeave,
    this.onReset,
    this.leading = AvatarStudioLeading.close,
    this.busy = false,
    this.note,
  });

  /// Seeds the avatars' personality.
  final String agentId;
  final String face;
  final String color;
  final ValueChanged<String> onFaceChanged;
  final ValueChanged<String> onColorChanged;
  final VoidCallback onConfirm;
  final VoidCallback onLeave;
  final VoidCallback? onReset;
  final AvatarStudioLeading leading;

  /// ✓ shows a spinner and the choices are locked.
  final bool busy;

  /// A footnote beside Reset.
  final String? note;

  /// Preview size.
  static const double previewSize = 90;

  /// A face cell's avatar, and the selected cell's tile (radius 12).
  static const double faceSize = 48;
  static const double faceTile = 66;
  static const double faceRowPitch = 74;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final animate = !(MediaQuery.maybeDisableAnimationsOf(context) ?? false);
    final selectedFace = resolveAvatarFace(face);
    final locale = Localizations.maybeLocaleOf(context);
    final leave = leading == AvatarStudioLeading.close
        ? CircleIconButton(
            icon: const Icon(FIcons.x),
            semanticLabel: l10n.t('close'),
            onTap: busy ? null : onLeave,
          )
        : CircleIconButton(
            // Lucide chevrons mirror themselves in RTL (matchTextDirection).
            icon: const Icon(FIcons.chevronLeft),
            semanticLabel: l10n.t('back'),
            onTap: busy ? null : onLeave,
          );
    final header = Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter - 2,
        LnSheetHeader.top,
        LnSpace.pageGutter - 2,
        0,
      ),
      child: SizedBox(
        height: LnSize.minTouch,
        child: NavigationToolbar(
          leading: leave,
          middle: Semantics(
            header: true,
            child: Text(
              l10n.t('avatarEdit'),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: ln.text.title.copyWith(color: c.fgWarm),
            ),
          ),
          trailing: ConfirmCircle(
            semanticLabel: l10n.t('save'),
            busy: busy,
            onTap: onConfirm,
          ),
          middleSpacing: LnSpace.xs,
        ),
      ),
    );

    final grid = LayoutBuilder(
      builder: (context, constraints) {
        final cell = constraints.maxWidth / 5;
        return Wrap(
          children: [
            for (final option in avatarFaces)
              SizedBox(
                width: cell,
                height: faceRowPitch,
                child: _FaceCell(
                  agentId: agentId,
                  face: option.id,
                  color: color,
                  label: option.label(locale),
                  selected: option.id == selectedFace,
                  enabled: !busy,
                  onTap: () {
                    HapticFeedback.selectionClick();
                    onFaceChanged(option.id);
                  },
                ),
              ),
          ],
        );
      },
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        header,
        Expanded(
          // Its own scroll: a drag in the studio never closes the sheet.
          child: SingleChildScrollView(
            padding: EdgeInsets.fromLTRB(
              LnSpace.pageGutter,
              LnSpace.xl,
              LnSpace.pageGutter,
              LnSpace.lg + MediaQuery.viewPaddingOf(context).bottom,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Center(
                  child: ExcludeSemantics(
                    child: LonoraAvatar(
                      agentId: agentId,
                      face: selectedFace,
                      color: color,
                      size: previewSize,
                      animate: animate,
                    ),
                  ),
                ),
                const SizedBox(height: LnSpace.md),
                Center(
                  child: ColorRingButton(
                    color: color,
                    enabled: !busy,
                    onChanged: (hex) {
                      HapticFeedback.selectionClick();
                      onColorChanged(hex);
                    },
                  ),
                ),
                const SizedBox(height: LnSpace.xl),
                grid,
                Padding(
                  padding: const EdgeInsets.fromLTRB(8, LnSpace.sm, 8, 0),
                  child: Container(height: 1, color: c.border),
                ),
                const SizedBox(height: LnSpace.xs),
                Row(
                  children: [
                    Expanded(
                      child: note == null
                          ? const SizedBox.shrink()
                          : Text(
                              note!,
                              style: ln.text.footnote.copyWith(
                                color: c.fgMuted,
                              ),
                            ),
                    ),
                    if (onReset != null)
                      LnTappable(
                        onTap: busy
                            ? null
                            : () {
                                HapticFeedback.selectionClick();
                                onReset!();
                              },
                        semanticLabel: l10n.t('avatarReset'),
                        excludeChildSemantics: true,
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(
                            minHeight: LnSize.minTouch,
                            minWidth: 64,
                          ),
                          child: Center(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: LnSpace.xs,
                              ),
                              child: Text(
                                l10n.t('avatarReset'),
                                style: ln.text.body.copyWith(color: c.fgMuted),
                              ),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// One face of the grid: the avatar in the draft colour; the selected face sits on a 66 dp tile
/// (radius 12) one fill step above the page.
class _FaceCell extends StatelessWidget {
  const _FaceCell({
    required this.agentId,
    required this.face,
    required this.color,
    required this.label,
    required this.selected,
    required this.enabled,
    required this.onTap,
  });

  final String agentId;
  final String face;
  final String color;
  final String label;
  final bool selected;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    return MergeSemantics(
      child: Semantics(
        inMutuallyExclusiveGroup: true,
        checked: selected,
        child: LnTappable(
          onTap: enabled ? onTap : null,
          semanticLabel: label,
          excludeChildSemantics: true,
          child: Center(
            child: AnimatedContainer(
              duration: LnMotion.fast,
              width: AvatarStudio.faceTile,
              height: AvatarStudio.faceTile,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: selected ? c.fill3 : null,
                borderRadius: const BorderRadius.all(Radius.circular(12)),
              ),
              child: LonoraAvatar(
                agentId: agentId,
                face: face,
                color: color,
                size: AvatarStudio.faceSize,
                animate: false,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The colour button: a 36 dp hue ring around a disc of the current [color], in a 48 dp touch
/// box. A tap opens the shell colours (Lonora's eleven, [avatarPalette]) in a popover centred
/// under it; picking one calls [onChanged] with its hex.
class ColorRingButton extends StatefulWidget {
  const ColorRingButton({
    super.key,
    required this.color,
    required this.onChanged,
    this.enabled = true,
  });

  final String color;
  final ValueChanged<String> onChanged;
  final bool enabled;

  @override
  State<ColorRingButton> createState() => _ColorRingButtonState();
}

class _ColorRingButtonState extends State<ColorRingButton> {
  final _key = GlobalKey();

  Future<void> _open() async {
    final navigator = Navigator.of(context, rootNavigator: true);
    final anchor = lnAnchorRect(navigator, key: _key);
    final picked = await navigator.push<String>(
      _SwatchPopoverRoute(
        anchor: anchor,
        selected: widget.color,
        theme: context.ln,
        direction: Directionality.of(context),
        barrierLabel: context.t('close'),
        label: context.t('ag_chooseColor'),
      ),
    );
    if (picked != null && mounted) widget.onChanged(picked);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return LnTappable(
      key: _key,
      onTap: widget.enabled ? _open : null,
      semanticLabel: l10n.t('ag_chooseColor'),
      excludeChildSemantics: true,
      child: SizedBox.square(
        dimension: LnSize.minTouch,
        child: Center(
          child: CustomPaint(
            size: const Size.square(36),
            painter: _HueRingPainter(avatarHexColor(widget.color)),
          ),
        ),
      ),
    );
  }
}

/// A 3 dp hue ring, a 2 dp gap and a disc of the current colour.
class _HueRingPainter extends CustomPainter {
  _HueRingPainter(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.width / 2;
    const stroke = 3.0;
    final ring = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..shader = const SweepGradient(
        colors: [
          Color(0xFFFF453A),
          Color(0xFFFFD60A),
          Color(0xFF32D74B),
          Color(0xFF64D2FF),
          Color(0xFF0A84FF),
          Color(0xFFBF5AF2),
          Color(0xFFFF453A),
        ],
      ).createShader(Rect.fromCircle(center: center, radius: radius));
    canvas.drawCircle(center, radius - stroke / 2, ring);
    canvas.drawCircle(center, radius - stroke - 2, Paint()..color = color);
  }

  @override
  bool shouldRepaint(_HueRingPainter old) => old.color != color;
}

/// The colour popover: the shell colours in rows of six on a menu card (radius 26), 10 dp under
/// the ring and centred on it (above it when there is no room below). No scrim; a tap outside or
/// back closes it.
class _SwatchPopoverRoute extends PopupRoute<String> {
  _SwatchPopoverRoute({
    required this.anchor,
    required this.selected,
    required this.theme,
    required this.direction,
    required this.barrierLabel,
    required this.label,
  });

  final Rect anchor;
  final String selected;
  final LnThemeData theme;
  final TextDirection direction;
  final String label;

  @override
  final String barrierLabel;

  static const int _perRow = 6;
  static const double _cell = 48;
  static const double _pad = 11;
  static const double _gap = 10;

  @override
  Color? get barrierColor => null;

  @override
  bool get barrierDismissible => true;

  @override
  Duration get transitionDuration => LnMotion.fast;

  @override
  Widget buildPage(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
  ) {
    final rows = (avatarPalette.length / _perRow).ceil();
    // The 0.5 dp border on both sides takes from the content.
    final width = _perRow * _cell + 2 * _pad + 1;
    final height = rows * _cell + 2 * _pad + 1;
    final media = MediaQuery.of(context);
    final area = lnMenuArea(context, media.size);
    final left = (anchor.center.dx - width / 2)
        .clamp(area.left, math.max(area.left, area.right - width))
        .toDouble();
    final below = anchor.bottom - 6 + _gap;
    final fitsBelow = below + height <= area.bottom;
    final top = fitsBelow ? below : anchor.top + 6 - _gap - height;
    final c = theme.colors;
    return LnTheme(
      data: theme,
      child: Directionality(
        textDirection: direction,
        child: Stack(
          children: [
            Positioned(
              left: left,
              top: top,
              width: width,
              child: FadeTransition(
                opacity: animation,
                child: Semantics(
                  scopesRoute: true,
                  namesRoute: true,
                  explicitChildNodes: true,
                  label: label,
                  child: Container(
                    padding: const EdgeInsets.all(_pad),
                    decoration: BoxDecoration(
                      color: c.popover,
                      borderRadius: const BorderRadius.all(
                        Radius.circular(LnRadius.group),
                      ),
                      border: Border.all(color: c.menuBorder, width: 0.5),
                      boxShadow: c.isDark ? null : LnShadow.menu,
                    ),
                    child: Wrap(
                      children: [
                        for (final option in avatarPalette)
                          _Swatch(
                            hex: option.hex,
                            label: context.t('ag_colorN', [option.hex]),
                            selected:
                                option.hex.toLowerCase() ==
                                selected.toLowerCase(),
                            onTap: () => Navigator.of(context).pop(option.hex),
                          ),
                      ],
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

/// A 26 dp disc in a 48 dp touch box; the selected one wears a 36 dp ring of its own colour.
class _Swatch extends StatelessWidget {
  const _Swatch({
    required this.hex,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String hex;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = avatarHexColor(hex);
    return MergeSemantics(
      child: Semantics(
        inMutuallyExclusiveGroup: true,
        checked: selected,
        child: LnTappable(
          onTap: onTap,
          semanticLabel: label,
          excludeChildSemantics: true,
          child: SizedBox.square(
            dimension: _SwatchPopoverRoute._cell,
            child: Center(
              child: Container(
                width: 36,
                height: 36,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: selected ? color : const Color(0x00000000),
                    width: 2,
                  ),
                ),
                child: Container(
                  width: 26,
                  height: 26,
                  decoration: BoxDecoration(
                    color: color,
                    shape: BoxShape.circle,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
