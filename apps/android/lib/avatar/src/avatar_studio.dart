// Embeddable avatar studio body: live preview, face grid and shell colours. Port of the
// content of apps/mobile/components/avatar-picker.tsx:197-310 without its modal, Save,
// Cancel and Reset chrome, which belong to the screen that embeds it.
import 'package:flutter/material.dart' show Theme;
import 'package:flutter/widgets.dart';

import '../../design/tokens.dart';
import 'avatar_colors.dart';
import 'avatar_faces.dart';
import 'lonora_avatar.dart';
import 'motion.dart' show resolveAvatarFace;

class AvatarStudioGrid extends StatelessWidget {
  const AvatarStudioGrid({
    super.key,
    required this.agentId,
    required this.face,
    required this.color,
    required this.onFaceChanged,
    required this.onColorChanged,
    this.enabled = true,
    this.previewSize = 126,
    this.palette,
  });

  /// Seeds the preview's personality (and colour when [color] is empty).
  final String agentId;

  /// The draft face id and shell colour hex.
  final String face;
  final String color;
  final ValueChanged<String> onFaceChanged;

  /// Receives the palette hex (e.g. `#8B5CF6`), the value `Agent.color` stores.
  final ValueChanged<String> onColorChanged;
  final bool enabled;

  /// Live preview size; 0 hides the preview.
  final double previewSize;

  /// Colours of labels and selection; defaults follow the theme brightness.
  final LnPalette? palette;

  @override
  Widget build(BuildContext context) {
    final colors =
        palette ??
        (Theme.of(context).brightness == Brightness.dark
            ? LnPalette.dark
            : LnPalette.light);
    final arabic = avatarIsArabic(context);
    final locale = Localizations.maybeLocaleOf(context);
    final selectedFace = resolveAvatarFace(face);
    final shell = resolveAvatarColor(agentId, color).color;
    final base = DefaultTextStyle.of(context).style;
    final heading = base.copyWith(
      color: colors.fgMuted,
      fontSize: 12,
      fontWeight: FontWeight.w600,
    );
    final colorLabel = arabic ? 'اللون' : 'Color';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (previewSize > 0)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: LnSpace.xs),
            child: Center(
              child: LonoraAvatar(
                agentId: agentId,
                face: selectedFace,
                color: color,
                size: previewSize,
              ),
            ),
          ),
        Container(
          padding: const EdgeInsets.only(bottom: LnSpace.xs),
          margin: const EdgeInsets.only(top: LnSpace.md, bottom: LnSpace.md),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: colors.border)),
          ),
          child: Text(arabic ? 'الوجه' : 'Face', style: heading),
        ),
        LayoutBuilder(
          builder: (context, constraints) {
            final cell = constraints.maxWidth / 4;
            return Wrap(
              runSpacing: LnSpace.xs,
              children: [
                for (final option in avatarFaces)
                  SizedBox(
                    width: cell,
                    child: _FaceCell(
                      agentId: agentId,
                      faceId: option.id,
                      label: option.label(locale),
                      color: color,
                      shell: shell,
                      selected: option.id == selectedFace,
                      enabled: enabled,
                      colors: colors,
                      style: base,
                      onTap: () => onFaceChanged(option.id),
                    ),
                  ),
              ],
            );
          },
        ),
        Container(
          padding: const EdgeInsets.only(top: 18),
          margin: const EdgeInsets.only(top: 18, bottom: LnSpace.md),
          decoration: BoxDecoration(
            border: Border(top: BorderSide(color: colors.border)),
          ),
          child: Text(colorLabel, style: heading),
        ),
        Wrap(
          spacing: 9,
          runSpacing: 9,
          children: [
            for (final option in avatarPalette)
              _Swatch(
                value: option.hex,
                label: '$colorLabel ${option.hex}',
                selected: option.hex.toLowerCase() == color.toLowerCase(),
                enabled: enabled,
                ring: colors.fg,
                onTap: () => onColorChanged(option.hex),
              ),
          ],
        ),
      ],
    );
  }
}

class _FaceCell extends StatelessWidget {
  const _FaceCell({
    required this.agentId,
    required this.faceId,
    required this.label,
    required this.color,
    required this.shell,
    required this.selected,
    required this.enabled,
    required this.colors,
    required this.style,
    required this.onTap,
  });

  final String agentId;
  final String faceId;
  final String label;
  final String color;
  final Color shell;
  final bool selected;
  final bool enabled;
  final LnPalette colors;
  final TextStyle style;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      inMutuallyExclusiveGroup: true,
      checked: selected,
      enabled: enabled,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: enabled ? onTap : null,
        child: Container(
          constraints: const BoxConstraints(minHeight: 86),
          margin: const EdgeInsets.symmetric(horizontal: 3),
          decoration: BoxDecoration(
            color: selected ? colors.fill2 : null,
            borderRadius: BorderRadius.circular(15),
            border: Border.all(
              color: selected ? shell : const Color(0x00000000),
            ),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              LonoraAvatar(
                agentId: agentId,
                face: faceId,
                color: color,
                size: 48,
                animate: false,
              ),
              const SizedBox(height: 5),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2),
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: style.copyWith(
                    fontSize: 10,
                    color: selected ? colors.fg : colors.fgMuted,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Swatch extends StatelessWidget {
  const _Swatch({
    required this.value,
    required this.label,
    required this.selected,
    required this.enabled,
    required this.ring,
    required this.onTap,
  });

  final String value;
  final String label;
  final bool selected;
  final bool enabled;
  final Color ring;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      inMutuallyExclusiveGroup: true,
      checked: selected,
      enabled: enabled,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: enabled ? onTap : null,
        child: Container(
          width: 44,
          height: 44,
          padding: const EdgeInsets.all(5),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              width: 2,
              color: selected ? ring : const Color(0x00000000),
            ),
          ),
          child: DecoratedBox(
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: avatarHexColor(value),
            ),
          ),
        ),
      ),
    );
  }
}
