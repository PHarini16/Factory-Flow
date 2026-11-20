# Starts backend and frontend in two new PowerShell windows (after setup.ps1 has been run).
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$PSScriptRoot\backend'; .\.venv\Scripts\activate; uvicorn app.main:app --reload"
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$PSScriptRoot\frontend'; npm run dev"
Start-Sleep 4; Start-Process "http://localhost:5173"
