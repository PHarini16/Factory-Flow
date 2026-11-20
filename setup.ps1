# FactoryFlow one-time setup for Windows PowerShell.  Run from the repository root:
#     powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
Write-Host "== Backend ==" -ForegroundColor Cyan
Set-Location "$PSScriptRoot\backend"
if (-not (Test-Path .venv)) { py -3.12 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created backend\.env (edit SECRET_KEY)" }
& .\.venv\Scripts\python.exe -m app.scripts.seed
Write-Host "== Frontend ==" -ForegroundColor Cyan
Set-Location "$PSScriptRoot\frontend"
npm install
Write-Host ""
Write-Host "Setup complete. Start the app in TWO terminals:" -ForegroundColor Green
Write-Host "  1) cd backend ; .\.venv\Scripts\activate ; uvicorn app.main:app --reload"
Write-Host "  2) cd frontend ; npm run dev"
Write-Host "Then open http://localhost:5173"
