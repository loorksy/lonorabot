import { api } from "./api";
export const onboardingStatus = () => api.get<{ owner_initialized: boolean }>("/onboarding");
export const initializeOwner = (email: string, password: string, bootstrap_token: string) =>
  api.post<{ owner_initialized: boolean }>("/onboarding", { email, password, bootstrap_token });
