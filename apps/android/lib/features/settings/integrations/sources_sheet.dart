// «المصادر الموثوقة»: every trusted source, active or removed, each with Remove (asks first) or
// Restore. Built from the sheet, a tile group and pill buttons.
// Lonora's counterpart of the trusted sources group of apps/mobile app/(settings)/
// integrations.tsx (`sourceLine`, `POST /trusted-sources/{id}/revoke|restore`). A source only
// lets agents read or install from it without asking; none carries money authority.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../core/json.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../settings_common.dart';
import 'ext_common.dart';
import 'integrations_data.dart';

/// Opens the list of [sources] (the capability report's). Completes when closed; the caller
/// reads the page again.
Future<void> showTrustedSourcesSheet(
  BuildContext context,
  List<Json> sources,
) => showLnSheet<void>(
  context,
  title: capabilityText(context.l10n.lang).trustedSources,
  builder: (_) => _SourcesSheet(initial: sources),
);

/// A source as the owner knows it: the GitHub default by its kind, others by label or
/// identifier.
String trustedSourceName(Json source, String lang) {
  final text = capabilityText(lang);
  if (source['kind'] == 'github') return text.github;
  final name = asString(source['label']) ?? asString(source['identifier']);
  return name == null || name.isEmpty ? text.unnamed : isolate(name);
}

class _SourcesSheet extends StatefulWidget {
  const _SourcesSheet({required this.initial});

  final List<Json> initial;

  @override
  State<_SourcesSheet> createState() => _SourcesSheetState();
}

class _SourcesSheetState extends State<_SourcesSheet> {
  late List<Json> _list = widget.initial;
  bool _busy = false;

  Future<void> _toggle(Json source) async {
    final lang = context.l10n.lang;
    final text = capabilityText(lang);
    final active = asBool(source['active']);
    if (active) {
      final ok = await showLnConfirm(
        context,
        title: context.t('ix_removeQ', [trustedSourceName(source, lang)]),
        message: sourceLine(source, lang),
        confirmLabel: text.remove,
        cancelLabel: context.t('sh_cancel'),
        destructive: true,
      );
      if (!ok || !mounted) return;
    }
    setState(() => _busy = true);
    try {
      await setSourceActive(asStr(source['id']), active: !active);
      final report = await fetchCapabilities();
      if (mounted) setState(() => _list = report.trustedSources);
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final lang = context.l10n.lang;
    final text = capabilityText(lang);
    return SingleChildScrollView(
      child: LnSection(
        padding: EdgeInsets.zero,
        children: [
          if (_list.isEmpty)
            WrapTile(title: text.none)
          else
            for (final s in _list)
              WrapTile(
                icon: switch (asStr(s['kind'])) {
                  'mcp_server' => FIcons.server,
                  'feed_domain' => FIcons.globe,
                  _ => FIcons.gitBranch,
                },
                title: trustedSourceName(s, lang),
                subtitle: sourceLine(s, lang),
                trailing: asBool(s['active'])
                    ? PillButton(
                        label: text.remove,
                        semanticLabel: context.t('ix_removeX', [
                          trustedSourceName(s, lang),
                        ]),
                        destructive: true,
                        onTap: _busy ? null : () => _toggle(s),
                      )
                    : PillButton(
                        label: text.restore,
                        semanticLabel: context.t('ix_restoreX', [
                          trustedSourceName(s, lang),
                        ]),
                        onTap: _busy ? null : () => _toggle(s),
                      ),
              ),
        ],
      ),
    );
  }
}
