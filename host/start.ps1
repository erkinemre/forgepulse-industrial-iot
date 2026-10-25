$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Set-Location $root
& (Join-Path $PSScriptRoot 'setup.ps1')
Write-Host 'ForgePulse API: http://127.0.0.1:8000'
& '.venv\Scripts\python.exe' host\run_api.py
