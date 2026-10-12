export type Owner = { id: string; email: string };
export type BrowserLogin = { owner: Owner; csrf: string };
export type NativeLogin = { owner: Owner; token: string; expires_in: number };
