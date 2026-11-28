// Shared pieces of the integrations, models, usage and running pages (WP-A2), built from the
// kit's tiles, chips and buttons only.
import 'package:flutter/material.dart' show MaterialPageRoute;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../models/models_strings.dart';
import '../running/running_strings.dart';
import '../settings_common.dart';
import '../usage/usage_strings.dart';
import '../../trading/trading_strings.dart';
import 'integrations_strings.dart';

/// Registers the labels of these pages (and the core settings ones) once per catalog.
void ensureExtStrings(BuildContext context) {
  ensureCoreSettingsStrings(context);
  final l10n = context.l10n;
  registerIntegrationsStrings(l10n);
  registerModelsStrings(l10n);
  registerUsageStrings(l10n);
  registerRunningStrings(l10n);
  registerTradingStrings(l10n);
}

/// Opens a sub-page that has no path of its own (a provider's key, a trading account, a
/// form) on the root navigator, with the app's page transition (predictive back).
Future<T?> pushSettingsPage<T>(BuildContext context, Widget page) =>
    Navigator.of(
      context,
      rootNavigator: true,
    ).push<T>(MaterialPageRoute<T>(builder: (_) => page));

/// Whether no other page, sheet or dialog covers this page (the Expo app's focus effect, the
/// Web's hidden-document pause): background reads wait while it is covered, and
/// [onUncovered] runs once it is on top again.
mixin CoverAware<T extends StatefulWidget> on State<T> {
  bool _onTop = true;

  /// This page is the top route of its navigator.
  bool get onTop => _onTop;

  /// What covered the page is gone.
  void onUncovered() {}

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final onTop = ModalRoute.isCurrentOf(context) ?? true;
    final back = onTop && !_onTop;
    _onTop = onTop;
    // After this frame: the page may read again or change its state then.
    if (back) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _onTop) onUncovered();
      });
    }
  }
}

/// The page gutter around a block (fields, buttons, cards) between tile groups.
class Gutter extends StatelessWidget {
  const Gutter({super.key, required this.child, this.bottom = 0});

  final Widget child;
  final double bottom;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsetsDirectional.fromSTEB(
      LnSpace.pageGutter,
      0,
      LnSpace.pageGutter,
      bottom,
    ),
    child: child,
  );
}

/// A small stadium button at the end of a row ("Stop", "Undo"), 32 dp tall inside a 48 dp
/// touch target.
class PillButton extends StatelessWidget {
  const PillButton({
    super.key,
    required this.label,
    required this.onTap,
    this.semanticLabel,
    this.destructive = false,
  });

  final String label;
  final VoidCallback? onTap;
  final String? semanticLabel;
  final bool destructive;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final enabled = onTap != null;
    final fg = !enabled
        ? c.fgSubtle
        : destructive
        ? c.error
        : c.fg;
    // Its own button node with the tap action: the label sits on the tappable itself (an outer
    // Semantics(excludeSemantics) would drop the tappable's action and merge into the row).
    return LnTappable(
      onTap: onTap,
      enabled: enabled,
      semanticLabel: semanticLabel ?? label,
      child: ExcludeSemantics(
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 48, minWidth: 48),
          child: Center(
            widthFactor: 1,
            child: Container(
              constraints: const BoxConstraints(minHeight: LnSize.chipHeight),
              padding: const EdgeInsets.symmetric(horizontal: LnSpace.sm),
              decoration: BoxDecoration(
                color: c.fill2,
                borderRadius: const BorderRadius.all(
                  Radius.circular(LnRadius.stadium),
                ),
              ),
              // Centred in the chip height, however tall the text scale makes it.
              child: Center(
                widthFactor: 1,
                heightFactor: 1,
                child: Text(
                  label,
                  maxLines: 1,
                  style: ln.text.footnoteStrong.copyWith(color: fg),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Which of a form's two requests is running: only its own button spins.
enum FormAction { test, save }

/// The outcome of «Test the connection»: a check or an alert with the server's words.
class TestResultLine extends StatelessWidget {
  const TestResultLine({super.key, required this.ok, required this.text});

  final bool ok;
  final String text;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Semantics(
      liveRegion: true,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            ok ? FIcons.circleCheck : FIcons.circleAlert,
            size: 18,
            color: ok ? c.success : c.error,
          ),
          const SizedBox(width: LnSpace.xs),
          Expanded(
            child: Text(text, style: ln.text.footnote.copyWith(color: c.fg)),
          ),
        ],
      ),
    );
  }
}

/// A stored secret: a lock and dots, never its value (write-only; the server never returns it).
class MaskedSecret extends StatelessWidget {
  const MaskedSecret({super.key, required this.caption});

  final String caption;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return Container(
      padding: const EdgeInsets.all(LnSpace.md),
      decoration: BoxDecoration(
        color: c.fill1,
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.field)),
      ),
      child: Row(
        children: [
          Icon(FIcons.lock, size: 20, color: c.fgMuted),
          const SizedBox(width: LnSpace.sm),
          Text(
            '••••••••••••',
            textDirection: TextDirection.ltr,
            style: ln.text.body.copyWith(color: c.fg, letterSpacing: 1),
          ),
          const SizedBox(width: LnSpace.sm),
          Expanded(
            child: Text(
              caption,
              textAlign: TextAlign.end,
              style: ln.text.footnote.copyWith(color: c.fgMuted),
            ),
          ),
        ],
      ),
    );
  }
}

/// A write-only secret input: obscured, no suggestions or autofill, with a show/hide eye.
/// The value lives only in [controller]; callers clear it once it is sent.
class SecretField extends StatefulWidget {
  const SecretField({
    super.key,
    required this.controller,
    required this.label,
    this.helper,
    this.hint,
    this.enabled = true,
    this.showToggle = true,
  });

  final TextEditingController controller;
  final String label;
  final String? helper;
  final String? hint;
  final bool enabled;
  final bool showToggle;

  @override
  State<SecretField> createState() => _SecretFieldState();
}

class _SecretFieldState extends State<SecretField> {
  bool _shown = false;

  @override
  Widget build(BuildContext context) => LnTextField(
    controller: widget.controller,
    label: widget.label,
    helper: widget.helper,
    hint: widget.hint,
    enabled: widget.enabled,
    obscureText: !_shown,
    // visiblePassword keeps the keyboard from learning the key while it is shown.
    keyboardType: TextInputType.visiblePassword,
    autocorrect: false,
    enableSuggestions: false,
    enableIMEPersonalizedLearning: false,
    textDirection: TextDirection.ltr,
    // A hint in the interface language stays under its label.
    hintTextDirection: Directionality.of(context),
    inputFormatters: [FilteringTextInputFormatter.deny(RegExp(r'[\n\r]'))],
    suffix: widget.showToggle
        // The label and state sit on the tappable's own node, which keeps its tap action.
        ? LnTappable(
            onTap: () => setState(() => _shown = !_shown),
            semanticLabel: context.t(_shown ? 'ix_hideKey' : 'ix_showKey'),
            child: Semantics(
              toggled: _shown,
              child: ExcludeSemantics(
                child: SizedBox.square(
                  dimension: 48,
                  child: Icon(_shown ? FIcons.eyeOff : FIcons.eye),
                ),
              ),
            ),
          )
        : null,
  );
}

/// A centred spinner while a sub-page loads (the settings skeleton for lists).
class PageLoading extends StatelessWidget {
  const PageLoading({super.key, this.groups = const [3, 2]});

  final List<int> groups;

  @override
  Widget build(BuildContext context) => ListView(
    physics: const NeverScrollableScrollPhysics(),
    children: [SettingsSkeleton(groups: groups)],
  );
}
