import { api, type Model, type Provider } from "./api";
export const providers: Provider[] = ["openai", "anthropic", "deepseek", "zai", "openrouter"];
export const readModels = (provider: Provider) => api.get<Model[]>(`/providers/${provider}/models`);
export const discoverModels = (provider: Provider) =>
  api.post<Model[]>(`/providers/${provider}/discover`, {});
