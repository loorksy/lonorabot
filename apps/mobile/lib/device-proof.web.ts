import type { DeviceChallenge } from "@lonora/contracts";
import { webDeviceProof, webDeviceSupported } from "@lonora/core";
import { ApiError } from "./api-error";
export const deviceSupported = webDeviceSupported;
export async function deviceProof(challenge: DeviceChallenge, enroll = false) {
  try {
    return await webDeviceProof(challenge, enroll);
  } catch (cause) {
    if (cause && typeof cause === "object" && "code" in cause && typeof cause.code === "string")
      throw new ApiError(cause.code, 0);
    throw cause;
  }
}
