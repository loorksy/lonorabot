import type { DeviceChallenge, DeviceProof } from "@lonora/contracts";
export function deviceSupported(): boolean | Promise<boolean>;
export function deviceProof(challenge: DeviceChallenge, enroll?: boolean): Promise<DeviceProof>;
