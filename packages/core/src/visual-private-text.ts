/** Display-value privacy boundary, matching the Python credential/location guard.
 * Do not classify ordinary tool names or diagnostic vocabulary as secrets.
 * UUID admission stays server-owned because only it knows authorized public IDs.
 */
const privateText = new RegExp(
  [
    "-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\\s\\S]*?(?:-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|$)",
    "\\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\\b",
    "\\beyJ[A-Za-z0-9_-]+\\.eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\b",
    "\\bBearer\\s+[A-Za-z0-9._~+/=-]{1,}",
    "\\b(?:password|passwd|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|auth[_ -]?token|token|secret|authorization)\\s*[:=]\\s*[\"']?[^\\s,;\"'<>]{1,}",
    "كلمة\\s+(?:السر|المرور)\\s*[:=]\\s*[\"']?[^\\s,;\"'<>]{1,}",
    "(?:sandbox:|file://)[^\\s<>\"'\\])]*",
    "(?:^|[^\\w:/])/(?:mnt/data|opt/lonora|workspace|tmp|app/packages|app/apps)(?![\\w.-])(?:/[^\\s<>\"'\\])]*)?",
    "</?(?:lonora_[a-z_]+|skill_runtime)[^>]*>",
  ].join("|"),
  "iu",
);

export function unsafeVisualText(value: string): boolean {
  if (value.includes("{{")) return true;
  const normalized = value.normalize("NFKC").replace(/[\p{Cf}\p{Mn}]/gu, "");
  return normalized.includes("{{") || privateText.test(normalized);
}
