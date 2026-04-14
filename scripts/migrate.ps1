# Run from repo root after DATABASE_URL is in .env or environment.
# Creates/updates tables via Alembic (production path).
#
#   .\.venv\Scripts\Activate.ps1   # optional
#   $env:DATABASE_URL = "postgresql+psycopg://..."
#   .\scripts\migrate.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m alembic upgrade head
Write-Host "Done: alembic upgrade head"
