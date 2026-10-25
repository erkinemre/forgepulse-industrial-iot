$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root 'web')
if (-not (Test-Path -LiteralPath 'node_modules')) {
  npm ci
  if ($LASTEXITCODE -ne 0) { throw 'Node bağımlılıkları kurulamadı.' }
}
npm run build
if ($LASTEXITCODE -ne 0) { throw 'React derlemesi başarısız.' }
Set-Location (Join-Path $root 'web/dist')
$python = Join-Path $root '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Önce ForgePulse: Kurulum görevini çalıştırın.' }
Write-Host 'ForgePulse React: http://127.0.0.1:5173'
& $python -m http.server 5173 --bind 127.0.0.1
