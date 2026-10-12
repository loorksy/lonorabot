import type { RunStatus } from "@lonora/contracts";

export const activeStatuses: readonly RunStatus[] = ["queued", "leased", "running"];
export function isWorking(status: RunStatus): boolean {
  return activeStatuses.includes(status);
}
export function canResume(status: RunStatus): boolean {
  return status === "waiting_input" || status === "waiting_takeover" || status === "failed";
}
export function canCancel(status: RunStatus): boolean {
  return isWorking(status) || status === "waiting_input" || status === "waiting_takeover";
}
