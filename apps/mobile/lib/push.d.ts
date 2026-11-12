/** Registers this phone for push (VISION 11.4); a no-op where push does not exist. */
export function syncPushDevice(): Promise<void>;
/** Calls `listener` when the system rotates this phone's push token. */
export function onPushTokenChange(listener: () => void): () => void;
