import { NativeModules, PermissionsAndroid, Platform } from "react-native";
import { ApiError } from "./api-error";
import type { VoiceDevice, VoiceMedia, VoicePeer } from "./voice-types";

export async function createVoiceDevice(): Promise<VoiceDevice> {
  // Check the installed binary before importing libraries that initialize native emitters.
  if (!NativeModules.WebRTCModule || !NativeModules.InCallManager)
    throw new ApiError("voice_native_unavailable", 409);
  if (Platform.OS === "android") {
    const result = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.RECORD_AUDIO);
    if (result !== PermissionsAndroid.RESULTS.GRANTED)
      throw new ApiError("voice_permission_denied", 403);
  }
  const [{ mediaDevices, RTCPeerConnection }, { default: InCallManager }] = await Promise.all([
    import("react-native-webrtc"),
    import("react-native-incall-manager"),
  ]);
  if (typeof RTCPeerConnection !== "function" || typeof mediaDevices.getUserMedia !== "function")
    throw new ApiError("voice_native_unavailable", 409);
  let audioStarted = false;
  const peer = new RTCPeerConnection({});
  return {
    peer: peer as unknown as VoicePeer,
    async microphone() {
      return mediaDevices.getUserMedia({
        audio: true,
        video: false,
      }) as unknown as Promise<VoiceMedia>;
    },
    startAudio() {
      audioStarted = true;
      InCallManager.start({ media: "audio", auto: true });
      InCallManager.setForceSpeakerphoneOn(true);
    },
    muteAudio(muted) {
      InCallManager.setMicrophoneMute(muted);
    },
    stopAudio() {
      // Silence received audio immediately while the server finalizes the session.
      for (const receiver of peer.getReceivers()) {
        if (receiver.track) receiver.track.enabled = false;
      }
      if (audioStarted) {
        audioStarted = false;
        InCallManager.setMicrophoneMute(false);
        InCallManager.stop();
      }
    },
  };
}
