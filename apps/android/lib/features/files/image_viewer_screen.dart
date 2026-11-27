// A file's image, full screen (apps/mobile app/image.tsx): pinch to zoom up to four times, pan,
// double-tap to step the zoom; share and save it where the owner chooses. The image is read
// through the owner session (`GET /artifacts/{id}/file?preview=true`). Composed: dark canvas,
// the kit's header circles over it.
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart' show Scaffold;
import 'package:flutter/services.dart' show SystemUiOverlayStyle;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:photo_view/photo_view.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../market/market_kit.dart';
import '../settings/settings_common.dart' show LoadFailure;
import 'file_name_title.dart';
import 'file_ops.dart';
import 'files_data.dart';

class ImageViewerScreen extends StatefulWidget {
  const ImageViewerScreen({super.key, required this.artifactId});
  final String artifactId;

  @override
  State<ImageViewerScreen> createState() => _ImageViewerScreenState();
}

class _ImageViewerScreenState extends State<ImageViewerScreen> {
  ArtifactRecord? _record;
  Uint8List? _bytes;
  Object? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final record = await fetchArtifact(widget.artifactId);
      if (!mounted) return;
      setState(() => _record = record);
      if (record.kind != FileKind.image) return;
      final bytes = await fetchArtifactBytes(record, preview: true);
      if (mounted) setState(() => _bytes = bytes);
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureWpfStrings(context);
    final ln = context.ln;
    final r = _record;
    final bytes = _bytes;
    // The canvas stays dark in both themes, as photo viewers do (the dark palette's page).
    final canvas = LnPalette.dark.bg;
    final Widget body;
    if (_error != null && bytes == null) {
      body = LnTheme(
        data: LnThemeData(colors: LnPalette.dark, text: ln.text),
        child: Center(
          child: LoadFailure(error: _error!, onRetry: _load),
        ),
      );
    } else if (r != null && r.kind != FileKind.image) {
      body = LnTheme(
        data: LnThemeData(colors: LnPalette.dark, text: ln.text),
        child: Center(
          child: EmptyState(icon: FIcons.imageOff, title: context.t('noImage')),
        ),
      );
    } else if (bytes == null) {
      body = Center(child: LnSpinner(size: 28, color: LnPalette.dark.fg));
    } else {
      body = PhotoView(
        imageProvider: MemoryImage(bytes),
        backgroundDecoration: BoxDecoration(color: canvas),
        minScale: PhotoViewComputedScale.contained,
        maxScale: PhotoViewComputedScale.contained * 4,
        initialScale: PhotoViewComputedScale.contained,
        semanticLabel: r?.name,
        filterQuality: FilterQuality.medium,
        loadingBuilder: (_, _) =>
            Center(child: LnSpinner(size: 28, color: LnPalette.dark.fg)),
        errorBuilder: (_, _, _) => Center(
          child: Icon(FIcons.imageOff, size: 40, color: ln.colors.fgSubtle),
        ),
      );
    }
    // Light status bar icons over the dark canvas, in both themes.
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: Scaffold(
        backgroundColor: canvas,
        body: Stack(
          children: [
            Positioned.fill(child: body),
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: LnTheme(
                data: LnThemeData(colors: LnPalette.dark, text: ln.text),
                child: ScreenHeader(
                  leading: CircleIconButton(
                    icon: const Icon(FIcons.chevronLeft),
                    semanticLabel: context.t('back'),
                    onTap: () => leaveTo(
                      context,
                      r == null ? Routes.artifacts() : Routes.artifact(r.id),
                    ),
                  ),
                  center: r == null
                      ? null
                      : SizedBox(
                          height: LnSize.headerCircle,
                          child: Center(
                            // One circle at the start, two at the end once the image is in,
                            // each in a 48 dp button box: the same 16 dp from them at both ends.
                            child: FileNameTitle(
                              name: r.name,
                              start: LnSize.minTouch + LnSpace.md,
                              end: bytes == null
                                  ? 0
                                  : 2 * LnSize.minTouch + LnSpace.md,
                              style: ln.text.title.copyWith(
                                color: LnPalette.dark.fg,
                              ),
                            ),
                          ),
                        ),
                  trailing: r == null || bytes == null
                      ? null
                      : Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            CircleIconButton(
                              icon: const Icon(FIcons.download),
                              semanticLabel: context.t('fl_saveImage'),
                              onTap: () => saveArtifact(context, r),
                            ),
                            CircleIconButton(
                              icon: const Icon(FIcons.share2),
                              semanticLabel: context.t('share'),
                              onTap: () => shareArtifact(context, r),
                            ),
                          ],
                        ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
