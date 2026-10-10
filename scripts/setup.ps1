# VoxPilot setup for Windows PowerShell. Run from the repository root:  .\scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Need($name, $hint) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { Write-Warning "$name not found. $hint"; return $false }
  return $true
}
[void](Need "python" "Install Python 3.10-3.12 from python.org (tick 'Add to PATH').")
[void](Need "node" "Install Node.js 20+ from nodejs.org.")
$hasOllama = Need "ollama" "Install from https://ollama.com/download"

Write-Host "== Backend =="
Set-Location "$root\backend"
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item "$root\.env.example" .env; Write-Host "Created backend\.env" }

Write-Host "== Frontend =="
Set-Location "$root\frontend"
npm install

if ($hasOllama) {
  Write-Host "== LLM =="
  ollama pull qwen2.5:3b
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Install Kokoro (TTS):  see README section 'Text-to-speech setup'"
Write-Host "  2. Download speech models: backend\.venv\Scripts\python.exe scripts\download_models.py"
Write-Host "  3. Start the backend:     .\scripts\run-backend.ps1"
Write-Host "  4. Start the frontend:    .\scripts\run-frontend.ps1   (then open http://localhost:5173)"
