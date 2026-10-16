import type { DeviceChallenge, DeviceProof } from "@lonora/contracts";

function bytes(value: string): ArrayBuffer {
  return Uint8Array.from(atob(value.replace(/-/g, "+").replace(/_/g, "/")), (char) =>
    char.charCodeAt(0),
  ).buffer;
}
function encoded(value: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(value)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}
export function webDeviceSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    window.isSecureContext &&
    typeof PublicKeyCredential !== "undefined" &&
    Boolean(navigator.credentials)
  );
}
export async function webDeviceProof(
  challenge: DeviceChallenge,
  enroll = false,
): Promise<DeviceProof> {
  if (!webDeviceSupported())
    throw Object.assign(new Error("device_not_supported"), { code: "device_not_supported" });
  const options = challenge.publicKey;
  const descriptors = (key: string) =>
    ((options[key] ?? []) as { id: string; type: "public-key" }[]).map((item) => ({
      ...item,
      id: bytes(item.id),
    }));
  try {
    const credential = enroll
      ? await navigator.credentials.create({
          publicKey: {
            ...(options as unknown as PublicKeyCredentialCreationOptions),
            challenge: bytes(String(options.challenge)),
            user: {
              ...(options.user as PublicKeyCredentialUserEntity),
              id: bytes(String((options.user as { id: string }).id)),
            },
            excludeCredentials: descriptors("excludeCredentials"),
          },
        })
      : await navigator.credentials.get({
          publicKey: {
            ...(options as unknown as PublicKeyCredentialRequestOptions),
            challenge: bytes(String(options.challenge)),
            allowCredentials: descriptors("allowCredentials"),
          },
        });
    if (!(credential instanceof PublicKeyCredential)) throw new Error("device_proof_invalid");
    const response = credential.response;
    const data: Record<string, unknown> = { clientDataJSON: encoded(response.clientDataJSON) };
    if (response instanceof AuthenticatorAttestationResponse) {
      data.attestationObject = encoded(response.attestationObject);
      data.transports = response.getTransports();
    } else if (response instanceof AuthenticatorAssertionResponse) {
      data.authenticatorData = encoded(response.authenticatorData);
      data.signature = encoded(response.signature);
      if (response.userHandle) data.userHandle = encoded(response.userHandle);
    }
    return {
      challenge_id: challenge.challenge_id,
      credential: {
        id: credential.id,
        rawId: encoded(credential.rawId),
        type: "public-key",
        response: data,
      },
    };
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "SecurityError")
      throw Object.assign(new Error("device_secure_origin_required"), {
        code: "device_secure_origin_required",
      });
    if (cause instanceof DOMException && ["NotAllowedError", "AbortError"].includes(cause.name))
      throw Object.assign(new Error("device_authorization_cancelled"), {
        code: "device_authorization_cancelled",
      });
    throw cause;
  }
}
