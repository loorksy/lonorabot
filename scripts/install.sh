#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python_bin="${LONORA_PYTHON:-python3.12}"
command -v "$python_bin" >/dev/null || { echo 'Python 3.12 is required.' >&2; exit 1; }
"$python_bin" -c 'import sys; assert sys.version_info >= (3,12)'
if [[ ! -x .venv/bin/python ]]; then "$python_bin" -m venv .venv; fi
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python - <<'PY'
import os,secrets
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import dotenv_values
path=Path('.env')
if not path.exists(): path.write_text(Path('.env.example').read_text())
values=dotenv_values(path)
generated={'LONORA_ENCRYPTION_KEY':lambda:Fernet.generate_key().decode(),'LONORA_BOOTSTRAP_TOKEN':lambda:secrets.token_urlsafe(32),'LONORA_LIVEKIT_API_KEY':lambda:'lonora'+secrets.token_hex(8),'LONORA_LIVEKIT_API_SECRET':lambda:secrets.token_urlsafe(36),'LONORA_COOKIE_SECURE':lambda:'false','LONORA_ALLOWED_ORIGIN':lambda:'http://localhost:8000','LONORA_LIVEKIT_URL':lambda:'ws://localhost:7880','LONORA_LIVEKIT_INTERNAL_URL':lambda:'ws://localhost:7880'}
text=path.read_text()
for name,make in generated.items():
    if values.get(name): continue
    value=make()
    lines=text.splitlines()
    text='\n'.join(line for line in lines if not line.startswith(name+'='))+'\n'+name+'='+value+'\n'
path.write_text(text)
os.chmod(path,0o600)
print('Local configuration is ready. Keys were preserved or generated privately in .env.')
PY
command -v pnpm >/dev/null || { echo 'Install pnpm 11.25.0 using Corepack before continuing.' >&2; exit 1; }
pnpm install --frozen-lockfile
pnpm build
echo 'Run bash scripts/dev.sh to start PostgreSQL, LiveKit, API and the resident Gateway.'
