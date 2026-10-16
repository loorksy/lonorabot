import type { DeviceChallenge, DeviceProof } from "@lonora/contracts";
import { ApiError } from "./api-error";

export async function deviceSupported(): Promise<boolean> {
  try {
    return (await import("react-native-passkeys")).isSupported();
  } catch {
    return false;
  }
}
export async function deviceProof(
  challenge: DeviceChallenge,
  enroll = false,
): Promise<DeviceProof> {
  let sdk: typeof import("react-native-passkeys");
  try {
    sdk = await import("react-native-passkeys");
  } catch {
    throw new ApiError("device_not_supported", 0);
  }
  if (!sdk.isSupported()) throw new ApiError("device_not_supported", 0);
  try {
    const credential = enroll
      ? await sdk.create(challenge.publicKey as unknown as Parameters<typeof sdk.create>[0])
      : await sdk.get(challenge.publicKey as unknown as Parameters<typeof sdk.get>[0]);
    if (!credential) throw new ApiError("device_authorization_cancelled", 0);
    return {
      challenge_id: challenge.challenge_id,
      credential: JSON.parse(JSON.stringify(credential)) as Record<string, unknown>,
    };
  } catch (cause) {
    if (cause instanceof ApiError) throw cause;
    throw new ApiError("device_proof_invalid", 0);
  }
}
