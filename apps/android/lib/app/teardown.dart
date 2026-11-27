import '../features/conversation/conversation_composer.dart';
import '../features/rich/artifact_image.dart';
import '../features/voice/voice_api.dart';
import '../state/actions/session_actions.dart';

/// Owner-scoped memory that must not survive a sign-out or a server change: unsent drafts and
/// the artifact bytes (with the voice notes' audio files). Platform teardown (notifications, voice,
/// background sync) registers its own hooks. A voice call closes on the server while the
/// session is still valid, alongside `POST /auth/logout`.
void registerSignOutHooks() {
  beforeSignOutHooks.add(_endVoiceCall);
  signOutHooks.add(_clearOwnerMemory);
}

Future<void> _endVoiceCall() => VoiceCalls.end();

Future<void> _clearOwnerMemory() async {
  ConversationComposerState.clearDrafts();
  ArtifactBytesCache.clear();
}
