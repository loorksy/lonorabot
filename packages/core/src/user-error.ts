export function errorCode(error: unknown, fallback = "request_failed"): string {
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && "code" in error) return String(error.code);
  return fallback;
}
