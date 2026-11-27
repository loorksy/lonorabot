import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';
import 'package:path_provider/path_provider.dart';

import '../../app/routes.dart';
import '../../app/services.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/app_state.dart';

/// Bytes of artifacts already drawn, newest last, bounded (~24 MB), for one owner on one
/// server: a different owner or server (read from the app store when one is registered)
/// empties it first, and [clear] drops it with the voice notes' cached files.
final class ArtifactBytesCache {
  ArtifactBytesCache._();
  static final _bytes = <String, Uint8List>{};
  static final _pending = <String, Future<Uint8List>>{};
  static int _total = 0;
  static const int _limit = 24 << 20;
  static String? _scope;
  static int _generation = 0;

  static Uint8List? peek(String id) {
    _syncScope();
    return _bytes[id];
  }

  /// The artifact's file through the owner session (`GET /artifacts/{id}/file?preview=true`;
  /// never a credential in a URL).
  static Future<Uint8List> load(String id) {
    _syncScope();
    final cached = _bytes[id];
    if (cached != null) return Future.value(cached);
    final generation = _generation;
    return _pending[id] ??= api
        .bytes('/artifacts/$id/file', query: {'preview': true})
        .then((data) {
          // Read for an owner the cache was cleared for: handed back, never kept.
          if (generation == _generation) _put(id, data);
          return data;
        })
        .whenComplete(() {
          if (generation == _generation) _pending.remove(id);
        });
  }

  /// Drops every cached artifact and the voice notes' audio files (sign-out, server
  /// change). Loads still in flight are not kept.
  static void clear() {
    _generation++;
    _bytes.clear();
    _pending.clear();
    _total = 0;
    unawaited(_deleteVoiceFiles());
  }

  /// Where a voice note's audio is written to be played (cleared by [clear]).
  static Future<File> voiceFile(String id) async {
    final dir = Directory('${(await getTemporaryDirectory()).path}/$_voiceDir');
    await dir.create(recursive: true);
    return File('${dir.path}/${id.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_')}');
  }

  static const _voiceDir = 'lonora_voice';

  static Future<void> _deleteVoiceFiles() async {
    try {
      final dir = Directory(
        '${(await getTemporaryDirectory()).path}/$_voiceDir',
      );
      if (dir.existsSync()) await dir.delete(recursive: true);
    } catch (_) {
      // No temporary directory here (tests) or already gone.
    }
  }

  static void _syncScope() {
    if (!sl.isRegistered<Store<AppState>>()) return;
    final session = appStore.state.session;
    final scope = '${session.server}\n${session.owner?.id}';
    if (_scope == scope) return;
    if (_scope != null) clear();
    _scope = scope;
  }

  static void _put(String id, Uint8List data) {
    _bytes.remove(id);
    _bytes[id] = data;
    _total += data.length;
    while (_total > _limit && _bytes.length > 1) {
      final first = _bytes.keys.first;
      _total -= _bytes.remove(first)!.length;
    }
  }

  @visibleForTesting
  static void seed(String id, Uint8List data) => _put(id, data);
}

/// An artifact image drawn inline (v1 `image` node, Markdown artifact image). Tap opens the
/// image viewer (`Routes.image`).
class ArtifactImage extends StatefulWidget {
  const ArtifactImage({
    super.key,
    required this.artifactId,
    this.label,
    this.height = 200,
  });

  final String artifactId;
  final String? label;
  final double height;

  @override
  State<ArtifactImage> createState() => _ArtifactImageState();
}

class _ArtifactImageState extends State<ArtifactImage> {
  Uint8List? _data;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _start();
  }

  @override
  void didUpdateWidget(ArtifactImage old) {
    super.didUpdateWidget(old);
    if (old.artifactId != widget.artifactId) _start();
  }

  void _start() {
    final id = widget.artifactId;
    _data = ArtifactBytesCache.peek(id);
    _failed = false;
    if (_data != null) return;
    unawaited(
      ArtifactBytesCache.load(id).then(
        (data) {
          // A late answer for an image this widget no longer shows is dropped.
          if (mounted && widget.artifactId == id) setState(() => _data = data);
        },
        onError: (Object _) {
          if (mounted && widget.artifactId == id) {
            setState(() => _failed = true);
          }
        },
      ),
    );
  }

  void _retry() => setState(_start);

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final label = widget.label;
    Widget body;
    if (_data != null) {
      body = Image.memory(
        _data!,
        height: widget.height,
        width: double.infinity,
        fit: BoxFit.contain,
        gaplessPlayback: true,
        semanticLabel: label ?? context.t('image'),
        errorBuilder: (context, _, _) => _placeholder(context, failed: true),
      );
    } else {
      body = _placeholder(context, failed: _failed);
    }
    // A failed image is tapped to try again; a drawn one opens the viewer.
    return LnTappable(
      onTap: _failed && _data == null
          ? _retry
          : () =>
                GoRouter.maybeOf(context)
                    ?.push(Routes.image(widget.artifactId)),
      semanticLabel: _failed && _data == null
          ? context.t('retry')
          : label ?? context.t('image'),
      child: ClipRRect(
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.image)),
        child: DecoratedBox(
          decoration: BoxDecoration(color: c.fill1),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              body,
              if (label != null && label.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.all(LnSpace.sm),
                  child: Text(
                    label,
                    style: ln.text.footnote.copyWith(color: c.fgMuted),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _placeholder(BuildContext context, {required bool failed}) {
    final c = context.ln.colors;
    return SizedBox(
      height: failed ? 64 : widget.height,
      child: Center(
        child: failed
            ? Icon(FIcons.imageOff, size: 24, color: c.fgSubtle)
            : const LnSpinner(),
      ),
    );
  }
}
