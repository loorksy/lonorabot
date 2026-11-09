/**
 * Supervision grants (lonora_db.supervision): one agent reads and steers another's
 * work. A grant never carries money authority; the owner revokes any grant in one tap.
 */
export type SupervisionVia = "default" | "owner_ui" | "owner_message" | "owner_card";
export type SupervisionGrant = {
  id: string;
  supervisor: { id: string; name: string | null };
  supervised: { id: string; name: string | null };
  created_via: SupervisionVia;
  created_at: string;
  revoked_at: string | null;
  revoked_via: "owner_ui" | "owner_card" | "owner_message" | null;
};
/** GET /supervision?agent_id=: the active grants around one agent. */
export type SupervisionView = {
  agent_id: string;
  supervises: SupervisionGrant[];
  supervised_by: SupervisionGrant[];
};
