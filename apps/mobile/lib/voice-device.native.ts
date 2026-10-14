import { PermissionsAndroid, Platform } from "react-native";
import InCallManager from "react-native-incall-manager";
import { mediaDevices, RTCPeerConnection } from "react-native-webrtc";
import { ApiError } from "./api-error";
import type { VoiceDevice, VoiceMedia, VoicePeer } from "./voice-types";

export function createVoiceDevice(): VoiceDevice {
  const peer = new RTCPeerConnection({});
  return {
    peer: peer as unknown as VoicePeer,
    async microphone() {
      if (Platform.OS === "android") {
        const result = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
        );
        if (result !== PermissionsAndroid.RESULTS.GRANTED)
          throw new ApiError("voice_permission_denied", 403);
      }
      return mediaDevices.getUserMedia({
        audio: true,
        video: false,
      }) as unknown as Promise<VoiceMedia>;
    },
    startAudio() {
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
      InCallManager.setMicrophoneMute(false);
      InCallManager.stop();
    },
  };
}
