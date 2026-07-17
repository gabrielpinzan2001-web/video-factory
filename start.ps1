# Video Factory - inicia backend (FastAPI) + frontend (Vite)
# Uso: clique com o botao direito -> "Executar com PowerShell", ou rode:
#   powershell -ExecutionPolicy Bypass -File start.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "Iniciando Video Factory..." -ForegroundColor Cyan

# Backend
$backend = Start-Process -PassThru -WindowStyle Minimized `
  -FilePath "$root\.venv\Scripts\python.exe" `
  -ArgumentList @("-m", "uvicorn", "app:app", "--app-dir", "$root\backend",
                  "--host", "127.0.0.1", "--port", "8756")
Write-Host "Backend rodando (porta 8756)" -ForegroundColor Green

# Frontend
$frontend = Start-Process -PassThru -WindowStyle Minimized `
  -FilePath "cmd.exe" -WorkingDirectory "$root\frontend" `
  -ArgumentList @("/c", "npm", "run", "dev")
Write-Host "Frontend rodando (porta 5173)" -ForegroundColor Green

Start-Sleep -Seconds 4
Write-Host "`nAbrindo no navegador: http://localhost:5173" -ForegroundColor Cyan
Start-Process "http://localhost:5173"

Write-Host "`nPara PARAR, feche as duas janelas minimizadas (python e node),"
Write-Host "ou rode: Get-Process python,node | Stop-Process"
