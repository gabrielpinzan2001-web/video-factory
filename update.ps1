# Video Factory - atualiza o codigo com as ultimas melhorias do GitHub
# Uso: clique com o botao direito -> "Executar com PowerShell"
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Baixando as ultimas atualizacoes do GitHub..." -ForegroundColor Cyan
git pull origin main

Write-Host "`nAtualizando dependencias do frontend (se necessario)..." -ForegroundColor Cyan
Set-Location "$PSScriptRoot\frontend"
npm install --no-audit --no-fund

Set-Location $PSScriptRoot
Write-Host "`nPronto! Codigo atualizado. Rode o start.ps1 para usar a ferramenta." -ForegroundColor Green
