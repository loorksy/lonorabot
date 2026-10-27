import { type AvatarStateId, turnActivity } from "@lonora/core";
import type { Event, Run } from "./api";

/** Avatar and transcript share one projection of the same actual observations. */
export function runActivity(run: Run, events: Event[]): AvatarStateId {
  return turnActivity(run, events).avatar;
}
