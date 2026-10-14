export type VoiceTrack = { enabled: boolean; stop(): void };
export type VoiceMedia = { getTracks(): VoiceTrack[]; getAudioTracks(): VoiceTrack[] };
export type VoiceChannel = {
  readyState: string;
  send(value: string): void;
  close(): void;
  addEventListener(type: string, listener: (event: { data?: string }) => void): void;
};
export type VoicePeer = {
  connectionState: string;
  iceGatheringState: string;
  localDescription: { sdp?: string } | null;
  addTrack(track: VoiceTrack, media: VoiceMedia): unknown;
  createDataChannel(label: string): VoiceChannel;
  createOffer(): Promise<{ type: string; sdp: string }>;
  setLocalDescription(value: { type: string; sdp: string }): Promise<void>;
  setRemoteDescription(value: { type: string; sdp: string }): Promise<void>;
  addEventListener(type: string, listener: () => void): void;
  removeEventListener(type: string, listener: () => void): void;
  getStats(): Promise<Map<string, Record<string, unknown>>>;
  close(): void;
};
export type VoiceDevice = {
  peer: VoicePeer;
  microphone(): Promise<VoiceMedia>;
  startAudio(): void;
  muteAudio(muted: boolean): void;
  stopAudio(): void;
};
export type VoiceActivity = { phase: "listening" | "speaking"; level: number };
