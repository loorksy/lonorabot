// «وكيل جديد» in a stacked sheet: ✕, the title and an «إنشاء» pill (enabled once the agent has a
// name) in the header; a big avatar with an edit badge that opens the avatar studio as the sheet's
// second page; the name field. «إنشاء» sends `POST /agents` for a flexible-scope agent (no market
// binding; the server picks its template), then the new agent's conversation opens. Agents are
// still created from chat too: Lonora's conversation keeps that path.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/api/api_error.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/shell_actions.dart';
import '../../state/actions/thread_actions.dart';
import '../groups/form_sheet.dart';
import 'profile/agent_data.dart';
import 'profile/agent_strings.dart';
import 'settings/avatar_editor.dart';

/// The longest agent name the server accepts (`AgentCreate.name`).
const int agentNameMaxLength = 80;

/// Opens the create-agent sheet over [context]'s root navigator. On success the sheet closes and
/// the new agent's conversation opens.
Future<void> showCreateAgentSheet(BuildContext context) async {
  registerAgentStrings(context.l10n);
  final dirty = ValueNotifier(false);
  try {
    await showFormSheet<void>(
      context,
      dirty: dirty,
      builder: (_) => CreateAgentForm(dirty: dirty),
    );
  } finally {
    dirty.dispose();
  }
}

/// The sheet's content: the form, or the avatar studio as its second page.
class CreateAgentForm extends StatefulWidget {
  const CreateAgentForm({super.key, this.dirty});

  /// Set while the form holds anything to lose or the studio page is shown (it turns the
  /// sheet's drag-to-close off).
  final ValueNotifier<bool>? dirty;

  @override
  State<CreateAgentForm> createState() => _CreateAgentFormState();
}

class _CreateAgentFormState extends State<CreateAgentForm> {
  /// Seeds the previews' personality until the agent has an id.
  static const _draftId = 'new-agent';

  final _name = TextEditingController();
  String _face = avatarFaces.first.id;
  String _color = defaultAvatarColor;

  /// The studio's own draft while it is open (null: the form shows).
  ({String face, String color})? _studio;
  bool _busy = false;
  String? _error;

  bool get _valid => _name.text.trim().isNotEmpty;

  bool get _dirty =>
      _name.text.isNotEmpty ||
      _face != avatarFaces.first.id ||
      _color != defaultAvatarColor;

  @override
  void initState() {
    super.initState();
    _name.addListener(_changed);
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  void _changed() {
    _syncDirty();
    setState(() {});
  }

  /// A drag would drop the form's edits, or the studio's draft from the sheet's second page.
  void _syncDirty() => widget.dirty?.value = _dirty || _studio != null;

  void _openStudio() {
    FocusManager.instance.primaryFocus?.unfocus();
    setState(() => _studio = (face: _face, color: _color));
    _syncDirty();
  }

  void _closeStudio({bool keep = false}) {
    final studio = _studio;
    setState(() {
      if (keep && studio != null) {
        _face = studio.face;
        _color = studio.color;
      }
      _studio = null;
    });
    _syncDirty();
  }

  Future<void> _leave() async {
    if (_busy) return;
    if (_dirty && !await confirmDiscard(context)) return;
    if (mounted) Navigator.of(context).pop();
  }

  Future<void> _create() async {
    if (!_valid || _busy) return;
    FocusManager.instance.primaryFocus?.unfocus();
    setState(() => (_busy = true, _error = null));
    final router = GoRouter.of(context);
    final navigator = Navigator.of(context);
    try {
      final agent = await createAgent(
        name: _name.text,
        face: _face,
        color: _color,
      );
      if (!mounted) return;
      context.dispatch(UpsertAgentAction(agent));
      unawaited(context.dispatchAndWait(RefreshShellAction()));
      final ensure = EnsureAgentThreadAction(agent.id);
      await context.dispatchAndWait(ensure);
      final thread = ensure.threadId;
      if (!mounted) return;
      navigator.pop();
      // The agent exists even when its conversation could not open yet: its profile can.
      router.go(
        thread == null || ensure.status.originalError != null
            ? Routes.agent(agent.id)
            : Routes.thread(thread),
      );
    } catch (error) {
      if (error is SessionRequestCancelled || !mounted) return;
      setState(() {
        _busy = false;
        _error = context.l10n.errorText(error is ApiError ? error.code : null);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final studio = _studio;
    final animate = !(MediaQuery.maybeDisableAnimationsOf(context) ?? false);
    final Widget page = studio == null
        ? _form(context)
        : AvatarStudio(
            key: const ValueKey('studio'),
            agentId: _draftId,
            face: studio.face,
            color: studio.color,
            leading: AvatarStudioLeading.back,
            onFaceChanged: (face) =>
                setState(() => _studio = (face: face, color: studio.color)),
            onColorChanged: (color) =>
                setState(() => _studio = (face: studio.face, color: color)),
            onReset: () => setState(
              () => _studio = (
                face: avatarFaces.first.id,
                color: defaultAvatarColor,
              ),
            ),
            onConfirm: () => _closeStudio(keep: true),
            onLeave: _closeStudio,
          );
    return PopScope(
      canPop: studio == null && !_dirty && !_busy,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) return;
        if (_studio != null) {
          _closeStudio();
        } else {
          _leave();
        }
      },
      child: AnimatedSwitcher(
        duration: animate ? LnMotion.medium : Duration.zero,
        child: KeyedSubtree(key: ValueKey(studio == null), child: page),
      ),
    );
  }

  Widget _form(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final animate = !(MediaQuery.maybeDisableAnimationsOf(context) ?? false);
    final avatar = SizedBox.square(
      dimension: CreateAgentLayout.avatar,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          ExcludeSemantics(
            child: LonoraAvatar(
              agentId: _draftId,
              face: _face,
              color: _color,
              size: CreateAgentLayout.avatar,
              animate: animate,
            ),
          ),
          // The edit badge's 48 dp box, centred on the avatar's bottom-end edge.
          PositionedDirectional(
            end: -CreateAgentLayout.badgeOverhang,
            bottom: -CreateAgentLayout.badgeOverhang,
            child: CircleIconButton(
              icon: const Icon(FIcons.pencil),
              semanticLabel: l10n.t('avatarEdit'),
              onTap: _busy ? null : _openStudio,
            ),
          ),
        ],
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        LnSheetHeader(
          title: l10n.t('newAgent'),
          closeLabel: l10n.t('close'),
          onClose: _leave,
          action: _busy
              ? const SizedBox.square(
                  dimension: LnSize.minTouch,
                  child: Center(child: LnSpinner(size: 18)),
                )
              : HeaderPillButton(
                  label: l10n.t('create'),
                  onPressed: _valid ? _create : null,
                ),
        ),
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              controller: LnStackedSheet.scrollControllerOf(context),
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                // The sheet does not shrink for the keyboard: its height is room to scroll.
                child: Padding(
                  padding: EdgeInsets.fromLTRB(
                    LnSpace.pageGutter,
                    LnSpace.xl,
                    LnSpace.pageGutter,
                    LnSpace.xxl + MediaQuery.viewInsetsOf(context).bottom,
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Center(child: avatar),
                      const SizedBox(height: CreateAgentLayout.avatarToField),
                      StadiumField(
                        controller: _name,
                        hint: l10n.t('ag_agentName'),
                        enabled: !_busy,
                        textAlign: TextAlign.center,
                        maxLength: agentNameMaxLength,
                        textInputAction: TextInputAction.done,
                        onSubmitted: (_) => _create(),
                      ),
                      if (_error != null)
                        Padding(
                          padding: const EdgeInsets.only(top: LnSpace.xs),
                          child: Semantics(
                            liveRegion: true,
                            child: Text(
                              _error!,
                              textAlign: TextAlign.center,
                              style: ln.text.caption.copyWith(color: c.error),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// The create-agent form's measures.
abstract final class CreateAgentLayout {
  /// The avatar's size.
  static const double avatar = 112;

  /// How far the edit badge's 48 dp box reaches past the avatar's end and bottom edges.
  static const double badgeOverhang = 8;

  /// Avatar bottom → name field.
  static const double avatarToField = 48;
}
