$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not $env:BACKEND_HOST) { $env:BACKEND_HOST = "127.0.0.1" }
if (-not $env:BACKEND_PORT) { $env:BACKEND_PORT = "8000" }
python -m app.main
