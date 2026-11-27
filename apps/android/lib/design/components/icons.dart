import 'package:flutter/widgets.dart';

/// Lucide icons that point along the reading direction, so they flip in right-to-left layouts (as
/// Material mirrors its undo, reply, log-out and list glyphs). forui_assets 0.15 sets
/// `matchTextDirection` only on its arrows and chevrons; these are the same `FIcons` glyphs with it
/// set, so every widget that draws an [Icon] mirrors them in RTL: `LnListTile(icon: LnIcons.logOut)`,
/// `Icon(LnIcons.undo2)`. Lonora-specific.
///
/// [IconData] equality includes `matchTextDirection`, so `find.byIcon(FIcons.undo2)` does not find
/// `LnIcons.undo2`: a test that switches with its screen must look for the `LnIcons` value (a
/// leftover `findsNothing` on the `FIcons` one would pass whatever is shown).
@staticIconProvider
abstract final class LnIcons {
  static const _family = 'ForuiLucideIcons';
  static const _package = 'forui_assets';

  /// `FIcons.list`.
  static const list = IconData(
    57612,
    fontFamily: _family,
    fontPackage: _package,
    matchTextDirection: true,
  );

  /// `FIcons.listChecks`.
  static const listChecks = IconData(
    57808,
    fontFamily: _family,
    fontPackage: _package,
    matchTextDirection: true,
  );

  /// `FIcons.listTodo`.
  static const listTodo = IconData(
    58568,
    fontFamily: _family,
    fontPackage: _package,
    matchTextDirection: true,
  );

  /// `FIcons.logOut`.
  static const logOut = IconData(
    57618,
    fontFamily: _family,
    fontPackage: _package,
    matchTextDirection: true,
  );

  /// `FIcons.reply`.
  static const reply = IconData(
    57898,
    fontFamily: _family,
    fontPackage: _package,
    matchTextDirection: true,
  );

  /// `FIcons.undo2`.
  static const undo2 = IconData(
    58017,
    fontFamily: _family,
    fontPackage: _package,
    matchTextDirection: true,
  );
}
