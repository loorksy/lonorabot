// Notifications and contact, built from forui tile groups; option sets from Lonora:
// apps/mobile/components/incoming-call-settings.tsx and apps/web NotifyPages.tsx (reach-me
// channel, the device a call rings, call switches, this phone's in-app banner and text
// preview, quiet hours to the minute, "urgent always arrives", confirmed-opportunity alerts)
// and the Web's «Per agent» list, which opens each agent's own delivery rules
// (`GET /agents/notifications`). Each choice saves at once, as the Web does. The Web's «Sounds»
// has no switch here: Android sets a notification's sound per channel, in the phone's settings.
//
// Android specifics: the phone's own notification permission (permission_handler, the platform
// channel's `openNotificationSettings`), and an honest note on delivery: the server pushes only
// through Expo, so this app shows alerts while open and from background checks when closed.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/prefs_actions.dart'
    show SetNotifyPrefsAction, platformChannel;
import '../../state/app_state.dart';
import '../me/me_data.dart';
import 'settings_common.dart';
import 'settings_core_data.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

/// «22:00» from minutes after local midnight.
String clockOfMinutes(int minutes) {
  String two(int v) => v.toString().padLeft(2, '0');
  return '${two(minutes ~/ 60)}:${two(minutes % 60)}';
}

class _NotificationsScreenState extends State<NotificationsScreen>
    with WidgetsBindingObserver {
  OwnerProfileData? _profile;
  AttentionPolicy? _attention;

  /// Agent id → its delivery rules (`in_app` false: its messages raise no alert).
  Json? _agentRules;
  Object? _error;
  PermissionStatus? _permission;
  bool _saving = false;
  bool _savingAttention = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_load());
    unawaited(_readPermission());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  /// Back from the phone's settings: the permission may have changed there.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_readPermission());
  }

  Future<void> _load() async {
    final attention = fetchAttentionPolicy()
        .then<AttentionPolicy?>((v) => v)
        .catchError((Object _) => null);
    final agentRules = fetchAgentAlertRules()
        .then<Json?>((v) => v)
        .catchError((Object _) => null);
    try {
      final profile = await fetchOwnerProfile();
      final policy = await attention;
      final rules = await agentRules;
      if (mounted) {
        setState(() {
          _profile = profile;
          _attention = policy ?? _attention;
          _agentRules = rules ?? _agentRules;
          _error = null;
        });
      }
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (!mounted) return;
      // A failed refresh keeps what is shown and says why.
      if (_profile != null) {
        showErrorToast(context, e);
      } else {
        setState(() => _error = e);
      }
    }
  }

  Future<void> _readPermission() async {
    try {
      final status = await Permission.notification.status;
      if (mounted) setState(() => _permission = status);
    } catch (_) {
      // No permission plugin on this host: the row stays neutral.
    }
  }

  Future<void> _phoneNotifications() async {
    final status = _permission;
    if (status != null && status.isDenied) {
      final next = await Permission.notification.request();
      if (mounted) setState(() => _permission = next);
      if (!next.isPermanentlyDenied) return;
    }
    var opened = false;
    try {
      opened =
          await platformChannel.invokeMethod<bool>(
            'openNotificationSettings',
          ) ??
          false;
    } catch (_) {
      opened = false;
    }
    if (!opened) await openAppSettings();
  }

  /// Saves the reach-me policy with [patch] (`PUT /owner/preferences {reach_me}`).
  Future<void> _saveReach(Json patch) async {
    final profile = _profile;
    if (profile == null || _saving || !mounted) return;
    setState(() => _saving = true);
    try {
      final next = await saveOwnerPreferences({
        'reach_me': reachMeWith(profile.reachMe, patch),
      });
      if (mounted) setState(() => _profile = next);
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _chooseChannel(String channel) {
    final profile = _profile!;
    final device = profile.deviceId;
    final enrolled = profile.devices.any((d) => d.id == device);
    return _saveReach({
      'channel': channel,
      // Choosing calls means being called when a decision is needed (Expo), on the chosen
      // enrolled device or else the most recent one.
      if (channel == 'call') 'action_required': true,
      if (channel == 'call' && !enrolled) 'device_id': profile.devices.first.id,
    });
  }

  /// Quiet hours to the minute; the hour fields follow (Web NotifyPages `setWindow`).
  Future<void> _setQuiet(int? start, int? end) async {
    if (!mounted) return;
    if (start != null && start == end) {
      LnToast.show(
        context,
        context.t('set_quietSame'),
        kind: LnToastKind.notice,
      );
      return;
    }
    final zone = await deviceTimeZone();
    await _saveReach({
      'quiet_start_minute': start,
      'quiet_end_minute': end,
      'quiet_start_hour': start == null ? null : start ~/ 60,
      'quiet_end_hour': end == null ? null : end ~/ 60,
      'timezone': ?zone,
    });
  }

  Future<void> _pickQuietTime({required bool start}) async {
    final profile = _profile!;
    final current =
        (start ? profile.quietStartMinute : profile.quietEndMinute) ??
        (start ? 22 * 60 : 8 * 60);
    final picked = await showLnSheet<int>(
      context,
      title: context.t(start ? 'set_from' : 'set_to'),
      builder: (_) => _TimeSheet(minutes: current),
    );
    if (picked == null || picked == current) return;
    await _setQuiet(
      start ? picked : profile.quietStartMinute,
      start ? profile.quietEndMinute : picked,
    );
  }

  Future<void> _setOpportunities(bool on) async {
    final current = _attention;
    if (current == null || _savingAttention) return;
    final locale = context.l10n.lang;
    setState(() => _savingAttention = true);
    try {
      final next = await saveAttentionPolicy(
        AttentionPolicy(
          opportunities: on,
          informational: current.informational,
          locale: locale,
        ),
      );
      if (mounted) setState(() => _attention = next);
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _savingAttention = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    final lang = context.l10n.lang;
    final profile = _profile;
    String label(String key) => ownerProfileLabel(key, lang);
    Widget? body;
    if (profile == null) {
      body = _error != null
          ? LoadFailure(error: _error!, onRetry: _load)
          : const SettingsSkeleton(groups: [1, 3, 2]);
    }
    return SettingsPageScaffold(
      title: context.t('notificationsAndContact'),
      onRefresh: () async {
        await Future.wait([_load(), _readPermission()]);
      },
      body: body,
      children: profile == null ? const [] : _sections(profile, label),
    );
  }

  List<Widget> _sections(
    OwnerProfileData profile,
    String Function(String) label,
  ) {
    final lang = context.l10n.lang;
    final c = context.ln.colors;
    final permission = _permission;
    final allowed =
        permission != null &&
        (permission.isGranted || permission.isProvisional);
    final hasDevices = profile.devices.isNotEmpty;
    final call = profile.channel == 'call';
    final attention = _attention;
    final agentRules = _agentRules;
    final (order, byId) = context.select(
      (AppState s) => (s.shell.agentOrder, s.shell.agents),
    );
    final notify = context.select((AppState s) => s.prefs.notify);
    final agents = [for (final id in order) ?byId[id]];
    return [
      LnSection(
        title: context.t('set_thisPhone'),
        footer: context.t('set_delivery'),
        children: [
          LnListTile(
            icon: allowed ? FIcons.bellRing : FIcons.bellOff,
            title: context.t('set_phoneNotifications'),
            subtitle: permission == null
                ? null
                : context.t(allowed ? 'set_notifOn' : 'set_notifOff'),
            value: permission == null
                ? null
                : context.t(
                    allowed || permission.isPermanentlyDenied
                        ? 'set_openPhoneSettings'
                        : 'set_allow',
                  ),
            onTap: _phoneNotifications,
          ),
        ],
      ),
      const SectionGap(),
      LnSection(
        title: label('reachMe'),
        footer: hasDevices
            ? null
            : '${label('noDevice')} ${context.t('set_passkeyElsewhere')}',
        children: [
          for (final (channel, icon) in const [
            ('notify', FIcons.bell),
            ('message', FIcons.messageSquare),
            ('call', FIcons.phone),
          ])
            ChoiceTile(
              icon: icon,
              title: reachMeLabel(channel, lang),
              subtitle: reachMeHint(channel, lang),
              selected: profile.channel == channel,
              enabled: !_saving && (channel != 'call' || hasDevices),
              onSelect: () => _chooseChannel(channel),
            ),
        ],
      ),
      if (call && hasDevices) ...[
        const SectionGap(),
        LnSection(
          title: label('device'),
          children: [
            for (final device in profile.devices)
              ChoiceTile(
                icon: FIcons.smartphone,
                title: device.name,
                subtitle: context.t('set_callRings'),
                selected: profile.deviceId == device.id,
                enabled: !_saving,
                onSelect: () => _saveReach({'device_id': device.id}),
              ),
          ],
        ),
        const SectionGap(),
        LnSection(
          children: [
            SwitchTile(
              icon: FIcons.phoneCall,
              title: label('actionRequiredCalls'),
              value: asBool(profile.reachMe['action_required']),
              onChanged: _saving
                  ? null
                  : (v) => _saveReach({'action_required': v}),
            ),
            SwitchTile(
              icon: FIcons.sparkles,
              title: label('opportunityCalls'),
              value: asBool(profile.reachMe['opportunities']),
              onChanged: _saving
                  ? null
                  : (v) => _saveReach({'opportunities': v}),
            ),
          ],
        ),
      ],
      const SectionGap(),
      LnSection(
        title: context.t('set_notifications'),
        children: [
          SwitchTile(
            icon: FIcons.bell,
            title: context.t('set_inApp'),
            subtitle: context.t('set_inAppSub'),
            value: notify.inApp,
            onChanged: (on) => context.dispatch(
              SetNotifyPrefsAction(notify.copyWith(inApp: on)),
            ),
          ),
          SwitchTile(
            icon: FIcons.eye,
            title: context.t('set_preview'),
            subtitle: context.t('set_previewSub'),
            value: notify.preview,
            onChanged: (on) => context.dispatch(
              SetNotifyPrefsAction(notify.copyWith(preview: on)),
            ),
          ),
          if (attention != null)
            SwitchTile(
              icon: FIcons.sparkles,
              title: context.t('set_opportunities'),
              subtitle: context.t('set_opportunitiesSub'),
              value: attention.opportunities,
              onChanged: _savingAttention ? null : _setOpportunities,
            ),
        ],
      ),
      const SectionGap(),
      LnSection(
        title: label('quietHours'),
        footer: context.t('set_timeZone', [ltr(profile.timeZone)]),
        children: [
          SwitchTile(
            icon: FIcons.moon,
            title: context.t('set_muteAtNight'),
            subtitle: profile.quiet
                ? context.t('set_fromTo', [
                    ltr(clockOfMinutes(profile.quietStartMinute!)),
                    ltr(clockOfMinutes(profile.quietEndMinute!)),
                  ])
                : context.t('set_fromTo', [ltr('22:00'), ltr('08:00')]),
            value: profile.quiet,
            onChanged: _saving
                ? null
                : (on) =>
                      on ? _setQuiet(22 * 60, 8 * 60) : _setQuiet(null, null),
          ),
          if (profile.quiet) ...[
            LnListTile(
              icon: FIcons.clock,
              title: context.t('set_from'),
              value: ltr(clockOfMinutes(profile.quietStartMinute!)),
              enabled: !_saving,
              onTap: () => _pickQuietTime(start: true),
            ),
            LnListTile(
              icon: FIcons.clock,
              title: context.t('set_to'),
              value: ltr(clockOfMinutes(profile.quietEndMinute!)),
              enabled: !_saving,
              onTap: () => _pickQuietTime(start: false),
            ),
            WrapTile(
              icon: FIcons.shieldAlert,
              title: context.t('set_urgent'),
              subtitle: context.t('set_urgentSub'),
              trailing: Icon(FIcons.check, color: c.selection),
            ),
          ],
        ],
      ),
      const SectionGap(),
      LnSection(
        children: [
          LnListTile(
            icon: FIcons.audioLines,
            title: context.t('voice'),
            onTap: () => context.push(Routes.voice),
          ),
        ],
      ),
      if (agents.isNotEmpty) ...[
        const SectionGap(),
        LnSection(
          title: context.t('set_perAgent'),
          children: [
            for (final agent in agents)
              _AgentRulesTile(
                agent: agent,
                // Unknown rules show no state; an agent without saved rules alerts.
                alerts: agentRules == null
                    ? null
                    : asJson(agentRules[agent.id])['in_app'] != false,
                onTap: () => context.push(Routes.agentSettings(agent.id)),
              ),
          ],
        ),
      ],
    ];
  }
}

/// One agent of «Per agent»: its avatar and name, whether its messages alert; opens its
/// settings, where its delivery rules are.
class _AgentRulesTile extends StatelessWidget with FTileMixin {
  const _AgentRulesTile({
    required this.agent,
    required this.alerts,
    required this.onTap,
  });

  final Agent agent;
  final bool? alerts;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => FTile(
    onPress: onTap,
    prefix: LonoraAvatar(
      agentId: agent.id,
      face: agent.avatar,
      color: agent.color,
      tradesOnItsOwn: agent.tradesOnItsOwn,
      size: LnSize.avatarGroup,
      animate: false,
    ),
    title: Text(isolate(agent.name), maxLines: 1),
    subtitle: alerts == null
        ? null
        : Text(context.t(alerts! ? 'set_notifOn' : 'set_notifOff')),
    suffix: const Icon(FIcons.chevronRight),
  );
}

/// A time wheel (forui [FTimePicker], 24-hour) with Save; completes with minutes after midnight.
class _TimeSheet extends StatefulWidget {
  const _TimeSheet({required this.minutes});

  final int minutes;

  @override
  State<_TimeSheet> createState() => _TimeSheetState();
}

class _TimeSheetState extends State<_TimeSheet> {
  late final _controller = FTimePickerController(
    initial: FTime(widget.minutes ~/ 60, widget.minutes % 60),
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Directionality(
        textDirection: TextDirection.ltr,
        child: SizedBox(
          height: 200,
          child: FTimePicker(
            controller: _controller,
            hour24: true,
            onChange: (_) => HapticFeedback.selectionClick(),
          ),
        ),
      ),
      const SizedBox(height: LnSpace.md),
      BlockButton(
        label: context.t('save'),
        onPressed: () {
          final t = _controller.value;
          Navigator.of(context).pop(t.hour * 60 + t.minute);
        },
      ),
    ],
  );
}
