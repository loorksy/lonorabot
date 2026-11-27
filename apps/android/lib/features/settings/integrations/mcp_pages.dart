// MCP servers: the review/approve sheet and «إضافة MCP», built from the sheet, tile groups, fields
// and block buttons. Lonora's counterparts of apps/web IntegrationsPage.tsx `mcpSheet` /
// ConnectionPages.tsx `McpFormPage` and apps/mobile app/(settings)/integrations.tsx (review →
// preview → trust read / write_nonfinancial). A server is never given a financial tool; one with a
// blocked money tool is trusted to read only (the Expo rule). Remote Streamable HTTP servers only.
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../core/json.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../settings_common.dart';
import 'ext_common.dart';
import 'integrations_data.dart';

/// Opens a server's tools and trust actions. Completes with the toast text of what was done
/// (approved, stopped), or null.
Future<String?> showMcpSheet(
  BuildContext context, {
  required Json server,
  Json? source,
}) {
  final name = asString(server['name']);
  return showLnSheet<String>(
    context,
    title: name == null || name.isEmpty
        ? context.t('ix_unnamedServer')
        : ltr(name),
    builder: (_) => _McpSheet(server: server, source: source),
  );
}

class _McpSheet extends StatefulWidget {
  const _McpSheet({required this.server, required this.source});

  final Json server;
  final Json? source;

  @override
  State<_McpSheet> createState() => _McpSheetState();
}

class _McpSheetState extends State<_McpSheet> {
  Json? _preview;
  bool _busy = false;

  /// The tool titles read once from a server trusted before its titles were kept.
  Json? _readTitles;

  String get _connectionId => asStr(widget.server['connection_id']);
  bool get _review => asBool(widget.source?['needs_review']);
  String? get _tier => asString(widget.server['trusted_tier']);

  @override
  void initState() {
    super.initState();
    // A server trusted before its tool titles were kept (and that is on) is read once for
    // them, so its saved tools show their titles; a failure leaves the names
    // (apps/web IntegrationsPage.tsx `McpToolRows`).
    final server = widget.server;
    if (asStringList(server['trusted_tools']).isNotEmpty &&
        asBool(server['enabled']) &&
        !asBool(server['tool_titles_kept'])) {
      previewMcp(_connectionId).then((preview) {
        if (mounted && _preview == null) {
          setState(() => _readTitles = asJson(preview['titles']));
        }
      }, onError: (Object _) {});
    }
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _fetch() => _run(() async {
    final preview = await previewMcp(_connectionId);
    if (mounted) setState(() => _preview = preview);
  });

  Future<void> _trust(String tier) => _run(() async {
    final preview = _preview ?? await previewMcp(_connectionId);
    await trustMcp(_connectionId, tier, asStr(preview['digest']));
    if (!mounted) return;
    Navigator.of(context)
        .pop(context.t(_review ? 'ix_schemaApproved' : 'ix_serverApproved'));
  });

  Future<void> _stop() async {
    final sourceId = asString(widget.server['trust_source_id']);
    if (sourceId == null) return;
    final ok = await showLnConfirm(
      context,
      title: context.t('ix_stopServerQ'),
      message: context.t('ix_mcpNote'),
      confirmLabel: context.t('running_stop'),
      cancelLabel: context.t('sh_cancel'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    await _run(() async {
      await setSourceActive(sourceId, active: false);
      if (mounted) Navigator.of(context).pop(context.t('ix_serverStopped'));
    });
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final ln = context.ln;
    final c = ln.colors;
    final preview = _preview;
    final server = widget.server;
    final tools = preview != null
        ? [
            for (final name in asStringList(preview['tools']))
              (
                name: name,
                write: asStringList(preview['writes']).contains(name),
              ),
          ]
        : [
            for (final name in asStringList(server['trusted_tools']))
              (
                name: name,
                write: asStringList(server['write_tools']).contains(name),
              ),
          ];
    final titles = preview != null
        ? asJson(preview['titles'])
        : {...asJson(server['tool_titles']), ...?_readTitles};
    final blocked = asStringList(preview?['blocked']);
    final writes = tools.any((t) => t.write);
    final lang = context.l10n.lang;
    String title(String name) => toolTitle(titles, name) ?? name;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_review)
            Padding(
              padding: const EdgeInsets.only(bottom: LnSpace.md),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(FIcons.refreshCw, size: 18, color: c.warning),
                  const SizedBox(width: LnSpace.xs),
                  Expanded(
                    child: Text(
                      context.t('ix_schemaChanged'),
                      style: ln.text.footnote.copyWith(color: c.fg),
                    ),
                  ),
                ],
              ),
            ),
          LnSection(
            padding: EdgeInsets.zero,
            title: context.t('ix_toolsLevels'),
            children: [
              if (tools.isEmpty)
                WrapTile(
                  title: context.t(
                    preview != null || _tier != null
                        ? 'ix_noToolsDot'
                        : 'ix_fetchTools',
                  ),
                )
              else
                for (final t in tools)
                  WrapTile(
                    icon: t.write ? FIcons.pencil : FIcons.eye,
                    title: toolTitle(titles, t.name) != null
                        ? isolate(title(t.name))
                        : ltr(t.name),
                    trailing: StatusChip(
                      label: context.t(
                        t.write ? 'ix_nonFinancialWrite' : 'ix_read',
                      ),
                      kind: t.write
                          ? StatusChipKind.waiting
                          : StatusChipKind.neutral,
                    ),
                  ),
            ],
          ),
          if (blocked.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: LnSpace.sm),
              child: Text(
                context.t('ix_blockedTools', [
                  blocked
                      .map((n) => isolate(title(n)))
                      .join(listSeparator(lang)),
                ]),
                style: ln.text.footnote.copyWith(color: c.fgMuted),
              ),
            ),
          const SizedBox(height: LnSpace.md),
          if (preview == null && (_tier == null || _review))
            BlockButton(
              label: context.t('ix_reviewTools'),
              variant: BlockButtonVariant.secondary,
              loading: _busy,
              onPressed: _busy ? null : _fetch,
            ),
          if (preview != null) ...[
            BlockButton(
              label: context.t(
                _review ? 'ix_approveSchema' : 'ix_approveServer',
              ),
              loading: _busy,
              onPressed: _busy || tools.isEmpty ? null : () => _trust('read'),
            ),
            // A server with a blocked money tool is trusted to read only.
            if (writes && blocked.isEmpty) ...[
              const SizedBox(height: LnSpace.sm),
              BlockButton(
                label: context.t('ix_approveWrites'),
                variant: BlockButtonVariant.secondary,
                onPressed: _busy ? null : () => _trust('write_nonfinancial'),
              ),
            ],
          ],
          if (server['trust_source_id'] != null &&
              (_tier != null || _review)) ...[
            const SizedBox(height: LnSpace.sm),
            BlockButton(
              label: context.t('ix_stopServer'),
              variant: BlockButtonVariant.destructive,
              onPressed: _busy ? null : _stop,
            ),
          ],
          const SizedBox(height: LnSpace.md),
          Text(
            context.t('ix_mcpNote'),
            style: ln.text.footnote.copyWith(color: c.fgMuted),
          ),
        ],
      ),
    );
  }
}

/// «إضافة MCP»: name, https address, no auth or an access token (stored as a secret first),
/// «Test the connection» (lists the tools, stores nothing) and «Add the server». Pops `true`
/// once added; the server then waits as «Not approved» until its tools are reviewed.
class McpFormPage extends StatefulWidget {
  const McpFormPage({super.key});

  @override
  State<McpFormPage> createState() => _McpFormPageState();
}

class _McpFormPageState extends State<McpFormPage> {
  final _name = TextEditingController();
  final _url = TextEditingController();
  final _token = TextEditingController();
  bool _withToken = false;
  ({bool ok, String text})? _test;
  FormAction? _running;

  bool get _busy => _running != null;

  @override
  void dispose() {
    _name.dispose();
    _url.dispose();
    _token
      ..clear()
      ..dispose();
    super.dispose();
  }

  bool _check() {
    String? problem;
    if (_name.text.trim().isEmpty) {
      problem = 'ix_enterServerName';
    } else if (!RegExp(r'^https://\S+').hasMatch(_url.text.trim())) {
      problem = 'ix_invalidLink';
    } else if (_withToken && _token.text.trim().isEmpty) {
      problem = 'ix_enterToken';
    }
    if (problem != null) {
      LnToast.show(context, context.t(problem), kind: LnToastKind.notice);
    }
    return problem == null;
  }

  String? get _tokenValue => _withToken ? _token.text.trim() : null;

  Future<void> _runTest() async {
    if (!_check() || _busy) return;
    setState(() {
      _running = FormAction.test;
      _test = null;
    });
    try {
      final result = await testMcp(_url.text.trim(), _tokenValue);
      if (mounted) {
        setState(
          () => _test = (
            ok: true,
            text: context.t('ix_mcpWorks', [
              asStringList(result['tools']).length,
            ]),
          ),
        );
      }
    } catch (e) {
      final text = mounted ? errorMessage(context, e) : null;
      if (mounted && text != null) {
        setState(() => _test = (ok: false, text: text));
      }
    } finally {
      if (mounted) setState(() => _running = null);
    }
  }

  Future<void> _add() async {
    if (!_check() || _busy) return;
    setState(() => _running = FormAction.save);
    try {
      await addMcp(
        name: _name.text.trim(),
        url: _url.text.trim(),
        token: _tokenValue,
      );
      _token.clear();
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _running = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final test = _test;
    return SettingsPageScaffold(
      title: context.t('ix_addMcpTitle'),
      children: [
        Gutter(
          bottom: LnSpace.md,
          child: LnTextField(
            controller: _name,
            label: context.t('ix_serverName'),
            hint: context.t('ix_serverNameHint'),
            enabled: !_busy,
            inputFormatters: [LengthLimitingTextInputFormatter(80)],
          ),
        ),
        LnSection(
          children: [
            LnListTile(
              title: context.t('ix_connectionType'),
              value: ltr('Streamable HTTP'),
            ),
          ],
        ),
        const SizedBox(height: LnSpace.md),
        Gutter(
          bottom: LnSpace.md,
          child: LnTextField(
            controller: _url,
            label: context.t('ix_serverAddress'),
            hint: 'https://mcp.example.com/mcp',
            enabled: !_busy,
            keyboardType: TextInputType.url,
            autocorrect: false,
            textDirection: TextDirection.ltr,
          ),
        ),
        LnSection(
          title: context.t('ix_authentication'),
          children: [
            ChoiceTile(
              title: context.t('ix_noAuth'),
              selected: !_withToken,
              onSelect: () => setState(() => _withToken = false),
            ),
            ChoiceTile(
              title: context.t('ix_accessToken'),
              selected: _withToken,
              onSelect: () => setState(() => _withToken = true),
            ),
          ],
        ),
        const SizedBox(height: LnSpace.md),
        if (_withToken)
          Gutter(
            bottom: LnSpace.md,
            child: SecretField(
              controller: _token,
              label: context.t('ix_accessTokenField'),
              enabled: !_busy,
            ),
          ),
        if (test != null)
          Gutter(
            bottom: LnSpace.md,
            child: TestResultLine(ok: test.ok, text: test.text),
          ),
        Gutter(
          bottom: LnSpace.sm,
          child: BlockButton(
            label: context.t('ix_testConnection'),
            variant: BlockButtonVariant.secondary,
            loading: _running == FormAction.test,
            onPressed: _busy ? null : _runTest,
          ),
        ),
        Gutter(
          bottom: LnSpace.lg,
          child: BlockButton(
            label: context.t('ix_addServer'),
            loading: _running == FormAction.save,
            onPressed: _busy ? null : _add,
          ),
        ),
        SettingsNote(context.t('ix_remoteOnly')),
      ],
    );
  }
}
