// A stacked sheet that holds a form (create an agent, create a group): the kit's stacked sheet
// whose drag-to-close is on only while the form has nothing to lose. A drag closes the sheet
// without asking, so once [dirty] is true only ✕ and back close it, through the form's
// PopScope and its discard question.
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart'
    show InputBorder, InputDecoration, Material, MaterialType, TextField;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../design/design.dart';
import '../../l10n/l10n.dart';

/// Pushes [builder] in a stacked sheet on the root navigator; a downward drag closes it while
/// [dirty] is false. Completes with the value the sheet is popped with.
Future<T?> showFormSheet<T>(
  BuildContext context, {
  required ValueListenable<bool> dirty,
  required WidgetBuilder builder,
  bool showHandle = false,
}) => Navigator.of(context, rootNavigator: true).push<T>(
  FormSheetRoute<T>(
    dirty: dirty,
    builder: builder,
    showHandle: showHandle,
    theme: context.ln,
  ),
);

/// The route of [showFormSheet].
class FormSheetRoute<T> extends LnStackedSheetRoute<T> {
  FormSheetRoute({
    required this.dirty,
    required super.builder,
    super.showHandle,
    super.theme,
  });

  /// Whether the form holds edits a drag would drop.
  final ValueListenable<bool> dirty;

  @override
  bool get enableDrag => !dirty.value;

  // The transition's drag detector reads [enableDrag] when the transitions build, and they
  // rebuild only on animation ticks: rebuild them whenever [dirty] changes.
  @override
  void install() {
    super.install();
    dirty.addListener(changedInternalState);
  }

  @override
  void dispose() {
    dirty.removeListener(changedInternalState);
    super.dispose();
  }
}

/// A one-line stadium field on the 4 % fill ([LnPalette.fill1]), [height] tall (54 dp),
/// the hint in the tertiary ink. Its text reads in its own direction.
class StadiumField extends StatelessWidget {
  const StadiumField({
    super.key,
    required this.controller,
    required this.hint,
    this.enabled = true,
    this.textAlign = TextAlign.start,
    this.maxLength,
    this.textInputAction,
    this.onSubmitted,
    this.onChanged,
    this.height = 54,
  });

  final TextEditingController controller;
  final String hint;
  final bool enabled;
  final TextAlign textAlign;
  final int? maxLength;
  final TextInputAction? textInputAction;
  final ValueChanged<String>? onSubmitted;

  /// Called for the owner's own edits only (not when the text is set by code).
  final ValueChanged<String>? onChanged;
  final double height;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final ambient = Directionality.of(context);
    return Container(
      height: height,
      padding: const EdgeInsets.symmetric(horizontal: 20),
      alignment: Alignment.center,
      decoration: ShapeDecoration(color: c.fill1, shape: const StadiumBorder()),
      child: Material(
        type: MaterialType.transparency,
        child: ValueListenableBuilder<TextEditingValue>(
          valueListenable: controller,
          builder: (context, value, _) => TextField(
            controller: controller,
            enabled: enabled,
            maxLines: 1,
            textAlign: textAlign,
            textCapitalization: TextCapitalization.sentences,
            textInputAction: textInputAction,
            onSubmitted: onSubmitted,
            onChanged: onChanged,
            textDirection: textDirectionFor(value.text, ambient),
            inputFormatters: [
              if (maxLength != null)
                LengthLimitingTextInputFormatter(maxLength),
            ],
            style: ln.text.body.copyWith(color: c.fg),
            cursorColor: c.brand,
            // The field fills the stadium's height, so the whole stadium is its touch band.
            decoration: InputDecoration(
              isCollapsed: true,
              filled: false,
              border: InputBorder.none,
              contentPadding: EdgeInsets.symmetric(vertical: (height - 24) / 2),
              hintText: hint,
              hintStyle: ln.text.body.copyWith(color: c.fgSubtle),
            ),
          ),
        ),
      ),
    );
  }
}
