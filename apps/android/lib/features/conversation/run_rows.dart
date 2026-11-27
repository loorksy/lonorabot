// Run rows in the transcript, composed from the inline event row. Only observable run and tool
// events are shown (packages/core turnActivity); nothing invents reasoning steps.
import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:shimmer/shimmer.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../avatar/avatar.dart';

import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../core/realtime/lonora_event.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/reply_stream.dart';
import 'message_widgets.dart';

/// The run as `turnActivity` reads it: its JSON with the live stream's phase and text.
Map<String, Object?> runJsonFor(Run run, LiveReplyStream? stream) => {
  ...run.raw,
  'status': run.status,
  if (stream != null)
    'stream': {
      'phase': stream.phase,
      'text': stream.text,
      'rich_content': stream.richContent,
    },
};

/// A reply that has no words yet: the agent's 32 dp avatar in the run's phase (animated) at the
/// bubbles' text column, and the phase («يفكر», «جارٍ العمل»…) in body type with a moving shimmer
/// (plain secondary ink with reduced motion). [label] null shows the avatar alone (the activity
/// line above already says it).
class WorkingRow extends StatelessWidget {
  const WorkingRow({
    super.key,
    required this.agent,
    required this.agentId,
    required this.state,
    this.label,
    this.semanticLabel,
  });

  final Agent? agent;
  final String agentId;
  final LonoraAvatarState state;
  final String? label;

  /// Spoken for the row (the phase), also when [label] is not drawn.
  final String? semanticLabel;

  /// The avatar and its start inset: the bubbles' text column (16 dp into the bubble).
  static const double avatar = 32;
  static const double inset = LnSize.bubblePadH;

  /// Avatar → label.
  static const double gap = 10.5;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final reduced = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    final a = agent;
    final text = label;
    Widget? words;
    if (text != null) {
      final plain = Text(
        text,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: ln.text.body.copyWith(color: c.fgMuted),
      );
      words = reduced
          ? plain
          : Shimmer.fromColors(
              baseColor: c.fg.withValues(alpha: 0.4),
              highlightColor: c.fg,
              period: const Duration(milliseconds: 1600),
              child: plain,
            );
    }
    return Semantics(
      liveRegion: true,
      label: semanticLabel ?? text,
      child: ExcludeSemantics(
        child: Padding(
          padding: const EdgeInsetsDirectional.only(start: inset),
          child: SizedBox(
            height: LnSize.minTouch,
            child: Row(
              children: [
                SizedBox.square(
                  dimension: avatar,
                  child: LonoraAvatar(
                    agentId: a?.id ?? agentId,
                    face: a?.avatar,
                    color: a?.color,
                    tradesOnItsOwn: a?.tradesOnItsOwn ?? false,
                    state: state,
                    size: avatar,
                  ),
                ),
                if (words != null) ...[
                  const SizedBox(width: gap),
                  Flexible(child: words),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The activity line above a reply being written: «يفكر», «يكتب الرد», «ينتظر ردك»…, with the
/// run's tool calls behind a tap when the owner keeps «خطوات عمل الوكيل» on.
class ActivityLine extends StatefulWidget {
  const ActivityLine({
    super.key,
    required this.run,
    this.stream,
    this.events = const [],
    this.connection = StreamStatus.connected,
    this.steps = true,
    this.stepsOpen = false,
    this.actions = const [],
  });

  final Run run;
  final LiveReplyStream? stream;

  /// This conversation's recent run/tool events (Event JSON).
  final List<Map<String, Object?>> events;
  final StreamStatus connection;
  final bool steps;
  final bool stepsOpen;

  /// Row actions (Resume, Stop…).
  final List<Widget> actions;

  @override
  State<ActivityLine> createState() => _ActivityLineState();
}

class _ActivityLineState extends State<ActivityLine> {
  late bool _open = widget.stepsOpen;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final activity = turnActivity(
      runJsonFor(widget.run, widget.stream),
      widget.events,
    );
    final working = widget.run.isActive;
    final reconnecting =
        working &&
        widget.connection != StreamStatus.connected &&
        widget.connection != StreamStatus.idle;
    final phase = activity.phase;
    final label = reconnecting
        ? l10n.t(
            widget.connection == StreamStatus.connecting
                ? 'connecting'
                : 'reconnecting',
          )
        : l10n.t('activity_$phase');
    final Widget icon = switch (phase) {
      'failed' => Icon(FIcons.circleAlert, color: c.error),
      'cancelled' => Icon(FIcons.circleStop, color: c.fgMuted),
      'completed' => Icon(FIcons.circleCheck, color: c.success),
      'waiting_input' ||
      'waiting_external' => Icon(FIcons.hourglass, color: c.pending),
      _ when reconnecting => Icon(FIcons.wifiOff, color: c.warning),
      _ => LnSpinner(size: 14, color: c.fgMuted),
    };
    final calls = activity.calls;
    final details = widget.steps && calls.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // The row's actions (Resume, Stop) follow its label on the same line.
        Row(
          children: [
            Flexible(
              child: Semantics(
                liveRegion: true,
                expanded: details ? _open : null,
                child: InlineEventRow(
                  icon: icon,
                  label: label,
                  alignment: InlineEventAlignment.start,
                  showChevron: details,
                  hug: true,
                  onTap: details ? () => setState(() => _open = !_open) : null,
                ),
              ),
            ),
            ...widget.actions,
          ],
        ),
        if (details && _open)
          Padding(
            padding: const EdgeInsetsDirectional.only(
              start: _textColumn,
              bottom: LnSpace.xs,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final call in calls)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Text.rich(
                      TextSpan(
                        text: activityCallLabel(
                          toolset: call.toolset,
                          effect: call.effect,
                          name: call.name,
                          locale: l10n.lang,
                        ),
                        children: [
                          TextSpan(
                            text:
                                '$dotSeparator${l10n.t('activity_call_${call.status}')}',
                            style: TextStyle(
                              color: call.status == 'failed'
                                  ? c.error
                                  : c.fgSubtle,
                            ),
                          ),
                        ],
                      ),
                      style: ln.text.footnote.copyWith(color: c.fgMuted),
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

/// Start of the label column of a start-aligned inline event row (16 + 22 + 4.5).
const double _textColumn = LnSpace.md + 22 + 4.5;

/// A reply that ended without a drawn answer: «تعذر إكمال العمل» with the server's reason, or
/// «توقف»; Retry for the newest provider failure (after its Retry-After), Manage usage for a
/// ChatGPT plan limit.
class RunEndRow extends StatefulWidget {
  const RunEndRow({
    super.key,
    required this.run,
    this.retryable = false,
    this.retryAt,
    this.onRetry,
    this.busy = false,
  });

  final Run run;
  final bool retryable;

  /// A control of this run is on its way (Retry waits).
  final bool busy;

  /// When the provider allows the retry (Retry-After); null when it already does.
  final DateTime? retryAt;
  final VoidCallback? onRetry;

  @override
  State<RunEndRow> createState() => _RunEndRowState();
}

class _RunEndRowState extends State<RunEndRow> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _arm();
  }

  @override
  void didUpdateWidget(RunEndRow old) {
    super.didUpdateWidget(old);
    if (old.retryAt != widget.retryAt) _arm();
  }

  void _arm() {
    _timer?.cancel();
    final at = widget.retryAt;
    if (at == null) return;
    final wait = at.difference(DateTime.now());
    if (wait.isNegative) return;
    _timer = Timer(wait + const Duration(milliseconds: 50), () {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final run = widget.run;
    final failed = run.status == 'failed';
    final plan = failed && planLimitReached(run.failure);
    final detail = !failed
        ? null
        : plan
        ? chatgptText(l10n.lang).planLimitTitle
        : run.errorCode != null
        ? l10n.errorText(run.errorCode)
        : null;
    final ready =
        widget.retryAt == null || !DateTime.now().isBefore(widget.retryAt!);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        InlineEventRow(
          icon: failed
              ? Icon(FIcons.circleAlert, color: c.error)
              : Icon(FIcons.circleStop, color: c.fgMuted),
          label: l10n.t(failed ? 'activity_failed' : 'activity_cancelled'),
          alignment: InlineEventAlignment.start,
          showChevron: false,
        ),
        if (detail != null)
          Padding(
            padding: const EdgeInsetsDirectional.only(
              start: _textColumn,
              end: LnSpace.md,
            ),
            child: Text(
              detail,
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
              style: ln.text.footnote.copyWith(color: c.fgMuted),
            ),
          ),
        if (plan || widget.retryable)
          Padding(
            padding: const EdgeInsetsDirectional.only(start: _textColumn - 8),
            child: Wrap(
              children: [
                if (plan)
                  RowTextButton(
                    label: chatgptText(l10n.lang).manageUsage,
                    onTap: () => launchUrl(
                      Uri.parse(manageUsageUrl),
                      mode: LaunchMode.externalApplication,
                    ),
                  ),
                if (widget.retryable && widget.onRetry != null)
                  RowTextButton(
                    label: l10n.t('retry'),
                    enabled: ready && !widget.busy,
                    onTap: widget.onRetry!,
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

/// Event JSON for [turnActivity] from a realtime event.
Json eventJson(LonoraEvent e) => {
  'cursor': e.cursor,
  'kind': e.kind,
  'run_id': e.runId,
  'thread_id': e.threadId,
  'payload': e.payload,
  'created_at': e.createdAt?.toUtc().toIso8601String(),
};
