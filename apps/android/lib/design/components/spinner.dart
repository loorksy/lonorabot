import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';

/// Small ring spinner: forui's [FProgress.circularIcon] (rotating Lucide loader-circle). Colour defaults
/// to the ambient [IconTheme] (so it matches a button's label inside [FButton]).
class LnSpinner extends StatelessWidget {
  const LnSpinner({super.key, this.size = 20, this.color, this.semanticLabel});

  final double size;
  final Color? color;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) => FProgress.circularIcon(
    semanticsLabel: semanticLabel,
    style: (s) => s.copyWith(size: size, color: color ?? s.color),
  );
}
