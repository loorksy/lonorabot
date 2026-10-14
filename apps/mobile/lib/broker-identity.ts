import type { Resource } from "@lonora/contracts";
import type { Label } from "./i18n";

/** A provisioning UUID identifies a connection, never its broker login. */
export function brokerIdentityLabel(
  connection: Resource,
  index: number,
  t: (key: Label) => string,
): string {
  const identity = connection.state?.broker_identity;
  if (identity && typeof identity === "object" && !Array.isArray(identity)) {
    const values = identity as Record<string, unknown>;
    if (values.connection_version === connection.version) {
      const parts = [values.broker, values.login, values.server].filter(
        (value): value is string =>
          typeof value === "string" &&
          value.trim().length > 0 &&
          value !== connection.id &&
          value !== connection.payload.account_id &&
          !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value),
      );
      if (parts.length) return parts.join(" · ");
    }
  }
  return `${t(connection.payload.provider === "simulation" ? "simulation" : "unverifiedBrokerAccount")} · ${index + 1}`;
}
