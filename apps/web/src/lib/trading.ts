import {
  type AccountSummary,
  api,
  type Journal,
  type OperationResolution,
  type Payload,
  type Resource,
  type Trade,
} from "./api";
export const readConnections = () => api.get<Resource[]>("/trading/connections");
export const connectBroker = (payload: Payload) =>
  api.post<Resource>("/trading/connections", payload);
export const readAccount = (id: string) => api.get<AccountSummary>(`/trading/accounts/${id}`);
export const executeTrade = (trade: Trade) => api.post<Payload>("/trading/execute", trade);
export const readJournal = () => api.get<Journal[]>("/trading/journal");
export const resolveOperation = (operationId: string, resolution: OperationResolution) =>
  api.post<Journal>(`/trading/journal/${encodeURIComponent(operationId)}/resolve`, resolution);
