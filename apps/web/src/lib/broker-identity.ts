import { t } from "@lingui/core/macro";
import type { Resource } from "./api";

type Identity = { broker?: string; login?: string; server?: string };

/** What the broker itself reported for a connection: null before it was observed, "stale" when
 * it was observed for an earlier version of the connection. */
function observed(connection: Resource): Identity | "stale" | null {
  const identity = connection.state?.broker_identity;
  if (!identity || typeof identity !== "object" || Array.isArray(identity)) return null;
  const values = identity as Record<string, unknown>;
  if (values.connection_version !== connection.version) return "stale";
  const text = (value: unknown) =>
    typeof value === "string" && value.length > 0 ? value : undefined;
  return { broker: text(values.broker), login: text(values.login), server: text(values.server) };
}

/** The broker's own name, login and server, once verified for this version of the connection. */
export function brokerIdentity(connection: Resource): Identity | null {
  const identity = observed(connection);
  return identity === "stale" ? null : identity;
}

/** The adapter's provisioning UUID is not a broker login or account number. */
export function brokerIdentityLabel(connection: Resource, index: number): string {
  const identity = observed(connection);
  if (identity === "stale") return `${t`Unverified broker account`} · ${index + 1}`;
  const parts = identity ? [identity.broker, identity.login, identity.server].filter(Boolean) : [];
  if (parts.length) return parts.join(" · ");
  return connection.payload.provider === "simulation"
    ? `${t`Simulation`} · ${index + 1}`
    : `${t`Unverified broker account`} · ${index + 1}`;
}
