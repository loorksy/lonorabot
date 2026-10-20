import type { SuperBotRequest } from "@lonora/contracts";

/** Delayed list reads must not overwrite a newer durable control result. */
export function mergeSuperBotRequest(
  current: SuperBotRequest,
  incoming: SuperBotRequest,
): SuperBotRequest {
  const oldTime = Date.parse(current.updated_at ?? "");
  const newTime = Date.parse(incoming.updated_at ?? "");
  if (Number.isFinite(oldTime) && Number.isFinite(newTime) && newTime < oldTime) return current;
  return { ...current, ...incoming };
}
