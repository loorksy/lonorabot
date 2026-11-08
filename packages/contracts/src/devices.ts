/** A passkey challenge and its signed answer; a proof is never a grant by itself. */
export type DeviceChallenge = { challenge_id: string; publicKey: Record<string, unknown> };
export type DeviceProof = { challenge_id: string; credential: Record<string, unknown> };
