import 'dart:io';

import 'package:flutter/painting.dart' show PaintingBinding;
import 'package:path_provider/path_provider.dart';

import '../../app/services.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../files/files_data.dart' show FileBytes;

/// «Clear cache», after a confirmation.
///
/// Removes what this phone keeps only to show things faster: every cached snapshot of the
/// signed-in owner (shell and conversations, listed or not), decoded images, and the app's
/// re-downloadable file copies older than ten minutes (newer ones may still be open). The
/// outbox stays (messages the owner has not sent yet; drafts live in memory). The server stays
/// the system of record, so everything reloads from it.
class ClearLocalCacheAction extends AppAction {
  /// Cache folders in the temporary directory whose files are copies of server data: the files
  /// package's hand-off copies (lib/features/files/files_data.dart `cacheArtifact`) and voice
  /// notes written to be played (lib/features/rich/artifact_image.dart `voiceFile`). Anything
  /// else there (a picked file being uploaded, a recording) is left alone.
  static const cacheFolders = ['lonora-artifacts', 'lonora_voice'];

  @override
  Future<AppState?> reduce() async {
    final scope = cacheScope;
    if (scope != null) {
      // The scope holds the shell snapshot, one snapshot per conversation and the outbox: it
      // is emptied and the outbox written back from memory, where it is current.
      await localStore.clearScope(scope);
      final outbox = state.outbox;
      if (outbox.isNotEmpty) {
        await localStore.write(scope, 'outbox', [
          for (final o in outbox) o.toJson(),
        ]);
      }
    }
    await _clearTemporaryFiles();
    FileBytes.clearMemory();
    final images = PaintingBinding.instance.imageCache;
    images
      ..clear()
      ..clearLiveImages();
    return null;
  }

  /// Only on Android, where the temporary directory is the app's private cache directory
  /// (elsewhere, such as a test host, it can be a shared system folder).
  static Future<void> _clearTemporaryFiles() async {
    if (!Platform.isAndroid) return;
    try {
      final temp = await getTemporaryDirectory();
      final cutoff = DateTime.now().subtract(const Duration(minutes: 10));
      for (final name in cacheFolders) {
        final dir = Directory('${temp.path}/$name');
        if (!await dir.exists()) continue;
        await for (final entity in dir.list(followLinks: false)) {
          try {
            final stat = await entity.stat();
            if (stat.modified.isBefore(cutoff)) {
              await entity.delete(recursive: true);
            }
          } on FileSystemException {
            // In use or already gone: left for the next time.
          }
        }
      }
    } catch (_) {
      // No temporary directory: nothing to clear.
    }
  }
}
