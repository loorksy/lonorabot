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
export const executeTrade = (trade: Trade) => api.post<Payload>("/trading/execute", trade);
export const readJournal = () => api.get<Journal[]>("/trading/journal");
