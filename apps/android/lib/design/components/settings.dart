// Settings building blocks: thin conveniences over forui's own widgets with forui's default styling
// under the Lonora theme. (LnTextField is the one exception: see its doc comment.)
import 'dart:math' as math;

import 'package:flutter/material.dart'
    show
        InputDecoration,
        Material,
        MaterialType,
        TextField,
        WidgetStateInputBorder;
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

import '../theme.dart';
import '../tokens.dart';

/// A titled group of [LnListTile]s: forui [FTileGroup] with an optional label and description.
class LnSection extends StatelessWidget {
  const LnSection({
    super.key,
    this.title,
    required this.children,
    this.footer,
    this.padding,
  });

  final String? title;
  final List<FTileMixin> children;

  /// Muted note below the group.
  final String? footer;

  /// Defaults to the 16 dp page gutter.
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) => Padding(
    padding:
        padding ??
        const EdgeInsetsDirectional.symmetric(horizontal: LnSpace.pageGutter),
    child: FTileGroup(
      label: title == null ? null : Text(title!),
      description: footer == null ? null : Text(footer!),
      children: children,
    ),
  );
}

/// Settings row on forui [FTile]: optional leading icon, title/subtitle, trailing value + chevron, or a
/// custom trailing widget such as [LnSwitch]. [destructive] colours the title and icon with the error
/// colour. A one-line row is at least [LnSize.minTouch] tall; taller rows keep forui's metrics.
class LnListTile extends StatelessWidget with FTileMixin {
  const LnListTile({
    super.key,
    required this.title,
    this.subtitle,
    this.icon,
    this.value,
    this.trailing,
    this.onTap,
    this.showChevron,
    this.destructive = false,
    this.enabled,
    this.trailingIsAction = false,
  });

  final String title;
  final String? subtitle;
  final IconData? icon;

  /// Muted trailing value ("English", "Dark"), shown in forui's details slot.
  final String? value;

  /// Custom trailing widget (e.g. [LnSwitch]); replaces the chevron. It reads as part of the row
  /// unless [trailingIsAction].
  final Widget? trailing;
  final VoidCallback? onTap;

  /// Defaults to true when [onTap] is set and there is no [trailing] widget.
  final bool? showChevron;
  final bool destructive;
  final bool? enabled;

  /// [trailing] is an action of its own (Remove, Stop): it stays a separate accessibility node instead
  /// of merging into the row's. Leave false for a status, a chevron or a switch the row also toggles.
  final bool trailingIsAction;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    final chevron =
        showChevron ?? (onTap != null && trailing == null && !destructive);
    final titleText = Text(
      title,
      style: destructive ? TextStyle(color: c.error) : null,
    );
    return FTile(
      enabled: enabled,
      onPress: onTap,
      prefix: icon == null
          ? null
          : Icon(icon, color: destructive ? c.error : null),
      title: subtitle != null ? titleText : MinTouchTileTitle(child: titleText),
      subtitle: subtitle == null ? null : Text(subtitle!),
      details: value == null ? null : Text(value!),
      suffix: trailing != null
          ? (trailingIsAction
                ? Semantics(container: true, child: trailing)
                : trailing)
          // Lucide chevrons mirror themselves in RTL (matchTextDirection).
          : (chevron ? const Icon(FIcons.chevronRight) : null),
    );
  }
}

/// The title of a one-line [FTile] (no subtitle), lifted to [LnSize.minTouch]: forui centres every
/// slot on the tallest one, so a minimum on the title inside the tile's padding (the group's style, as
/// FTile uses) lifts the whole row to the touch-target height. Taller titles keep their own height.
class MinTouchTileTitle extends StatelessWidget {
  const MinTouchTileTitle({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final style =
        FInheritedItemData.maybeOf(context)?.style ??
        FTheme.of(context).tileStyle;
    final padding = style.contentStyle.padding.resolve(
      Directionality.of(context),
    );
    return ConstrainedBox(
      constraints: BoxConstraints(
        minHeight: LnSize.minTouch - padding.vertical,
      ),
      child: Align(
        alignment: AlignmentDirectional.centerStart,
        widthFactor: 1,
        heightFactor: 1,
        child: child,
      ),
    );
  }
}

/// forui [FSwitch] (themed by `lnForuiTheme`).
class LnSwitch extends StatelessWidget {
  const LnSwitch({
    super.key,
    required this.value,
    required this.onChanged,
    this.semanticLabel,
    this.enabled = true,
  });

  final bool value;
  final ValueChanged<bool>? onChanged;
  final String? semanticLabel;
  final bool enabled;

  @override
  Widget build(BuildContext context) => FSwitch(
    value: value,
    onChange: onChanged,
    enabled: enabled && onChanged != null,
    semanticsLabel: semanticLabel,
  );
}

/// Labelled text field styled by forui's `FTextFieldStyle` (the ambient `context.theme.textFieldStyle`:
/// fill, per-state borders, paddings, label/description/error text styles).
///
/// Built on Material's [TextField] rather than forui's `FTextField`: forui 0.15.1 wraps its field in
/// `MergeSemantics` with an `InputDecoration.prefix`, which trips a Flutter 3.47 semantics assertion
/// (`node.isMergedIntoParent`) on every edit while accessibility is on.
///
/// The field box keeps forui's height; a tap up to [LnSize.minTouch] / 2 from its centre line still
/// reaches it (a band laid out above and below a shorter box, like Material's padded tap target).
class LnTextField extends StatelessWidget {
  const LnTextField({
    super.key,
    this.controller,
    this.label,
    this.hint,
    this.helper,
    this.error,
    this.prefix,
    this.suffix,
    this.obscureText = false,
    this.enabled = true,
    this.autofocus = false,
    this.maxLines = 1,
    this.minLines,
    this.keyboardType,
    this.textInputAction,
    this.inputFormatters,
    this.autofillHints,
    this.onChanged,
    this.onSubmitted,
    this.focusNode,
    this.textCapitalization = TextCapitalization.none,
    this.autocorrect = true,
    this.enableSuggestions = true,
    this.enableIMEPersonalizedLearning = true,
    this.textDirection,
    this.hintTextDirection,
    this.maxLength,
  });

  final TextEditingController? controller;
  final String? label;
  final String? hint;
  final String? helper;
  final String? error;
  final Widget? prefix;
  final Widget? suffix;
  final bool obscureText;
  final bool enabled;
  final bool autofocus;
  final int? maxLines;
  final int? minLines;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  final List<TextInputFormatter>? inputFormatters;
  final Iterable<String>? autofillHints;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final FocusNode? focusNode;
  final TextCapitalization textCapitalization;

  /// Pass false for secrets, addresses and identifiers.
  final bool autocorrect;
  final bool enableSuggestions;
  final bool enableIMEPersonalizedLearning;

  /// Direction of the typed text and, unless [hintTextDirection] is given, the hint (e.g. ltr for a
  /// URL, key or account in Arabic); the label, notes and icons follow the interface.
  final TextDirection? textDirection;

  /// Direction of the hint; defaults to [textDirection]. Pass the interface direction to keep a hint
  /// in the interface language under its label while the typed text reads [textDirection].
  final TextDirection? hintTextDirection;

  /// Stops input at this many characters (no counter is shown).
  final int? maxLength;

  @override
  Widget build(BuildContext context) {
    final style = FTheme.of(context).textFieldStyle;
    final states = <WidgetState>{
      if (!enabled) WidgetState.disabled,
      if (error != null) WidgetState.error,
    };
    Widget? slot(Widget? child, EdgeInsetsGeometry padding) => child == null
        ? null
        : Padding(
            padding: padding,
            child: IconTheme.merge(
              data: IconThemeData(size: 18, color: context.ln.colors.fgMuted),
              child: child,
            ),
          );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (label != null)
          Padding(
            padding: style.labelPadding,
            child: Text(label!, style: style.labelTextStyle.resolve(states)),
          ),
        _TouchBand(
          child: Material(
            type: MaterialType.transparency,
            child: TextField(
              controller: controller,
              focusNode: focusNode,
              enabled: enabled,
              autofocus: autofocus,
              obscureText: obscureText,
              maxLines: obscureText ? 1 : maxLines,
              minLines: minLines,
              keyboardType: keyboardType,
              textInputAction: textInputAction,
              inputFormatters: inputFormatters,
              autofillHints: autofillHints,
              textCapitalization: textCapitalization,
              autocorrect: autocorrect,
              enableSuggestions: enableSuggestions,
              enableIMEPersonalizedLearning: enableIMEPersonalizedLearning,
              textDirection: textDirection,
              maxLength: maxLength,
              onChanged: onChanged,
              onSubmitted: onSubmitted,
              style: style.contentTextStyle.resolve(states),
              cursorColor: style.cursorColor,
              keyboardAppearance: style.keyboardAppearance,
              scrollPadding: style.scrollPadding,
              decoration: InputDecoration(
                isDense: true,
                contentPadding: style.contentPadding,
                hintText: hint,
                hintTextDirection: hintTextDirection ?? textDirection,
                counterText: maxLength == null ? null : '',
                hintStyle: WidgetStateTextStyle.resolveWith(
                  style.hintTextStyle.resolve,
                ),
                filled: style.filled,
                fillColor: style.fillColor,
                border: WidgetStateInputBorder.resolveWith(
                  style.border.resolve,
                ),
                prefixIcon: slot(
                  prefix,
                  const EdgeInsetsDirectional.only(start: 12, end: 8),
                ),
                prefixIconConstraints: const BoxConstraints(),
                suffixIcon: slot(
                  suffix,
                  const EdgeInsetsDirectional.only(start: 8, end: 12),
                ),
                suffixIconConstraints: const BoxConstraints(),
                // Triggers the error border; the message is rendered below with forui's error style.
                error: error == null ? null : const SizedBox.shrink(),
              ),
            ),
          ),
        ),
        if (error != null)
          Padding(
            padding: style.errorPadding,
            child: Text(error!, style: style.errorTextStyle),
          )
        else if (helper != null)
          Padding(
            padding: style.descriptionPadding,
            child: Text(
              helper!,
              style: style.descriptionTextStyle.resolve(states),
            ),
          ),
      ],
    );
  }
}

/// Centres [child] in a band at least [LnSize.minTouch] tall and hands a pointer that lands in the
/// band to the child at the nearest point inside it, so a shorter field box keeps its look and still
/// has a 48 dp touch target.
class _TouchBand extends SingleChildRenderObjectWidget {
  const _TouchBand({required Widget super.child});

  @override
  RenderObject createRenderObject(BuildContext context) => _RenderTouchBand();
}

class _RenderTouchBand extends RenderShiftedBox {
  _RenderTouchBand() : super(null);

  Size _bandSize(BoxConstraints constraints, Size child) => constraints
      .constrain(Size(child.width, math.max(child.height, LnSize.minTouch)));

  @override
  Size computeDryLayout(BoxConstraints constraints) => _bandSize(
    constraints,
    child!.getDryLayout(constraints.copyWith(minHeight: 0)),
  );

  @override
  double? computeDryBaseline(
    BoxConstraints constraints,
    TextBaseline baseline,
  ) {
    final childConstraints = constraints.copyWith(minHeight: 0);
    final childBaseline = child!.getDryBaseline(childConstraints, baseline);
    if (childBaseline == null) return null;
    final childSize = child!.getDryLayout(childConstraints);
    return childBaseline +
        (_bandSize(constraints, childSize).height - childSize.height) / 2;
  }

  @override
  double computeMinIntrinsicHeight(double width) =>
      math.max(super.computeMinIntrinsicHeight(width), LnSize.minTouch);

  @override
  double computeMaxIntrinsicHeight(double width) =>
      math.max(super.computeMaxIntrinsicHeight(width), LnSize.minTouch);

  @override
  void performLayout() {
    final child = this.child!;
    child.layout(constraints.copyWith(minHeight: 0), parentUsesSize: true);
    size = _bandSize(constraints, child.size);
    (child.parentData! as BoxParentData).offset = Offset(
      0,
      (size.height - child.size.height) / 2,
    );
  }

  @override
  bool hitTestChildren(BoxHitTestResult result, {required Offset position}) {
    final child = this.child!;
    final offset = (child.parentData! as BoxParentData).offset;
    final inside = Offset(
      position.dx,
      position.dy.clamp(
        offset.dy,
        offset.dy + math.max(0.0, child.size.height - 1),
      ),
    );
    return result.addWithPaintOffset(
      offset: offset + position - inside,
      position: position,
      hitTest: (result, transformed) =>
          child.hitTest(result, position: transformed),
    );
  }
}

/// One option of an [LnSegmented] control.
@immutable
class LnSegment<T> {
  const LnSegment({required this.value, required this.label});

  final T value;
  final String label;
}

/// Segmented control on forui [FTabs] (tab bar only, no content area).
class LnSegmented<T> extends StatefulWidget {
  const LnSegmented({
    super.key,
    required this.segments,
    required this.selected,
    required this.onChanged,
  }) : assert(segments.length >= 2);

  final List<LnSegment<T>> segments;
  final T selected;
  final ValueChanged<T> onChanged;

  @override
  State<LnSegmented<T>> createState() => _LnSegmentedState<T>();
}

class _LnSegmentedState<T> extends State<LnSegmented<T>>
    with SingleTickerProviderStateMixin {
  late final FTabController _controller = FTabController(
    length: widget.segments.length,
    vsync: this,
    initialIndex: _index,
  );

  int get _index => widget.segments
      .indexWhere((s) => s.value == widget.selected)
      .clamp(0, widget.segments.length - 1);

  @override
  void didUpdateWidget(LnSegmented<T> old) {
    super.didUpdateWidget(old);
    if (_controller.index != _index) _controller.animateTo(_index);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FTabs(
    controller: _controller,
    // Selected-segment fill: white in light, 24 % white over the track in dark (forui's page
    // colour would sit darker than the track).
    style: (s) => s.copyWith(
      spacing: 0,
      indicatorDecoration: s.indicatorDecoration.copyWith(
        color: context.ln.colors.segmentedSelected,
      ),
    ),
    onPress: (i) => widget.onChanged(widget.segments[i].value),
    children: [
      for (final s in widget.segments)
        FTabEntry(label: Text(s.label), child: const SizedBox.shrink()),
    ],
  );
}
