// «التكاملات»: tile groups, chips and sheets from the kit. Lonora's counterpart of apps/web
// IntegrationsPage.tsx (its order: trading accounts → AI → servers and repositories → news and
// channels → skills) with the Expo app's trusted sources (remove / restore), built-in capabilities
// and other integrations (apps/mobile app/(settings)/integrations.tsx), plus the saved workspace
// secrets by name. Nothing here carries money authority: there is no global trading switch; each
// agent's Mandate is in its settings.
import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/core/values.dart' show truthy;
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../../state/realtime.dart';
import 'integrations/broker_pages.dart';
import 'integrations/channel_sheets.dart';
import 'integrations/ext_common.dart';
import 'integrations/integrations_data.dart';
import 'integrations/mcp_pages.dart';
import 'integrations/providers_page.dart';
import 'integrations/sources_sheet.dart';
import 'settings_common.dart';

class IntegrationsScreen extends StatefulWidget {
  const IntegrationsScreen({super.key});

  @override
  State<IntegrationsScreen> createState() => _IntegrationsScreenState();
}

class _IntegrationsScreenState extends State<IntegrationsScreen>
    with CoverAware {
  CapabilityReport? _report;
  List<BrokerConnection>? _connections;
  List<ProviderStatus>? _providers;
  List<Json>? _secrets;
  Object? _error;

  /// Why each read failed on its last attempt (null once it answers): a section that has
  /// nothing to show says so with a retry instead of looking empty.
  Object? _reportError;
  Object? _connectionsError;
  Object? _providersError;
  bool _busy = false;
  StreamSubscription<LonoraEvent>? _events;
  Timer? _debounce;

  /// Only the latest reading is shown.
  int _serial = 0;

  /// Something changed while another page covered this one: read again once it is back.
  bool _stale = false;

  /// Event kinds that change what this page lists (lonora-api-contract §4.6).
  static bool _relevant(String kind) =>
      kind.startsWith('trusted_source.') ||
      kind.startsWith('integrations.') ||
      kind.startsWith('mcp.') ||
      kind.startsWith('skill') ||
      kind == 'broker_identity.updated';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    try {
      _events = realtime.events.listen((e) {
        if (!_relevant(e.kind)) return;
        _debounce?.cancel();
        _debounce = Timer(const Duration(milliseconds: 400), () {
          if (onTop) {
            unawaited(_load());
          } else {
            _stale = true;
          }
        });
      });
    } catch (_) {
      // No realtime controller (previews): the page still reads on open and on refresh.
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    unawaited(_events?.cancel());
    super.dispose();
  }

  @override
  void onUncovered() {
    if (!_stale) return;
    _stale = false;
    unawaited(_load());
  }

  /// Each read is tolerated on its own; the page fails only when none answered. [pulled]:
  /// the owner pulled to refresh, so a read that failed while its last answer is still on
  /// screen is said in a toast.
  Future<void> _load({bool pulled = false}) async {
    final mine = ++_serial;
    Future<Object?> attempt(Future<Object?> Function() read) async {
      try {
        return await read();
      } on SessionRequestCancelled {
        return null;
      } catch (e) {
        return _Failed(e);
      }
    }

    final results = await Future.wait([
      attempt(fetchCapabilities),
      attempt(fetchConnections),
      attempt(fetchProviders),
      attempt(fetchSecrets),
    ]);
    if (!mounted || mine != _serial) return;
    final failures = results.whereType<_Failed>().toList();
    Object? failed(int i) =>
        results[i] is _Failed ? (results[i]! as _Failed).error : null;
    final stale = [
      if (failed(0) != null && _report != null) failed(0),
      if (failed(1) != null && _connections != null) failed(1),
      if (failed(2) != null && _providers != null) failed(2),
      if (failed(3) != null && _secrets != null) failed(3),
    ];
    setState(() {
      if (results[0] case final CapabilityReport r) _report = r;
      if (results[1] case final List<BrokerConnection> c) _connections = c;
      if (results[2] case final List<ProviderStatus> p) _providers = p;
      if (results[3] case final List<Json> s) _secrets = s;
      _reportError = failed(0);
      _connectionsError = failed(1);
      _providersError = failed(2);
      _error = failures.length == results.length ? failures.first.error : null;
    });
    if (pulled && stale.isNotEmpty) showErrorToast(context, stale.first!);
  }

  Future<void> _act(Future<void> Function() action, {String? done}) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
      if (mounted && done != null) {
        LnToast.show(context, done, kind: LnToastKind.positive);
      }
      await _load();
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openBroker(String id) async {
    final unlinked = await pushSettingsPage<String>(
      context,
      BrokerAccountPage(connectionId: id),
    );
    if (unlinked == null || !mounted) return;
    LnToast.show(context, unlinked, kind: LnToastKind.positive);
    await _load();
  }

  Future<void> _linkBroker() async {
    final id = await pushSettingsPage<String>(context, const BrokerFormPage());
    if (id == null || !mounted) return;
    LnToast.show(
      context,
      context.t('ix_accountLinked'),
      kind: LnToastKind.positive,
    );
    unawaited(_load());
    await _openBroker(id);
  }

  Future<void> _addMcp() async {
    final added = await pushSettingsPage<bool>(context, const McpFormPage());
    if (added != true || !mounted) return;
    LnToast.show(
      context,
      context.t('ix_serverAdded'),
      kind: LnToastKind.positive,
    );
    await _load();
  }

  Future<void> _openMcp(Json server) async {
    final done = await showMcpSheet(
      context,
      server: server,
      source: _report?.sourceOf(server),
    );
    if (done == null || !mounted) return;
    LnToast.show(context, done, kind: LnToastKind.positive);
    await _load();
  }

  Future<void> _openTelegram(Json? telegram, List<Agent> agents) async {
    final done = await showTelegramSheet(
      context,
      telegram: telegram,
      agents: agents,
    );
    if (done == null || !mounted) return;
    LnToast.show(context, done, kind: LnToastKind.positive);
    await _load();
  }

  Future<void> _undoSkill(Json skill) async {
    final name = isolate(asString(skill['title']) ?? asStr(skill['skill_id']));
    final ok = await showLnConfirm(
      context,
      title: context.t('ix_undoVersionQ'),
      message: [
        name,
        if (skill['version'] != null)
          context.t('ix_version', [isolate(asStr(skill['version']))]),
      ].join(dotSeparator),
      confirmLabel: capabilityText(context.l10n.lang).undo,
      cancelLabel: context.t('sh_cancel'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    await _act(
      () => undoSkillVersion(skill),
      done: context.t('ix_versionUndone'),
    );
  }

  Future<void> _removeIntegration(Json item) async {
    final name = integrationLine(item, context.l10n.lang);
    final ok = await showLnConfirm(
      context,
      title: context.t('ix_removeQ', [isolate(asStr(item['name']))]),
      message: name,
      confirmLabel: capabilityText(context.l10n.lang).remove,
      cancelLabel: context.t('sh_cancel'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    await _act(() => removeIntegration(asStr(item['id'])));
  }

  Future<void> _openSources(List<Json> sources) async {
    await showTrustedSourcesSheet(context, sources);
    if (mounted) await _load();
  }

  Future<void> _deleteSecret(Json secret) async {
    final name = isolate(asStr(secret['name']));
    final ok = await showLnConfirm(
      context,
      title: context.t('ix_deleteSecretQ', [name]),
      message: context.t('ix_deleteSecretBody'),
      confirmLabel: context.t('sh_delete'),
      cancelLabel: context.t('sh_cancel'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    await _act(
      () => deleteSecret(asStr(secret['id'])),
      done: context.t('ix_secretDeleted', [name]),
    );
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final title = context.t('integrations');
    final report = _report;
    if (report == null && _connections == null && _providers == null) {
      return SettingsPageScaffold(
        title: title,
        body: _error == null
            ? const PageLoading(groups: [2, 2, 3])
            : LoadFailure(error: _error!, onRetry: _load),
      );
    }
    final lang = context.l10n.lang;
    final text = capabilityText(lang);
    final c = context.ln.colors;
    final agents = context.select((AppState s) => s.shell.agents);
    final orderedAgents = context.select((AppState s) => s.shell.orderedAgents);
    final connections = _connections ?? const <BrokerConnection>[];
    final configured = (_providers ?? const <ProviderStatus>[])
        .where((p) => p.configured)
        .length;
    final chevron = Icon(FIcons.chevronRight, color: c.chevron);
    final domains = report?.feedDomains ?? const <Json>[];
    final feeds = report?.feeds ?? const <Json>[];
    final telegram = report?.telegram;
    final telegramAgent = asString(telegram?['deliver_to_agent_name']);
    final skills = report?.skills ?? const <Json>[];
    final others = report?.otherIntegrations ?? const <Json>[];
    final secrets = _secrets ?? const <Json>[];

    final sources = report?.trustedSources ?? const <Json>[];
    final removedSources = sources.where((s) => !asBool(s['active'])).length;

    return SettingsPageScaffold(
      title: title,
      onRefresh: () => _load(pulled: true),
      children: [
        SettingsNote(context.t('ix_intro')),
        // Trading accounts.
        LnSection(
          title: context.t('ix_tradingAccounts'),
          children: [
            if (_connections == null && _connectionsError != null)
              _failureTile(context, _connectionsError!),
            ...connectionTiles(
              context,
              connections,
              agents,
              (row) => _openBroker(row.id),
            ),
            LnListTile(
              icon: FIcons.plus,
              title: context.t(
                connections.isEmpty ? 'ix_linkAccount' : 'ix_addAccount',
              ),
              enabled: _connections != null,
              onTap: _linkBroker,
            ),
          ],
        ),
        const SectionGap(),
        // Artificial intelligence.
        LnSection(
          title: context.t('ix_ai'),
          children: [
            LnListTile(
              icon: FIcons.cpu,
              title: context.t('ix_modelProviders'),
              value: _providers == null
                  ? null
                  : configured > 0
                  ? '$configured'
                  : context.t('ix_notAddedYet'),
              onTap: () async {
                await pushSettingsPage<void>(context, const ProvidersPage());
                if (mounted) await _load();
              },
            ),
            LnListTile(
              icon: FIcons.slidersHorizontal,
              // The models page's own title, as the Me row names it.
              title: context.t('models'),
              onTap: () => context.push(Routes.models),
            ),
            if (_providers == null && _providersError != null)
              _failureTile(context, _providersError!),
          ],
        ),
        const SectionGap(),
        if (report == null && _reportError != null)
          LnSection(children: [_failureTile(context, _reportError!)]),
        if (report != null) ...[
          // Servers and repositories.
          LnSection(
            title: context.t('ix_servers'),
            children: [
              // Every trusted source, removed ones included, to remove or restore (Expo).
              WrapTile(
                icon: FIcons.shieldCheck,
                title: text.trustedSources,
                subtitle: removedSources == 0
                    ? null
                    : context.t('ix_removedCount', [removedSources]),
                trailing: _CountChevron(count: sources.length - removedSources),
                onTap: () => _openSources(sources),
              ),
              for (final s in report.githubSources)
                WrapTile(
                  icon: FIcons.gitBranch,
                  title: ltr(asString(s['label']) ?? asStr(s['identifier'])),
                  subtitle:
                      'GitHub · ${context.t('ix_addedOn', [_addedOn(s['created_at'], lang)])}',
                  trailing: StatusChip(
                    label: context.t('ix_trusted'),
                    kind: StatusChipKind.success,
                    icon: FIcons.check,
                  ),
                ),
              for (final server in report.mcpServers)
                _mcpTile(context, server, report, chevron),
              LnListTile(
                icon: FIcons.plus,
                title: context.t('ix_addMcp'),
                onTap: _addMcp,
              ),
            ],
          ),
          const SectionGap(),
          // News and channels.
          LnSection(
            title: context.t('ix_newsChannels'),
            children: [
              WrapTile(
                icon: FIcons.globe,
                title: context.t('ix_newsDomains'),
                subtitle: domains.isEmpty
                    ? null
                    : ltr(
                        [
                              for (final d in domains.take(3))
                                asStr(d['identifier']),
                            ].join(dotSeparator) +
                            (domains.length > 3 ? ' …' : ''),
                      ),
                trailing: _CountChevron(count: domains.length),
                onTap: () async {
                  await showDomainsSheet(context, domains);
                  if (mounted) await _load();
                },
              ),
              WrapTile(
                icon: FIcons.rss,
                title: context.t('ix_rssFeeds'),
                subtitle: feeds.isEmpty
                    ? context.t('ix_noFeeds')
                    : [for (final f in feeds) isolate(asStr(f['name']))]
                          .join(dotSeparator),
                trailing: _CountChevron(count: feeds.length),
                onTap: () async {
                  await showFeedsSheet(context, feeds);
                  if (mounted) await _load();
                },
              ),
              WrapTile(
                icon: FIcons.send,
                title: 'Telegram',
                subtitle: telegram == null
                    ? context.t('ix_telegramNotLinked')
                    : telegramAgent != null
                    ? context.t('ix_telegramLinkedTo', [isolate(telegramAgent)])
                    : context.t('ix_telegramLinked'),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (telegram != null)
                      StatusChip(
                        label: context.t('ix_linked'),
                        kind: StatusChipKind.success,
                        icon: FIcons.check,
                      )
                    else
                      Text(
                        context.t('ix_link'),
                        style: context.ln.text.body.copyWith(color: c.fgMuted),
                      ),
                    const SizedBox(width: LnSpace.xxs),
                    chevron,
                  ],
                ),
                onTap: () => _openTelegram(telegram, orderedAgents),
              ),
            ],
          ),
          const SectionGap(),
          // Skills.
          LnSection(
            title: context.t('ix_skills'),
            children: [
              if (skills.isEmpty)
                WrapTile(title: context.t('ix_noSkills'))
              else
                for (final skill in skills) _skillTile(context, skill),
            ],
          ),
          const SectionGap(),
          // What agents can use without any setup (the Expo app's list).
          LnSection(
            title: text.builtIn,
            footer: text.intro,
            children: [
              for (final item in report.builtIn)
                WrapTile(
                  icon: item['state'] == 'ready'
                      ? FIcons.circleCheck
                      : FIcons.circleDashed,
                  title:
                      text[asStr(item['capability'])] ??
                      asStr(item['capability']),
                  trailing: StatusChip(
                    label: text[asStr(item['state'])] ?? asStr(item['state']),
                    kind: item['state'] == 'ready'
                        ? StatusChipKind.success
                        : StatusChipKind.neutral,
                  ),
                ),
            ],
          ),
          if (others.isNotEmpty) ...[
            const SectionGap(),
            LnSection(
              title: text.integrations,
              children: [
                for (final item in others)
                  WrapTile(
                    icon: FIcons.plug,
                    title: _integrationName(item, lang),
                    subtitle: sentenceStart(_integrationState(item, lang)),
                    trailing: PillButton(
                      label: text.remove,
                      destructive: true,
                      onTap: _busy ? null : () => _removeIntegration(item),
                    ),
                  ),
              ],
            ),
          ],
        ],
        if (secrets.isNotEmpty) ...[
          const SectionGap(),
          LnSection(
            title: context.t('ix_secrets'),
            footer: context.t('ix_secretsNote'),
            children: [
              for (final s in secrets)
                WrapTile(
                  icon: FIcons.keyRound,
                  title: ltr(asStr(s['name'])),
                  subtitle: _addedOn(s['updated_at'], lang).isEmpty
                      ? null
                      : _addedOn(s['updated_at'], lang),
                  trailing: _IconAction(
                    icon: FIcons.trash2,
                    label: context.t('ix_deleteSecret', [asStr(s['name'])]),
                    onTap: _busy ? null : () => _deleteSecret(s),
                  ),
                ),
            ],
          ),
        ],
      ],
    );
  }

  /// A section's read failed and it has nothing to show: the reason and a retry.
  WrapTile _failureTile(BuildContext context, Object error) => WrapTile(
    icon: FIcons.triangleAlert,
    title: errorMessage(context, error) ?? context.t('request_failed'),
    trailing: PillButton(label: context.t('retry'), onTap: _load),
  );

  WrapTile _mcpTile(
    BuildContext context,
    Json server,
    CapabilityReport report,
    Widget chevron,
  ) {
    final review = asBool(report.sourceOf(server)?['needs_review']);
    final tier = asString(server['trusted_tier']);
    final name = asString(server['name']);
    final levels = mcpLevelText(context.l10n, server);
    return WrapTile(
      icon: FIcons.server,
      title: name == null || name.isEmpty
          ? context.t('ix_unnamedServer')
          : ltr(name),
      subtitle: context.t('ix_mcpServerLine', [
        isolate(levels.isEmpty ? context.t('ix_noTools') : levels),
      ]),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (review)
            StatusChip(
              label: context.t('ix_reviewNeeded'),
              kind: StatusChipKind.waiting,
              icon: FIcons.refreshCw,
            )
          else if (tier != null)
            StatusChip(
              label: context.t('ix_trusted'),
              kind: StatusChipKind.success,
              icon: FIcons.check,
            )
          else
            StatusChip(label: context.t('ix_notApproved')),
          const SizedBox(width: LnSpace.xxs),
          chevron,
        ],
      ),
      onTap: () => _openMcp(server),
    );
  }

  WrapTile _skillTile(BuildContext context, Json skill) {
    final title = asString(skill['title']);
    final version = asString(skill['version']);
    final agent = asString(skill['agent_name']);
    final bundled = skill['provenance'] == 'bundled';
    final active = asBool(skill['enabled']) && !asBool(skill['undone']);
    final canUndo =
        asBool(skill['can_undo']) &&
        !asBool(skill['undone']) &&
        skill['agent_id'] != null &&
        version != null;
    return WrapTile(
      icon: FIcons.zap,
      enabled: active || canUndo,
      title: title != null ? isolate(title) : ltr(asStr(skill['skill_id'])),
      subtitle: [
        if (bundled)
          context.t('ix_builtInSkill')
        else
          asString(skill['repository']) == null
              ? context.t('ix_owner')
              : ltr(asStr(skill['repository'])),
        if (version != null) context.t('ix_version', [isolate(version)]),
        if (agent != null) isolate(agent),
      ].join(dotSeparator),
      trailing: canUndo
          ? PillButton(
              label: capabilityText(context.l10n.lang).undo,
              semanticLabel: context.t('ix_undoVersion'),
              onTap: _busy ? null : () => _undoSkill(skill),
            )
          : null,
    );
  }

  /// «27 نوفمبر 2026» in the owner's language (the Web's `addedOn`); '' when unknown.
  static String _addedOn(Object? iso, String lang) {
    final date = asDate(iso);
    return date == null
        ? ''
        : isolate(formatDate('d MMMM y', lang, date.toLocal()));
  }
}

/// The on/off state [integrationLine] ends with (the same truthiness).
String _integrationState(Json item, String lang) {
  final text = capabilityText(lang);
  return truthy(item['enabled']) ? text.on : text.off;
}

/// [integrationLine] without the on/off state it ends with (the row's subtitle shows it);
/// «Unnamed» when the line is the state alone.
String _integrationName(Json item, String lang) {
  final state = _integrationState(item, lang);
  final line = integrationLine(item, lang);
  final suffix = '$dotSeparator$state';
  if (line == state) return capabilityText(lang).unnamed;
  return line.endsWith(suffix)
      ? line.substring(0, line.length - suffix.length)
      : line;
}

class _Failed {
  const _Failed(this.error);
  final Object error;
}

class _CountChevron extends StatelessWidget {
  const _CountChevron({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('$count', style: ln.text.body.copyWith(color: ln.colors.fgMuted)),
        const SizedBox(width: LnSpace.xxs),
        Icon(FIcons.chevronRight, color: ln.colors.chevron),
      ],
    );
  }
}

class _IconAction extends StatelessWidget {
  const _IconAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  // Its own button node with the tap action (as PillButton): the label sits on the tappable.
  @override
  Widget build(BuildContext context) => LnTappable(
    onTap: onTap,
    enabled: onTap != null,
    semanticLabel: label,
    child: ExcludeSemantics(
      child: SizedBox.square(
        dimension: 48,
        child: Icon(icon, color: context.ln.colors.error),
      ),
    ),
  );
}
