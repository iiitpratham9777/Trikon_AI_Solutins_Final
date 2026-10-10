$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
