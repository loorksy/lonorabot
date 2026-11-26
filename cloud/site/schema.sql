-- Lonora Cloud website: portal accounts waiting for staff approval (D46).
-- Applied with: wrangler d1 execute lonora_site --remote --file=schema.sql
CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  country TEXT NOT NULL,
  lang TEXT NOT NULL CHECK (lang IN ('ar', 'en')),
  broker TEXT,
  uses TEXT NOT NULL DEFAULT '[]',
  password_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'active', 'rejected', 'suspended')),
  instance_url TEXT,
  setup_link TEXT,
  reason TEXT,
  terms_version TEXT NOT NULL,
  risk_version TEXT NOT NULL,
  privacy_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  decided_at TEXT,
  decided_by TEXT
);
CREATE INDEX IF NOT EXISTS accounts_status_created ON accounts (status, created_at);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_account ON sessions (account_id);
CREATE TABLE IF NOT EXISTS audit (
  id TEXT PRIMARY KEY,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  account_id TEXT,
  details TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS audit_account ON audit (account_id, at);
CREATE TABLE IF NOT EXISTS rate (
  bucket TEXT PRIMARY KEY,
  count INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
