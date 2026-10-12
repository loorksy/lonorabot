$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 is required" }
& .venv/Scripts/python.exe -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
$setup = @'
import os,secrets
from pathlib import Path
from dotenv import dotenv_values
from cryptography.fernet import Fernet
p=Path('.env')
if not p.exists(): p.write_text(Path('.env.example').read_text())
values=dotenv_values(p);text=p.read_text()
for key,value in {'LONORA_ENCRYPTION_KEY':Fernet.generate_key().decode(),'LONORA_BOOTSTRAP_TOKEN':secrets.token_urlsafe(32),}.items():
    if not values.get(key): text='\n'.join(line for line in text.splitlines() if not line.startswith(key+'='))+'\n'+key+'='+value+'\n'
p.write_text(text)
'@
$setup | & .venv/Scripts/python.exe -
pnpm install --frozen-lockfile
if ($LASTEXITCODE -ne 0) { throw "Web dependencies failed" }
pnpm build
if ($LASTEXITCODE -ne 0) { throw "Web build failed" }
Write-Host "Start Docker Compose services, migrate with .venv/Scripts/alembic.exe -c packages/db/alembic.ini upgrade head, then run lonora-api and lonora-gateway in separate terminals."
