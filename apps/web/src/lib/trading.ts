import {
  type AccountSummary,
  api,
  type Journal,
  type Payload,
  type Resource,
  type Trade,
  type TradingControls,
} from "./api";
export const readConnections = () => api.get<Resource[]>("/trading/connections");
export const connectBroker = (payload: Payload) =>
  api.post<Resource>("/trading/connections", payload);
export const readAccount = (id: string) => api.get<AccountSummary>(`/trading/accounts/${id}`);
export const readControls = () => api.get<TradingControls>("/trading/controls");
export const setControls = (controls: TradingControls) =>
  api.put<TradingControls>("/trading/controls", controls);
/** One brake: new risk stops for every agent and manual orders; exits stay allowed. */
export const stopNewTrading = () => setControls({ enabled: false, emergency_stop: true });
/** One tap, no passkey: it widens no authority; every grant and limit still applies. */
export const resumeTrading = () => setControls({ enabled: true, emergency_stop: false });
/** Lifting the owner's own pause: one tap, owner session only (no agent can lift one). */
export const liftRestriction = (restrictionId: string) =>
  api.post<Payload>(`/trading/restrictions/${encodeURIComponent(restrictionId)}/revoke`, {
    reason: "",
  });
export const tradingStopped = (controls: TradingControls) =>
  controls.emergency_stop || !controls.enabled;
export const executeTrade = (trade: Trade) => api.post<Payload>("/trading/execute", trade);
export const readJournal = () => api.get<Journal[]>("/trading/journal");
