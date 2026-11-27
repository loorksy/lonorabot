// A push-reveal drawer on the start side: the page slides toward the end and becomes a dimmed card
// with rounded start corners, uncovering a drawer that grows into place behind it.
import 'dart:math' as math;

import 'package:flutter/foundation.dart' show ValueListenable;
import 'package:flutter/gestures.dart';
import 'package:flutter/widgets.dart';

import '../theme.dart';
import '../tokens.dart';

/// Opens and closes an [LnDrawerScaffold]'s drawer and reports where it is. Listeners are told when
/// [isOpen] changes; [progress] reports every frame.
class LnDrawerController extends ChangeNotifier {
  LnDrawerController({bool open = false})
    : _open = open,
      _progress = ValueNotifier<double>(open ? 1 : 0);

  bool _open;
  final ValueNotifier<double> _progress;
  _LnDrawerScaffoldState? _scaffold;

  /// Whether the drawer is open or on its way open (a drag that has not been released yet keeps
  /// the value it had).
  bool get isOpen => _open;

  /// 0 (closed) to 1 (open), following drags and animations frame by frame.
  ValueListenable<double> get progress => _progress;

  /// Animates the drawer open; completes when it is (at once with reduced motion).
  Future<void> open() => _settle(true);

  /// Animates the drawer closed; completes when it is.
  Future<void> close() => _settle(false);

  Future<void> toggle() => _settle(!_open);

  Future<void> _settle(bool open) {
    _setOpen(open);
    final scaffold = _scaffold;
    if (scaffold == null) {
      _progress.value = open ? 1 : 0;
      return Future<void>.value();
    }
    return scaffold._animateTo(open ? 1 : 0);
  }

  void _setOpen(bool open) {
    if (_open == open) return;
    _open = open;
    notifyListeners();
  }

  @override
  void dispose() {
    _progress.dispose();
    super.dispose();
  }
}

/// A page with a push-reveal drawer on the start side (the right in Arabic).
///
/// Open, the drawer panel ([LnPalette.drawerSurface], full height) spans the width minus [peek]
/// (at most [maxDrawerWidth]); [child] (the whole page, its floating tab bar included) moves toward
/// the end by that width and becomes a card: its start corners round up to [cardRadius], a
/// one-pixel hairline runs along its start edge, and a veil of the canvas colour dims it (60 % at
/// the end). There is no scrim. The drawer's content grows from 90 % to full size and fades in.
/// Every value is linear in [LnDrawerController.progress].
///
/// A tap or a drag on the visible card closes the drawer; a drag from the start edge ([edgeDragWidth]
/// wide, inside the system gesture inset) opens it; Android back closes it first, also while a
/// drag is under way. The edge strip yields to the page: where the page has a horizontal drag of
/// its own under the strip (swipe to reply on a message, a horizontal list), that drag wins, as
/// the strip claims a drag only after twice the touch slop; the drawer then opens from the ☰
/// button or from the edge beside that content. Opening, closing and settling after a drag use
/// [LnMotion.drawer] and [LnMotion.standard], or jump with reduced motion.
///
/// Semantics: the drawer is a route-scoping region named [drawerLabel] that takes focus when it
/// opens; while it is open the card's content is hidden from screen readers and focus, and the card
/// is a button named [closeLabel] (tap and dismiss close the drawer).
class LnDrawerScaffold extends StatefulWidget {
  const LnDrawerScaffold({
    super.key,
    required this.controller,
    required this.drawer,
    required this.child,
    required this.drawerLabel,
    required this.closeLabel,
    this.edgeDragWidth = 20,
    this.enableEdgeDrag = true,
  });

  final LnDrawerController controller;

  /// The drawer's content; it handles its own safe-area padding.
  final Widget drawer;

  /// The page the drawer pushes aside.
  final Widget child;

  /// Names the drawer region for screen readers ("Chats").
  final String drawerLabel;

  /// Names the card's close action ("Close chats").
  final String closeLabel;

  /// Width of the start-edge strip that opens the drawer by dragging, measured from the system
  /// gesture inset.
  final double edgeDragWidth;
  final bool enableEdgeDrag;

  /// The card's visible width at the end side when the drawer is open (dp).
  static const double peek = 82;

  /// The drawer's widest extent (tablets).
  static const double maxDrawerWidth = 360;

  /// Corner radius of the card's start corners when open.
  static const double cardRadius = 64;

  /// The veil's opacity over the card when open.
  static const double veilOpacity = 0.6;

  /// The drawer content's scale when closed.
  static const double closedScale = 0.9;

  /// The drawer's width on a page [width] wide.
  static double drawerWidthFor(double width) =>
      math.max(0, math.min(width - peek, maxDrawerWidth));

  @override
  State<LnDrawerScaffold> createState() => _LnDrawerScaffoldState();
}

class _LnDrawerScaffoldState extends State<LnDrawerScaffold>
    with SingleTickerProviderStateMixin {
  late final AnimationController _anim = AnimationController(
    vsync: this,
    value: widget.controller.progress.value,
  )..addListener(_tick);
  final FocusScopeNode _drawerScope = FocusScopeNode(
    debugLabel: 'LnDrawerScaffold drawer',
  );

  /// Values of the last layout, used by the drag handlers.
  double _width = 1;
  bool _rtl = false;

  /// The drawer shows at all (progress above 0): back closes it rather than leaving the page.
  bool _shown = false;

  /// Minimum fling speed that decides the direction on release (as Material's drawer).
  static const double _minFlingVelocity = 365;

  LnDrawerController get _controller => widget.controller;

  @override
  void initState() {
    super.initState();
    _attach(_controller);
  }

  @override
  void didUpdateWidget(LnDrawerScaffold old) {
    super.didUpdateWidget(old);
    if (old.controller != widget.controller) {
      _detach(old.controller);
      _attach(widget.controller);
      _anim.value = widget.controller.progress.value;
    }
  }

  @override
  void dispose() {
    _detach(_controller);
    _anim.dispose();
    _drawerScope.dispose();
    super.dispose();
  }

  void _attach(LnDrawerController controller) {
    controller._scaffold = this;
    controller.addListener(_openChanged);
    _shown = controller.progress.value > 0;
  }

  void _detach(LnDrawerController controller) {
    if (controller._scaffold == this) controller._scaffold = null;
    controller.removeListener(_openChanged);
  }

  void _tick() {
    _controller._progress.value = _anim.value;
    final shown = _anim.value > 0;
    if (shown != _shown && mounted) setState(() => _shown = shown);
  }

  void _openChanged() {
    if (!mounted) return;
    setState(() {});
    // The drawer becomes focusable in the next build; focus moves in after it.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _controller.isOpen) _drawerScope.requestFocus();
    });
  }

  Future<void> _animateTo(double target) {
    if (!mounted) return Future<void>.value();
    final distance = (target - _anim.value).abs();
    if (distance == 0) return Future<void>.value();
    if (MediaQuery.disableAnimationsOf(context)) {
      _anim.value = target;
      return Future<void>.value();
    }
    return _anim
        .animateTo(
          target,
          duration: LnMotion.drawer * distance,
          curve: LnMotion.standard,
        )
        .orCancel
        .catchError((Object _) {}, test: (e) => e is TickerCanceled);
  }

  double get _sign => _rtl ? -1 : 1;

  void _dragStart(DragStartDetails details) => _anim.stop();

  void _dragUpdate(DragUpdateDetails details) {
    _anim.value += _sign * details.primaryDelta! / _width;
  }

  void _dragEnd(DragEndDetails details) {
    final velocity = _sign * details.velocity.pixelsPerSecond.dx;
    final open = velocity.abs() >= _minFlingVelocity
        ? velocity > 0
        : _anim.value >= 0.5;
    open ? _controller.open() : _controller.close();
  }

  void _dragCancel() =>
      _anim.value >= 0.5 ? _controller.open() : _controller.close();

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    _rtl = Directionality.of(context) == TextDirection.rtl;
    final open = _controller.isOpen;
    final gestureInsets = MediaQuery.systemGestureInsetsOf(context);
    final edgeInset = _rtl ? gestureInsets.right : gestureInsets.left;
    final hairline = 1 / MediaQuery.devicePixelRatioOf(context);

    // Built once per build: the frame-by-frame builder below reuses these subtrees.
    final drawer = ExcludeFocus(
      excluding: !open,
      child: FocusScope(
        node: _drawerScope,
        child: Semantics(
          scopesRoute: true,
          namesRoute: true,
          explicitChildNodes: true,
          label: widget.drawerLabel,
          child: widget.drawer,
        ),
      ),
    );
    final page = ExcludeFocus(
      excluding: open,
      child: ColoredBox(color: c.bg, child: widget.child),
    );

    return PopScope(
      canPop: !open && !_shown,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _controller.close();
      },
      child: LayoutBuilder(
        builder: (context, box) {
          final width = LnDrawerScaffold.drawerWidthFor(box.maxWidth);
          _width = math.max(1, width);
          return AnimatedBuilder(
            animation: _anim,
            builder: (context, _) {
              final p = _anim.value;
              final shown = p > 0;
              final radius = Radius.circular(LnDrawerScaffold.cardRadius * p);
              return Stack(
                children: [
                  PositionedDirectional(
                    start: 0,
                    top: 0,
                    bottom: 0,
                    width: width,
                    child: Offstage(
                      offstage: !shown,
                      child: ColoredBox(
                        color: c.drawerSurface,
                        child: Opacity(
                          opacity: p,
                          child: Transform.scale(
                            scale:
                                LnDrawerScaffold.closedScale +
                                (1 - LnDrawerScaffold.closedScale) * p,
                            child: drawer,
                          ),
                        ),
                      ),
                    ),
                  ),
                  Positioned.fill(
                    child: Transform.translate(
                      offset: Offset(_sign * width * p, 0),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          ClipRRect(
                            clipBehavior: shown ? Clip.antiAlias : Clip.none,
                            borderRadius: BorderRadiusDirectional.horizontal(
                              start: radius,
                            ),
                            child: Stack(
                              fit: StackFit.expand,
                              children: [
                                ExcludeSemantics(excluding: shown, child: page),
                                IgnorePointer(
                                  child: ColoredBox(
                                    color: c.bg.withValues(
                                      alpha: LnDrawerScaffold.veilOpacity * p,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          IgnorePointer(
                            child: CustomPaint(
                              painter: _StartEdgePainter(
                                radius: radius.x,
                                color: shown
                                    ? c.border
                                    : const Color(0x00000000),
                                width: hairline,
                                rtl: _rtl,
                              ),
                            ),
                          ),
                          // The card's own surface while the drawer shows: tap or drag to close.
                          IgnorePointer(
                            ignoring: !shown,
                            child: ExcludeSemantics(
                              excluding: !shown,
                              child: Semantics(
                                button: true,
                                label: widget.closeLabel,
                                onTap: _controller.close,
                                onDismiss: _controller.close,
                                child: GestureDetector(
                                  behavior: HitTestBehavior.opaque,
                                  excludeFromSemantics: true,
                                  onTap: _controller.close,
                                  onHorizontalDragStart: _dragStart,
                                  onHorizontalDragUpdate: _dragUpdate,
                                  onHorizontalDragEnd: _dragEnd,
                                  onHorizontalDragCancel: _dragCancel,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  // The start-edge strip that opens the drawer (closed only).
                  Positioned(
                    left: _rtl ? null : edgeInset,
                    right: _rtl ? edgeInset : null,
                    top: 0,
                    bottom: 0,
                    width: widget.edgeDragWidth,
                    child: IgnorePointer(
                      ignoring: shown || !widget.enableEdgeDrag,
                      child: RawGestureDetector(
                        behavior: HitTestBehavior.translucent,
                        excludeFromSemantics: true,
                        gestures: {
                          _YieldingHorizontalDrag:
                              GestureRecognizerFactoryWithHandlers<
                                _YieldingHorizontalDrag
                              >(
                                () => _YieldingHorizontalDrag(debugOwner: this),
                                (r) => r
                                  // The drawer follows the finger from where it
                                  // landed, the slop included.
                                  ..dragStartBehavior = DragStartBehavior.down
                                  ..onStart = _dragStart
                                  ..onUpdate = _dragUpdate
                                  ..onEnd = _dragEnd
                                  ..onCancel = _dragCancel
                                  ..gestureSettings =
                                      MediaQuery.maybeGestureSettingsOf(
                                        context,
                                      ),
                              ),
                        },
                      ),
                    ),
                  ),
                ],
              );
            },
          );
        },
      ),
    );
  }
}

/// The edge strip's drag: it claims the gesture only after twice the touch slop, so a horizontal
/// drag of the page under the strip, which claims at the slop, wins the arena first.
class _YieldingHorizontalDrag extends HorizontalDragGestureRecognizer {
  _YieldingHorizontalDrag({super.debugOwner});

  @override
  bool hasSufficientGlobalDistanceToAccept(
    PointerDeviceKind pointerDeviceKind,
    double? deviceTouchSlop,
  ) =>
      globalDistanceMoved.abs() >
      2 * computeHitSlop(pointerDeviceKind, gestureSettings);
}

/// The hairline along the card's start edge and around its rounded start corners.
class _StartEdgePainter extends CustomPainter {
  _StartEdgePainter({
    required this.radius,
    required this.color,
    required this.width,
    required this.rtl,
  });

  final double radius;
  final Color color;
  final double width;
  final bool rtl;

  @override
  void paint(Canvas canvas, Size size) {
    if (color.a == 0) return;
    final r = math.min(radius, size.height / 2);
    final inset = width / 2;
    // Drawn for the left edge, mirrored for the right one.
    if (rtl) {
      canvas
        ..translate(size.width, 0)
        ..scale(-1, 1);
    }
    final path = Path()
      ..moveTo(inset + r, inset)
      ..arcToPoint(
        Offset(inset, inset + r),
        radius: Radius.circular(r),
        clockwise: false,
      )
      ..lineTo(inset, size.height - inset - r)
      ..arcToPoint(
        Offset(inset + r, size.height - inset),
        radius: Radius.circular(r),
        clockwise: false,
      );
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = width
        ..isAntiAlias = true,
    );
  }

  @override
  bool shouldRepaint(_StartEdgePainter old) =>
      old.radius != radius ||
      old.color != color ||
      old.width != width ||
      old.rtl != rtl;
}
