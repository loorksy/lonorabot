import { t } from "@lingui/core/macro";
import type { Resource } from "./api";

/** The adapter's provisioning UUID is not a broker login or account number. */
export function brokerIdentityLabel(connection: Resource, index: number): string {
  const identity = connection.state.broker_identity;
  if (identity && typeof identity === "object" && !Array.isArray(identity)) {
    const values = identity as Record<string, unknown>;
    const parts = [values.broker, values.login, values.server].filter(
      (value): value is string => typeof value === "string" && value.length > 0,
    );
    if (parts.length) return parts.join(" · ");
  }
  return connection.payload.provider === "simulation"
    ? `${t`Simulation`} · ${index + 1}`
    : `${t`Unverified broker account`} · ${index + 1}`;
}
