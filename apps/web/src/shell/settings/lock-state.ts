import { readDevicePref, writeDevicePref } from "./device-prefs";

/* «قفل التطبيق» (owner decision Q51): a 4-digit code and, where the device has one, unlock through
   a WebAuthn platform credential (fingerprint or face) that requires user verification. The lock
   is device-local, like the reference: the code is kept as a salted SHA-256 digest, never as
   digits; the credential id is all that is kept of the biometric key. It guards this browser's
   view of Lonora; it is not a sign-in and grants nothing. */
export type LockPrefs = {
  on: boolean;
  salt: string;
  digest: string;
  /** The WebAuthn credential id (base64url) when «الفتح بالبصمة أو الوجه» is on. */
  credential: string | null;
  /** Seconds away from the app before it locks again: 0 · 60 · 900. */
  after: 0 | 60 | 900;
};
export const LOCK_DEFAULTS: LockPrefs = {
  on: false,
  salt: "",
  digest: "",
  credential: null,
  after: 60,
};
export const readLock = () => readDevicePref<LockPrefs>("lock", LOCK_DEFAULTS);
export const writeLock = (patch: Partial<LockPrefs>) =>
  writeDevicePref<LockPrefs>("lock", { ...readLock(), ...patch });

const b64url = (bytes: ArrayBuffer | Uint8Array) =>
  btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
const fromB64url = (text: string) => {
  const plain = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(plain, (char) => char.charCodeAt(0));
};
const random = (size: number) => crypto.getRandomValues(new Uint8Array(size));

export async function pinDigest(pin: string, salt: string) {
  const data = new TextEncoder().encode(`${salt}:${pin}`);
  return b64url(await crypto.subtle.digest("SHA-256", data));
}
export async function setPin(pin: string) {
  const salt = b64url(random(16));
  writeLock({ on: true, salt, digest: await pinDigest(pin, salt) });
}
export async function checkPin(pin: string) {
  const lock = readLock();
  return Boolean(lock.digest) && (await pinDigest(pin, lock.salt)) === lock.digest;
}

/** Whether the device has a user-verifying platform authenticator (else the row is hidden). */
export async function biometricAvailable() {
  try {
    return (
      typeof PublicKeyCredential !== "undefined" &&
      window.isSecureContext &&
      (await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable())
    );
  } catch {
    return false;
  }
}

/** Registers a platform credential that needs fingerprint or face; returns its id. */
export async function enrollBiometric(label: string): Promise<string> {
  const credential = (await navigator.credentials.create({
    publicKey: {
      rp: { name: "Lonora" },
      user: { id: random(16), name: label, displayName: label },
      challenge: random(32),
      pubKeyCredParams: [
        { type: "public-key", alg: -7 },
        { type: "public-key", alg: -257 },
      ],
      authenticatorSelection: {
        authenticatorAttachment: "platform",
        userVerification: "required",
        residentKey: "discouraged",
      },
      timeout: 60_000,
      attestation: "none",
    },
  })) as PublicKeyCredential | null;
  if (!credential) throw new Error("biometric_cancelled");
  return b64url(credential.rawId);
}

/** Asks the platform authenticator to verify the person; true only with the UV flag set. */
export async function verifyBiometric(id: string): Promise<boolean> {
  const assertion = (await navigator.credentials.get({
    publicKey: {
      challenge: random(32),
      allowCredentials: [{ type: "public-key", id: fromB64url(id), transports: ["internal"] }],
      userVerification: "required",
      timeout: 60_000,
    },
  })) as PublicKeyCredential | null;
  const response = assertion?.response as AuthenticatorAssertionResponse | undefined;
  if (!response || assertion?.id !== id) return false;
  // authenticatorData: rpIdHash (32 bytes) then the flags byte; bit 2 is «user verified».
  const flags = new Uint8Array(response.authenticatorData)[32] ?? 0;
  return (flags & 0x04) !== 0;
}
