import {
  type AccountSummary,
  api,
  type Journal,
  type Payload,
  type Resource,
  type Trade,
} from "./api";
export const readConnections = () => api.get<Resource[]>("/trading/connections");
export const connectBroker = (payload: Payload) =>
  api.post<Resource>("/trading/connections", payload);
export const readAccount = (id: string) => api.get<AccountSummary>(`/trading/accounts/${id}`);
/** Lifting the owner's own pause: one tap, owner session only (no agent can lift one). */
export const liftRestriction = (restrictionId: string) =>
  api.post<Payload>(`/trading/restrictions/${encodeURIComponent(restrictionId)}/revoke`, {
    reason: "",
  });
export const executeTrade = (trade: Trade) => api.post<Payload>("/trading/execute", trade);
export const readJournal = () => api.get<Journal[]>("/trading/journal");
