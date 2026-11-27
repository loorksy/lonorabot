// Small pieces shared by the sign-in, server and connect screens. Composed from the kit.
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons, FTheme;

import '../../design/design.dart';
import '../../l10n/l10n.dart';

enum AuthNoticeKind { error, info }

/// An inline notice above a form's button: error (red) or information (muted).
class AuthNotice extends StatelessWidget {
  const AuthNotice({
    super.key,
    required this.text,
    this.kind = AuthNoticeKind.error,
  });

  final String text;
  final AuthNoticeKind kind;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final error = kind == AuthNoticeKind.error;
    final accent = error ? c.error : c.fgMuted;
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsetsDirectional.fromSTEB(14, 12, 14, 12),
        decoration: BoxDecoration(
          color: error
              ? c.error.withValues(alpha: c.isDark ? 0.16 : 0.08)
              : c.fill2,
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.field)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 1),
              child: Icon(
                error ? FIcons.circleAlert : FIcons.info,
                size: 18,
                color: accent,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                text,
                style: ln.text.caption.copyWith(color: error ? c.error : c.fg),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A password (or setup token) field: obscured, with a show/hide eye unless [revealable] is
/// false. The screen clears the value after use.
class SecretField extends StatefulWidget {
  const SecretField({
    super.key,
    required this.controller,
    required this.label,
    this.autofillHints,
    this.textInputAction,
    this.onSubmitted,
    this.onChanged,
    this.enabled = true,
    this.ltr = false,
    this.revealable = true,
    this.focusNode,
  });

  final TextEditingController controller;
  final FocusNode? focusNode;
  final String label;
  final Iterable<String>? autofillHints;
  final TextInputAction? textInputAction;
  final ValueChanged<String>? onSubmitted;
  final ValueChanged<String>? onChanged;
  final bool enabled;

  /// Codes, tokens and the sign-in password: the box (text, eye at the right) is laid out left to
  /// right under a label that keeps the interface direction. The typed text of every secret reads
  /// left to right.
  final bool ltr;

  /// Whether the eye can show the value (false for server secrets such as the setup token).
  final bool revealable;

  @override
  State<SecretField> createState() => _SecretFieldState();
}

class _SecretFieldState extends State<SecretField> {
  bool _visible = false;

  @override
  Widget build(BuildContext context) {
    final field = LnTextField(
      controller: widget.controller,
      focusNode: widget.focusNode,
      label: widget.ltr ? null : widget.label,
      obscureText: !_visible,
      enabled: widget.enabled,
      keyboardType: TextInputType.visiblePassword,
      autocorrect: false,
      enableSuggestions: false,
      enableIMEPersonalizedLearning: false,
      textDirection: TextDirection.ltr,
      autofillHints: widget.autofillHints,
      textInputAction: widget.textInputAction,
      onSubmitted: widget.onSubmitted,
      onChanged: widget.onChanged,
      inputFormatters: [FilteringTextInputFormatter.deny(RegExp(r'[\n\r]'))],
      suffix: !widget.revealable
          ? null
          : LnTappable(
              onTap: () => setState(() => _visible = !_visible),
              semanticLabel: context.t(
                _visible ? 'auth_hidePassword' : 'auth_showPassword',
              ),
              // ExcludeSemantics, not excludeChildSemantics: that would drop the tap action.
              // 48 dp wide and as tall as the field allows (the kit's field is 40 dp).
              child: ExcludeSemantics(
                child: SizedBox(
                  width: 48,
                  height: 40,
                  child: Icon(_visible ? FIcons.eyeOff : FIcons.eye),
                ),
              ),
            ),
    );
    if (!widget.ltr) return field;
    return LtrField(label: widget.label, child: field);
  }
}

/// A field whose text reads left to right (address, email, token) under a label that keeps
/// the interface direction. Give [child] an [LnTextField] without its own label.
class LtrField extends StatelessWidget {
  const LtrField({super.key, required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final style = FTheme.of(context).textFieldStyle;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: style.labelPadding,
          child: Text(label, style: style.labelTextStyle.resolve(const {})),
        ),
        Directionality(textDirection: TextDirection.ltr, child: child),
      ],
    );
  }
}
